/**
 * Jessie Code Review — Azure branch (web parity) + local workspace folder.
 * Uses the same /review/start backend as the web app (Flutter, impact, issues, missing).
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

interface ReviewIssue {
  severity?: string;
  title?: string;
  detail?: string;
  fix?: string;
  file?: string;
  layer?: string;
  category?: string;
}

interface ReviewCompleteEvent {
  type: 'complete';
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
  issues?: ReviewIssue[];
  missing_items?: ReviewIssue[];
  impact_analysis?: {
    summary?: string;
    must_change?: ReviewIssue[];
    missing?: Array<ReviewIssue | string>;
    file_changes?: { file?: string; changes?: string[] }[];
    test_checklist?: string[];
    recommendation?: string;
    model?: string;
    error?: string;
  };
}

interface ReviewErrorEvent {
  type: 'error';
  code: string;
  message: string;
}

function progressLabel(message: string): string {
  return `$(loading~spin) Jessie — ${message}`;
}

function gradeEmoji(grade: string): string {
  return { A: '🏆', B: '✅', C: '⚠️', D: '🔶', F: '🔴' }[grade] ?? '❓';
}

function layerLabel(score: number, scored?: boolean): string {
  if (scored === false) return '— (not scored)';
  return `${score}/100`;
}

/** Same content shape as web Impact .docx — markdown for VS Code. */
function writeCodeReviewImpact(result: ReviewCompleteEvent): string {
  const impact = result.impact_analysis || {};
  const lines: string[] = [
    '# Jessie — Code Review Impact',
    '',
    result.is_flutter ? '**Stack:** Flutter / Dart' : '',
    `**Score:** ${result.overall_score}/100 (${result.grade})`,
    `**Files:** ${result.total_files}  ·  **Issues:** ${result.total_issues}  ·  **Missing:** ${result.missing_count ?? (result.missing_items?.length || 0)}`,
    result.branch ? `**Branch:** ${result.branch}` : '',
    '',
    '## Summary',
    impact.summary || impact.error || 'No Claude summary available.',
    '',
    `Recommendation: **${impact.recommendation || 'needs_changes'}**`,
    '',
    '## Layer scores',
    `| Layer | Score |`,
    `|-------|-------|`,
    `| Frontend | ${layerLabel(result.frontend_score, result.has_frontend)} |`,
    `| Backend | ${layerLabel(result.backend_score, result.has_backend)} |`,
    `| Database | ${layerLabel(result.db_score, result.has_database)} |`,
    '',
    '## What needs to change',
  ];

  for (const item of impact.must_change || []) {
    lines.push(`### ● ${(item.severity || 'medium').toUpperCase()} — ${item.title || 'Change'}`);
    lines.push(item.detail || '');
    if (item.file) lines.push(`File: \`${item.file}\``);
    if (item.fix) lines.push(`Fix: ${item.fix}`);
    lines.push('');
  }

  lines.push('## What is missing');
  for (const item of impact.missing || result.missing_items || []) {
    if (typeof item === 'string') {
      lines.push(`- ${item}`);
    } else {
      lines.push(`- **${item.title || 'Gap'}** (\`${item.file || ''}\`): ${item.detail || ''}`);
    }
  }

  lines.push('', '## File-by-file changes');
  for (const fc of impact.file_changes || []) {
    lines.push(`### \`${fc.file || 'unknown'}\``);
    for (const ch of fc.changes || []) lines.push(`- ${ch}`);
    lines.push('');
  }

  lines.push('## Findings (from layer review)');
  for (const iss of (result.issues || []).slice(0, 40)) {
    lines.push(
      `- **[${(iss.severity || 'medium').toUpperCase()}]** ${iss.title || ''} ` +
        `(\`${iss.file || ''}\` · ${iss.layer || ''}/${iss.category || ''})`,
    );
    if (iss.detail) lines.push(`  - ${iss.detail}`);
    if (iss.fix) lines.push(`  - Fix: ${iss.fix}`);
  }

  lines.push('', '## Test checklist');
  for (const c of impact.test_checklist || []) lines.push(`- [ ] ${c}`);

  const out = path.join(os.tmpdir(), `jessie-code-review-impact-${Date.now()}.md`);
  fs.writeFileSync(out, lines.filter(l => l !== undefined).join('\n'), 'utf8');
  return out;
}

export class JessieCodeReview {
  private _statusBar: vscode.StatusBarItem;
  private _backendUrl: string;
  private _context: vscode.ExtensionContext;
  private _isRunning = false;

  constructor(
    statusBar: vscode.StatusBarItem,
    backendUrl: string,
    context: vscode.ExtensionContext,
  ) {
    this._statusBar = statusBar;
    this._backendUrl = backendUrl || getBackendUrl();
    this._context = context;
  }

  async startReview(triggeredBy: string, projectPath?: string): Promise<void> {
    if (this._isRunning) {
      vscode.window.showWarningMessage('A Jessie review is already running.');
      return;
    }

    const mode = await vscode.window.showQuickPick(
      [
        {
          label: '$(cloud) Azure DevOps branch',
          description: 'Same as web — clone URL + password + branch',
          mode: 'azure' as const,
        },
        {
          label: '$(folder) Local workspace folder',
          description: 'Review files on this machine',
          mode: 'local' as const,
        },
      ],
      { title: 'Jessie Code Review', placeHolder: 'How should Jessie get the code?', ignoreFocusOut: true },
    );
    if (!mode) return;

    if (mode.mode === 'azure') {
      await this.startAzureReview(triggeredBy);
      return;
    }

    const claudeKey = await ensureClaudeApiKey(this._context);
    if (!claudeKey) return;

    const folder =
      projectPath ||
      vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ||
      '';
    if (!folder) {
      vscode.window.showErrorMessage('Open a workspace folder to review locally.');
      return;
    }
    await this._runReview(
      {
        project_path: folder,
        azure_url: '',
        token: '',
        branch: '',
        user_id: getUserId(),
        workspace_id: workspaceIdFrom(folder),
        triggered_by: triggeredBy,
        claude_api_key: claudeKey,
      },
      undefined,
    );
  }

  async startAzureReview(triggeredBy: string): Promise<void> {
    if (this._isRunning) {
      vscode.window.showWarningMessage('A Jessie review is already running.');
      return;
    }

    const claudeKey = await ensureClaudeApiKey(this._context);
    if (!claudeKey) return;

    const conn = await promptAzureConnection(this._context);
    if (!conn) return;

    const preferred =
      conn.branches.find(b => b === 'main' || b === 'master' || b === 'develop') ??
      conn.branches[0];
    const branch = await pickBranch(conn.branches, 'Select branch to review', preferred);
    if (!branch) return;

    await this._runReview(
      {
        project_path: '',
        azure_url: conn.url,
        token: conn.token,
        branch,
        user_id: getUserId(),
        workspace_id: workspaceIdFrom(`${conn.ref.org}/${conn.ref.project}/${conn.ref.repo}`),
        triggered_by: triggeredBy,
        claude_api_key: claudeKey,
      },
      undefined,
    );
  }

  async handleChatTrigger(
    _message: string,
    stream: vscode.ChatResponseStream,
  ): Promise<void> {
    if (this._isRunning) {
      stream.markdown('⚠️ **A Jessie review is already in progress.**');
      return;
    }

    stream.markdown('🔍 **Code Review** — same backend as the web app…\n\n');
    await this.startReview('chat');
  }

  private async _runReview(
    body: Record<string, unknown>,
    stream?: vscode.ChatResponseStream,
  ): Promise<void> {
    this._isRunning = true;
    this._statusBar.text = '$(loading~spin) Jessie — starting review...';
    stream?.markdown(
      body.azure_url
        ? `Cloning \`${body.branch}\` from Azure and reviewing…\n\n`
        : `Reviewing local folder \`${body.project_path}\`…\n\n`,
    );

    try {
      const result = await streamSse(
        `${this._backendUrl}/review/start`,
        body,
        (event) => {
          if (event.type === 'progress') {
            const msg = String(event.message || '');
            this._statusBar.text = progressLabel(msg);
            stream?.progress(msg);
          }
        },
      );

      if (result.type === 'complete') {
        const r = result as unknown as ReviewCompleteEvent;
        this._statusBar.text = `$(sparkle) Jessie — ${r.overall_score}/100 (${r.grade})`;
        const emoji = gradeEmoji(r.grade);
        const flutter = r.is_flutter ? ' · Flutter/Dart' : '';
        const summary =
          `${emoji} Review complete — ${r.overall_score}/100 (${r.grade})${flutter} · ` +
          `${r.total_issues} issues · ${r.missing_count ?? 0} missing`;

        const impactPath = writeCodeReviewImpact(r);

        if (stream) {
          const impact = r.impact_analysis;
          stream.markdown(
            `## ${emoji} Review Complete — ${r.overall_score}/100 (${r.grade})${flutter}\n\n` +
              `| Layer | Score |\n|-------|-------|\n` +
              `| Frontend | ${layerLabel(r.frontend_score, r.has_frontend)} |\n` +
              `| Backend | ${layerLabel(r.backend_score, r.has_backend)} |\n` +
              `| Database | ${layerLabel(r.db_score, r.has_database)} |\n\n` +
              `**Issues:** ${r.total_issues} · **Missing:** ${r.missing_count ?? 0}\n\n` +
              `### Claude impact\n${impact?.summary || '_No summary_'}\n\n` +
              `📄 Full report: \`${r.report_path}\`\n` +
              `📋 Impact: \`${impactPath}\`\n`,
          );
        }

        const choice = await vscode.window.showInformationMessage(
          summary,
          'Open Report',
          'Open Impact',
          'Dismiss',
        );
        if (choice === 'Open Report' && r.report_path) {
          await vscode.commands.executeCommand('vscode.open', vscode.Uri.file(r.report_path));
        } else if (choice === 'Open Impact') {
          await vscode.commands.executeCommand('vscode.open', vscode.Uri.file(impactPath));
        }
      } else {
        const err = result as unknown as ReviewErrorEvent;
        this._statusBar.text = '$(error) Jessie — review failed';
        const msg = err.message || 'Review failed';
        stream?.markdown(`❌ **Review failed:** ${msg}`);
        vscode.window.showErrorMessage(`Jessie review failed: ${msg}`);
      }
    } catch (err: any) {
      this._statusBar.text = '$(error) Jessie — review failed';
      const msg = err.message ?? 'Unknown error';
      stream?.markdown(`❌ **Review error:** ${msg}`);
      vscode.window.showErrorMessage(`Jessie review error: ${msg}`);
    } finally {
      this._isRunning = false;
    }
  }
}
