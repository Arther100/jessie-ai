// Jessie design system — colours, grades, severity styles
// Palette: teal / indigo / amber (readable in dark + light)

export const VERDICT_STYLES = {
  safe: {
    bg: "#ECFDF5", border: "#059669", text: "#064E3B",
    emoji: "✅", label: "Safe to merge",
  },
  merge_with_fixes: {
    bg: "#FFFBEB", border: "#D97706", text: "#78350F",
    emoji: "⚠️", label: "Merge with fixes",
  },
  fix: {
    bg: "#FFFBEB", border: "#D97706", text: "#78350F",
    emoji: "⚠️", label: "Merge with fixes",
  },
  do_not_merge: {
    bg: "#FFF1F2", border: "#E11D48", text: "#881337",
    emoji: "🚫", label: "Do not merge",
  },
  danger: {
    bg: "#FFF1F2", border: "#E11D48", text: "#881337",
    emoji: "🚫", label: "Do not merge",
  },
} as const;

export const GRADE_STYLES: Record<string, { color: string; label: string; letter: string; track: string }> = {
  A: { color: "#059669", label: "Excellent",     letter: "A", track: "#A7F3D0" },
  B: { color: "#0D9488", label: "Good",           letter: "B", track: "#99F6E4" },
  C: { color: "#D97706", label: "Needs work",     letter: "C", track: "#FDE68A" },
  D: { color: "#EA580C", label: "Poor",           letter: "D", track: "#FED7AA" },
  F: { color: "#E11D48", label: "Critical",       letter: "F", track: "#FECDD3" },
  N: { color: "#64748B", label: "Not scored",     letter: "—", track: "#E2E8F0" },
};

export const SEVERITY_STYLES: Record<string, { bg: string; text: string; emoji: string }> = {
  critical: { bg: "#E11D48", text: "#FFF1F2", emoji: "🔴" },
  high:     { bg: "#EA580C", text: "#FFF7ED", emoji: "🟠" },
  medium:   { bg: "#D97706", text: "#FFFBEB", emoji: "🟡" },
  low:      { bg: "#059669", text: "#ECFDF5", emoji: "🟢" },
  missing:  { bg: "#6366F1", text: "#EEF2FF", emoji: "❓" },
  info:     { bg: "#0EA5E9", text: "#E0F2FE", emoji: "ℹ️"  },
};

/** Grade for a numeric score. Pass `scored=false` when that layer had no files / no analysis. */
export function getGrade(score: number, scored = true): { letter: string; color: string; label: string; track: string } {
  if (!scored) return { ...GRADE_STYLES.N };
  if (score >= 90) return { ...GRADE_STYLES.A };
  if (score >= 80) return { ...GRADE_STYLES.B };
  if (score >= 70) return { ...GRADE_STYLES.C };
  if (score >= 60) return { ...GRADE_STYLES.D };
  return { ...GRADE_STYLES.F };
}

export function getSeverityStyle(severity: string) {
  return SEVERITY_STYLES[severity.toLowerCase()] ?? SEVERITY_STYLES.info;
}

export function getVerdictStyle(verdict: string) {
  const key = verdict.toLowerCase().replace(/ /g, "_") as keyof typeof VERDICT_STYLES;
  return VERDICT_STYLES[key] ?? VERDICT_STYLES.merge_with_fixes;
}

export function scoreToBar(score: number): string {
  const filled = Math.round(score / 10);
  return "█".repeat(filled) + "░".repeat(10 - filled);
}
