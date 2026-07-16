"use client";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useDashboardStats, useTeamUsage } from "@/hooks/useReviews";
import { StatsRow } from "@/components/dashboard/StatsRow";
import { TeamTable } from "@/components/dashboard/TeamTable";
import { RecentReviews } from "@/components/dashboard/RecentReviews";
import { Loader2 } from "lucide-react";

const ScoreChart = dynamic(
  () => import("@/components/dashboard/ScoreChart").then(m => ({ default: m.ScoreChart })),
  {
    loading: () => <div className="h-48 rounded-lg bg-gray-100 dark:bg-gray-800/70 animate-pulse" />,
    ssr: false,
  },
);

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading, error: statsError } = useDashboardStats();
  const { data: usageData, isLoading: usageLoading } = useTeamUsage();

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Team code quality overview</p>
        </div>
        <div className="flex gap-3">
          <Link href="/review" className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium transition-colors">
            Run Code Review
          </Link>
          <Link href="/merge" className="px-4 py-2 rounded-lg border dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 text-sm font-medium transition-colors">
            Run Merge Review
          </Link>
        </div>
      </div>

      {statsLoading ? (
        <div className="flex items-center gap-2 text-gray-400"><Loader2 size={16} className="animate-spin" /> Loading stats...</div>
      ) : statsError ? (
        <div className="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950 p-4 text-sm text-amber-700 dark:text-amber-300">
          ⚠️ Could not reach Jessie backend at <code className="font-mono">{process.env.NEXT_PUBLIC_JESSIE_API}</code>. Start it with <code className="font-mono">cd backend && uvicorn api.main:app --reload</code>
        </div>
      ) : (
        <StatsRow
          reviewsThisWeek={stats?.reviews_this_week ?? 0}
          avgScore={Math.round(stats?.avg_score_this_week ?? 0)}
          criticalIssues={stats?.critical_issues_this_week ?? 0}
          activeMembersToday={stats?.active_members_today ?? 0}
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-8">
          <section>
            <h2 className="text-lg font-semibold mb-4">Score Trend (30 days)</h2>
            <div className="rounded-xl border dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
              <ScoreChart data={stats?.score_trend ?? []} />
            </div>
          </section>

          <section>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Recent Reviews</h2>
              <Link href="/history" className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline">View all →</Link>
            </div>
            <RecentReviews reviews={stats?.recent_reviews ?? []} />
          </section>
        </div>

        <div className="space-y-6">
          <section>
            <h2 className="text-lg font-semibold mb-4">Team Usage Today</h2>
            {usageLoading
              ? <div className="flex items-center gap-2 text-gray-400 text-sm"><Loader2 size={14} className="animate-spin" /> Loading...</div>
              : <TeamTable members={usageData?.usage ?? []} />
            }
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-4">Quick actions</h2>
            <div className="space-y-2">
              {[
                { href: "/review",   label: "🔍 Run Code Review"  },
                { href: "/merge",    label: "🔀 Run Merge Review"  },
                { href: "/history",  label: "📋 View All History"  },
                { href: "/settings", label: "⚙️  Settings"          },
              ].map(({ href, label }) => (
                <Link key={href} href={href}
                  className="block px-4 py-3 rounded-lg border dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 text-sm font-medium transition-colors">
                  {label}
                </Link>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
