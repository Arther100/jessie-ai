"use client";
import { useState, useEffect } from "react";
import { Eye, EyeOff, Loader2, Check } from "lucide-react";
import { PlatformTabs, Platform } from "./PlatformTabs";
import { PRPicker } from "./PRPicker";
import { SearchableSelect } from "@/components/ui/SearchableSelect";
import { useTokenStorage } from "@/hooks/useTokenStorage";
import { api, PR } from "@/lib/api";

export interface MergeFormValues {
  platform: Platform;
  userId: string;
  repo: string;
  token: string;
  azureOrg: string;
  azureProject: string;
  gitlabProjectId: string;
  mode: "pr" | "branch" | "commits";
  prNumber?: number;
  baseBranch: string;
  headBranch: string;
  fromSha: string;
  toSha: string;
  postComments: boolean;
  repoPath: string;
  claudeApiKey: string;
}

interface Props { onStart: (values: MergeFormValues) => void }

export function MergeForm({ onStart }: Props) {
  const [platform,  setPlatform]  = useState<Platform>("azure");
  const [userId,    setUserId]    = useState("");
  const [repo,      setRepo]      = useState("");
  const [token,     setToken]     = useState("");
  const [showToken, setShowToken] = useState(false);
  const [saveToken, setSaveToken] = useState(true);
  const [azureOrg,  setAzureOrg]  = useState("");
  const [azureProj, setAzureProj] = useState("");
  const [glProjectId, setGlId]   = useState("");
  const [mode,      setMode]      = useState<"pr" | "branch" | "commits">("branch");
  const [selectedPR,setSelectedPR]= useState<PR | null>(null);
  const [baseBranch, setBase]     = useState("main");
  const [headBranch, setHead]     = useState("");
  const [fromSha,   setFrom]      = useState("");
  const [toSha,     setTo]        = useState("");
  const [postComments, setPost]   = useState(false);
  const [repoPath,  setRepoPath]  = useState("");

  const [branches, setBranches] = useState<string[]>([]);
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [claudeKeyMissing, setClaudeKeyMissing] = useState(false);

  const { saveToken: storeToken, getToken } = useTokenStorage(userId);

  useEffect(() => {
    const id = localStorage.getItem("jessie_user_id") ?? "";
    setUserId(id);
  }, []);

  useEffect(() => {
    // Load token only after userId is known, so decrypt salt matches save salt.
    const saved = getToken(platform);
    if (saved) setToken(saved);
    else setToken("");
    setConnected(false);
    setBranches([]);
    setConnectError(null);
    setClaudeKeyMissing(!getToken("Claude"));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [platform, userId]);

  async function handleConnect() {
    const missing: string[] = [];
    if (!repo.trim()) missing.push("Repository");
    if (!token.trim()) missing.push("PAT");
    if (platform === "azure") {
      if (!azureOrg.trim()) missing.push("Organisation");
      if (!azureProj.trim()) missing.push("Project");
    }
    if (missing.length) {
      setConnectError(`Fill these first: ${missing.join(", ")}`);
      return;
    }

    setConnecting(true);
    setConnectError(null);
    try {
      const res = await api.getBranches({
        platform,
        repo: repo.trim(),
        token: token.trim(),
        azure_org: azureOrg.trim(),
        azure_project: azureProj.trim(),
      });
      const list = res.branches ?? [];
      if (!list.length) {
        setConnectError("Connected, but no branches were returned. Check repo name/PAT scopes.");
        setConnected(false);
        setBranches([]);
        return;
      }
      setBranches(list);
      setConnected(true);
      if (saveToken) storeToken(platform, token.trim());

      const preferredBase = list.find(b => b === "main" || b === "master" || b === "develop") ?? list[0];
      setBase(preferredBase || "main");
      if (!headBranch || !list.includes(headBranch)) {
        const preferredHead = list.find(b => b !== preferredBase) ?? "";
        setHead(preferredHead);
      }
    } catch (e: unknown) {
      setConnected(false);
      setBranches([]);
      setConnectError(e instanceof Error ? e.message : "Failed to connect / load branches");
    } finally {
      setConnecting(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const claudeKey = getToken("Claude").trim();
    if (!claudeKey) {
      setClaudeKeyMissing(true);
      return;
    }
    if (platform !== "local" && mode === "branch" && !connected) {
      setConnectError("Click Connect first to load branches.");
      return;
    }
    if (saveToken && token) storeToken(platform, token);
    if (userId) localStorage.setItem("jessie_user_id", userId);
    onStart({
      platform, userId, repo, token,
      azureOrg, azureProject: azureProj,
      gitlabProjectId: glProjectId,
      mode,
      prNumber: selectedPR?.number,
      baseBranch, headBranch, fromSha, toSha,
      postComments, repoPath,
      claudeApiKey: claudeKey,
    });
  }

  const needsToken = platform !== "local";
  const missingForConnect: string[] = [];
  if (!repo.trim()) missingForConnect.push("Repository");
  if (!token.trim()) missingForConnect.push("PAT");
  if (platform === "azure") {
    if (!azureOrg.trim()) missingForConnect.push("Organisation");
    if (!azureProj.trim()) missingForConnect.push("Project");
  }
  const canConnect = missingForConnect.length === 0;

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
        <label className="block text-sm font-medium mb-1 dark:text-gray-300">Platform</label>
        <PlatformTabs value={platform} onChange={p => { setPlatform(p); setSelectedPR(null); }} />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1 dark:text-gray-300">Your user ID</label>
        <input value={userId} onChange={e => setUserId(e.target.value)} placeholder="e.g. vijay" required
          className="w-full rounded-lg border dark:border-gray-600 px-3 py-2 text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none" />
      </div>

      {platform === "local" ? (
        <div>
          <label className="block text-sm font-medium mb-1 dark:text-gray-300">Repository path</label>
          <input value={repoPath} onChange={e => setRepoPath(e.target.value)} placeholder="/home/user/my-repo" required
            className="w-full rounded-lg border dark:border-gray-600 px-3 py-2 text-sm font-mono bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none" />
        </div>
      ) : (
        <>
          {platform === "azure" && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1 dark:text-gray-300">Organisation</label>
                <input value={azureOrg} onChange={e => { setAzureOrg(e.target.value); setConnected(false); }} placeholder="Ruposapp" required
                  className="w-full rounded-lg border dark:border-gray-600 px-3 py-2 text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 dark:text-gray-300">Project</label>
                <input value={azureProj} onChange={e => { setAzureProj(e.target.value); setConnected(false); }} placeholder="Rupos" required
                  className="w-full rounded-lg border dark:border-gray-600 px-3 py-2 text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none" />
              </div>
            </div>
          )}

          {platform === "gitlab" && (
            <div>
              <label className="block text-sm font-medium mb-1 dark:text-gray-300">GitLab Project ID</label>
              <input value={glProjectId} onChange={e => setGlId(e.target.value)} placeholder="12345678" required
                className="w-full rounded-lg border dark:border-gray-600 px-3 py-2 text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none" />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium mb-1 dark:text-gray-300">Repository</label>
            <input value={repo} onChange={e => { setRepo(e.target.value); setConnected(false); }}
              placeholder={platform === "github" ? "owner/repo" : "Rupos"} required
              className="w-full rounded-lg border dark:border-gray-600 px-3 py-2 text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none" />
          </div>

          {needsToken && (
            <div>
              <label className="block text-sm font-medium mb-1 dark:text-gray-300">
                {platform === "azure" ? "Personal Access Token" : platform === "github" ? "GitHub Token" : "GitLab Token"}
              </label>
              <div className="flex gap-2">
                <input
                  type={showToken ? "text" : "password"}
                  value={token}
                  onChange={e => { setToken(e.target.value); setConnected(false); }}
                  placeholder="••••••••••••••••"
                  required
                  className="flex-1 rounded-lg border dark:border-gray-600 px-3 py-2 text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none font-mono"
                />
                <button type="button" onClick={() => setShowToken(s => !s)}
                  className="px-3 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                  {showToken ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              <label className="flex items-center gap-2 mt-2 text-xs text-gray-500 cursor-pointer">
                <input type="checkbox" checked={saveToken} onChange={e => setSaveToken(e.target.checked)}
                  className="rounded" />
                Save token (browser localStorage, 30-day expiry)
              </label>

              <button
                type="button"
                onClick={handleConnect}
                disabled={connecting}
                className="mt-3 w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-50 dark:bg-indigo-950 border border-indigo-200 dark:border-indigo-800 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-900 disabled:opacity-50 text-sm font-semibold"
              >
                {connecting ? <Loader2 size={14} className="animate-spin" /> : connected ? <Check size={14} className="text-green-600" /> : null}
                {connecting ? "Connecting..." : connected ? `Connected · ${branches.length} branches` : "Connect & load branches"}
              </button>
              {!canConnect && !connecting && (
                <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
                  Fill these first: <strong>{missingForConnect.join(", ")}</strong>
                </p>
              )}
              {connectError && (
                <div className="mt-2 space-y-1">
                  <p className="text-sm text-red-600 dark:text-red-400">{connectError}</p>
                  <p className="text-xs text-gray-400">
                    Tip: clear the PAT field, paste a fresh Azure PAT (Code Read), then Connect again.
                  </p>
                </div>
              )}
              {connected && (
                <p className="mt-2 text-xs text-green-600 dark:text-green-400">
                  PAT verified. Pick base/head from dropdowns below.
                </p>
              )}
            </div>
          )}
        </>
      )}

      {platform !== "local" && (
        <div>
          <label className="block text-sm font-medium mb-2 dark:text-gray-300">Review mode</label>
          <div className="flex gap-2">
            {(["pr", "branch", "commits"] as const).map(m => (
              <button key={m} type="button"
                onClick={() => setMode(m)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                  mode === m ? "bg-indigo-600 border-indigo-600 text-white" : "border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800"
                }`}
              >
                {m === "pr" ? "Pull Request" : m === "branch" ? "Branch" : "Commits"}
              </button>
            ))}
          </div>
        </div>
      )}

      {mode === "pr" && platform !== "local" && (
        <div>
          <label className="block text-sm font-medium mb-2 dark:text-gray-300">Select PR</label>
          <PRPicker
            platform={platform} repo={repo} token={token}
            azureOrg={azureOrg} azureProject={azureProj}
            onSelect={pr => setSelectedPR(pr)}
          />
          {selectedPR && (
            <div className="mt-2 rounded-lg bg-indigo-50 dark:bg-indigo-950 border border-indigo-200 dark:border-indigo-800 px-3 py-2 text-sm">
              ✓ Selected: <strong>#{selectedPR.number} {selectedPR.title}</strong>
            </div>
          )}
        </div>
      )}

      {mode === "branch" && (
        <div className="space-y-2">
          {!connected && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              Click <strong>Connect &amp; load branches</strong> above first — then Base/Head become searchable dropdowns.
            </p>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1 dark:text-gray-300">Base branch</label>
              <SearchableSelect
                value={baseBranch}
                options={branches}
                onChange={setBase}
                disabled={!connected || branches.length === 0}
                placeholder={connected ? "Search base branch…" : "Connect first…"}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1 dark:text-gray-300">Head branch</label>
              <SearchableSelect
                value={headBranch}
                options={branches}
                onChange={setHead}
                required
                disabled={!connected || branches.length === 0}
                placeholder={connected ? "Search head branch…" : "Connect first…"}
              />
            </div>
          </div>
        </div>
      )}

      {mode === "commits" && (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium mb-1 dark:text-gray-300">From SHA</label>
            <input value={fromSha} onChange={e => setFrom(e.target.value)} placeholder="abc1234"
              className="w-full rounded-lg border dark:border-gray-600 px-3 py-2 text-sm font-mono bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1 dark:text-gray-300">To SHA</label>
            <input value={toSha} onChange={e => setTo(e.target.value)} placeholder="def5678"
              className="w-full rounded-lg border dark:border-gray-600 px-3 py-2 text-sm font-mono bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none" />
          </div>
        </div>
      )}

      {platform !== "local" && (
        <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 cursor-pointer">
          <input type="checkbox" checked={postComments} onChange={e => setPost(e.target.checked)} className="rounded" />
          Post Jessie comments back to PR
        </label>
      )}

      <button type="submit"
        className="w-full py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-sm transition-colors">
        Start Merge Review →
      </button>
    </form>
  );
}
