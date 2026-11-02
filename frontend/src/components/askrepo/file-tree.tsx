import { ChevronRight, FileCode2, Folder } from "lucide-react";

type TreeNode = { path?: string; children: Record<string, TreeNode> };

export function FileTree({ paths, onFile }: { paths: string[]; onFile: (path: string) => void }) {
  const root: TreeNode = { children: {} };
  for (const path of paths) {
    let node = root;
    const parts = path.split("/");
    parts.forEach((part, index) => {
      node.children[part] ??= { children: {} };
      node = node.children[part]!;
      if (index === parts.length - 1) node.path = path;
    });
  }
  function render(node: TreeNode) {
    return Object.entries(node.children)
      .sort(
        ([a, first], [b, second]) =>
          Number(Boolean(first.path)) - Number(Boolean(second.path)) || a.localeCompare(b),
      )
      .map(([name, child]) =>
        child.path ? (
          <button className="tree-file" key={name} onClick={() => onFile(child.path!)}>
            <FileCode2 size={13} />
            <span>{name}</span>
          </button>
        ) : (
          <details className="tree-folder" key={name} open>
            <summary>
              <ChevronRight size={12} />
              <Folder size={13} />
              <span>{name}</span>
            </summary>
            <div>{render(child)}</div>
          </details>
        ),
      );
  }
  return (
    <div className="file-tree">
      {paths.length ? (
        render(root)
      ) : (
        <p className="sidebar-empty">Files appear here as they are retrieved.</p>
      )}
    </div>
  );
}
