"use client";
import { useState } from "react";
import { cn } from "@/lib/utils";

export type Platform = "azure" | "github" | "gitlab" | "local";

const TABS: { id: Platform; label: string }[] = [
  { id: "azure",  label: "Azure DevOps" },
  { id: "github", label: "GitHub"       },
  { id: "gitlab", label: "GitLab"       },
  { id: "local",  label: "Local git"    },
];

interface Props {
  value: Platform;
  onChange: (p: Platform) => void;
}

export function PlatformTabs({ value, onChange }: Props) {
  return (
    <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 p-1 rounded-lg">
      {TABS.map(t => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={cn(
            "flex-1 px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
            value === t.id
              ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm"
              : "text-gray-500 hover:text-gray-700 dark:hover:text-gray-300",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
