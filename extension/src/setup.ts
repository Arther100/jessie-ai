/**
 * Jessie — extension/src/setup.ts
 * Guided setup walkthrough on first install.
 * Checks Python, installs dependencies, starts the backend,
 * confirms everything is working before letting the user in.
 */

import * as vscode from 'vscode';
import * as cp from 'child_process';
import * as path from 'path';
import axios from 'axios';
import { showTour } from './tour';

export async function setupWalkthrough(context: vscode.ExtensionContext, onComplete?: () => void) {
    const panel = vscode.window.createWebviewPanel(
        'jessieSetup',
        'Jessie — Setup',
        vscode.ViewColumn.One,
        { enableScripts: true }
    );

    panel.webview.html = getSetupHtml();

    panel.webview.onDidReceiveMessage(async msg => {
        if (msg.type === 'start_setup') {
            await runSetup(panel, context, onComplete);
        }
        if (msg.type === 'open_settings') {
            vscode.commands.executeCommand('workbench.action.openSettings', 'jessie');
        }
        if (msg.type === 'open_tour') {
            panel.dispose();
            showTour(context);
        }
    });
}

async function runSetup(panel: vscode.WebviewView | any, context: vscode.ExtensionContext, onComplete?: () => void) {
    const send = (step: string, status: 'running' | 'ok' | 'error', detail = '') => {
        panel.webview.postMessage({ type: 'step', step, status, detail });
    };

    // ── Step 1: Find Python ───────────────────────────────────────────────
    send('python', 'running', 'Looking for Python 3.9+...');
    const pythonPath = await findPython();
    if (!pythonPath) {
        send('python', 'error', 'Python 3.9+ not found. Install from python.org and restart VS Code.');
        return;
    }
    send('python', 'ok', `Found: ${pythonPath}`);

    // ── Step 2: Find Jessie backend ───────────────────────────────────────
    send('backend_path', 'running', 'Looking for Jessie backend folder...');
    const backendPath = await findBackendPath(context);
    if (!backendPath) {
        send('backend_path', 'error',
            'Could not find Jessie backend. Clone the repo and set jessie.backendUrl in settings.');
        return;
    }
    send('backend_path', 'ok', `Found at: ${backendPath}`);

    // ── Step 3: Install dependencies ──────────────────────────────────────
    send('deps', 'running', 'Installing Python dependencies (this may take a minute)...');
    const reqFile = path.join(backendPath, 'requirements.txt');
    const installed = await runCommand(pythonPath, ['-m', 'pip', 'install', '-r', reqFile, '-q']);
    if (!installed.ok) {
        send('deps', 'error', `pip install failed: ${installed.stderr}`);
        return;
    }
    send('deps', 'ok', 'All dependencies installed');

    // ── Step 4: Start the backend ─────────────────────────────────────────
    send('server', 'running', 'Starting Jessie backend server...');
    startBackend(pythonPath, backendPath);

    // Wait up to 20 seconds for the server to be ready
    const ready = await waitForBackend('http://localhost:8000', 20);
    if (!ready) {
        send('server', 'error',
            'Backend did not start in time. Check the terminal for errors, or run manually: ' +
            'cd backend && uvicorn api.main:app --reload');
        return;
    }
    send('server', 'ok', 'Jessie backend running on http://localhost:8000');

    // ── Step 5: Done ──────────────────────────────────────────────────────
    panel.webview.postMessage({ type: 'done' });
    onComplete?.();
}

function findPython(): Promise<string | null> {
    return new Promise(resolve => {
        const candidates = ['python3', 'python', 'python3.11', 'python3.10', 'python3.9'];
        let found = 0;
        for (const cmd of candidates) {
            cp.exec(`${cmd} --version`, (err, stdout) => {
                found++;
                if (!err && stdout.includes('Python 3')) {
                    resolve(cmd);
                    return;
                }
                if (found === candidates.length) resolve(null);
            });
        }
    });
}

async function findBackendPath(context: vscode.ExtensionContext): Promise<string | null> {
    // Check common locations
    const candidates = [
        path.join(context.extensionPath, '..', 'backend'),
        path.join(vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '', 'backend'),
    ];
    for (const p of candidates) {
        try {
            await vscode.workspace.fs.stat(vscode.Uri.file(path.join(p, 'requirements.txt')));
            return p;
        } catch {}
    }
    return null;
}

function runCommand(python: string, args: string[]): Promise<{ ok: boolean; stderr: string }> {
    return new Promise(resolve => {
        cp.execFile(python, args, { timeout: 120_000 }, (err, _, stderr) => {
            resolve({ ok: !err, stderr: stderr || '' });
        });
    });
}

function startBackend(_python: string, backendPath: string) {
    // Use a visible terminal so startup errors are readable
    const term = vscode.window.createTerminal({
        name: 'Jessie Backend',
        cwd: backendPath,
    });
    term.show(true);
    term.sendText('python -m uvicorn api.main:app --reload --port 8000');
}

async function waitForBackend(url: string, seconds: number): Promise<boolean> {
    for (let i = 0; i < seconds; i++) {
        await new Promise(r => setTimeout(r, 1000));
        try {
            await axios.get(`${url}/health`, { timeout: 1000 });
            return true;
        } catch {}
    }
    return false;
}

function getSetupHtml(): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 560px; margin: 40px auto; padding: 0 20px;
         color: var(--vscode-foreground);
         background: var(--vscode-editor-background); }
  h1 { font-size: 22px; font-weight: 600; margin-bottom: 6px;
       color: var(--vscode-foreground); }
  p  { font-size: 13px; color: var(--vscode-descriptionForeground); margin-bottom: 24px; }
  .step { display: flex; align-items: flex-start; gap: 12px;
          padding: 10px 0; border-bottom: 1px solid var(--vscode-widget-border, #444);
          font-size: 13px; }
  .icon { width: 20px; text-align: center; flex-shrink: 0; margin-top: 1px; }
  .step-name { font-weight: 500; color: var(--vscode-foreground); }
  .step-detail { font-size: 11px; color: var(--vscode-descriptionForeground); margin-top: 2px; }
  .ok    { color: #4caf50; }
  .error { color: #f44336; }
  .spin  { animation: spin 1s linear infinite; display: inline-block; }
  @keyframes spin { to { transform: rotate(360deg); } }
  button { margin-top: 24px; padding: 10px 24px;
           background: var(--vscode-button-background, #0078d4);
           color: var(--vscode-button-foreground, #fff);
           border: none; border-radius: 6px; font-size: 14px; cursor: pointer; }
  button:hover { background: var(--vscode-button-hoverBackground, #005fa3); }
  .done-box { background: var(--vscode-inputValidation-infoBackground, #1b3a1b);
              border: 1px solid #4caf50; border-radius: 8px;
              padding: 16px; margin-top: 20px; font-size: 13px;
              color: var(--vscode-foreground); display: none; }
  .error-detail { color: #f44336; word-break: break-word; }
  .tour-btn { margin-top: 12px; padding: 8px 20px;
              background: var(--vscode-button-background);
              color: var(--vscode-button-foreground);
              border: none; border-radius: 6px; font-size: 13px;
              cursor: pointer; display: block; }
</style>
</head>
<body>
<h1>⚡ Jessie Setup</h1>
<p>Let's get your Jessie backend running. This only takes a minute and happens once.</p>

<div class="step" id="step-python">
  <span class="icon">○</span>
  <div><div class="step-name">Find Python 3.9+</div><div class="step-detail" id="det-python"></div></div>
</div>
<div class="step" id="step-backend_path">
  <span class="icon">○</span>
  <div><div class="step-name">Find Jessie backend folder</div><div class="step-detail" id="det-backend_path"></div></div>
</div>
<div class="step" id="step-deps">
  <span class="icon">○</span>
  <div><div class="step-name">Install Python dependencies</div><div class="step-detail" id="det-deps"></div></div>
</div>
<div class="step" id="step-server">
  <span class="icon">○</span>
  <div><div class="step-name">Start Jessie backend</div><div class="step-detail" id="det-server"></div></div>
</div>

<button id="start-btn" onclick="start()">Start Setup</button>

<div class="done-box" id="done-box">
  ✅ Jessie is ready! Press <strong>Ctrl+Shift+J</strong> to start coding.
  <button class="tour-btn" onclick="openTour()">📖 Take the tour →</button>
</div>

<script>
  const vscode = acquireVsCodeApi();
  function start() {
    document.getElementById('start-btn').disabled = true;
    document.getElementById('start-btn').textContent = 'Setting up...';
    vscode.postMessage({ type: 'start_setup' });
  }
  function openTour() { vscode.postMessage({ type: 'open_tour' }); }
  window.addEventListener('message', e => {
    const msg = e.data;
    if (msg.type === 'step') {
      const icon = document.querySelector('#step-' + msg.step + ' .icon');
      const det  = document.getElementById('det-' + msg.step);
      if (msg.status === 'running') { icon.textContent = '⟳'; icon.className = 'icon spin'; }
      if (msg.status === 'ok')      { icon.textContent = '✓'; icon.className = 'icon ok'; }
      if (msg.status === 'error')   { icon.textContent = '✗'; icon.className = 'icon error'; }
      if (det) {
        det.textContent = msg.detail;
        det.className = 'step-detail' + (msg.status === 'error' ? ' error-detail' : '');
      }
    }
    if (msg.type === 'done') {
      document.getElementById('done-box').style.display = 'block';
      document.getElementById('start-btn').style.display = 'none';
    }
  });
</script>
</body>
</html>`;
}
