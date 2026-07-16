import { getGrade } from "@/lib/design";

interface Props {
  score: number;
  label: string;
  showBar?: boolean;
  scored?: boolean;
}

export function ScoreBar({ score, label, showBar = true, scored = true }: Props) {
  const { color, letter, track } = getGrade(score, scored);
  return (
    <div className="flex items-center gap-3 py-1">
      <span className="w-28 text-sm text-gray-600 dark:text-gray-400 truncate">{label}</span>
      <span className="w-16 text-sm font-mono font-semibold" style={{ color }}>
        {scored ? `${score}/100` : "—"}
      </span>
      {showBar && (
        <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ backgroundColor: track }}>
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{ width: scored ? `${score}%` : "0%", backgroundColor: color }}
          />
        </div>
      )}
      <span
        className="w-6 text-xs font-bold text-center rounded px-1"
        style={{ color, border: `1px solid ${color}` }}
      >
        {letter}
      </span>
    </div>
  );
}
