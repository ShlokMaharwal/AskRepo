"""Pluggable AST/fixed chunking; all source ranges are inclusive, one-based lines."""

import hashlib
import re
from dataclasses import asdict, dataclass

LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".md": "markdown",
    ".mdx": "markdown",
    ".rst": "text",
}
FUNCTIONS = {
    "function_definition",
    "function_declaration",
    "method_definition",
    "method_declaration",
    "constructor_declaration",
    "arrow_function",
    "function_expression",
    "generator_function",
}
CLASSES = {
    "class_definition",
    "class_declaration",
    "class_specifier",
    "struct_specifier",
    "interface_declaration",
}


@dataclass
class Chunk:
    id: str
    repo_id: str
    path: str
    language: str
    start_line: int
    end_line: int
    symbol_name: str
    parent_symbol: str | None
    code: str
    text: str
    kind: str = "code"

    def to_dict(self):
        return asdict(self)


def language_for(path: str) -> str:
    from pathlib import PurePosixPath

    return LANGUAGES.get(PurePosixPath(path).suffix.lower(), "text")


def chunk_file(
    repo_id: str, path: str, content: str, strategy: str = "ast", max_chars: int = 6000
) -> list[Chunk]:
    if strategy not in {"ast", "fixed"}:
        raise ValueError("Chunk strategy must be ast or fixed")
    lines = content.splitlines()
    language = language_for(path)
    result: list[Chunk] = []
    seen = set()

    def emit(start: int, end: int, symbol: str = "", parent: str | None = None, kind: str = "code"):
        start, end = max(1, start), min(len(lines), end)
        if end < start:
            return
        # A single source line cannot be subdivided without losing exact-line provenance.
        if any(len(line) > max_chars for line in lines[start - 1 : end]):
            raise ValueError("A source line exceeds the configured chunk character budget")
        offset = start
        while offset <= end:
            last = offset
            used = 0
            while last <= end and used + len(lines[last - 1]) + 1 <= max_chars:
                used += len(lines[last - 1]) + 1
                last += 1
            last = max(offset, last - 1)
            key = (offset, last, kind, symbol, parent)
            code = "\n".join(lines[offset - 1 : last])
            if code.strip() and key not in seen:
                seen.add(key)
                qualified = ".".join(part for part in (parent, symbol) if part)
                text = f"{path} | {language} | {qualified}\n{code}"
                identifier = hashlib.sha256(
                    f"{repo_id}:{path}:{offset}:{last}:{kind}:{symbol}:{parent}".encode()
                ).hexdigest()
                result.append(
                    Chunk(
                        identifier,
                        repo_id,
                        path,
                        language,
                        offset,
                        last,
                        symbol,
                        parent,
                        code,
                        text,
                        kind,
                    )
                )
            if last >= end:
                break
            offset = max(offset + 1, last - min(9, (last - offset) // 3))

    def windows(start=1, end=None):
        end = end or len(lines)
        for first in range(start, end + 1, 50):
            emit(first, min(first + 59, end))

    if not lines:
        return []
    if strategy == "fixed":
        windows()
        return result
    if language == "markdown":
        boundaries = [index + 1 for index, line in enumerate(lines) if re.match(r"^#{1,6}\s", line)]
        boundaries = sorted({1, *boundaries, len(lines) + 1})
        for start, end in zip(boundaries, boundaries[1:], strict=False):
            emit(start, end - 1, lines[start - 1].lstrip("# "), kind="documentation")
        return result
    if language not in {"python", "javascript", "typescript", "tsx", "java", "c", "cpp"}:
        windows()
        return result
    from tree_sitter_language_pack import get_parser

    raw = content.encode("utf-8")
    tree = get_parser(language).parse(raw)
    covered: set[int] = set()
    symbols = []

    def node_name(node):
        name = node.child_by_field_name("name")
        if name:
            return raw[name.start_byte : name.end_byte].decode("utf-8")
        parent = node.parent
        if parent and parent.type in {"variable_declarator", "pair"}:
            name = parent.child_by_field_name("name") or parent.child_by_field_name("key")
            if name:
                return raw[name.start_byte : name.end_byte].decode("utf-8")
        declarator = node.child_by_field_name("declarator")
        while declarator:
            if declarator.type in {"identifier", "field_identifier", "qualified_identifier"}:
                return raw[declarator.start_byte : declarator.end_byte].decode("utf-8")
            declarator = declarator.child_by_field_name("declarator")
        return "anonymous"

    def visit(node, parent=None):
        start = node.start_point.row + 1
        end = node.end_point.row + (1 if node.end_point.column else 0)
        if node.type in CLASSES:
            name = node_name(node)
            body = node.child_by_field_name("body")
            header_end = (body.start_point.row + 1) if body else start
            emit(start, header_end, name, parent, "class_header")
            covered.update(range(start, header_end + 1))
            symbols.append(start)
            for child in node.named_children:
                if child != body:
                    continue
                for member in child.named_children:
                    visit(member, name)
            # Closing braces and fields remain searchable through uncovered-line chunks.
            return
        if node.type in FUNCTIONS:
            decorated = (
                node.parent if node.parent and node.parent.type == "decorated_definition" else node
            )
            start = decorated.start_point.row + 1
            emit(start, max(start, end), node_name(node), parent)
            covered.update(range(start, end + 1))
            symbols.append(start)
            for child in node.named_children:
                visit(child, node_name(node))
            return
        for child in node.named_children:
            visit(child, parent)

    visit(tree.root_node)
    first_symbol = min(symbols) if symbols else len(lines) + 1
    emit(1, min(first_symbol - 1, 60), "imports", kind="imports")
    covered.update(range(1, min(first_symbol, 61)))
    # Preserve executable module code, class fields, and syntax-error fragments too.
    start = None
    for number in range(1, len(lines) + 2):
        available = number <= len(lines) and number not in covered
        if available and start is None:
            start = number
        elif not available and start is not None:
            windows(start, number - 1)
            start = None
    return result
