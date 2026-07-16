"use client";
import { useState } from "react";
import { Download, Share2, RotateCcw, FileText } from "lucide-react";
import {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType,
} from "docx";
import { ScoreRing } from "@/components/ui/ScoreRing";
import { ScoreBar } from "@/components/ui/ScoreBar";
import { SeverityBadge } from "@/components/ui/SeverityBadge";
import { IssueCard, Issue } from "@/components/ui/IssueCard";
import { getGrade } from "@/lib/design";

export interface CompleteEvent {
  overall_score: number;
  grade: string;
  frontend_score: number;
  backend_score: number;
  db_score: number;
  has_frontend?: boolean;
  has_backend?: boolean;
  has_database?: boolean;
  is_flutter?: boolean;
  total_issues: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  missing_count?: number;
  report_path: string;
  duration_seconds: number;
  total_files: number;
  tokens_used: number;
  cost_estimate: number;
  branch?: string;
  azure_url?: string;
  issues?: Issue[];
  missing_items?: Issue[];
  impact_analysis?: {
    summary?: string;
    must_change?: { severity?: string; title?: string; detail?: string; file?: string; fix?: string }[];
    missing?: { title?: string; detail?: string; file?: string }[] | string[];
    file_changes?: { file?: string; changes?: string[] }[];
    test_checklist?: string[];
    recommendation?: string;
    model?: string;
    error?: string;
  };
}

interface Props {
  result: CompleteEvent;
  onReset: () => void;
}

const SEV_COLOR: Record<string, string> = {
  critical: "501313",
  high: "A32D2D",
  medium: "854F0B",
  low: "3B6D11",
  missing: "534AB7",
};

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function buildImpactDocx(result: CompleteEvent): Document {
  const impact = result.impact_analysis;
  const children: (Paragraph | Table)[] = [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 200 },
      children: [new TextRun({ text: "Jessie — Code Review Impact", bold: true, size: 32, font: "Calibri" })],
    }),
    new Paragraph({
      spacing: { after: 80 },
      children: [new TextRun({
        text: `Score: ${result.overall_score}/100 (${result.grade})  ·  Files: ${result.total_files}  ·  Issues: ${result.total_issues}`,
        bold: true, size: 20, font: "Calibri",
      })],
    }),
    new Paragraph({
      spacing: { after: 160 },
      children: [new TextRun({
        text: impact?.summary || impact?.error || "No Claude impact summary.",
        size: 20, font: "Calibri",
      })],
    }),
  ];

  const border = { style: BorderStyle.SINGLE, size: 8, color: "CBD5E1" };
  const borders = { top: border, bottom: border, left: border, right: border };

  function card(title: string, detail: string, severity?: string, file?: string, fix?: string) {
    const color = SEV_COLOR[(severity || "medium").toLowerCase()] || SEV_COLOR.medium;
    const paras = [
      new Paragraph({
        spacing: { after: 60 },
        children: [
          new TextRun({ text: `● ${(severity || "medium")}`, bold: true, size: 18, color, font: "Calibri" }),
          new TextRun({ text: `   ${title}`, bold: true, size: 22, font: "Calibri" }),
        ],
      }),
      new Paragraph({
        spacing: { after: 60 },
        children: [new TextRun({ text: detail || "", size: 20, color: "334155", font: "Calibri" })],
      }),
    ];
    if (file) {
      paras.push(new Paragraph({
        spacing: { after: 40 },
        children: [new TextRun({ text: `File: ${file}`, size: 18, color: "4F46E5", font: "Calibri" })],
      }));
    }
    if (fix) {
      paras.push(new Paragraph({
        spacing: { after: 40 },
        children: [new TextRun({ text: `Fix: ${fix}`, italics: true, size: 18, color: "475569", font: "Calibri" })],
      }));
    }
    children.push(new Table({
      width: { size: 100, type: WidthType.PERCENTAGE },
      rows: [new TableRow({
        children: [new TableCell({
          borders,
          width: { size: 100, type: WidthType.PERCENTAGE },
          shading: { type: ShadingType.CLEAR, fill: "F8FAFC" },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: paras,
        })],
      })],
    }));
    children.push(new Paragraph({ spacing: { after: 100 }, children: [] }));
  }

  children.push(new Paragraph({ text: "What needs to change", heading: HeadingLevel.HEADING_1 }));
  const must = impact?.must_change ?? [];
  if (!must.length) {
    children.push(new Paragraph({
      children: [new TextRun({ text: "No must-change items from Claude.", italics: true, size: 20 })],
    }));
  } else {
    for (const item of must) {
      card(item.title || "Change", item.detail || "", item.severity, item.file, item.fix);
    }
  }

  children.push(new Paragraph({ text: "What is missing", heading: HeadingLevel.HEADING_1 }));
  const missing = impact?.missing ?? [];
  if (!missing.length) {
    children.push(new Paragraph({
      children: [new TextRun({ text: "No missing coverage flagged.", italics: true, size: 20 })],
    }));
  } else {
    for (const item of missing) {
      if (typeof item === "string") card("Coverage gap", item, "missing");
      else card(item.title || "Missing", item.detail || "", "missing", item.file);
    }
  }

  children.push(new Paragraph({ text: "File-by-file changes", heading: HeadingLevel.HEADING_1 }));
  for (const fc of impact?.file_changes ?? []) {
    children.push(new Paragraph({
      spacing: { before: 80, after: 40 },
      children: [new TextRun({ text: fc.file || "unknown", bold: true, size: 20, font: "Calibri" })],
    }));
    for (const ch of fc.changes ?? []) {
      children.push(new Paragraph({
        bullet: { level: 0 },
        children: [new TextRun({ text: ch, size: 20, font: "Calibri" })],
      }));
    }
  }

  children.push(new Paragraph({ text: "Test checklist", heading: HeadingLevel.HEADING_1 }));
  for (const c of impact?.test_checklist ?? []) {
    children.push(new Paragraph({
      bullet: { level: 0 },
      children: [new TextRun({ text: c, size: 20, font: "Calibri" })],
    }));
  }

  return new Document({ sections: [{ properties: {}, children }] });
}

export function ReviewResults({ result, onReset }: Props) {
  const [tab, setTab] = useState<"issues" | "missing" | "impact">("impact");
  const scoredOverall = Boolean(result.has_frontend || result.has_backend || result.has_database);
  const { color, label, track } = getGrade(result.overall_score, scoredOverall);
  const issues = result.issues ?? [];
  const missing = result.missing_items ?? [];
  const impact = result.impact_analysis;

  function downloadMd() {
    const link = document.createElement("a");
    link.href = `/api/report-proxy?path=${encodeURIComponent(result.report_path)}`;
    link.download = "jessie-review.md";
    link.click();
  }

  async function downloadDocx() {
    try {
      const doc = buildImpactDocx(result);
      const blob = await Packer.toBlob(doc);
      triggerDownload(blob, "jessie-code-review-impact.docx");
    } catch (err) {
      console.error(err);
      alert("Could not build Word document.");
    }
  }

  function share() {
    navigator.clipboard.writeText(window.location.href);
    alert("Link copied to clipboard!");
  }

  const TABS = [
    { id: "impact" as const,  label: "Impact (Claude)" },
    { id: "issues" as const,  label: `Needs change (${issues.length})` },
    { id: "missing" as const, label: `Missing (${missing.length})` },
  ];

  return (
    <div className="space-y-6">
      <div
        className="rounded-xl border-2 p-4 text-center"
        style={{ borderColor: color, background: `linear-gradient(180deg, ${track}33 0%, transparent 70%)` }}
      >
        <p className="text-4xl font-black" style={{ color }}>
          {scoredOverall ? `${result.overall_score}/100` : "—"}
        </p>
        <p className="text-sm mt-1 font-medium" style={{ color }}>{label}</p>
        {result.is_flutter && (
          <p className="text-xs mt-2 inline-flex px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300">
            Flutter / Dart review
          </p>
        )}
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
          {result.total_files} files · {result.duration_seconds}s · {result.tokens_used.toLocaleString()} tokens · ${result.cost_estimate.toFixed(4)}
          {result.branch ? ` · branch ${result.branch}` : ""}
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
        {[
          { label: "Overall",  score: result.overall_score,  scored: scoredOverall },
          { label: "Frontend", score: result.frontend_score, scored: result.has_frontend !== false && (result.has_frontend || result.frontend_score > 0) },
          { label: "Backend",  score: result.backend_score,  scored: !!result.has_backend },
          { label: "Database", score: result.db_score,       scored: !!result.has_database },
        ].map(({ label: lbl, score, scored }) => (
          <div key={lbl} className="flex flex-col items-center gap-1">
            <ScoreRing score={score} size={72} scored={scored} />
            <span className="text-xs text-gray-500">{lbl}</span>
          </div>
        ))}
      </div>

      <div className="space-y-1">
        <ScoreBar score={result.frontend_score} label="Frontend" scored={result.has_frontend !== false && (result.has_frontend || result.frontend_score > 0)} />
        <ScoreBar score={result.backend_score}  label="Backend"  scored={!!result.has_backend} />
        <ScoreBar score={result.db_score}        label="Database" scored={!!result.has_database} />
      </div>

      <div className="flex flex-wrap gap-2">
        <SeverityBadge severity="critical" count={result.critical_count} />
        <SeverityBadge severity="high"     count={result.high_count}     />
        <SeverityBadge severity="medium"   count={result.medium_count}   />
        <SeverityBadge severity="low"      count={result.low_count}      />
        <SeverityBadge severity="missing"  count={result.missing_count ?? missing.length} />
      </div>

      <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 p-1 rounded-lg overflow-x-auto">
        {TABS.map(t => (
          <button key={t.id} type="button" onClick={() => setTab(t.id)}
            className={`flex-1 min-w-fit px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === t.id ? "bg-white dark:bg-gray-700 shadow-sm" : "text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "impact" && (
        <div className="space-y-5">
          <div className="rounded-xl border dark:border-gray-700 p-4 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">Claude impact analysis</h2>
              {impact?.model && <span className="text-[11px] text-gray-400 font-mono">{impact.model}</span>}
            </div>
            <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
              {impact?.summary || impact?.error || "No Claude analysis yet. Re-run Code Review."}
            </p>
            {impact?.recommendation && (
              <p className="text-xs text-gray-500">Recommendation: <strong>{impact.recommendation}</strong></p>
            )}
          </div>

          <section className="space-y-2">
            <h3 className="text-sm font-semibold">What needs to change</h3>
            {(impact?.must_change?.length ?? 0) === 0 ? (
              <p className="text-sm text-gray-400">No must-change items.</p>
            ) : impact!.must_change!.map((item, i) => (
              <div key={i} className="rounded-lg border dark:border-gray-700 p-3 space-y-1">
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={item.severity || "medium"} />
                  <p className="text-sm font-medium">{item.title}</p>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-300">{item.detail}</p>
                {item.file && <p className="text-xs text-indigo-500 font-mono">{item.file}</p>}
                {item.fix && (
                  <div className="rounded-md bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 p-2 text-xs text-green-700 dark:text-green-300">
                    <strong>Fix:</strong> {item.fix}
                  </div>
                )}
              </div>
            ))}
          </section>

          <section className="space-y-2">
            <h3 className="text-sm font-semibold">File-by-file changes</h3>
            {(impact?.file_changes?.length ?? 0) === 0 ? (
              <p className="text-sm text-gray-400">No file-level change list.</p>
            ) : impact!.file_changes!.map((fc, i) => (
              <div key={i} className="rounded-lg border dark:border-gray-700 p-3">
                <p className="text-sm font-mono font-medium text-indigo-600 dark:text-indigo-300">{fc.file}</p>
                <ul className="mt-1 space-y-1">
                  {(fc.changes ?? []).map((ch, j) => (
                    <li key={j} className="text-sm text-gray-600 dark:text-gray-300 flex gap-2">
                      <span className="text-gray-400">•</span><span>{ch}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </section>

          <section className="space-y-2">
            <h3 className="text-sm font-semibold">Test checklist</h3>
            <ul className="space-y-1">
              {(impact?.test_checklist ?? []).map((c, i) => (
                <li key={i} className="text-sm flex gap-2"><span>☐</span><span>{c}</span></li>
              ))}
            </ul>
          </section>
        </div>
      )}

      {tab === "issues" && (
        <div className="space-y-1">
          <p className="text-xs text-gray-500 mb-2">
            Concrete findings: severity, file, what is wrong, and how to fix.
          </p>
          {issues.length ? issues.map((iss, i) => (
            <IssueCard key={i} issue={iss} />
          )) : (
            <p className="text-sm text-gray-400 py-4">No change items found.</p>
          )}
        </div>
      )}

      {tab === "missing" && (
        <div className="space-y-1">
          <p className="text-xs text-gray-500 mb-2">
            Gaps Claude flagged (tests, error handling, config, coverage).
          </p>
          {missing.length ? missing.map((iss, i) => (
            <IssueCard key={i} issue={iss} />
          )) : (
            <p className="text-sm text-gray-400 py-4">No missing items.</p>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        <button type="button" onClick={downloadMd}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium">
          <Download size={14} /> Download .md
        </button>
        <button type="button" onClick={downloadDocx}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium"
          title="Claude impact + missing + file changes (no full source)">
          <FileText size={14} /> Download Impact .docx
        </button>
        <button type="button" onClick={share}
          className="flex items-center gap-2 px-4 py-2 rounded-lg border dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 text-sm font-medium">
          <Share2 size={14} /> Share Report
        </button>
        <button type="button" onClick={onReset}
          className="flex items-center gap-2 px-4 py-2 rounded-lg border dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 text-sm font-medium">
          <RotateCcw size={14} /> Run New Review
        </button>
      </div>
    </div>
  );
}
