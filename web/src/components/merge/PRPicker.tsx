"use client";
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { api, PR } from "@/lib/api";

interface Props {
  platform: string;
  repo: string;
  token: string;
  azureOrg?: string;
  azureProject?: string;
  onSelect: (pr: PR) => void;
}

export function PRPicker({ platform, repo, token, azureOrg, azureProject, onSelect }: Props) {
  const [prs,     setPRs]     = useState<PR[]>([]);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  async function fetchPRs() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getOpenPRs({
        platform, repo, token,
        azure_org:     azureOrg,
        azure_project: azureProject,
      });
      setPRs(res.prs);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to fetch PRs");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={fetchPRs}
        disabled={loading || !repo || !token}
        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-40 text-sm font-medium transition-colors"
      >
        {loading && <Loader2 size={14} className="animate-spin" />}
        Fetch open PRs
      </button>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      {prs.length > 0 && (
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {prs.map(pr => (
            <button
              key={pr.number}
              type="button"
              onClick={() => onSelect(pr)}
              className="w-full text-left rounded-lg border dark:border-gray-600 px-4 py-3 hover:bg-indigo-50 dark:hover:bg-indigo-950 transition-colors"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="font-medium text-sm">#{pr.number} {pr.title}</span>
                <span className="text-xs text-gray-400 shrink-0">
                  +{pr.added} −{pr.removed}
                </span>
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {pr.author} · {new Date(pr.created_at).toLocaleDateString()}
              </div>
            </button>
          ))}
        </div>
      )}

      {!loading && prs.length === 0 && !error && (
        <p className="text-xs text-gray-400">Click &quot;Fetch open PRs&quot; to load available pull requests.</p>
      )}
    </div>
  );
}
