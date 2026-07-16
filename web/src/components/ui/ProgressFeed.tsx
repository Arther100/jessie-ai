"use client";
import { useEffect, useRef } from "react";
import { Loader2 } from "lucide-react";

interface Props {
  title: string;
  updates: string[];
  pct: number;
}

export function ProgressFeed({ title, updates, pct }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const latest = updates[updates.length - 1] ?? "Starting…";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [updates]);

  return (
    <div className="rounded-xl border dark:border-gray-700 overflow-hidden">
      <div className="bg-gray-50 dark:bg-gray-800 px-4 py-3 border-b dark:border-gray-700">
        <div className="flex items-center gap-2">
          <Loader2 size={16} className="animate-spin text-indigo-500 shrink-0" />
          <p className="font-semibold text-sm text-gray-800 dark:text-gray-200">{title}</p>
        </div>

        <div className="mt-2 h-2.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500 ease-out jessie-progress-bar"
            style={{ width: `${Math.max(pct, 4)}%` }}
          />
        </div>
        <div className="mt-1.5 flex items-center justify-between gap-2">
          <p className="text-xs text-indigo-600 dark:text-indigo-300 truncate animate-pulse">
            {latest}
          </p>
          <p className="text-xs font-semibold text-gray-500 tabular-nums shrink-0">{pct}%</p>
        </div>
      </div>

      <div className="h-48 overflow-y-auto p-3 space-y-1 bg-gray-900 dark:bg-black font-mono">
        {updates.map((msg, i) => {
          const isLatest = i === updates.length - 1;
          return (
            <div key={i} className="flex gap-2 text-xs">
              <span className="text-gray-500 shrink-0">
                {new Date().toLocaleTimeString("en-GB", {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}
              </span>
              <span className={isLatest ? "text-green-300 animate-pulse" : "text-green-400"}>
                {isLatest ? "● " : ""}
                {msg}
              </span>
            </div>
          );
        })}
        <div className="flex items-center gap-2 text-xs text-indigo-300 pt-1">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-indigo-400 animate-ping" />
          <span className="animate-pulse">Working…</span>
        </div>
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
