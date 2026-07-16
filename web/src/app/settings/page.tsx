"use client";
import { useState, useEffect } from "react";
import { useQueryClient, useQuery } from "@tanstack/react-query";
import { useTeamUsage } from "@/hooks/useReviews";
import { useTokenStorage } from "@/hooks/useTokenStorage";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Eye, EyeOff, Check, X } from "lucide-react";

type Tab = "profile" | "tokens" | "quotas" | "webhooks" | "info";

const PLATFORMS = ["GitHub", "Azure DevOps", "GitLab"] as const;
const CLAUDE_PLATFORM = "Claude";
const TABS: Tab[] = ["profile", "tokens", "quotas", "webhooks", "info"];

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("profile");
  const [visited, setVisited] = useState<Set<Tab>>(() => new Set(["profile"]));
  const queryClient = useQueryClient();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const t = params.get("tab");
    if (t === "info" || t === "tokens" || t === "profile" || t === "quotas" || t === "webhooks") {
      setTab(t);
      setVisited(prev => new Set(prev).add(t));
    }
  }, []);

  useEffect(() => {
    queryClient.prefetchQuery({
      queryKey: ["team-usage", ""],
      queryFn: () => api.getTeamUsage(),
    });
    queryClient.prefetchQuery({
      queryKey: ["health"],
      queryFn: () => api.getHealth(),
    });
  }, [queryClient]);

  function selectTab(next: Tab) {
    setTab(next);
    setVisited(prev => new Set(prev).add(next));
    const url = new URL(window.location.href);
    url.searchParams.set("tab", next);
    window.history.replaceState({}, "", url.toString());
  }

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>
      <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 p-1 rounded-lg">
        {TABS.map(t => (
          <button key={t} onClick={() => selectTab(t)}
            className={cn(
              "flex-1 px-3 py-1.5 rounded-md text-sm font-medium capitalize transition-colors",
              tab === t ? "bg-white dark:bg-gray-700 shadow-sm" : "text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
            )}>
            {t === "quotas" ? "Team Quotas" : t === "webhooks" ? "CI/CD" : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      <div className="rounded-xl border dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
        {visited.has("profile") && (
          <div hidden={tab !== "profile"}><ProfileTab /></div>
        )}
        {visited.has("tokens") && (
          <div hidden={tab !== "tokens"}><TokensTab /></div>
        )}
        {visited.has("quotas") && (
          <div hidden={tab !== "quotas"}><QuotasTab /></div>
        )}
        {visited.has("webhooks") && (
          <div hidden={tab !== "webhooks"}><WebhooksTab /></div>
        )}
        {visited.has("info") && (
          <div hidden={tab !== "info"}><InfoTab /></div>
        )}
      </div>
    </div>
  );
}

function ProfileTab() {
  const [userId,    setUserId]    = useState("");
  const [displayName, setDisplay] = useState("");
  const [saved,     setSaved]     = useState(false);

  useEffect(() => {
    setUserId(localStorage.getItem("jessie_user_id") ?? "");
    setDisplay(localStorage.getItem("jessie_display_name") ?? "");
  }, []);

  function save() {
    localStorage.setItem("jessie_user_id", userId);
    localStorage.setItem("jessie_display_name", displayName);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div className="space-y-5">
      <h2 className="text-lg font-semibold">Profile</h2>
      <div>
        <label className="block text-sm font-medium mb-1 dark:text-gray-300">User ID</label>
        <input value={userId} onChange={e => setUserId(e.target.value)} placeholder="e.g. vijay"
          className="w-full rounded-lg border dark:border-gray-600 px-3 py-2 text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none" />
        <p className="text-xs text-gray-400 mt-1">Used for quota tracking and history attribution.</p>
      </div>
      <div>
        <label className="block text-sm font-medium mb-1 dark:text-gray-300">Display name</label>
        <input value={displayName} onChange={e => setDisplay(e.target.value)} placeholder="Your name"
          className="w-full rounded-lg border dark:border-gray-600 px-3 py-2 text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none" />
      </div>
      <button onClick={save}
        className={cn("flex items-center gap-2 px-4 py-2 rounded-lg text-white text-sm font-medium transition-colors",
          saved ? "bg-green-600" : "bg-indigo-600 hover:bg-indigo-700")}>
        {saved ? <><Check size={14} /> Saved!</> : "Save Profile"}
      </button>
    </div>
  );
}

function TokensTab() {
  const [userId, setUserId] = useState("anon");
  const { saveToken, getToken, deleteToken } = useTokenStorage(userId);
  const [show,   setShow]   = useState<Record<string, boolean>>({});
  const [vals,   setVals]   = useState<Record<string, string>>({});
  const [tested, setTested] = useState<Record<string, boolean | null>>({});

  useEffect(() => {
    setUserId(localStorage.getItem("jessie_user_id") ?? "anon");
  }, []);

  function maskedDisplay(platform: string): string {
    const t = getToken(platform);
    if (!t) return "Not connected";
    return "●".repeat(Math.max(0, t.length - 4)) + t.slice(-4);
  }

  async function testToken(platform: string) {
    try {
      await api.getOpenPRs({ platform: platform.toLowerCase().replace(/ /g, "_"), repo: "test/test", token: getToken(platform) });
      setTested(p => ({ ...p, [platform]: true }));
    } catch {
      setTested(p => ({ ...p, [platform]: false }));
    }
  }

  return (
    <div className="space-y-5">
      <h2 className="text-lg font-semibold">Git platform PATs</h2>
      <p className="text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-lg p-3">
        Tokens are stored in your browser&apos;s localStorage with a 30-day expiry. Sent to the Jessie backend only during a review — not persisted server-side.
        Claude API key lives on the <a href="/settings?tab=info" className="underline font-medium">Info</a> tab.
      </p>
      {PLATFORMS.map(platform => (
        <div key={platform} className="border dark:border-gray-700 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="font-medium text-sm">{platform}</p>
            <span className="text-xs text-gray-400 font-mono">{maskedDisplay(platform)}</span>
          </div>
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <input
                type={show[platform] ? "text" : "password"}
                value={vals[platform] ?? ""}
                onChange={e => setVals(p => ({ ...p, [platform]: e.target.value }))}
                placeholder="Paste new token…"
                className="w-full rounded-lg border dark:border-gray-600 px-3 py-1.5 text-sm font-mono bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
              <button type="button" onClick={() => setShow(p => ({ ...p, [platform]: !p[platform] }))}
                className="absolute right-2 top-1.5 text-gray-400">
                {show[platform] ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            {vals[platform] && (
              <button onClick={() => { saveToken(platform, vals[platform]!); setVals(p => ({ ...p, [platform]: "" })); }}
                className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-medium">
                Save
              </button>
            )}
            {getToken(platform) && (
              <>
                <button onClick={() => deleteToken(platform)}
                  className="px-3 py-1.5 rounded-lg border dark:border-gray-600 text-xs font-medium hover:bg-gray-50 dark:hover:bg-gray-800 text-red-600">
                  Delete
                </button>
                <button onClick={() => testToken(platform)}
                  className="px-3 py-1.5 rounded-lg border dark:border-gray-600 text-xs font-medium hover:bg-gray-50 dark:hover:bg-gray-800">
                  Test
                </button>
              </>
            )}
          </div>
          {tested[platform] !== undefined && tested[platform] !== null && (
            <p className={`text-xs flex items-center gap-1 ${tested[platform] ? "text-green-600" : "text-red-600"}`}>
              {tested[platform] ? <><Check size={12} /> Token valid</> : <><X size={12} /> Invalid or no access</>}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function QuotasTab() {
  const { data, isLoading } = useTeamUsage();
  const [limits, setLimits] = useState<Record<string, number>>({});
  const [saved,  setSaved]  = useState<Record<string, boolean>>({});

  async function saveLimit(userId: string) {
    await api.updateQuota(userId, limits[userId] ?? 50);
    setSaved(p => ({ ...p, [userId]: true }));
    setTimeout(() => setSaved(p => ({ ...p, [userId]: false })), 2000);
  }

  return (
    <div className="space-y-5">
      <h2 className="text-lg font-semibold">Team Quotas</h2>
      {isLoading ? <p className="text-sm text-gray-400">Loading...</p> : (
        <div className="space-y-3">
          {(data?.usage ?? []).map(m => (
            <div key={m.user_id} className="flex items-center gap-4 border dark:border-gray-700 rounded-xl p-3">
              <span className="font-medium text-sm w-32">{m.user_id}</span>
              <span className="text-sm text-gray-500">{m.used}/{m.limit} today</span>
              <div className="flex-1" />
              <input
                type="number" min={1} max={1000}
                value={limits[m.user_id] ?? m.limit}
                onChange={e => setLimits(p => ({ ...p, [m.user_id]: Number(e.target.value) }))}
                className="w-20 rounded-lg border dark:border-gray-600 px-2 py-1 text-sm text-center bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
              <button onClick={() => saveLimit(m.user_id)}
                className={cn("px-3 py-1 rounded-lg text-xs font-medium text-white transition-colors",
                  saved[m.user_id] ? "bg-green-600" : "bg-indigo-600 hover:bg-indigo-700")}>
                {saved[m.user_id] ? "Saved!" : "Save"}
              </button>
            </div>
          ))}
          {!data?.usage?.length && <p className="text-sm text-gray-400">No team members have used Jessie yet.</p>}
        </div>
      )}
    </div>
  );
}

function WebhooksTab() {
  const [tested, setTested] = useState<boolean | null>(null);
  const base = process.env.NEXT_PUBLIC_JESSIE_API ?? "http://localhost:8000";

  const hooks = [
    { platform: "GitHub",        url: `${base}/webhook/github`,  events: "Pull requests", type: "Payload URL" },
    { platform: "Azure DevOps",  url: `${base}/webhook/azure`,   events: "Git pull request", type: "Service connection URL" },
    { platform: "GitLab",        url: `${base}/webhook/gitlab`,  events: "Merge request events", type: "Webhook URL" },
  ];

  async function testWebhook() {
    try {
      await api.testWebhook();
      setTested(true);
    } catch {
      setTested(false);
    }
  }

  return (
    <div className="space-y-5">
      <h2 className="text-lg font-semibold">CI/CD Webhooks</h2>
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Add these webhooks to your repos to auto-review every PR automatically.
      </p>
      {hooks.map(h => (
        <div key={h.platform} className="border dark:border-gray-700 rounded-xl p-4 space-y-2">
          <p className="font-medium text-sm">{h.platform}</p>
          <div className="flex gap-2">
            <code className="flex-1 text-xs bg-gray-100 dark:bg-gray-800 rounded px-3 py-2 font-mono overflow-x-auto">
              {h.url}
            </code>
            <button onClick={() => navigator.clipboard.writeText(h.url)}
              className="px-3 py-1 rounded-lg border dark:border-gray-600 text-xs hover:bg-gray-50 dark:hover:bg-gray-800">
              Copy
            </button>
          </div>
          <p className="text-xs text-gray-400">{h.type} · Events: {h.events} · Content-Type: application/json</p>
        </div>
      ))}
      <div className="border dark:border-gray-700 rounded-xl p-4">
        <p className="text-sm font-medium mb-3">Test connection</p>
        <button onClick={testWebhook}
          className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium">
          Send test ping
        </button>
        {tested !== null && (
          <p className={`mt-2 text-sm flex items-center gap-1 ${tested ? "text-green-600" : "text-red-600"}`}>
            {tested ? <><Check size={14} /> Backend responded OK</> : <><X size={14} /> No response from backend</>}
          </p>
        )}
      </div>
    </div>
  );
}

function InfoTab() {
  const [userId, setUserId] = useState("anon");
  const { saveToken, getToken, deleteToken } = useTokenStorage(userId);
  const [show, setShow] = useState(false);
  const [val, setVal] = useState("");
  const [savedOk, setSavedOk] = useState<boolean | null>(null);
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.getHealth(),
    retry: false,
  });

  useEffect(() => {
    setUserId(localStorage.getItem("jessie_user_id") ?? "anon");
  }, []);

  function maskedClaude(): string {
    const t = getToken(CLAUDE_PLATFORM);
    if (!t) return "Not configured";
    return "●".repeat(Math.max(0, t.length - 4)) + t.slice(-4);
  }

  function saveClaude() {
    const v = val.trim();
    if (!v.startsWith("sk-ant-") && !v.startsWith("sk-")) {
      setSavedOk(false);
      return;
    }
    saveToken(CLAUDE_PLATFORM, v);
    setVal("");
    setSavedOk(true);
    setTimeout(() => setSavedOk(null), 2500);
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Info</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Web app and VS Code extension share the same Jessie backend. Add your Claude key here (or in the extension Info panel) before running reviews.
        </p>
      </div>

      <div className="border border-indigo-200 dark:border-indigo-800 rounded-xl p-4 space-y-3 bg-indigo-50/40 dark:bg-indigo-950/30">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="font-medium text-sm">Claude (Anthropic) API key</p>
            <p className="text-xs text-gray-500 mt-0.5">
              Mandatory for Code Review and Merge Review. Get a key from{" "}
              <a href="https://console.anthropic.com/" target="_blank" rel="noreferrer" className="underline">
                console.anthropic.com
              </a>
              .
            </p>
          </div>
          <span className="text-xs text-gray-400 font-mono shrink-0">{maskedClaude()}</span>
        </div>
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <input
              type={show ? "text" : "password"}
              value={val}
              onChange={e => setVal(e.target.value)}
              placeholder="sk-ant-…"
              className="w-full rounded-lg border dark:border-gray-600 px-3 py-1.5 text-sm font-mono bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            />
            <button type="button" onClick={() => setShow(s => !s)} className="absolute right-2 top-1.5 text-gray-400">
              {show ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
          {val && (
            <button onClick={saveClaude} className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-medium">
              Save
            </button>
          )}
          {getToken(CLAUDE_PLATFORM) && (
            <button onClick={() => deleteToken(CLAUDE_PLATFORM)}
              className="px-3 py-1.5 rounded-lg border dark:border-gray-600 text-xs font-medium text-red-600">
              Delete
            </button>
          )}
        </div>
        {savedOk === false && (
          <p className="text-xs text-red-600 flex items-center gap-1"><X size={12} /> Key should start with sk-ant-</p>
        )}
        {savedOk === true && (
          <p className="text-xs text-green-600 flex items-center gap-1"><Check size={12} /> Claude key saved</p>
        )}
      </div>

      <div className="space-y-3">
        <h3 className="text-sm font-semibold">Same features on web &amp; VS Code</h3>
        <ul className="text-sm text-gray-600 dark:text-gray-300 space-y-2 list-disc pl-5">
          <li><span className="font-medium text-gray-800 dark:text-gray-100">Code Review</span> — Azure clone URL + password/PAT + branch; Claude scores layers and project impact. Extension also supports a local folder.</li>
          <li><span className="font-medium text-gray-800 dark:text-gray-100">Merge Review</span> — Azure base → head diff; Claude explains UI, functionality, risks, missing coverage; download impact report.</li>
          <li><span className="font-medium text-gray-800 dark:text-gray-100">History</span> — past code &amp; merge reviews (open from web History or extension History).</li>
          <li><span className="font-medium text-gray-800 dark:text-gray-100">Your Claude key</span> — used only for the request; not stored on the Jessie server.</li>
        </ul>
      </div>

      <div className="space-y-2 text-sm">
        <h3 className="text-sm font-semibold">Status</h3>
        <div className="flex justify-between py-2 border-b dark:border-gray-700">
          <span className="text-gray-500">Web app</span>
          <span className="font-mono">1.0.0</span>
        </div>
        <div className="flex justify-between py-2 border-b dark:border-gray-700">
          <span className="text-gray-500">Backend</span>
          <span className="font-mono">{health?.version ?? "—"} · {health?.status === "ok" ? "Online" : "Offline"}</span>
        </div>
        <div className="flex justify-between py-2 border-b dark:border-gray-700">
          <span className="text-gray-500">API URL</span>
          <code className="text-xs font-mono">{process.env.NEXT_PUBLIC_JESSIE_API ?? "http://localhost:8000"}</code>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <a href="/review" className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700">
          Code Review
        </a>
        <a href="/merge" className="px-4 py-2 rounded-lg border dark:border-gray-600 text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-800">
          Merge Review
        </a>
        <a href="https://console.anthropic.com/" target="_blank" rel="noreferrer"
          className="px-4 py-2 rounded-lg border dark:border-gray-600 text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-800">
          Anthropic Console →
        </a>
      </div>
    </div>
  );
}
