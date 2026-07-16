"use client";
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { SeverityBadge } from "./SeverityBadge";
import { getSeverityStyle } from "@/lib/design";

export interface Issue {
  severity: string;
  title: string;
  file?: string;
  line?: number;
  category?: string;
  detail?: string;
  description?: string;
  fix?: string;
  suggestion?: string;
  example_before?: string;
  example_after?: string;
  /** Related code snippet / unified diff excerpt */
  code_snippet?: string;
  related_files?: string[];
}

interface Props {
  issue: Issue;
  onOpenDiff?: (filename?: string) => void;
}

export function IssueCard({ issue, onOpenDiff }: Props) {
  const [open, setOpen] = useState(true);
  const s    = getSeverityStyle(issue.severity);
  const detail = issue.detail || issue.description || "";
  const fix = issue.fix || issue.suggestion || "";
  const loc  = issue.line ? `${issue.file ?? ""}:${issue.line}` : (issue.file || "");
  const Icon = open ? ChevronDown : ChevronRight;
  const related = issue.related_files?.filter(Boolean) ?? [];

  return (
    <div
      className="border rounded-lg overflow-hidden mb-2 dark:border-gray-700"
      style={{ borderLeftWidth: 4, borderLeftColor: s.bg }}
    >
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
      >
        <Icon size={14} className="text-gray-400 shrink-0" />
        <SeverityBadge severity={issue.severity} />
        <span className="flex-1 font-medium text-sm text-gray-800 dark:text-gray-200">
          {issue.title}
        </span>
        {loc && loc !== "merge" && (
          <code className="text-xs text-gray-500 dark:text-gray-400 font-mono shrink-0 truncate max-w-[40%]">
            {loc}
          </code>
        )}
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3 border-t dark:border-gray-700">
          {detail ? (
            <p className="text-sm text-gray-700 dark:text-gray-300 pt-3">{detail}</p>
          ) : (
            <p className="text-sm text-gray-400 pt-3">No additional detail for this item.</p>
          )}

          {fix && (
            <div className="rounded-lg bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 p-3">
              <p className="text-xs font-semibold text-green-800 dark:text-green-300 mb-1">Fix</p>
              <p className="text-sm text-green-700 dark:text-green-400">{fix}</p>
            </div>
          )}

          {issue.code_snippet && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">Related code</p>
              <pre className="text-xs font-mono whitespace-pre-wrap break-words rounded-lg border dark:border-gray-700 bg-gray-50 dark:bg-gray-950 p-3 overflow-x-auto max-h-72">
                {issue.code_snippet.split("\n").map((line, i) => {
                  const cls = line.startsWith("+") && !line.startsWith("+++")
                    ? "text-green-700 dark:text-green-400"
                    : line.startsWith("-") && !line.startsWith("---")
                    ? "text-red-700 dark:text-red-400"
                    : "text-gray-600 dark:text-gray-400";
                  return (
                    <div key={i} className={cls}>{line || " "}</div>
                  );
                })}
              </pre>
            </div>
          )}

          {(issue.example_before || issue.example_after) && (
            <div className="space-y-2">
              {issue.example_before && (
                <div>
                  <p className="text-xs text-gray-500 mb-1">Before</p>
                  <pre className="text-xs bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded p-2 overflow-x-auto">
                    <code>{issue.example_before}</code>
                  </pre>
                </div>
              )}
              {issue.example_after && (
                <div>
                  <p className="text-xs text-gray-500 mb-1">After</p>
                  <pre className="text-xs bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 rounded p-2 overflow-x-auto">
                    <code>{issue.example_after}</code>
                  </pre>
                </div>
              )}
            </div>
          )}

          {(related.length > 0 || (issue.file && issue.file !== "merge")) && onOpenDiff && (
            <div className="flex flex-wrap gap-2 pt-1">
              {(related.length ? related : [issue.file!]).slice(0, 5).map(f => (
                <button
                  key={f}
                  type="button"
                  onClick={() => onOpenDiff(f)}
                  className="text-xs px-2.5 py-1 rounded-md border dark:border-gray-600 hover:bg-indigo-50 dark:hover:bg-indigo-950 text-indigo-700 dark:text-indigo-300"
                >
                  Open in Diff → {f.split("/").pop()}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
