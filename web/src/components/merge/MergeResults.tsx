"use client";
import { useMemo, useState } from "react";
import { Download, Share2, RotateCcw, FileText } from "lucide-react";
import {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType,
} from "docx";
import { VerdictBanner } from "@/components/ui/VerdictBanner";
import { SeverityBadge } from "@/components/ui/SeverityBadge";
import { IssueCard, Issue } from "@/components/ui/IssueCard";
import { DiffViewer } from "./DiffViewer";

export interface MergeCompleteEvent {
  verdict: string;
  overall_score: number;
  grade: string;
  total_issues: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  missing_count: number;
  report_path: string;
  duration_seconds: number;
  files_changed: number;
  lines_added: number;
  lines_removed: number;
  commits_count: number;
  new_files: number;
  deleted_files: number;
  comments_posted: number;
  issues?: Issue[];
  missing_items?: Issue[];
  diff_files?: unknown[];
  commits?: { sha: string; message: string; author: string; date: string }[];
  suggested_reviewers?: { name: string; reason: string }[];
  metadata?: Record<string, unknown>;
  change_summary?: {
    overview_text?: string;
    areas?: { name: string; explanation: string; files: string[]; added: number; removed: number }[];
    has_login_auth?: boolean;
    has_ui?: boolean;
    has_api?: boolean;
  };
  impact_analysis?: {
    summary?: string;
    ui_changes?: { title: string; detail: string; files?: string[]; severity?: string }[];
    functionality_changes?: { title: string; detail: string; files?: string[]; severity?: string }[];
    expected_issues?: { title: string; detail: string; why?: string; how_to_verify?: string; severity?: string; files?: string[] }[];
    test_checklist?: string[];
    recommendation?: string;
    model?: string;
    error?: string;
  };
}

interface DiffFile {
  filename: string;
  status: "added" | "modified" | "deleted" | "renamed";
  added: number;
  removed: number;
  patch?: string;
  previous_content?: string;
  new_content?: string;
}

interface Props {
  result: MergeCompleteEvent;
  onReset: () => void;
}

function buildMarkdown(result: MergeCompleteEvent, diffs: DiffFile[], issues: Issue[], missing: Issue[]): string {
  const meta = result.metadata ?? {};
  const impact = result.impact_analysis;
  const lines = [
    "# Jessie Merge Review",
    "",
    `Verdict: ${result.verdict}`,
    `Score: ${result.overall_score} (${result.grade})`,
    `Files changed: ${result.files_changed}`,
    `Lines: +${result.lines_added} / -${result.lines_removed}`,
    `Base: ${meta.base_branch ?? "-"}`,
    `Head: ${meta.head_branch ?? "-"}`,
    "",
    "## Claude Impact Analysis",
    impact?.summary || "No Claude summary available.",
    "",
    "### UI changes users will notice",
  ];
  for (const item of impact?.ui_changes ?? []) {
    lines.push(`- **${item.title}** (${item.severity ?? "medium"}): ${item.detail}`);
    if (item.files?.length) lines.push(`  - Files: ${item.files.join(", ")}`);
  }
  lines.push("", "### Functionality / behaviour changes");
  for (const item of impact?.functionality_changes ?? []) {
    lines.push(`- **${item.title}** (${item.severity ?? "medium"}): ${item.detail}`);
    if (item.files?.length) lines.push(`  - Files: ${item.files.join(", ")}`);
  }
  lines.push("", "### Issues you may face");
  for (const item of impact?.expected_issues ?? []) {
    lines.push(`- **${item.title}** (${item.severity ?? "medium"})`);
    lines.push(`  - What: ${item.detail}`);
    if (item.why) lines.push(`  - Why: ${item.why}`);
    if (item.how_to_verify) lines.push(`  - Verify: ${item.how_to_verify}`);
    if (item.files?.length) lines.push(`  - Files: ${item.files.join(", ")}`);
  }
  lines.push("", "### Test checklist");
  for (const check of impact?.test_checklist ?? []) lines.push(`- [ ] ${check}`);
  lines.push("", "## Risks (titles only — no code)");
  for (const issue of issues) {
    lines.push(`### [${(issue.severity || "info").toUpperCase()}] ${issue.title}`);
    lines.push(issue.detail || issue.description || "");
    if (issue.fix || issue.suggestion) lines.push(`Fix: ${issue.fix || issue.suggestion}`);
    const files = issue.related_files?.length
      ? issue.related_files
      : issue.file && issue.file !== "merge" ? [issue.file] : [];
    if (files.length) lines.push(`Files: ${files.join(", ")}`);
    lines.push("");
  }
  lines.push("## Missing (no code)");
  for (const issue of missing) {
    lines.push(`### ${issue.title}`);
    lines.push(issue.detail || issue.description || "");
    const files = issue.related_files?.length
      ? issue.related_files
      : issue.file && issue.file !== "merge" ? [issue.file] : [];
    if (files.length) lines.push(`Files: ${files.join(", ")}`);
    lines.push("");
  }
  lines.push("## Changed files (names only)");
  for (const f of diffs) {
    lines.push(`- \`${f.filename}\` (${f.status}) +${f.added} -${f.removed}`);
  }
  return lines.join("\n");
}

function heading(text: string, level: typeof HeadingLevel[keyof typeof HeadingLevel] = HeadingLevel.HEADING_1) {
  return new Paragraph({
    text,
    heading: level,
    spacing: { before: 280, after: 120 },
  });
}

function body(text: string, opts?: { bold?: boolean; italics?: boolean; color?: string }) {
  return new Paragraph({
    spacing: { after: 80 },
    children: [
      new TextRun({
        text,
        bold: opts?.bold,
        italics: opts?.italics,
        color: opts?.color,
        size: 20,
        font: "Calibri",
      }),
    ],
  });
}

function bullet(text: string) {
  return new Paragraph({
    spacing: { after: 60 },
    bullet: { level: 0 },
    children: [new TextRun({ text, size: 20, font: "Calibri" })],
  });
}

const SEVERITY_DOC: Record<string, { label: string; color: string }> = {
  critical: { label: "Critical", color: "501313" },
  high:     { label: "High",     color: "A32D2D" },
  medium:   { label: "Medium",   color: "854F0B" },
  low:      { label: "Low",      color: "3B6D11" },
  missing:  { label: "Missing",  color: "534AB7" },
  info:     { label: "Info",     color: "185FA5" },
};

function severityStyle(raw?: string) {
  const key = (raw || "medium").toLowerCase();
  return SEVERITY_DOC[key] ?? SEVERITY_DOC.medium;
}

/** Card-style block matching Impact tab: High/Medium/Low + title + detail + files */
function impactCard(opts: {
  title: string;
  detail: string;
  severity?: string;
  files?: string[];
  extra?: string[];
}): Table {
  const sev = severityStyle(opts.severity);
  const border = { style: BorderStyle.SINGLE, size: 8, color: "CBD5E1" };
  const borders = { top: border, bottom: border, left: border, right: border };

  const cardParas: Paragraph[] = [
    new Paragraph({
      spacing: { after: 80 },
      children: [
        new TextRun({
          text: `● ${sev.label}`,
          bold: true,
          size: 18,
          font: "Calibri",
          color: sev.color,
        }),
        new TextRun({ text: "   ", size: 18 }),
        new TextRun({
          text: opts.title,
          bold: true,
          size: 22,
          font: "Calibri",
          color: "0F172A",
        }),
      ],
    }),
    new Paragraph({
      spacing: { after: 100 },
      children: [
        new TextRun({
          text: opts.detail || "",
          size: 20,
          font: "Calibri",
          color: "334155",
        }),
      ],
    }),
  ];

  for (const line of opts.extra ?? []) {
    if (!line) continue;
    cardParas.push(new Paragraph({
      spacing: { after: 60 },
      children: [
        new TextRun({ text: line, size: 18, font: "Calibri", color: "475569", italics: true }),
      ],
    }));
  }

  if (opts.files?.length) {
    cardParas.push(new Paragraph({
      spacing: { before: 60, after: 40 },
      children: [
        new TextRun({ text: "Related files:", bold: true, size: 18, font: "Calibri", color: "64748B" }),
      ],
    }));
    for (const f of opts.files) {
      const name = f.split("/").pop() || f;
      cardParas.push(new Paragraph({
        spacing: { after: 40 },
        children: [
          new TextRun({
            text: `  Open ${name}`,
            size: 18,
            font: "Calibri",
            color: "4F46E5",
          }),
          new TextRun({
            text: `  (${f})`,
            size: 16,
            font: "Calibri",
            color: "94A3B8",
          }),
        ],
      }));
    }
  }

  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    rows: [
      new TableRow({
        children: [
          new TableCell({
            borders,
            width: { size: 100, type: WidthType.PERCENTAGE },
            shading: { type: ShadingType.CLEAR, fill: "F8FAFC" },
            margins: { top: 80, bottom: 80, left: 120, right: 120 },
            children: cardParas,
          }),
        ],
      }),
    ],
  });
}

function spacerPara() {
  return new Paragraph({ spacing: { after: 120 }, children: [] });
}

/** Claude impact only — file paths, no source code / diffs. */
function buildImpactDocx(result: MergeCompleteEvent): Document {
  const meta = result.metadata ?? {};
  const impact = result.impact_analysis;
  const verdictLabel = String(result.verdict || "needs_changes").replace(/_/g, " ");
  const children: (Paragraph | Table)[] = [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 200 },
      children: [
        new TextRun({ text: "Jessie — Claude Impact Report", bold: true, size: 32, font: "Calibri" }),
      ],
    }),
    heading("Score & verdict (how to read)", HeadingLevel.HEADING_1),
    body(`Verdict: ${verdictLabel}`, { bold: true }),
    body(
      "Verdict is the merge recommendation. "
      + "approve = safe to merge after normal QA. "
      + "needs changes = fix or verify risks before merging.",
    ),
    body(`Score: ${result.overall_score} / 100  (Grade ${result.grade})`, { bold: true }),
    body(
      "Score is a merge-safety score from 0–100 (higher is safer). "
      + "It starts at 100 and drops when critical/high/medium/low risks are found "
      + "(critical −25, high −12, medium −5, low −2). "
      + "Grade: A ≥90, B ≥80, C ≥70, D ≥60, else F.",
    ),
    body(
      `Branches: ${meta.head_branch ?? "?"} → ${meta.base_branch ?? "?"}  |  `
      + `${result.files_changed} files  |  +${result.lines_added} / -${result.lines_removed}`,
    ),
    body(`Claude recommendation: ${impact?.recommendation || result.verdict}`, { bold: true }),
    heading("Summary", HeadingLevel.HEADING_1),
    body(impact?.summary || impact?.error || "No Claude summary available."),
    body("Severity legend: Critical · High · Medium · Low (same colours as the Impact tab)."),
  ];

  children.push(heading("UI changes users will notice", HeadingLevel.HEADING_1));
  const ui = impact?.ui_changes ?? [];
  if (!ui.length) {
    children.push(body("No clear UI changes detected.", { italics: true }));
  } else {
    for (const item of ui) {
      children.push(impactCard({
        title: item.title,
        detail: item.detail || "",
        severity: item.severity,
        files: item.files,
      }));
      children.push(spacerPara());
    }
  }

  children.push(heading("Functionality / behaviour changes", HeadingLevel.HEADING_1));
  const fn = impact?.functionality_changes ?? [];
  if (!fn.length) {
    children.push(body("No clear functionality changes detected.", { italics: true }));
  } else {
    for (const item of fn) {
      children.push(impactCard({
        title: item.title,
        detail: item.detail || "",
        severity: item.severity,
        files: item.files,
      }));
      children.push(spacerPara());
    }
  }

  children.push(heading("Issues you may face", HeadingLevel.HEADING_1));
  const issues = impact?.expected_issues ?? [];
  if (!issues.length) {
    children.push(body("No specific expected issues flagged.", { italics: true }));
  } else {
    for (const item of issues) {
      const extra = [
        item.why ? `Why: ${item.why}` : "",
        item.how_to_verify ? `Verify: ${item.how_to_verify}` : "",
      ].filter(Boolean);
      children.push(impactCard({
        title: item.title,
        detail: item.detail || "",
        severity: item.severity,
        files: item.files,
        extra,
      }));
      children.push(spacerPara());
    }
  }

  children.push(heading("Test checklist", HeadingLevel.HEADING_1));
  const checks = impact?.test_checklist ?? [];
  if (!checks.length) {
    children.push(body("No checklist returned.", { italics: true }));
  } else {
    for (const check of checks) children.push(bullet(check));
  }

  // Unique file list from impact items only (no patches/code)
  const fileSet = new Set<string>();
  for (const list of [ui, fn, issues]) {
    for (const item of list) {
      for (const f of item.files ?? []) if (f) fileSet.add(f);
    }
  }
  children.push(heading("Related files (names only)", HeadingLevel.HEADING_1));
  children.push(body("File paths referenced by Claude impact — no source code included.", { italics: true }));
  if (!fileSet.size) {
    children.push(body("No file paths attached to impact items.", { italics: true }));
  } else {
    for (const f of [...fileSet].sort()) children.push(bullet(f));
  }

  return new Document({
    sections: [{ properties: {}, children }],
  });
}

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function withCodeFromDiffs(issue: Issue, diffs: DiffFile[]): Issue {
  if (issue.code_snippet) return issue;
  const candidates = [
    ...(issue.related_files ?? []),
    ...(issue.file && issue.file !== "merge" ? [issue.file] : []),
  ];
  const matched = diffs.filter(d => candidates.includes(d.filename) && d.patch);
  const pool = matched.length
    ? matched
    : [...diffs].sort((a, b) => (b.added + b.removed) - (a.added + a.removed)).slice(0, 3);
  const snippets = pool
    .filter(d => d.patch)
    .slice(0, 3)
    .map(d => {
      const changed = (d.patch || "")
        .split("\n")
        .filter(l => (l.startsWith("+") || l.startsWith("-")) && !l.startsWith("+++") && !l.startsWith("---"))
        .slice(0, 40);
      return `--- ${d.filename} (+${d.added} / -${d.removed})\n${changed.join("\n")}`;
    });
  return {
    ...issue,
    related_files: pool.map(d => d.filename),
    code_snippet: snippets.join("\n\n"),
  };
}

export function MergeResults({ result, onReset }: Props) {
  const [tab, setTab] = useState<"risks" | "missing" | "diff" | "impact" | "commits">("impact");
  const [focusFile, setFocusFile] = useState<string | undefined>();

  const diffs = (result.diff_files as DiffFile[] | undefined) ?? [];
  const impact = result.impact_analysis;
  const issues = useMemo(
    () => (result.issues ?? []).map(i => withCodeFromDiffs(i, diffs)),
    [result.issues, diffs],
  );
  const missing = useMemo(
    () => (result.missing_items ?? []).map(i => withCodeFromDiffs(i, diffs)),
    [result.missing_items, diffs],
  );
  const commits = result.commits ?? [];
  const visibleDiffs = focusFile
    ? diffs.filter(d => d.filename === focusFile).concat(diffs.filter(d => d.filename !== focusFile))
    : diffs;

  function share() {
    navigator.clipboard.writeText(window.location.href);
    alert("Link copied!");
  }

  function downloadMarkdown() {
    const md = buildMarkdown(result, diffs, issues, missing);
    triggerBlobDownload(
      new Blob([md], { type: "text/markdown;charset=utf-8" }),
      "jessie-merge-review.md",
    );
  }

  async function downloadImpactDocx() {
    try {
      const doc = buildImpactDocx(result);
      const blob = await Packer.toBlob(doc);
      triggerBlobDownload(blob, "jessie-claude-impact.docx");
    } catch (err) {
      console.error(err);
      alert("Could not build Word document. Try Download .md instead.");
    }
  }

  function openInDiff(filename?: string) {
    setFocusFile(filename);
    setTab("diff");
  }

  const TABS = [
    { id: "risks",   label: `Risks (${issues.length})`   },
    { id: "missing", label: `Missing (${missing.length})` },
    { id: "diff",    label: `Diff (${diffs.length})`     },
    { id: "impact",  label: "Impact (Claude)"            },
    { id: "commits", label: `Commits (${commits.length})` },
  ] as const;

  return (
    <div className="space-y-6">
      <VerdictBanner verdict={result.verdict} />
      <p className="text-xs text-gray-500 -mt-3">
        <strong>Verdict</strong> = merge recommendation (approve / needs changes).{" "}
        <strong>Score {result.overall_score}/100 ({result.grade})</strong> = merge safety
        (starts at 100; drops for each risk found — higher is safer).
      </p>

      <div className="grid grid-cols-3 sm:grid-cols-6 gap-3 text-center">
        {[
          { label: "Files",    value: result.files_changed   },
          { label: "+Added",   value: result.lines_added     },
          { label: "−Removed", value: result.lines_removed   },
          { label: "New",      value: result.new_files       },
          { label: "Deleted",  value: result.deleted_files   },
          { label: "Commits",  value: result.commits_count   },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-lg border dark:border-gray-700 p-2">
            <p className="text-lg font-bold text-gray-900 dark:text-gray-100">{value ?? 0}</p>
            <p className="text-xs text-gray-400">{label}</p>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        <SeverityBadge severity="critical" count={result.critical_count} />
        <SeverityBadge severity="high"     count={result.high_count}     />
        <SeverityBadge severity="medium"   count={result.medium_count}   />
        <SeverityBadge severity="low"      count={result.low_count}      />
        <SeverityBadge severity="missing"  count={result.missing_count}  />
      </div>

      {result.comments_posted > 0 && (
        <p className="text-sm text-gray-600 dark:text-gray-400">
          💬 {result.comments_posted} comments posted to PR
        </p>
      )}

      <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 p-1 rounded-lg overflow-x-auto">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex-1 min-w-fit px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === t.id ? "bg-white dark:bg-gray-700 shadow-sm" : "text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "risks" && (
        <div className="space-y-1">
          <p className="text-xs text-gray-500 mb-2">
            Risks are generated from Claude impact analysis of the real diff.
          </p>
          {issues.length ? issues.map((iss, i) => (
            <IssueCard key={i} issue={iss} onOpenDiff={openInDiff} />
          )) : (
            <p className="text-sm text-gray-400 py-4">No risks found — great work!</p>
          )}
        </div>
      )}

      {tab === "missing" && (
        <div className="space-y-1">
          <p className="text-xs text-gray-500 mb-2">
            Real gaps in the PR (missing tests, error handling, config, QA evidence) — not the full QA checklist (see Impact).
          </p>
          {missing.length ? missing.map((iss, i) => (
            <IssueCard key={i} issue={iss} onOpenDiff={openInDiff} />
          )) : (
            <p className="text-sm text-gray-400 py-4">No missing items detected.</p>
          )}
        </div>
      )}

      {tab === "diff" && (
        <div className="space-y-2">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Click a file to expand. Use <strong>Diff</strong> / <strong>Previous</strong> / <strong>Current</strong> to inspect code.
            {focusFile ? <> Focusing: <code className="font-mono">{focusFile}</code></> : null}
          </p>
          <DiffViewer files={visibleDiffs} />
        </div>
      )}

      {tab === "impact" && (
        <div className="space-y-5">
          <div className="rounded-xl border dark:border-gray-700 bg-white dark:bg-gray-900 p-4 space-y-2">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold">Claude impact analysis</h2>
              {impact?.model && (
                <span className="text-[11px] text-gray-400 font-mono">{impact.model}</span>
              )}
            </div>
            <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
              {impact?.summary || impact?.error || "No Claude analysis yet. Re-run Merge Review."}
            </p>
          </div>

          <section className="space-y-2">
            <h3 className="text-sm font-semibold">UI changes users will notice</h3>
            {(impact?.ui_changes?.length ?? 0) === 0 ? (
              <p className="text-sm text-gray-400">No clear UI changes detected by Claude.</p>
            ) : (
              impact!.ui_changes!.map((item, i) => (
                <div key={i} className="rounded-lg border dark:border-gray-700 p-3 space-y-1">
                  <div className="flex items-center gap-2">
                    <SeverityBadge severity={item.severity || "medium"} />
                    <p className="text-sm font-medium">{item.title}</p>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-300">{item.detail}</p>
                  {!!item.files?.length && (
                    <div className="flex flex-wrap gap-2 pt-1">
                      {item.files.slice(0, 4).map(f => (
                        <button key={f} type="button" onClick={() => openInDiff(f)}
                          className="text-xs px-2 py-1 rounded border dark:border-gray-600 text-indigo-600 dark:text-indigo-300">
                          Open {f.split("/").pop()}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </section>

          <section className="space-y-2">
            <h3 className="text-sm font-semibold">Functionality / behaviour changes</h3>
            {(impact?.functionality_changes?.length ?? 0) === 0 ? (
              <p className="text-sm text-gray-400">No clear functionality changes detected by Claude.</p>
            ) : (
              impact!.functionality_changes!.map((item, i) => (
                <div key={i} className="rounded-lg border dark:border-gray-700 p-3 space-y-1">
                  <div className="flex items-center gap-2">
                    <SeverityBadge severity={item.severity || "medium"} />
                    <p className="text-sm font-medium">{item.title}</p>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-300">{item.detail}</p>
                  {!!item.files?.length && (
                    <div className="flex flex-wrap gap-2 pt-1">
                      {item.files.slice(0, 4).map(f => (
                        <button key={f} type="button" onClick={() => openInDiff(f)}
                          className="text-xs px-2 py-1 rounded border dark:border-gray-600 text-indigo-600 dark:text-indigo-300">
                          Open {f.split("/").pop()}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </section>

          <section className="space-y-2">
            <h3 className="text-sm font-semibold">Issues you may face</h3>
            {(impact?.expected_issues?.length ?? 0) === 0 ? (
              <p className="text-sm text-gray-400">Claude did not flag specific expected issues.</p>
            ) : (
              impact!.expected_issues!.map((item, i) => (
                <div key={i} className="rounded-lg border dark:border-gray-700 p-3 space-y-1">
                  <div className="flex items-center gap-2">
                    <SeverityBadge severity={item.severity || "medium"} />
                    <p className="text-sm font-medium">{item.title}</p>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-300">{item.detail}</p>
                  {item.why && <p className="text-xs text-gray-500"><strong>Why:</strong> {item.why}</p>}
                  {item.how_to_verify && (
                    <div className="rounded-md bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 p-2 text-xs text-green-700 dark:text-green-300">
                      <strong>Verify:</strong> {item.how_to_verify}
                    </div>
                  )}
                </div>
              ))
            )}
          </section>

          <section className="space-y-2">
            <h3 className="text-sm font-semibold">Test checklist</h3>
            {(impact?.test_checklist?.length ?? 0) === 0 ? (
              <p className="text-sm text-gray-400">No checklist returned.</p>
            ) : (
              <ul className="space-y-1">
                {impact!.test_checklist!.map((check, i) => (
                  <li key={i} className="text-sm text-gray-700 dark:text-gray-300 flex gap-2">
                    <span className="text-gray-400">☐</span>
                    <span>{check}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      {tab === "commits" && (
        <div className="overflow-x-auto rounded-xl border dark:border-gray-700">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-gray-50 dark:bg-gray-800 text-xs uppercase text-gray-500 tracking-wide">
                <th className="px-4 py-3 text-left">SHA</th>
                <th className="px-4 py-3 text-left">Message</th>
                <th className="px-4 py-3 text-left">Author</th>
                <th className="px-4 py-3 text-left">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y dark:divide-gray-700">
              {commits.map(c => (
                <tr key={c.sha}>
                  <td className="px-4 py-2 font-mono text-xs text-gray-400">{c.sha.slice(0, 7)}</td>
                  <td className="px-4 py-2">{c.message}</td>
                  <td className="px-4 py-2 text-gray-500">{c.author}</td>
                  <td className="px-4 py-2 text-gray-400 text-xs">{new Date(c.date).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {result.suggested_reviewers?.length ? (
        <div>
          <p className="text-sm font-medium mb-2 dark:text-gray-300">Suggested reviewers</p>
          <div className="flex flex-wrap gap-3">
            {result.suggested_reviewers.map(r => (
              <div key={r.name} className="flex items-center gap-2 rounded-full border dark:border-gray-600 px-3 py-1.5">
                <span className="w-7 h-7 rounded-full bg-indigo-100 dark:bg-indigo-900 flex items-center justify-center text-xs font-bold text-indigo-600 dark:text-indigo-300">
                  {r.name[0]?.toUpperCase()}
                </span>
                <div>
                  <p className="text-xs font-medium">{r.name}</p>
                  <p className="text-xs text-gray-400">{r.reason}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={downloadMarkdown}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium"
        >
          <Download size={14} /> Download .md
        </button>
        <button
          type="button"
          onClick={downloadImpactDocx}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium"
          title="Claude impact details + related file names only (no source code)"
        >
          <FileText size={14} /> Download Impact .docx
        </button>
        <button onClick={share}
          className="flex items-center gap-2 px-4 py-2 rounded-lg border dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 text-sm font-medium">
          <Share2 size={14} /> Share Report
        </button>
        <button onClick={onReset}
          className="flex items-center gap-2 px-4 py-2 rounded-lg border dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 text-sm font-medium">
          <RotateCcw size={14} /> New Review
        </button>
      </div>
    </div>
  );
}
