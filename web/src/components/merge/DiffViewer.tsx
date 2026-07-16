"use client";
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

interface DiffFile {
  filename: string;
  status: "added" | "modified" | "deleted" | "renamed";
  added: number;
  removed: number;
  patch?: string;
  previous_content?: string;
  new_content?: string;
  comments?: { line: number; body: string }[];
}

interface Props { files: DiffFile[] }

type ViewMode = "diff" | "before" | "after";

const STATUS_COLOR: Record<string, string> = {
  added:    "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300",
  modified: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300",
  deleted:  "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300",
  renamed:  "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-300",
};

function CodeBlock({ text, emptyLabel }: { text?: string; emptyLabel: string }) {
  if (!text) {
    return <p className="px-4 py-3 text-xs text-gray-400">{emptyLabel}</p>;
  }
  return (
    <pre className="px-4 py-3 text-xs font-mono whitespace-pre-wrap break-words text-gray-700 dark:text-gray-300 overflow-x-auto">
      {text}
    </pre>
  );
}

function DiffFileRow({ file }: { file: DiffFile }) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<ViewMode>("diff");
  const Icon = open ? ChevronDown : ChevronRight;
  const hasPatch = Boolean(file.patch?.trim());
  const hasBefore = Boolean(file.previous_content?.trim());
  const hasAfter = Boolean(file.new_content?.trim());

  return (
    <div className="border dark:border-gray-700 rounded-lg overflow-hidden mb-2">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
      >
        <Icon size={14} className="text-gray-400 shrink-0" />
        <span
          className={`text-xs px-2 py-0.5 rounded font-medium ${STATUS_COLOR[file.status] ?? STATUS_COLOR.modified}`}
        >
          {file.status}
        </span>
        <code className="flex-1 text-sm font-mono text-gray-800 dark:text-gray-200 truncate">{file.filename}</code>
        <span className="text-xs text-green-600 dark:text-green-400 font-mono">+{file.added}</span>
        <span className="text-xs text-red-600 dark:text-red-400 font-mono">−{file.removed}</span>
      </button>

      {open && (
        <div className="border-t dark:border-gray-700">
          <div className="flex gap-1 p-2 bg-gray-50 dark:bg-gray-900/60 border-b dark:border-gray-700">
            {(["diff", "before", "after"] as const).map(mode => (
              <button
                key={mode}
                type="button"
                onClick={() => setView(mode)}
                className={`px-2.5 py-1 rounded text-xs font-medium capitalize ${
                  view === mode
                    ? "bg-white dark:bg-gray-700 shadow-sm"
                    : "text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                }`}
              >
                {mode === "before" ? "Previous" : mode === "after" ? "Current" : "Diff"}
              </button>
            ))}
          </div>

          {view === "diff" && (
            hasPatch ? (
              <div className="overflow-x-auto">
                {file.patch!.split("\n").map((line, i) => {
                  const comment = file.comments?.find(c => c.line === i);
                  const cls = line.startsWith("+")
                    ? "bg-green-50 dark:bg-green-950 text-green-800 dark:text-green-300"
                    : line.startsWith("-")
                    ? "bg-red-50 dark:bg-red-950 text-red-800 dark:text-red-300"
                    : "text-gray-500 dark:text-gray-400";
                  return (
                    <div key={`line-${i}`}>
                      <div className={`px-4 py-0.5 text-xs font-mono whitespace-pre ${cls}`}>
                        {line || " "}
                      </div>
                      {comment && (
                        <div className="px-4 py-2 bg-amber-50 dark:bg-amber-950 border-l-4 border-amber-400 text-xs text-amber-800 dark:text-amber-200">
                          💬 {comment.body}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="px-4 py-3 text-xs text-gray-400">
                No line diff available for this file (folder, binary, or unchanged content).
              </p>
            )
          )}

          {view === "before" && (
            <CodeBlock text={file.previous_content} emptyLabel="No previous version (new file)." />
          )}

          {view === "after" && (
            <CodeBlock text={file.new_content} emptyLabel="No current version (deleted file)." />
          )}

          {view === "diff" && !hasPatch && (hasBefore || hasAfter) && (
            <p className="px-4 pb-3 text-xs text-gray-500">
              Tip: open <strong>Previous</strong> or <strong>Current</strong> to compare full file content.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function DiffViewer({ files }: Props) {
  if (!files.length) return (
    <p className="text-sm text-gray-400">No diff data available.</p>
  );
  return (
    <div>
      {files.map((f, i) => <DiffFileRow key={`${f.filename}-${i}`} file={f} />)}
    </div>
  );
}
