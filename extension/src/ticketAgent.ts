/**
 * Jessie v3 — Ticket Agent (extension).
 * Fix tickets via POST /tickets/fix SSE.
 */

import * as vscode from 'vscode';
import { getBackendUrl, getUserId } from './azure';
import { buildAuthHeaders, getApiKey } from './apiKeys';
import { streamSse } from './sse';

const TICKET_SECRET = 'jessie_token_tickets';

export class JessieTicketAgent {
  constructor(
    private readonly _context: vscode.ExtensionContext,
    private readonly _statusBar: vscode.StatusBarItem,
  ) {}

  async fixTicket(ticketId?: string, _triggeredBy?: string): Promise<void> {
    let id = ticketId;
    if (!id) {
      id = await vscode.window.showInputBox({
        prompt: 'Enter ticket number',
        placeHolder: 'AB#1047, JIRA-203, #892',
        ignoreFocusOut: true,
      });
    }
    if (!id) return;

    const platform =
      vscode.workspace.getConfiguration('jessie').get<string>('ticketPlatform') || 'azure';
    const token = (await this._context.secrets.get(TICKET_SECRET)) || '';
    const claude = await getApiKey(this._context);
    if (!claude) {
      vscode.window.showWarningMessage('Add API key via Jessie: Update API Key first.');
      return;
    }

    const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '.';
    const workspaceId = Buffer.from(folder).toString('base64').slice(0, 12);
    const backend = getBackendUrl();
    this._statusBar.text = `$(loading~spin) Jessie — reading ${id}...`;

    try {
      const authHeaders = await buildAuthHeaders(this._context, workspaceId);
      const result = await streamSse(`${backend}/tickets/fix`, {
        ticket_id: id,
        platform,
        platform_token: token,
        workspace_id: workspaceId,
        workspace_path: folder,
        user_id: getUserId(),
        claude_api_key: claude,
        azure_org: vscode.workspace.getConfiguration('jessie').get<string>('azureOrg') || '',
        azure_project: vscode.workspace.getConfiguration('jessie').get<string>('azureProject') || '',
        github_repo: vscode.workspace.getConfiguration('jessie').get<string>('githubRepo') || '',
      }, (event) => {
        if (event.type === 'progress') {
          this._statusBar.text = `$(loading~spin) Jessie — ${event.message}`;
        }
      }, authHeaders);

      if (result.type === 'error') {
        vscode.window.showErrorMessage(String(result.message || 'Ticket fix failed'));
        return;
      }

      this._statusBar.text = `$(git-branch) Jessie — PR #${result.pr_number || '?'} · ${id}`;
      const pick = await vscode.window.showInformationMessage(
        `✅ Jessie fixed ${id}\nPR #${result.pr_number || 'n/a'} · Quality: ${result.quality_score}/100\nBranch: ${result.branch || ''}`,
        'Open PR',
        'Dismiss',
      );
      if (pick === 'Open PR' && result.pr_url) {
        await vscode.env.openExternal(vscode.Uri.parse(String(result.pr_url)));
      }
    } catch (err: any) {
      vscode.window.showErrorMessage(`Ticket fix failed: ${err.message || err}`);
      this._statusBar.text = '$(sparkle) Jessie';
    }
  }

  async scanSprint(): Promise<void> {
    await vscode.commands.executeCommand('jessie.openTicketBoard');
  }

  async weeklyReport(): Promise<void> {
    const backend = getBackendUrl();
    const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || 'ws';
    const ws = Buffer.from(folder).toString('base64').slice(0, 12);
    try {
      const axios = (await import('axios')).default;
      const r = await axios.get(`${backend}/sprint/weekly-report/${ws}`);
      const doc = await vscode.workspace.openTextDocument({
        content: r.data.markdown || '# No report yet',
        language: 'markdown',
      });
      await vscode.window.showTextDocument(doc);
    } catch (err: any) {
      vscode.window.showErrorMessage(`Weekly report failed: ${err.message || err}`);
    }
  }

  async handleChatTrigger(message: string): Promise<boolean> {
    const ticketPatterns = [
      /fix\s+((?:AB#|#|JIRA-|ENG-|LIN-)?\d+)/i,
      /implement\s+((?:AB#|#|JIRA-|ENG-)?\d+)/i,
      /resolve\s+(?:issue|ticket|bug)?\s*#?(\d+)/i,
      /work\s+on\s+(?:ticket|issue)\s*#?(\d+)/i,
    ];
    if (/scan\s+(sprint|board)/i.test(message)) {
      await this.scanSprint();
      return true;
    }
    if (/weekly\s+report|sprint\s+health/i.test(message)) {
      await this.weeklyReport();
      return true;
    }
    for (const re of ticketPatterns) {
      const m = message.match(re);
      if (m) {
        await this.fixTicket(m[1].startsWith('#') || /[A-Z]/i.test(m[1]) ? m[1] : `#${m[1]}`);
        return true;
      }
    }
    return false;
  }
}
