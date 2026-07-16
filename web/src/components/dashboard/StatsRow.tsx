import { getGrade } from "@/lib/design";

interface Props {
  reviewsThisWeek: number;
  avgScore: number;
  criticalIssues: number;
  activeMembersToday: number;
}

function StatCard({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <div className="rounded-xl border dark:border-gray-700 bg-white dark:bg-gray-900 p-4 flex flex-col gap-1">
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p className="text-2xl font-bold" style={{ color: color ?? undefined }}>{value}</p>
      {sub && <p className="text-xs text-gray-400 dark:text-gray-500">{sub}</p>}
    </div>
  );
}

export function StatsRow({ reviewsThisWeek, avgScore, criticalIssues, activeMembersToday }: Props) {
  const { color } = getGrade(avgScore);
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <StatCard label="Reviews this week" value={reviewsThisWeek} sub="total reviews run" />
      <StatCard label="Average score" value={`${avgScore}/100`} sub="across all reviews" color={color} />
      <StatCard label="Critical issues" value={criticalIssues} sub="found this week" color={criticalIssues > 0 ? "#A32D2D" : undefined} />
      <StatCard label="Active today" value={activeMembersToday} sub="team members" />
    </div>
  );
}
