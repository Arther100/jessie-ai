"use client";
import { useEffect, useState } from "react";
import { useSSEStream } from "@/hooks/useSSEStream";
import { useTokenStorage } from "@/hooks/useTokenStorage";

type Board = {
  empty?: boolean;
  message?: string;
  sprint?: string;
  sprint_name?: string;
  auto_fixable?: any[];
  classified?: any[];
  ai_assist?: any[];
  human_only?: any[];
  health?: { health_score?: number; health_grade?: string; at_risk?: boolean };
};

export default function TicketsPage() {
  const [userId, setUserId] = useState("anon");
  const [board, setBoard] = useState<Board | null>(null);
  const [tab, setTab] = useState<"auto" | "assist" | "human">("auto");
  const [selected, setSelected] = useState<any>(null);
  const { getToken } = useTokenStorage(userId);
  const { start, updates, pct, result, error, reset, isLoading } = useSSEStream<any>("/tickets/fix");
  const scan = useSSEStream<any>("/tickets/scan-sprint");

  useEffect(() => {
    const id = localStorage.getItem("jessie_user_id") ?? "anon";
    setUserId(id);
    const ws = localStorage.getItem("jessie_workspace_id") ?? "web";
    const base = process.env.NEXT_PUBLIC_JESSIE_API ?? "http://localhost:8000";
    fetch(`${base}/tickets/board/${ws}`)
      .then(r => r.json())
      .then(setBoard)
      .catch(() => setBoard({
        empty: true,
        message: "No sprint scanned yet. Click Scan Sprint to analyse your current board.",
      }));
  }, []);

  async function scanSprint() {
    const ws = localStorage.getItem("jessie_workspace_id") ?? "web";
    await scan.start({
      platform: localStorage.getItem("jessie_ticket_platform") ?? "github",
      token: getToken("tickets_github") || getToken("Claude") || "test",
      workspace_id: ws,
      user_id: userId,
      claude_api_key: getToken("Claude"),
      mock_tickets: [
        { id: "DEMO#1", title: "Fix login 500 KeyError email", description: "KeyError email on login", label: "bug", priority: "high" },
        { id: "DEMO#2", title: "Add unit test for auth", description: "missing unit test", label: "task", priority: "medium" },
        { id: "DEMO#3", title: "Dark mode redesign", description: "needs design approval ".repeat(40), label: "feature", priority: "low" },
      ],
    }, {
      onComplete: (r) => setBoard({ ...(r as any), empty: false }),
    });
  }

  async function fixTicket(t: any) {
    setSelected(t);
    reset();
    const ws = localStorage.getItem("jessie_workspace_id") ?? "web";
    await start({
      ticket_id: t.id,
      platform: "github",
      platform_token: "test",
      workspace_id: ws,
      workspace_path: ".",
      user_id: userId,
      claude_api_key: getToken("Claude"),
      mock_ticket: t,
    });
  }

  const list =
    tab === "auto" ? board?.auto_fixable ?? [] :
    tab === "assist" ? board?.ai_assist ?? [] :
    board?.human_only ?? [];

  return (
    <div className="max-w-6xl grid md:grid-cols-2 gap-6">
      <div className="rounded-xl border dark:border-gray-700 bg-white dark:bg-gray-900 p-5 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold">Ticket Board</h1>
            <p className="text-sm text-gray-500">{board?.sprint || board?.sprint_name || "No active sprint"}</p>
          </div>
          <button onClick={scanSprint} className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm">
            {scan.isLoading ? "Scanning…" : "Scan Sprint"}
          </button>
        </div>

        {board?.health && (
          <div className="text-sm">Health: <b>{board.health.health_grade}</b> ({board.health.health_score}/100)
            {board.health.at_risk ? <span className="text-amber-600 ml-2">At risk</span> : null}
          </div>
        )}

        {board?.empty !== false && (!board?.auto_fixable && !board?.classified) ? (
          <p className="text-sm text-gray-500 border border-dashed dark:border-gray-700 rounded-lg p-6 text-center">
            {board?.message || "No sprint scanned yet. Click Scan Sprint to analyse your current board."}
          </p>
        ) : (
          <>
            <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 p-1 rounded-lg">
              {(["auto", "assist", "human"] as const).map(t => (
                <button key={t} onClick={() => setTab(t)}
                  className={`flex-1 text-xs py-1.5 rounded-md ${tab === t ? "bg-white dark:bg-gray-700 shadow" : "text-gray-500"}`}>
                  {t === "auto" ? "Can fix" : t === "assist" ? "Needs help" : "Human only"}
                </button>
              ))}
            </div>
            <div className="space-y-2 max-h-[28rem] overflow-auto">
              {list.map((t: any) => (
                <div key={t.id} className="border dark:border-gray-700 rounded-lg p-3 text-sm">
                  <div className="flex justify-between gap-2">
                    <div>
                      <span className="font-mono text-xs text-indigo-600">{t.id}</span>
                      <p className="font-medium">{t.title}</p>
                      <p className="text-xs text-gray-500">{t.category} · {t.confidence ?? "—"}%</p>
                    </div>
                    {tab === "auto" && (
                      <button onClick={() => fixTicket(t)} className="shrink-0 px-2 py-1 rounded bg-indigo-600 text-white text-xs">
                        Fix with Jessie
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {!list.length && <p className="text-xs text-gray-400">No tickets in this bucket.</p>}
            </div>
          </>
        )}
      </div>

      <div className="rounded-xl border dark:border-gray-700 bg-white dark:bg-gray-900 p-5 space-y-3">
        <h2 className="font-semibold">Fix progress / results</h2>
        {!selected && !isLoading && !result && (
          <p className="text-sm text-gray-500">Select a ticket to fix.</p>
        )}
        {(isLoading || updates.length > 0) && (
          <div className="space-y-1 text-sm">
            <div className="h-2 rounded bg-gray-100 dark:bg-gray-800 overflow-hidden">
              <div className="h-full bg-indigo-500 transition-all" style={{ width: `${pct}%` }} />
            </div>
            {updates.slice(-6).map((u, i) => (
              <p key={i} className="text-xs text-gray-600 dark:text-gray-300">
                {typeof u === "string" ? u : (u as { message?: string }).message || ""}
              </p>
            ))}
          </div>
        )}
        {error && <p className="text-sm text-red-600">{error}</p>}
        {result && (
          <div className="text-sm space-y-2">
            <p>Quality: <b>{result.quality_score}/100</b></p>
            {result.pr_url && <a className="text-indigo-600 underline" href={result.pr_url} target="_blank" rel="noreferrer">Open PR</a>}
            {result.git_error && <p className="text-amber-700 text-xs">{result.git_error}</p>}
            <p className="text-xs text-gray-500">{result.explanation}</p>
            <ul className="text-xs list-disc pl-4">
              {(result.files_changed || []).map((f: string) => <li key={f}>{f}</li>)}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
