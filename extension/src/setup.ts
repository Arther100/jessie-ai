/**
 * Jessie — extension/src/setup.ts
 * 3-screen BYOK setup wizard (hosted Railway backend).
 * Uses VS Code CSS variables only — no hardcoded colors.
 */

import * as vscode from 'vscode';
import * as crypto from 'crypto';
import { showTour } from './tour';
import {
  getBackendUrl,
  getProvider,
  storeApiKey,
  verifyApiKey,
  type AiProvider,
} from './apiKeys';

export async function setupWalkthrough(
  context: vscode.ExtensionContext,
  onComplete?: () => void,
) {
  const panel = vscode.window.createWebviewPanel(
    'jessieSetup',
    'Jessie — Setup',
    vscode.ViewColumn.One,
    { enableScripts: true },
  );

  const backendUrl = getBackendUrl();
  let serverOnline = false;
  try {
    const res = await fetch(`${backendUrl}/health`, { signal: AbortSignal.timeout(4000) });
    serverOnline = res.ok;
  } catch {
    serverOnline = false;
  }

  panel.webview.html = getSetupHtml(backendUrl, serverOnline);

  panel.webview.onDidReceiveMessage(async (msg) => {
    if (msg.type === 'open_console') {
      vscode.env.openExternal(vscode.Uri.parse('https://console.anthropic.com'));
      return;
    }

    if (msg.type === 'validate_key') {
      const key = String(msg.key || '').trim();
      const provider = (msg.provider || 'anthropic') as AiProvider;
      if (!key) {
        panel.webview.postMessage({
          type: 'validate_result',
          ok: false,
          message: 'Enter an API key first.',
        });
        return;
      }
      panel.webview.postMessage({ type: 'validate_status', message: 'Checking key...' });
      const result = await verifyApiKey(backendUrl, key, provider);
      if (result.ok) {
        await storeApiKey(context, key);
        await vscode.workspace
          .getConfiguration('jessie')
          .update('aiProvider', provider, vscode.ConfigurationTarget.Global);
      }
      panel.webview.postMessage({
        type: 'validate_result',
        ok: result.ok,
        model: result.model || '',
        message: result.message,
      });
      return;
    }

    if (msg.type === 'finish') {
      const name = String(msg.name || '').trim();
      if (!name) {
        panel.webview.postMessage({
          type: 'finish_error',
          message: 'Please enter your name.',
        });
        return;
      }
      await vscode.workspace
        .getConfiguration('jessie')
        .update('userId', name, vscode.ConfigurationTarget.Global);
      await context.globalState.update('jessie.setupComplete', true);
      panel.webview.postMessage({ type: 'ready' });
      onComplete?.();
      return;
    }

    if (msg.type === 'open_tour') {
      panel.dispose();
      showTour(context);
    }

    if (msg.type === 'close') {
      panel.dispose();
    }
  });
}

function getSetupHtml(backendUrl: string, online: boolean): string {
  const status = online
    ? '✓ Server is online'
    : '⚠ Server unreachable — check jessie.backendUrl';
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<style>
  :root { color-scheme: light dark; }
  body {
    font-family: var(--vscode-font-family);
    font-size: var(--vscode-font-size);
    color: var(--vscode-foreground);
    background: var(--vscode-editor-background);
    margin: 0;
    padding: 24px;
    line-height: 1.5;
  }
  .screen { display: none; max-width: 520px; margin: 0 auto; }
  .screen.active { display: block; }
  h1 { font-size: 1.4rem; font-weight: 600; margin: 0 0 12px; }
  p { opacity: 0.9; margin: 0 0 12px; }
  .muted { opacity: 0.7; font-size: 0.92em; }
  code {
    background: var(--vscode-textCodeBlock-background);
    padding: 2px 6px;
    border-radius: 3px;
  }
  .tabs { display: flex; gap: 8px; margin: 16px 0 12px; flex-wrap: wrap; }
  .tab {
    border: 1px solid var(--vscode-button-secondaryBackground);
    background: var(--vscode-button-secondaryBackground);
    color: var(--vscode-button-secondaryForeground);
    padding: 6px 12px;
    border-radius: 4px;
    cursor: pointer;
  }
  .tab.active {
    background: var(--vscode-button-background);
    color: var(--vscode-button-foreground);
    border-color: var(--vscode-focusBorder);
  }
  input[type="password"], input[type="text"] {
    width: 100%;
    box-sizing: border-box;
    padding: 10px 12px;
    margin: 8px 0 16px;
    background: var(--vscode-input-background);
    color: var(--vscode-input-foreground);
    border: 1px solid var(--vscode-input-border, var(--vscode-widget-border));
    border-radius: 4px;
  }
  .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }
  button {
    background: var(--vscode-button-background);
    color: var(--vscode-button-foreground);
    border: none;
    padding: 10px 16px;
    border-radius: 4px;
    cursor: pointer;
  }
  button.secondary {
    background: var(--vscode-button-secondaryBackground);
    color: var(--vscode-button-secondaryForeground);
  }
  button:disabled { opacity: 0.5; cursor: default; }
  .msg { margin-top: 10px; min-height: 1.2em; }
  .ok { color: var(--vscode-testing-iconPassed, var(--vscode-charts-green)); }
  .err { color: var(--vscode-errorForeground); }
  .server { margin: 12px 0 20px; padding: 10px 12px;
    border-left: 3px solid var(--vscode-focusBorder);
    background: var(--vscode-textBlockQuote-background);
  }
</style>
</head>
<body>
  <div id="s1" class="screen active">
    <h1>⚡ Welcome to Jessie AI</h1>
    <div class="server">
      Jessie is hosted at:<br/>
      <code>${escapeHtml(backendUrl)}</code><br/>
      <span class="${online ? 'ok' : 'err'}">${status}</span>
    </div>
    <p>You need one thing to get started:<br/><strong>Your own Claude API key.</strong></p>
    <p class="muted">This lets you use Jessie anywhere. Your key is stored only on this device (VS Code SecretStorage) — never on Jessie servers.</p>
    <div class="actions">
      <button onclick="go(2)">I have a Claude API key →</button>
      <button class="secondary" onclick="post({type:'open_console'})">Get a free Claude API key →</button>
    </div>
  </div>

  <div id="s2" class="screen">
    <h1>Enter your Claude API key</h1>
    <p class="muted">Starts with sk-ant- (Anthropic) or sk- (OpenAI)</p>
    <div class="tabs">
      <button class="tab active" data-p="anthropic" onclick="setProvider('anthropic')">Anthropic</button>
      <button class="tab" data-p="openai" onclick="setProvider('openai')">OpenAI</button>
      <button class="tab" data-p="gemini" onclick="setProvider('gemini')">Gemini</button>
    </div>
    <input id="apiKey" type="password" placeholder="sk-ant-..." autocomplete="off" />
    <div class="actions">
      <button class="secondary" onclick="go(1)">← Back</button>
      <button id="validateBtn" onclick="validate()">Validate &amp; continue</button>
    </div>
    <div id="validateMsg" class="msg"></div>
  </div>

  <div id="s3" class="screen">
    <h1>What's your name?</h1>
    <p class="muted">Used to track your usage and personalise Jessie's responses.</p>
    <input id="userName" type="text" placeholder="e.g. vijay" />
    <div class="actions">
      <button class="secondary" onclick="go(2)">← Back</button>
      <button onclick="finish()">Finish setup</button>
    </div>
    <div id="finishMsg" class="msg"></div>
  </div>

  <div id="s4" class="screen">
    <h1>✓ Jessie is ready!</h1>
    <p>Your API key is stored securely on this device. Status bar shows Jessie — ready.</p>
    <div class="actions">
      <button onclick="post({type:'open_tour'})">Take the tour</button>
      <button class="secondary" onclick="post({type:'close'})">Close</button>
    </div>
  </div>

<script>
  const vscode = acquireVsCodeApi();
  let provider = 'anthropic';
  function post(msg) { vscode.postMessage(msg); }
  function go(n) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    document.getElementById('s' + n).classList.add('active');
  }
  function setProvider(p) {
    provider = p;
    document.querySelectorAll('.tab').forEach(t => {
      t.classList.toggle('active', t.getAttribute('data-p') === p);
    });
    const ph = p === 'openai' ? 'sk-...' : p === 'gemini' ? 'AIza...' : 'sk-ant-...';
    document.getElementById('apiKey').placeholder = ph;
  }
  function validate() {
    const key = document.getElementById('apiKey').value;
    const btn = document.getElementById('validateBtn');
    btn.disabled = true;
    document.getElementById('validateMsg').textContent = 'Checking key...';
    post({ type: 'validate_key', key, provider });
  }
  function finish() {
    post({ type: 'finish', name: document.getElementById('userName').value });
  }
  window.addEventListener('message', (e) => {
    const msg = e.data;
    if (msg.type === 'validate_status') {
      document.getElementById('validateMsg').textContent = msg.message;
    }
    if (msg.type === 'validate_result') {
      document.getElementById('validateBtn').disabled = false;
      const el = document.getElementById('validateMsg');
      if (msg.ok) {
        el.className = 'msg ok';
        el.textContent = '✓ Key valid' + (msg.model ? ' (' + msg.model + ')' : '');
        setTimeout(() => go(3), 500);
      } else {
        el.className = 'msg err';
        el.textContent = '✗ Invalid key — ' + (msg.message || 'check and retry');
      }
    }
    if (msg.type === 'finish_error') {
      const el = document.getElementById('finishMsg');
      el.className = 'msg err';
      el.textContent = msg.message;
    }
    if (msg.type === 'ready') {
      go(4);
    }
  });
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

/** Used by status bar when no key is set. */
export function getWorkspaceId(): string {
  const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '';
  return crypto.createHash('md5').update(folder).digest('hex').slice(0, 12);
}
