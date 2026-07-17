"use client";
import { useEffect, useState } from "react";

export default function SprintPage() {
  const [health, setHealth] = useState<any>(null);
  const [report, setReport] = useState("");
  const apiBase = process.env.NEXT_PUBLIC_JESSIE_API ?? "http://localhost:8000";

  async function refresh() {
    const ws = localStorage.getItem("jessie_workspace_id") ?? "web";
    const h = await fetch(`${apiBase}/sprint/health`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace_id: ws, platform: "github" }),
    }).then(r => r.json());
    setHealth(h);
    const rep = await fetch(`${apiBase}/sprint/weekly-report/${ws}`).then(r => r.json());
    setReport(rep.markdown || "");
  }

  useEffect(() => { refresh(); }, []);

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Sprint Health</h1>
        <button onClick={refresh} className="px-3 py-1.5 rounded-lg border text-sm">Generate fresh report</button>
      </div>
      {health?.empty ? (
        <p className="text-sm text-gray-500">{health.message}</p>
      ) : health ? (
        <div className="rounded-xl border p-6 space-y-3 dark:border-gray-700">
          <p className="text-4xl font-bold">{health.health_score ?? "—"}<span className="text-lg text-gray-500">/100 ({health.health_grade})</span></p>
          {health.at_risk && <p className="text-amber-700 bg-amber-50 dark:bg-amber-950 border border-amber-200 rounded-lg px-3 py-2 text-sm">Sprint at risk</p>}
          <p className="text-sm text-gray-500">{health.days_remaining} days left · {health.tickets_remaining} tickets remaining</p>
          <ul className="text-sm list-disc pl-5">
            {(health.recommendations || []).map((r: string) => <li key={r}>{r}</li>)}
          </ul>
        </div>
      ) : null}
      <div className="rounded-xl border p-6 dark:border-gray-700">
        <h2 className="font-semibold mb-3">Weekly report</h2>
        <pre className="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300">{report || "No report yet."}</pre>
      </div>
    </div>
  );
}
