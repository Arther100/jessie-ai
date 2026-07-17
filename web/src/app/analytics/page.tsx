"use client";
import { useEffect, useState } from "react";

export default function AnalyticsPage() {
  const [metrics, setMetrics] = useState<any>(null);
  const [insights, setInsights] = useState<string[]>([]);
  const apiBase = process.env.NEXT_PUBLIC_JESSIE_API ?? "http://localhost:8000";

  useEffect(() => {
    const ws = localStorage.getItem("jessie_workspace_id") ?? "web";
    fetch(`${apiBase}/analytics/team/${ws}`).then(r => r.json()).then(setMetrics);
    fetch(`${apiBase}/analytics/insights/${ws}`).then(r => r.json()).then(d => setInsights(d.insights || []));
  }, [apiBase]);

  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-bold">Team Analytics</h1>
      <div className="grid sm:grid-cols-4 gap-3">
        {[
          ["Tickets fixed", metrics?.total_tickets_fixed],
          ["Hours saved", metrics?.time_saved_hours],
          ["Avg quality", metrics?.avg_quality_score],
          ["Cost / ticket", metrics?.cost_per_ticket],
        ].map(([label, val]) => (
          <div key={String(label)} className="rounded-xl border dark:border-gray-700 p-4">
            <p className="text-xs text-gray-500">{label}</p>
            <p className="text-2xl font-semibold">{val ?? "—"}</p>
          </div>
        ))}
      </div>
      <div className="space-y-2">
        <h2 className="font-semibold">Insights</h2>
        {insights.map(i => (
          <div key={i} className="rounded-lg border dark:border-gray-700 p-3 text-sm">{i}</div>
        ))}
        {!insights.length && <p className="text-sm text-gray-500">No insights yet — run ticket fixes / sprint scans first.</p>}
      </div>
      <div className="rounded-xl border dark:border-gray-700 p-4">
        <h2 className="font-semibold mb-2">Top contributors</h2>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-gray-500"><th>Member</th><th>Tickets</th></tr></thead>
          <tbody>
            {(metrics?.top_contributors || []).map((m: any) => (
              <tr key={m.user_id} className="border-t dark:border-gray-800"><td className="py-2">{m.user_id}</td><td>{m.tickets}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
