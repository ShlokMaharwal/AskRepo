"""Bounded, stateless conversation context and cheap rewrite decisions."""

import re

MAX_HISTORY_MESSAGES = 6
MAX_HISTORY_CHARS = 6000
FOLLOWUP = re.compile(
    r"\b(it|its|that|this|those|these|they|them|their|there)\b|\band\s+where\b|\bwhat\s+about\b",
    re.I,
)


def truncate_content(content, limit):
    if len(content) <= limit:
        return content
    tail = min(300, limit // 4)
    return content[: limit - tail - 5] + "\n...\n" + content[-tail:]


def bounded_history(messages):
    output, remaining = [], MAX_HISTORY_CHARS
    for message in reversed(messages[-MAX_HISTORY_MESSAGES:]):
        content = truncate_content(
            message.content.strip(), min(remaining, 1200 if message.role == "assistant" else 500)
        )
        if content:
            output.append(message.model_copy(update={"content": content}))
            remaining -= len(content)
        if remaining < 20:
            break
    return list(reversed(output))


def should_rewrite(question, history):
    return bool(history and FOLLOWUP.search(question))


def normalize_rewrite(value, original):
    value = " ".join(str(value or "").strip().strip('"').split())
    return value if 0 < len(value) <= 500 else original


def contextual_rewrite(question, history):
    """No-key fallback: carry actual prior identifiers, without inventing an LLM call."""
    identifiers = []
    previous = ""
    for message in history:
        if message.role == "user":
            previous = message.content
        else:
            identifiers.extend(
                re.findall(r"`([^`\n]{1,120})`|\[([^\]\n]+):\d+-\d+\]", message.content)
            )
    names = list(dict.fromkeys(part for pair in identifiers for part in pair if part))[-6:]
    context = ", ".join(names) if names else previous
    return normalize_rewrite(f"{question} Context: {context}"[:500], question)
