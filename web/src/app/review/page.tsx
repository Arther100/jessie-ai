"use client";
import { useState } from "react";
import dynamic from "next/dynamic";
import { ReviewForm, type ReviewFormValues } from "@/components/review/ReviewForm";
import type { CompleteEvent } from "@/components/review/ReviewResults";
import { useSSEStream } from "@/hooks/useSSEStream";
import { workspaceId } from "@/lib/utils";

const ReviewProgress = dynamic(
  () => import("@/components/review/ReviewProgress").then(m => ({ default: m.ReviewProgress })),
  { loading: () => <div className="h-32 rounded-lg bg-gray-100 dark:bg-gray-800/70 animate-pulse" /> },
);
const ReviewResults = dynamic(
  () => import("@/components/review/ReviewResults").then(m => ({ default: m.ReviewResults })),
  { loading: () => <div className="h-48 rounded-lg bg-gray-100 dark:bg-gray-800/70 animate-pulse" /> },
);

type State = "form" | "running" | "done" | "error";

export default function ReviewPage() {
  const [uiState, setUiState] = useState<State>("form");
  const { start, reset, isLoading, updates, pct, result, error } = useSSEStream<CompleteEvent>("/review/start");

  async function handleStart(p: ReviewFormValues) {
    setUiState("running");
    await start(
      {
        azure_url:    p.azureUrl,
        token:        p.token,
        branch:       p.branch,
        user_id:      p.userId,
        workspace_id: workspaceId(`${p.org}/${p.project}/${p.repo}`),
        triggered_by: "web",
        project_path: "",
        claude_api_key: p.claudeApiKey,
      },
      {
        onComplete: () => setUiState("done"),
        onError:    () => setUiState("error"),
      },
    );
  }

  function handleReset() {
    reset();
    setUiState("form");
  }

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Code Review</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Clone an Azure DevOps branch and scan it for security, performance, and quality issues.
        </p>
      </div>

      {uiState === "form" && (
        <div className="rounded-xl border dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
          <ReviewForm onStart={handleStart} />
        </div>
      )}

      {(uiState === "running" || isLoading) && (
        <div className="rounded-xl border dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
          <ReviewProgress updates={updates} pct={pct} />
          <button
            onClick={handleReset}
            className="mt-4 px-4 py-2 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
          >
            Cancel
          </button>
        </div>
      )}

      {uiState === "done" && result && (
        <div className="rounded-xl border dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
          <ReviewResults result={result as CompleteEvent} onReset={handleReset} />
        </div>
      )}

      {uiState === "error" && (
        <div className="rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950 p-6">
          <p className="text-red-700 dark:text-red-300 font-medium">Review failed</p>
          <p className="text-sm text-red-600 dark:text-red-400 mt-1">{error}</p>
          <button onClick={handleReset} className="mt-4 text-sm text-red-600 hover:underline">
            Try again
          </button>
        </div>
      )}
    </div>
  );
}
