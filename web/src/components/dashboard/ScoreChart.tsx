"use client";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from "recharts";
import { ScoreTrendPoint } from "@/lib/api";

interface Props { data: ScoreTrendPoint[] }

export function ScoreChart({ data }: Props) {
  if (!data.length) return (
    <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
      Not enough review history to show a trend yet.
    </div>
  );
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
        <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
        <Tooltip />
        <Legend />
        <Line type="monotone" dataKey="avg_score" stroke="#6366f1" name="Overall" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="frontend"  stroke="#3B6D11" name="Frontend" strokeWidth={1.5} dot={false} />
        <Line type="monotone" dataKey="backend"   stroke="#185FA5" name="Backend"  strokeWidth={1.5} dot={false} />
        <Line type="monotone" dataKey="database"  stroke="#854F0B" name="Database" strokeWidth={1.5} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
