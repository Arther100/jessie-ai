/**
 * Jessie v3 — Ticket Board webview panel.
 */

import * as vscode from 'vscode';
import axios from 'axios';
import { getBackendUrl, getUserId } from './azure';

export async function openTicketBoard(context: vscode.ExtensionContext): Promise<void> {
  const panel = vscode.window.createWebviewPanel(
    'jessieTicketBoard',
    'Jessie — Ticket Board',
    vscode.ViewColumn.One,
    { enableScripts: true },
  );

  const backend = getBackendUrl();
  const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || 'ws';
  const ws = Buffer.from(folder).toString('base64').slice(0, 12);

  const render = async () => {
    let board: any = { empty: true, message: 'No sprint scanned yet. Click Scan Sprint to analyse your current board.' };
    try {
      const r = await axios.get(`${backend}/tickets/board/${ws}`);
      board = r.data;
    } catch {
      // keep empty state
    }
    panel.webview.html = getHtml(board);
  };

  await render();

  panel.webview.onDidReceiveMessage(async (msg) => {
    if (msg.type === 'scan') {
      const platform = vscode.workspace.getConfiguration('jessie').get<string>('ticketPlatform') || 'azure';
      const token = (await context.secrets.get('jessie_token_tickets')) || '';
      const claude = (await context.secrets.get('jessie.claudeApiKey')) || '';
      try {
        await axios.post(
          `${backend}/tickets/scan-sprint`,
          {
            platform,
            token,
            workspace_id: ws,
            user_id: getUserId(),
            claude_api_key: claude,
            mock_tickets: [
              { id: 'DEMO#1', title: 'Fix login 500', description: 'KeyError email', label: 'bug', priority: 'high' },
              { id: 'DEMO#2', title: 'Add auth unit test', description: 'missing unit test', label: 'task', priority: 'medium' },
            ],
          },
          { responseType: 'text', timeout: 120000 },
        );
      } catch {
        // SSE response — board endpoint will update after scanner finishes if using non-stream client;
      }
      // Prefer calling board refresh; for mock scan use fetch via Node stream is complex — hit scan then board
      await render();
      vscode.window.showInformationMessage('Sprint scan requested. Refresh board if still empty.');
    }
    if (msg.type === 'fix') {
      await vscode.commands.executeCommand('jessie.fixTicket', msg.ticketId);
    }
    if (msg.type === 'refresh') {
      await render();
    }
  });
}

function getHtml(board: any): string {
  const empty = board?.empty;
  const auto = board?.auto_fixable || [];
  const assist = board?.ai_assist || [];
  const human = board?.human_only || [];
  const health = board?.health || {};
  const rows = (list: any[], showFix: boolean) =>
    list
      .map(
        (t) => `<div class="card">
      <div><b>${esc(t.id)}</b> ${esc(t.title || '')}</div>
      <div class="meta">${esc(t.category || '')} · ${t.confidence ?? '—'}%</div>
      ${showFix ? `<button onclick="fix('${esc(t.id)}')">Fix now</button>` : ''}
    </div>`,
      )
      .join('') || '<p class="muted">None</p>';

  return `<!DOCTYPE html><html><head><meta charset="UTF-8">
  <style>
    body{font-family:var(--vscode-font-family);padding:16px;color:var(--vscode-foreground)}
    .card{border:1px solid var(--vscode-widget-border);border-radius:8px;padding:10px;margin:8px 0}
    .meta{opacity:.7;font-size:12px;margin:4px 0}
    button{margin-right:6px;margin-top:8px}
    .muted{opacity:.6}
    h2{font-size:14px;margin-top:18px}
  </style></head><body>
  <h1>Sprint overview</h1>
  <p>${esc(board?.sprint || board?.sprint_name || 'No sprint')} · Health ${health.health_score ?? '—'}/100
  ${health.at_risk ? ' · <b>At risk</b>' : ''}</p>
  <div>
    <button onclick="scan()">Scan sprint</button>
    <button onclick="refresh()">Refresh board</button>
  </div>
  ${empty ? `<p class="muted">${esc(board?.message || 'No sprint scanned yet.')}</p>` : ''}
  <h2>Jessie can fix (${auto.length})</h2>
  ${rows(auto, true)}
  <h2>Needs guidance (${assist.length})</h2>
  ${rows(assist, false)}
  <h2>Human only (${human.length})</h2>
  <details><summary>Show ${human.length}</summary>${rows(human, false)}</details>
  <script>
    const vscode = acquireVsCodeApi();
    function scan(){ vscode.postMessage({type:'scan'}); }
    function refresh(){ vscode.postMessage({type:'refresh'}); }
    function fix(id){ vscode.postMessage({type:'fix', ticketId:id}); }
  </script>
  </body></html>`;
}

function esc(s: string): string {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/"/g, '&quot;');
}
