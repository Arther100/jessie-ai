import Link from "next/link";
import { ScoreRing } from "@/components/ui/ScoreRing";
import { SeverityBadge } from "@/components/ui/SeverityBadge";
import { RecentReview } from "@/lib/api";
import { formatDate } from "@/lib/utils";

interface Props { reviews: RecentReview[] }

export function RecentReviews({ reviews }: Props) {
  if (!reviews.length) return (
    <div className="text-center py-12 text-gray-500 dark:text-gray-400">
      <p className="text-2xl mb-2">📋</p>
      <p>No reviews yet. Run your first review above.</p>
    </div>
  );

  return (
    <div className="overflow-x-auto rounded-xl border dark:border-gray-700">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="bg-gray-50 dark:bg-gray-800 text-xs uppercase text-gray-500 dark:text-gray-400 tracking-wide">
            <th className="px-4 py-3 text-left">Type</th>
            <th className="px-4 py-3 text-left">Project</th>
            <th className="px-4 py-3 text-left">Score</th>
            <th className="px-4 py-3 text-left">Issues</th>
            <th className="px-4 py-3 text-left">Date</th>
            <th className="px-4 py-3 text-left"></th>
          </tr>
        </thead>
        <tbody className="divide-y dark:divide-gray-700">
          {reviews.map(r => (
            <tr key={`${r.type}-${r.id}`} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
              <td className="px-4 py-3">
                <span className="text-base">{r.type === "code_review" ? "🔍" : "🔀"}</span>
              </td>
              <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{r.project}</td>
              <td className="px-4 py-3">
                <ScoreRing score={r.overall_score} size={40} showGrade={false} />
              </td>
              <td className="px-4 py-3">
                {r.critical_count > 0
                  ? <SeverityBadge severity="critical" count={r.critical_count} />
                  : <span className="text-gray-400 text-xs">{r.total_issues} issues</span>
                }
              </td>
              <td className="px-4 py-3 text-gray-500">{formatDate(r.date)}</td>
              <td className="px-4 py-3">
                <Link
                  href={`/reports/${r.id}`}
                  className="text-indigo-600 dark:text-indigo-400 hover:underline text-xs font-medium"
                >
                  View report →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
