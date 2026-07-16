"use client";
import { useCallback, useEffect, useState } from "react";
import { Folder, FolderOpen, ChevronUp, Loader2, X } from "lucide-react";
import { api } from "@/lib/api";

interface Props {
  open: boolean;
  initialPath?: string;
  onClose: () => void;
  onSelect: (path: string) => void;
}

export function FolderPicker({ open, initialPath = "", onClose, onSelect }: Props) {
  const [current, setCurrent] = useState(initialPath);
  const [parent, setParent] = useState<string | null>(null);
  const [dirs, setDirs] = useState<{ name: string; path: string }[]>([]);
  const [isRootList, setIsRootList] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (path: string) => {
    setLoading(true);
    setError("");
    try {
      const data = await api.browseFs(path);
      setCurrent(data.path);
      setParent(data.parent);
      setDirs(data.dirs);
      setIsRootList(data.is_root_list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not list folders");
      setDirs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    void load(initialPath || "");
  }, [open, initialPath, load]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/50"
        aria-label="Close folder picker"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Browse project folder"
        className="relative w-full max-w-lg rounded-xl border dark:border-gray-700 bg-white dark:bg-gray-900 shadow-xl flex flex-col max-h-[80vh]"
      >
        <div className="flex items-center justify-between gap-3 px-4 py-3 border-b dark:border-gray-700">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Browse folder on backend machine
            </p>
            <p className="text-xs text-gray-500 truncate font-mono" title={current || "Roots"}>
              {current || "Select a drive or folder"}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-md text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-3 py-2 border-b dark:border-gray-700 flex gap-2">
          <button
            type="button"
            disabled={loading || (!parent && !isRootList && !current)}
            onClick={() => {
              if (isRootList) return;
              if (parent) void load(parent);
              else void load("");
            }}
            className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border dark:border-gray-600 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            <ChevronUp size={14} /> Up
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => void load("")}
            className="text-xs px-2.5 py-1.5 rounded-md border dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            Roots
          </button>
        </div>

        <div className="flex-1 overflow-y-auto min-h-[220px] p-2">
          {loading && (
            <div className="flex items-center justify-center gap-2 py-10 text-sm text-gray-500">
              <Loader2 size={16} className="animate-spin" /> Loading…
            </div>
          )}
          {!loading && error && (
            <p className="text-sm text-red-500 p-3">{error}</p>
          )}
          {!loading && !error && dirs.length === 0 && (
            <p className="text-sm text-gray-400 p-3">No subfolders here.</p>
          )}
          {!loading && !error && dirs.map(d => (
            <button
              key={d.path}
              type="button"
              onClick={() => void load(d.path)}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm hover:bg-indigo-50 dark:hover:bg-indigo-950 text-gray-800 dark:text-gray-200"
            >
              <Folder size={16} className="text-amber-500 shrink-0" />
              <span className="truncate">{d.name}</span>
            </button>
          ))}
        </div>

        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t dark:border-gray-700">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg border dark:border-gray-600 text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!current || isRootList}
            onClick={() => {
              if (!current) return;
              onSelect(current);
              onClose();
            }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white text-sm font-medium"
          >
            <FolderOpen size={14} /> Use this folder
          </button>
        </div>
      </div>
    </div>
  );
}
