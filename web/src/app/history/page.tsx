"use client";
import { useState } from "react";
import Link from "next/link";
import { ScoreRing } from "@/components/ui/ScoreRing";
import { SeverityBadge } from "@/components/ui/SeverityBadge";
import { useReviewHistory } from "@/hooks/useReviews";
import { formatDate, formatCost, workspaceId } from "@/lib/utils";
import { Loader2, Download, Link as LinkIcon } from "lucide-react";

type FilterType = "all" | "code_review" | "merge_review";
type FilterGrade = "all" | "A" | "B" | "C" | "D" | "F";
function grade(s: number) {
  return s >= 90 ? "A" : s >= 80 ? "B" : s >= 70 ? "C" : s >= 60 ? "D" : "F";
}

const PAGE_SIZE = 20;

export default function HistoryPage() {
  const wsId = typeof window !== "undefined" ? workspaceId(window.location.pathname) : "";
  const { data = [], isLoading } = useReviewHistory(wsId);
  const [typeFilter, setType] = useState<FilterType>("all");
  const [gradeFilter, setGrd] = useState<FilterGrade>("all");
  const [page,    setPage]    = useState(0);

  const rows = data.map((r, i) => ({ ...r, id: i + 1, type: "code_review" as const }));

  const filtered = rows.filter(r => {
    if (typeFilter  !== "all" && r.type !== typeFilter)       return false;
    if (gradeFilter !== "all" && grade(r.overall_score) !== gradeFilter) return false;
    return true;
  });

  const paged    = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const total    = filtered.length;
  const avgScore = total ? Math.round(filtered.reduce((a, r) => a + r.overall_score, 0) / total) : 0;
  const totalCrit= filtered.reduce((a, r) => a + r.critical_count, 0);
  const totalCost= filtered.reduce((a, r) => a + r.cost_estimate, 0);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Review History</h1>

      {/* Summary */}
      {!isLoading && total > 0 && (
        <p className="text-sm text-gray-500">
          {total} reviews · avg score {avgScore}/100 · {totalCrit} critical issues · total cost {formatCost(totalCost)}
        </p>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select value={typeFilter} onChange={e => { setType(e.target.value as FilterType); setPage(0); }}
          className="rounded-lg border dark:border-gray-600 px-3 py-1.5 text-sm bg-white dark:bg-gray-800">
          <option value="all">All types</option>
          <option value="code_review">Code Review</option>
          <option value="merge_review">Merge Review</option>
        </select>
        <select value={gradeFilter} onChange={e => { setGrd(e.target.value as FilterGrade); setPage(0); }}
          className="rounded-lg border dark:border-gray-600 px-3 py-1.5 text-sm bg-white dark:bg-gray-800">
          <option value="all">All grades</option>
          {["A","B","C","D","F"].map(g => <option key={g} value={g}>{g}</option>)}
        </select>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-gray-400"><Loader2 size={16} className="animate-spin" /> Loading...</div>
      ) : paged.length === 0 ? (
        <div className="text-center py-20">
          <p className="text-2xl mb-2">📋</p>
          <p className="text-gray-500">No reviews found. Run your first review to see history here.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border dark:border-gray-700">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-gray-50 dark:bg-gray-800 text-xs uppercase text-gray-500 tracking-wide">
                <th className="px-4 py-3 text-left">Type</th>
                <th className="px-4 py-3 text-left">Date</th>
                <th className="px-4 py-3 text-left">Score</th>
                <th className="px-4 py-3 text-left">Issues</th>
                <th className="px-4 py-3 text-left">Cost</th>
                <th className="px-4 py-3 text-left">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y dark:divide-gray-700">
              {paged.map(r => (
                <tr key={r.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <td className="px-4 py-3">
                    <span>{r.type === "code_review" ? "🔍" : "🔀"}</span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">{formatDate(r.date)}</td>
                  <td className="px-4 py-3"><ScoreRing score={r.overall_score} size={40} showGrade={false} /></td>
                  <td className="px-4 py-3">
                    {r.critical_count > 0
                      ? <SeverityBadge severity="critical" count={r.critical_count} />
                      : <span className="text-gray-400">{r.total_issues}</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-500">{formatCost(r.cost_estimate)}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <Link href={`/reports/${r.id}`} className="text-indigo-600 dark:text-indigo-400 hover:underline text-xs">
                        View
                      </Link>
                      <a href={`/api/report-proxy?path=${encodeURIComponent(r.report_path)}`}
                        download className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                        <Download size={13} />
                      </a>
                      <button onClick={() => navigator.clipboard.writeText(`${window.location.origin}/reports/${r.id}`)}
                        className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                        <LinkIcon size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="flex items-center gap-3 justify-center">
          <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
            className="px-3 py-1.5 text-sm rounded-lg border dark:border-gray-600 disabled:opacity-40">
            ← Prev
          </button>
          <span className="text-sm text-gray-500">{page + 1} / {Math.ceil(total / PAGE_SIZE)}</span>
          <button onClick={() => setPage(p => Math.min(Math.ceil(total / PAGE_SIZE) - 1, p + 1))} disabled={(page + 1) * PAGE_SIZE >= total}
            className="px-3 py-1.5 text-sm rounded-lg border dark:border-gray-600 disabled:opacity-40">
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
