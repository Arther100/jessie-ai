"use client";
import { useEffect, useState } from "react";
import { Eye, EyeOff, Loader2, Check } from "lucide-react";
import { SearchableSelect } from "@/components/ui/SearchableSelect";
import { useTokenStorage } from "@/hooks/useTokenStorage";
import { api } from "@/lib/api";
import { parseAzureGitUrl } from "@/lib/utils";

export interface ReviewFormValues {
  userId: string;
  azureUrl: string;
  token: string;
  branch: string;
  org: string;
  project: string;
  repo: string;
  claudeApiKey: string;
}

interface Props {
  onStart: (values: ReviewFormValues) => void;
}

export function ReviewForm({ onStart }: Props) {
  const [userId, setUserId] = useState("");
  const [azureUrl, setAzureUrl] = useState("");
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [saveToken, setSaveToken] = useState(true);
  const [branch, setBranch] = useState("");
  const [branches, setBranches] = useState<string[]>([]);
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [claudeKeyMissing, setClaudeKeyMissing] = useState(false);

  const { saveToken: storeToken, getToken } = useTokenStorage(userId);

  useEffect(() => {
    setUserId(localStorage.getItem("jessie_user_id") ?? "");
    setAzureUrl(localStorage.getItem("jessie_last_azure_url") ?? "");
  }, []);

  useEffect(() => {
    const saved = getToken("azure");
    if (saved) setToken(saved);
    setClaudeKeyMissing(!getToken("Claude"));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  async function handleConnect() {
    const parsed = parseAzureGitUrl(azureUrl);
    if (!parsed) {
      setConnectError(
        "Paste the Azure clone URL, e.g. https://dev.azure.com/{org}/{project}/_git/{repo} or https://{user}@dev.azure.com/...",
      );
      return;
    }
    if (!token.trim()) {
      setConnectError("Paste your password / PAT first.");
      return;
    }

    setConnecting(true);
    setConnectError(null);
    try {
      const res = await api.getBranches({
        platform: "azure",
        repo: parsed.repo,
        token: token.trim(),
        azure_org: parsed.org,
        azure_project: parsed.project,
      });
      const list = res.branches ?? [];
      if (!list.length) {
        setConnected(false);
        setBranches([]);
        setConnectError("Connected, but no branches returned. Check PAT Code (Read) scope.");
        return;
      }
      setBranches(list);
      setConnected(true);
      if (saveToken) storeToken("azure", token.trim());
      localStorage.setItem("jessie_last_azure_url", azureUrl.trim());

      const preferred =
        list.find(b => b === "main" || b === "master" || b === "develop") ?? list[0];
      setBranch(preferred);
    } catch (e: unknown) {
      setConnected(false);
      setBranches([]);
      setConnectError(e instanceof Error ? e.message : "Failed to load branches");
    } finally {
      setConnecting(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const parsed = parseAzureGitUrl(azureUrl);
    const claudeKey = getToken("Claude").trim();
    if (!claudeKey) {
      setClaudeKeyMissing(true);
      return;
    }
    if (!userId.trim() || !parsed || !token.trim() || !branch.trim()) return;
    localStorage.setItem("jessie_user_id", userId.trim());
    localStorage.setItem("jessie_last_azure_url", azureUrl.trim());
    if (saveToken) storeToken("azure", token.trim());
    onStart({
      userId: userId.trim(),
      azureUrl: azureUrl.trim(),
      token: token.trim(),
      branch: branch.trim(),
      org: parsed.org,
      project: parsed.project,
      repo: parsed.repo,
      claudeApiKey: claudeKey,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5 max-w-xl">
      {claudeKeyMissing && (
        <div className="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40 px-3 py-2 text-sm text-amber-800 dark:text-amber-200">
          Claude API key is required.{" "}
          <a href="/settings?tab=info" className="underline font-medium">Add it in Settings → Info</a>
          {" "}then return here.
        </div>
      )}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Your user ID
        </label>
        <input
          value={userId}
          onChange={e => setUserId(e.target.value)}
          placeholder="e.g. vijay"
          required
          className="w-full rounded-lg border dark:border-gray-600 px-3 py-2 text-sm bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Project clone URL
        </label>
        <input
          value={azureUrl}
          onChange={e => {
            setAzureUrl(e.target.value);
            setConnected(false);
            setBranches([]);
            setBranch("");
          }}
          placeholder="https://user@dev.azure.com/{org}/{project}/_git/{repo}"
          required
          className="w-full rounded-lg border dark:border-gray-600 px-3 py-2 text-sm bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
        />
        <p className="text-xs text-gray-400 mt-1">
          Paste the clone URL from Azure (username@ is fine).
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Password
        </label>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type={showToken ? "text" : "password"}
              value={token}
              onChange={e => {
                setToken(e.target.value);
                setConnected(false);
              }}
              placeholder="Azure password or Personal Access Token"
              required
              className="w-full rounded-lg border dark:border-gray-600 px-3 py-2 pr-10 text-sm bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
            />
            <button
              type="button"
              onClick={() => setShowToken(v => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              {showToken ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </div>
        <label className="mt-2 flex items-center gap-2 text-xs text-gray-500">
          <input
            type="checkbox"
            checked={saveToken}
            onChange={e => setSaveToken(e.target.checked)}
            className="rounded"
          />
          Save password in this browser (30 days)
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleConnect}
          disabled={connecting}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium"
        >
          {connecting ? <Loader2 size={14} className="animate-spin" /> : null}
          {connecting ? "Connecting…" : "Connect & load branches"}
        </button>
        {connected && (
          <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
            <Check size={14} /> {branches.length} branches
          </span>
        )}
      </div>
      {connectError && (
        <p className="text-xs text-red-500">{connectError}</p>
      )}

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Branch
        </label>
        <SearchableSelect
          value={branch}
          options={branches}
          onChange={setBranch}
          placeholder={connected ? "Select branch…" : "Connect first to load branches"}
          disabled={!connected}
          required
          emptyLabel="No branches"
        />
      </div>

      <div className="rounded-lg bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 p-3 text-xs text-amber-700 dark:text-amber-300">
        ⚠️ A project review costs <strong>10 daily requests</strong>. Jessie clones the branch,
        scans it, then deletes the temp copy.
      </div>

      <button
        type="submit"
        disabled={!connected || !branch}
        className="w-full py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white font-semibold text-sm transition-colors"
      >
        Start Code Review →
      </button>
    </form>
  );
}
