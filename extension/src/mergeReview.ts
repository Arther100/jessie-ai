/**
 * Jessie Merge Review — Azure branch diff + Claude impact (web parity).
 */

import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import * as vscode from 'vscode';
import {
  ensureClaudeApiKey,
  getBackendUrl,
  getUserId,
  pickBranch,
  promptAzureConnection,
  workspaceIdFrom,
} from './azure';
import { streamSse } from './sse';

interface ImpactItem {
  title?: string;
  detail?: string;
  severity?: string;
  files?: string[];
  why?: string;
  how_to_verify?: string;
}

interface MergeComplete {
  type: 'complete';
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
  files_changed: number;
  lines_added: number;
  lines_removed: number;
  commits_count: number;
  impact_analysis?: {
    summary?: string;
    ui_changes?: ImpactItem[];
    functionality_changes?: ImpactItem[];
    expected_issues?: ImpactItem[];
    test_checklist?: string[];
    recommendation?: string;
    model?: string;
  };
  metadata?: Record<string, unknown>;
}

function writeImpactMarkdown(result: MergeComplete): string {
  const impact = result.impact_analysis || {};
  const meta = result.metadata || {};
  const lines: string[] = [
    '# Jessie — Claude Impact Report',
    '',
    `**Verdict:** ${result.verdict}`,
    `**Score:** ${result.overall_score}/100 (${result.grade})`,
    '',
    'Verdict = merge recommendation (approve / needs changes).',
    'Score = merge safety 0–100 (higher is safer).',
    '',
    `Branches: ${meta.head_branch ?? '?'} → ${meta.base_branch ?? '?'}`,
    `Files: ${result.files_changed}  ·  +${result.lines_added} / -${result.lines_removed}`,
    '',
    '## Summary',
    impact.summary || 'No Claude summary available.',
    '',
    '## UI changes users will notice',
  ];

  for (const item of impact.ui_changes || []) {
    lines.push(`### ● ${(item.severity || 'medium').toUpperCase()} — ${item.title}`);
    lines.push(item.detail || '');
    if (item.files?.length) lines.push(`Files: ${item.files.join(', ')}`);
    lines.push('');
  }

  lines.push('## Functionality / behaviour changes');
  for (const item of impact.functionality_changes || []) {
    lines.push(`### ● ${(item.severity || 'medium').toUpperCase()} — ${item.title}`);
    lines.push(item.detail || '');
    if (item.files?.length) lines.push(`Files: ${item.files.join(', ')}`);
    lines.push('');
  }

  lines.push('## Issues you may face');
  for (const item of impact.expected_issues || []) {
    lines.push(`### ● ${(item.severity || 'medium').toUpperCase()} — ${item.title}`);
    lines.push(item.detail || '');
    if (item.why) lines.push(`Why: ${item.why}`);
    if (item.how_to_verify) lines.push(`Verify: ${item.how_to_verify}`);
    if (item.files?.length) lines.push(`Files: ${item.files.join(', ')}`);
    lines.push('');
  }

  lines.push('## Test checklist');
  for (const c of impact.test_checklist || []) lines.push(`- [ ] ${c}`);

  const out = path.join(os.tmpdir(), `jessie-claude-impact-${Date.now()}.md`);
  fs.writeFileSync(out, lines.join('\n'), 'utf8');
  return out;
}

export class JessieMergeReview {
  private _statusBar: vscode.StatusBarItem;
  private _context: vscode.ExtensionContext;
  private _isRunning = false;

  constructor(statusBar: vscode.StatusBarItem, context: vscode.ExtensionContext) {
    this._statusBar = statusBar;
    this._context = context;
  }

  async start(): Promise<void> {
    if (this._isRunning) {
      vscode.window.showWarningMessage('A Jessie merge review is already running.');
      return;
    }

    const claudeKey = await ensureClaudeApiKey(this._context);
    if (!claudeKey) return;

    const conn = await promptAzureConnection(this._context);
    if (!conn) return;

    const preferredBase =
      conn.branches.find(b => b === 'main' || b === 'master' || b === 'develop') ??
      conn.branches[0];
    const baseBranch = await pickBranch(conn.branches, 'Select BASE branch (target)', preferredBase);
    if (!baseBranch) return;

    const preferredHead =
      conn.branches.find(b => b !== baseBranch) ?? conn.branches[0];
    const headBranch = await pickBranch(conn.branches, 'Select HEAD branch (source / feature)', preferredHead);
    if (!headBranch) return;

    if (baseBranch === headBranch) {
      vscode.window.showWarningMessage('Base and head branches must be different.');
      return;
    }

    this._isRunning = true;
    this._statusBar.text = '$(loading~spin) Jessie — merge review...';

    const backendUrl = getBackendUrl();
    const body = {
      platform: 'azure',
      user_id: getUserId(),
      workspace_id: workspaceIdFrom(`${conn.ref.org}/${conn.ref.project}/${conn.ref.repo}`),
      repo: conn.ref.repo,
      token: conn.token,
      azure_org: conn.ref.org,
      azure_project: conn.ref.project,
      mode: 'branch',
      base_branch: baseBranch,
      head_branch: headBranch,
      post_comments: false,
      triggered_by: 'extension',
      claude_api_key: claudeKey,
    };

    try {
      const result = await streamSse(`${backendUrl}/merge/review`, body, (event) => {
        if (event.type === 'progress') {
          this._statusBar.text = `$(loading~spin) Jessie — ${event.message}`;
        }
      });

      if (result.type !== 'complete') {
        const msg = String((result as any).message || 'Merge review failed');
        this._statusBar.text = '$(error) Jessie — merge review failed';
        vscode.window.showErrorMessage(msg);
        return;
      }

      const r = result as unknown as MergeComplete;
      this._statusBar.text = `$(sparkle) Jessie — ${r.verdict} (${r.overall_score})`;

      const summary =
        `Merge review: ${r.verdict} · score ${r.overall_score}/100 (${r.grade}) · ` +
        `${r.files_changed} files · ${r.total_issues} issues`;

      const choice = await vscode.window.showInformationMessage(
        summary,
        'Open Report',
        'Open Impact',
        'Dismiss',
      );

      if (choice === 'Open Report' && r.report_path) {
        await vscode.commands.executeCommand('vscode.open', vscode.Uri.file(r.report_path));
      } else if (choice === 'Open Impact') {
        const impactPath = writeImpactMarkdown(r);
        await vscode.commands.executeCommand('vscode.open', vscode.Uri.file(impactPath));
      }
    } catch (err: any) {
      this._statusBar.text = '$(error) Jessie — merge review failed';
      vscode.window.showErrorMessage(`Merge review error: ${err.message ?? 'Unknown error'}`);
    } finally {
      this._isRunning = false;
    }
  }
}
