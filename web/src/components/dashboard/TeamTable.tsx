import { TeamMember } from "@/lib/api";

interface Props { members: TeamMember[] }

function pctColor(used: number, limit: number): string {
  const p = used / limit;
  if (p >= 0.9) return "text-red-600 dark:text-red-400";
  if (p >= 0.7) return "text-amber-600 dark:text-amber-400";
  return "text-green-600 dark:text-green-400";
}

export function TeamTable({ members }: Props) {
  if (!members.length) return (
    <p className="text-sm text-gray-500 py-4">No team members have used Jessie today yet.</p>
  );
  return (
    <div className="overflow-x-auto rounded-xl border dark:border-gray-700">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="bg-gray-50 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wide">
            <th className="px-4 py-3 text-left">Member</th>
            <th className="px-4 py-3 text-left">Requests today</th>
            <th className="px-4 py-3 text-left">Daily limit</th>
            <th className="px-4 py-3 text-left">Remaining</th>
          </tr>
        </thead>
        <tbody className="divide-y dark:divide-gray-700">
          {members.map(m => (
            <tr key={m.user_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
              <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{m.user_id}</td>
              <td className={`px-4 py-3 font-semibold ${pctColor(m.used, m.limit)}`}>{m.used}</td>
              <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{m.limit}</td>
              <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{m.remaining}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
