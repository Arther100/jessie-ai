"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronsUpDown, Search } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  value: string;
  options: string[];
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  emptyLabel?: string;
}

export function SearchableSelect({
  value,
  options,
  onChange,
  placeholder = "Search…",
  disabled = false,
  required = false,
  emptyLabel = "No matches",
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter(opt => opt.toLowerCase().includes(q));
  }, [options, query]);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      {/* Hidden input so HTML form required still works */}
      <input type="hidden" value={value} required={required} readOnly />

      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen(o => !o)}
        className={cn(
          "w-full flex items-center justify-between gap-2 rounded-lg border dark:border-gray-600 px-3 py-2 text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none disabled:opacity-60 text-left",
          !value && "text-gray-400",
        )}
      >
        <span className="truncate">{value || placeholder}</span>
        <ChevronsUpDown size={14} className="shrink-0 text-gray-400" />
      </button>

      {open && !disabled && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border dark:border-gray-600 bg-white dark:bg-gray-900 shadow-lg overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2 border-b dark:border-gray-700">
            <Search size={14} className="text-gray-400 shrink-0" />
            <input
              ref={inputRef}
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Type to search branches…"
              className="w-full bg-transparent text-sm outline-none"
            />
          </div>
          <div className="max-h-56 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <p className="px-3 py-2 text-xs text-gray-400">{emptyLabel}</p>
            ) : (
              filtered.map(opt => (
                <button
                  key={opt}
                  type="button"
                  onClick={() => {
                    onChange(opt);
                    setOpen(false);
                    setQuery("");
                  }}
                  className={cn(
                    "w-full flex items-center gap-2 px-3 py-2 text-left text-sm hover:bg-indigo-50 dark:hover:bg-indigo-950",
                    value === opt && "bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300",
                  )}
                >
                  <Check
                    size={14}
                    className={cn("shrink-0", value === opt ? "opacity-100" : "opacity-0")}
                  />
                  <span className="truncate font-mono text-xs">{opt}</span>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
