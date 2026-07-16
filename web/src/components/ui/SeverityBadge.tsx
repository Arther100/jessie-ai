import { getSeverityStyle } from "@/lib/design";

interface Props {
  severity: string;
  count?: number;
}

export function SeverityBadge({ severity, count }: Props) {
  const s = getSeverityStyle(severity);
  const label = severity.charAt(0).toUpperCase() + severity.slice(1);
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold"
      style={{ backgroundColor: s.bg, color: s.text }}
    >
      <span>{s.emoji}</span>
      {count !== undefined ? `${count} ` : ""}
      {label}
    </span>
  );
}
