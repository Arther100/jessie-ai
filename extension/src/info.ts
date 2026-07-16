/**
 * Jessie Info panel — parity with web Settings → Info.
 * Claude API key setup + shared feature guide (web & extension).
 */

import * as vscode from 'vscode';
import axios from 'axios';
import {
  clearClaudeKey,
  ensureClaudeApiKey,
  getBackendUrl,
  getStoredClaudeKey,
  getUserId,
} from './azure';

function maskKey(key: string): string {
  if (!key) return 'Not configured';
  if (key.length <= 4) return '●'.repeat(key.length);
  return '●'.repeat(key.length - 4) + key.slice(-4);
}

export async function showJessieInfo(context: vscode.ExtensionContext): Promise<void> {
  const panel = vscode.window.createWebviewPanel(
    'jessieInfo',
    'Jessie — Info',
    vscode.ViewColumn.One,
    { enableScripts: true, retainContextWhenHidden: true },
  );

  const refresh = async () => {
    const backendUrl = getBackendUrl();
    let backendStatus = 'Offline';
    let backendVersion = '—';
    try {
      const r = await axios.get(`${backendUrl}/health`, { timeout: 4000 });
      backendStatus = r.data?.status === 'ok' ? 'Online' : 'Offline';
      backendVersion = r.data?.version || '—';
    } catch {
      backendStatus = 'Offline';
    }
    const claudeKey = await getStoredClaudeKey(context);
    const webApp =
      vscode.workspace.getConfiguration('jessie').get<string>('webAppUrl') ||
      'http://localhost:3000';

    panel.webview.html = getHtml({
      userId: getUserId(),
      backendUrl,
      backendStatus,
      backendVersion,
      claudeMasked: maskKey(claudeKey),
      hasClaude: !!claudeKey,
      webApp,
    });
  };

  await refresh();

  panel.webview.onDidReceiveMessage(async (msg) => {
    if (msg.type === 'setClaude') {
      const key = await ensureClaudeApiKey(context);
      if (key) {
        vscode.window.showInformationMessage('Claude API key saved securely.');
      }
      await refresh();
    }
    if (msg.type === 'clearClaude') {
      await clearClaudeKey(context);
      vscode.window.showInformationMessage('Claude API key cleared.');
      await refresh();
    }
    if (msg.type === 'openWeb') {
      const web =
        vscode.workspace.getConfiguration('jessie').get<string>('webAppUrl') ||
        'http://localhost:3000';
      await vscode.env.openExternal(vscode.Uri.parse(`${web}/settings?tab=info`));
    }
    if (msg.type === 'openAnthropic') {
      await vscode.env.openExternal(vscode.Uri.parse('https://console.anthropic.com/'));
    }
    if (msg.type === 'run') {
      await vscode.commands.executeCommand(msg.command);
    }
  });
}

function getHtml(opts: {
  userId: string;
  backendUrl: string;
  backendStatus: string;
  backendVersion: string;
  claudeMasked: string;
  hasClaude: boolean;
  webApp: string;
}): string {
  const online = opts.backendStatus === 'Online';
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); background: var(--vscode-editor-background); padding: 20px; max-width: 640px; }
  h1 { font-size: 18px; margin: 0 0 6px; }
  .sub { opacity: .75; font-size: 12px; margin-bottom: 18px; line-height: 1.45; }
  .card { border: 1px solid var(--vscode-widget-border); border-radius: 8px; padding: 14px; margin-bottom: 14px; }
  .card.accent { border-color: var(--vscode-focusBorder); }
  .title { font-size: 13px; font-weight: 600; margin-bottom: 4px; }
  .hint { font-size: 11px; opacity: .7; margin-bottom: 10px; line-height: 1.4; }
  .row { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; padding: 6px 0; border-bottom: 1px solid var(--vscode-widget-border); }
  .row:last-child { border-bottom: none; }
  .mono { font-family: var(--vscode-editor-font-family); font-size: 11px; opacity: .85; }
  .ok { color: #4caf50; }
  .bad { color: #f44336; }
  .btns { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
  button, a.btn {
    font-family: inherit; font-size: 12px; padding: 6px 12px; border-radius: 5px; cursor: pointer;
    border: 1px solid var(--vscode-button-border, transparent);
    background: var(--vscode-button-background); color: var(--vscode-button-foreground); text-decoration: none;
  }
  button.secondary, a.btn.secondary {
    background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground);
  }
  button.danger { color: #f44336; background: transparent; border-color: var(--vscode-widget-border); }
  ul { margin: 8px 0 0 18px; padding: 0; font-size: 12px; line-height: 1.55; opacity: .9; }
  li { margin-bottom: 6px; }
</style>
</head>
<body>
  <h1>Jessie — Info</h1>
  <p class="sub">Web app and VS Code extension share the same Jessie backend. Configure your Claude API key here before Code Review or Merge Review.</p>

  <div class="card accent">
    <div class="title">Claude (Anthropic) API key</div>
    <p class="hint">Mandatory for Code Review and Merge Review. Stored in VS Code SecretStorage (never on the Jessie server). Same requirement as web Settings → Info.</p>
    <div class="row"><span>Status</span><span class="mono">${opts.claudeMasked}</span></div>
    <div class="btns">
      <button onclick="post('setClaude')">${opts.hasClaude ? 'Update key' : 'Add Claude key'}</button>
      ${opts.hasClaude ? `<button class="danger" onclick="post('clearClaude')">Clear key</button>` : ''}
      <button class="secondary" onclick="post('openAnthropic')">Anthropic Console</button>
    </div>
  </div>

  <div class="card">
    <div class="title">Same features on web &amp; VS Code</div>
    <ul>
      <li><b>Code Review</b> — Azure clone URL + password/PAT + branch; Claude scores layers and project impact. Extension also supports a local folder.</li>
      <li><b>Merge Review</b> — Azure base → head diff; Claude explains UI, functionality, risks, missing coverage; open impact report.</li>
      <li><b>History</b> — past code &amp; merge reviews (or open the web dashboard).</li>
      <li><b>Your Claude key</b> — sent only for the review request; not stored server-side.</li>
    </ul>
    <div class="btns">
      <button onclick="post('run','jessie.reviewProject')">Code Review</button>
      <button class="secondary" onclick="post('run','jessie.mergeReview')">Merge Review</button>
      <button class="secondary" onclick="post('run','jessie.history')">History</button>
      <button class="secondary" onclick="post('openWeb')">Open web Info</button>
    </div>
  </div>

  <div class="card">
    <div class="title">Status</div>
    <div class="row"><span>User ID</span><span class="mono">${escapeHtml(opts.userId)}</span></div>
    <div class="row"><span>Backend</span><span class="mono">${escapeHtml(opts.backendVersion)} · <span class="${online ? 'ok' : 'bad'}">${opts.backendStatus}</span></span></div>
    <div class="row"><span>API URL</span><span class="mono">${escapeHtml(opts.backendUrl)}</span></div>
    <div class="row"><span>Web app</span><span class="mono">${escapeHtml(opts.webApp)}</span></div>
  </div>

<script>
  const vscode = acquireVsCodeApi();
  function post(type, command) {
    vscode.postMessage(command ? { type, command } : { type });
  }
</script>
</body>
</html>`;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
