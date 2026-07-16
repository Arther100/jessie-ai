import { getVerdictStyle } from "@/lib/design";

interface Props {
  verdict: string;
  reason?: string;
}

export function VerdictBanner({ verdict, reason }: Props) {
  const s = getVerdictStyle(verdict);
  return (
    <div
      className="w-full rounded-xl border-2 px-5 py-4"
      style={{ backgroundColor: s.bg, borderColor: s.border }}
    >
      <div className="flex items-center gap-2">
        <span className="text-2xl">{s.emoji}</span>
        <span className="text-lg font-bold" style={{ color: s.text }}>
          {s.label}
        </span>
      </div>
      {reason && (
        <p className="mt-1 text-sm" style={{ color: s.text }}>
          {reason}
        </p>
      )}
    </div>
  );
}
