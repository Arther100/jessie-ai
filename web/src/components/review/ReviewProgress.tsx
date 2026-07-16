"use client";
import { ProgressFeed } from "@/components/ui/ProgressFeed";
import { CheckCircle, Circle, Loader2 } from "lucide-react";

const STEPS = [
  { label: "Connecting / cloning", min: 0, max: 15 },
  { label: "Scanning project files", min: 15, max: 20 },
  { label: "Reviewing frontend", min: 20, max: 50 },
  { label: "Reviewing backend", min: 50, max: 75 },
  { label: "Claude impact analysis", min: 75, max: 92 },
  { label: "Generating report", min: 92, max: 101 },
];

interface Props {
  updates: string[];
  pct: number;
}

function stepState(pct: number, min: number, max: number): "done" | "active" | "pending" {
  if (pct >= max) return "done";
  if (pct >= min) return "active";
  return "pending";
}

export function ReviewProgress({ updates, pct }: Props) {
  return (
    <div className="space-y-6">
      <ProgressFeed title="Jessie Code Review" updates={updates} pct={pct} />
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        {STEPS.map(step => {
          const state = stepState(pct, step.min, step.max);
          return (
            <div
              key={step.label}
              className={`flex items-center gap-2 text-sm rounded-lg px-3 py-2 transition-colors ${
                state === "done"
                  ? "bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300"
                  : state === "active"
                    ? "bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 ring-1 ring-indigo-300 dark:ring-indigo-700"
                    : "bg-gray-50 dark:bg-gray-800 text-gray-400"
              }`}
            >
              {state === "done" ? (
                <CheckCircle size={14} className="shrink-0" />
              ) : state === "active" ? (
                <Loader2 size={14} className="shrink-0 animate-spin" />
              ) : (
                <Circle size={14} className="shrink-0" />
              )}
              <span className={state === "active" ? "animate-pulse" : undefined}>{step.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
