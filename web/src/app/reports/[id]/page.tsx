"use client";
import { use } from "react";
import { useReport } from "@/hooks/useReviews";
import { ReportMarkdown } from "@/components/ui/ReportMarkdown";
import { ScoreRing } from "@/components/ui/ScoreRing";
import { SeverityBadge } from "@/components/ui/SeverityBadge";
import { VerdictBanner } from "@/components/ui/VerdictBanner";
import { Loader2, Download } from "lucide-react";
import { formatDate, formatCost } from "@/lib/utils";

export default function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, isLoading, error } = useReport(id);

  if (isLoading) return (
    <div className="flex items-center gap-3 py-20 justify-center text-gray-400">
      <Loader2 className="animate-spin" size={20} /> Loading report...
    </div>
  );

  if (error || !data) return (
    <div className="max-w-xl mx-auto py-20 text-center">
      <p className="text-4xl mb-4">📋</p>
      <h1 className="text-xl font-bold text-gray-700 dark:text-gray-300">Report not found</h1>
      <p className="text-sm text-gray-500 mt-2">
        No review with ID <code className="font-mono">{id}</code> exists in the database.
      </p>
    </div>
  );

  const meta   = data.metadata as Record<string, unknown>;
  const type   = data.type;
  const isCode = type === "code_review";

  const overall  = (meta.overall_score  as number) ?? 0;
  const fe       = (meta.frontend_score as number) ?? 0;
  const be       = (meta.backend_score  as number) ?? 0;
  const db       = (meta.db_score       as number) ?? 0;
  const critical = (meta.critical_count as number) ?? 0;
  const high     = (meta.high_count     as number) ?? 0;
  const medium   = (meta.medium_count   as number) ?? 0;
  const low      = (meta.low_count      as number) ?? 0;
  const verdict  = (meta.verdict        as string) ?? "";
  const date     = (meta.date           as string) ?? "";
  const cost     = (meta.cost_estimate  as number) ?? 0;

  return (
    <div className="flex gap-6 max-w-screen-xl">
      {/* Sticky sidebar */}
      <aside className="hidden lg:flex flex-col gap-5 w-56 shrink-0 sticky top-20 self-start">
        <div className="rounded-xl border dark:border-gray-700 bg-white dark:bg-gray-900 p-4 space-y-3">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            {isCode ? "Code Review" : "Merge Review"}
          </p>
          {date && <p className="text-xs text-gray-400">{formatDate(date)}</p>}
          {cost > 0 && <p className="text-xs text-gray-400">Cost {formatCost(cost)}</p>}

          <div className="flex flex-col items-center gap-2 py-2">
            <ScoreRing score={overall} size={80} />
            <p className="text-xs text-gray-500">Overall</p>
          </div>

          {isCode && (
            <div className="space-y-2">
              {[{ label: "Frontend", score: fe }, { label: "Backend", score: be }, { label: "Database", score: db }].map(({ label, score }) => (
                <div key={label} className="flex items-center justify-between text-xs">
                  <span className="text-gray-500">{label}</span>
                  <ScoreRing score={score} size={36} showGrade={false} />
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-wrap gap-1">
            {critical > 0 && <SeverityBadge severity="critical" count={critical} />}
            {high > 0     && <SeverityBadge severity="high"     count={high}     />}
            {medium > 0   && <SeverityBadge severity="medium"   count={medium}   />}
            {low > 0      && <SeverityBadge severity="low"      count={low}      />}
          </div>

          <a
            href={`/api/report-proxy?id=${id}`}
            download={`jessie-report-${id}.md`}
            className="flex items-center gap-2 w-full justify-center px-3 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium"
          >
            <Download size={12} /> Download .md
          </a>
        </div>

        <nav className="rounded-xl border dark:border-gray-700 bg-white dark:bg-gray-900 p-4 space-y-1">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Jump to</p>
          {["Verdict", "Frontend", "Backend", "Database", "Priority Fixes", "Checklist"].map(s => (
            <a key={s} href={`#${s.toLowerCase().replace(/ /g, "-")}`}
              className="block text-sm text-indigo-600 dark:text-indigo-400 hover:underline py-0.5">
              → {s}
            </a>
          ))}
        </nav>
      </aside>

      {/* Main content */}
      <div className="flex-1 min-w-0">
        {verdict && (
          <div className="mb-6" id="verdict">
            <VerdictBanner verdict={verdict} />
          </div>
        )}
        <div className="rounded-xl border dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
          <ReportMarkdown content={data.markdown_content} />
        </div>
      </div>
    </div>
  );
}
