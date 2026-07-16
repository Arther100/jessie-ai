"use client";
import { useState } from "react";
import dynamic from "next/dynamic";
import { MergeForm, MergeFormValues } from "@/components/merge/MergeForm";
import { MergeCompleteEvent } from "@/components/merge/MergeResults";
import { useSSEStream } from "@/hooks/useSSEStream";
import { workspaceId } from "@/lib/utils";

const MergeProgress = dynamic(
  () => import("@/components/merge/MergeProgress").then(m => ({ default: m.MergeProgress })),
  { loading: () => <div className="h-32 rounded-lg bg-gray-100 dark:bg-gray-800/70 animate-pulse" /> },
);
const MergeResults = dynamic(
  () => import("@/components/merge/MergeResults").then(m => ({ default: m.MergeResults })),
  { loading: () => <div className="h-48 rounded-lg bg-gray-100 dark:bg-gray-800/70 animate-pulse" /> },
);

type State = "form" | "running" | "done" | "error";

export default function MergePage() {
  const [uiState,  setUiState]  = useState<State>("form");
  const [platform, setPlatform] = useState("github");
  const { start, reset, updates, pct, result, error } = useSSEStream<MergeCompleteEvent>("/merge/review");

  async function handleStart(values: MergeFormValues) {
    setPlatform(values.platform);
    setUiState("running");
    await start(
      {
        platform:         values.platform,
        user_id:          values.userId,
        workspace_id:     workspaceId(values.repo || values.repoPath),
        repo:             values.repo,
        token:            values.token,
        azure_org:        values.azureOrg,
        azure_project:    values.azureProject,
        gitlab_project_id:values.gitlabProjectId,
        mode:             values.mode,
        pr_number:        values.prNumber,
        base_branch:      values.baseBranch,
        head_branch:      values.headBranch,
        from_sha:         values.fromSha,
        to_sha:           values.toSha,
        post_comments:    values.postComments,
        repo_path:        values.repoPath,
        triggered_by:     "web",
        claude_api_key:   values.claudeApiKey,
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
        <h1 className="text-2xl font-bold">Merge Review</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Analyse a pull request or branch diff for risks, missing code, and quality issues.
        </p>
      </div>

      {uiState === "form" && (
        <div className="rounded-xl border dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
          <MergeForm onStart={handleStart} />
        </div>
      )}

      {uiState === "running" && (
        <div className="rounded-xl border dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
          <MergeProgress updates={updates} pct={pct} platform={platform} />
          <button onClick={handleReset} className="mt-4 px-4 py-2 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
            Cancel
          </button>
        </div>
      )}

      {uiState === "done" && result && (
        <div className="rounded-xl border dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
          <MergeResults result={result} onReset={handleReset} />
        </div>
      )}

      {uiState === "error" && (
        <div className="rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950 p-6">
          <p className="text-red-700 dark:text-red-300 font-medium">Merge review failed</p>
          <p className="text-sm text-red-600 dark:text-red-400 mt-1">{error}</p>
          <button onClick={handleReset} className="mt-4 text-sm text-red-600 hover:underline">Try again</button>
        </div>
      )}
    </div>
  );
}
