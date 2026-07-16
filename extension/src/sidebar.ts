/**
 * Jessie — extension/src/sidebar.ts
 * Webview sidebar:
 * - Live status feed (step by step what Jessie is doing)
 * - Prompt approval panel (original vs improved, approve/edit/reject)
 * - Result display (code, quality score, memory note, request count)
 */

import * as vscode from 'vscode';

interface ApprovalResult {
    approved: boolean;
    editedPrompt?: string;
}

interface ResultData {
    code: string;
    qualityScore: number;
    memoryNote: string;
    promptDiff: string;
    requestCount: number;
}

export class JessieSidebar implements vscode.WebviewViewProvider {
    private _view?: vscode.WebviewView;
    private _approvalResolve?: (result: ApprovalResult) => void;

    constructor(private readonly _extensionUri: vscode.Uri) {}

    resolveWebviewView(webviewView: vscode.WebviewView) {
        this._view = webviewView;
        webviewView.webview.options = { enableScripts: true };
        webviewView.webview.html = this._getHtml();

        // Handle messages from webview (approval buttons + nav)
        webviewView.webview.onDidReceiveMessage(msg => {
            if (msg.type === 'approve' && this._approvalResolve) {
                this._approvalResolve({ approved: true, editedPrompt: msg.editedPrompt });
                this._approvalResolve = undefined;
            }
            if (msg.type === 'reject' && this._approvalResolve) {
                this._approvalResolve({ approved: false });
                this._approvalResolve = undefined;
            }
            if (msg.type === 'copy') {
                vscode.env.clipboard.writeText(msg.text);
                vscode.window.showInformationMessage('Code copied to clipboard');
            }
            if (msg.type === 'command' && typeof msg.command === 'string') {
                vscode.commands.executeCommand(msg.command);
            }
        });
    }

    clearAndShow() {
        this._view?.webview.postMessage({ type: 'clear' });
        this._view?.show?.(true);
    }

    addStatus(message: string) {
        this._view?.webview.postMessage({ type: 'status', message });
    }

    showPromptApproval(diff: string, improvedPrompt: string) {
        this._view?.webview.postMessage({
            type: 'approval',
            diff,
            improvedPrompt,
        });
    }

    waitForApproval(): Promise<ApprovalResult | null> {
        return new Promise(resolve => {
            this._approvalResolve = resolve;
            // Auto-reject after 5 minutes
            setTimeout(() => {
                if (this._approvalResolve) {
                    this._approvalResolve = undefined;
                    resolve(null);
                }
            }, 5 * 60 * 1000);
        });
    }

    showResult(data: ResultData) {
        this._view?.webview.postMessage({ type: 'result', ...data });
    }

    private _getHtml(): string {
        return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: var(--vscode-font-family);
    font-size: var(--vscode-font-size);
    color: var(--vscode-foreground);
    background: var(--vscode-sideBar-background);
    padding: 12px;
  }
  h2 { font-size: 13px; font-weight: 600; margin-bottom: 10px; opacity: .7; letter-spacing: .05em; text-transform: uppercase; }
  .status-feed { margin-bottom: 14px; }
  .status-item { font-size: 12px; padding: 4px 0; border-bottom: 1px solid var(--vscode-widget-border); opacity: .85; }
  .status-item:last-child { opacity: 1; font-weight: 500; }

  /* Approval panel */
  .approval { background: var(--vscode-editor-background); border: 1px solid var(--vscode-focusBorder); border-radius: 6px; padding: 12px; margin-bottom: 12px; }
  .approval h3 { font-size: 12px; font-weight: 600; margin-bottom: 8px; color: var(--vscode-textLink-foreground); }
  .diff-box { font-size: 11px; font-family: var(--vscode-editor-font-family); background: var(--vscode-textBlockQuote-background); border-radius: 4px; padding: 8px; margin-bottom: 10px; white-space: pre-wrap; max-height: 200px; overflow-y: auto; }
  .edit-area { width: 100%; font-family: var(--vscode-editor-font-family); font-size: 11px; background: var(--vscode-input-background); color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border); border-radius: 4px; padding: 6px; resize: vertical; min-height: 80px; margin-bottom: 8px; }
  .btn-row { display: flex; gap: 6px; }
  .btn { padding: 5px 12px; font-size: 12px; border: none; border-radius: 4px; cursor: pointer; font-family: inherit; }
  .btn-approve { background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
  .btn-approve:hover { background: var(--vscode-button-hoverBackground); }
  .btn-reject { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
  .btn-reject:hover { opacity: .8; }

  /* Result panel */
  .result { margin-top: 10px; }
  .score-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
  .score-label { font-size: 11px; opacity: .7; }
  .score-num { font-size: 13px; font-weight: 600; }
  .score-good { color: #4caf50; }
  .score-warn { color: #ff9800; }
  .code-block { font-family: var(--vscode-editor-font-family); font-size: 11px; background: var(--vscode-editor-background); border: 1px solid var(--vscode-widget-border); border-radius: 4px; padding: 10px; white-space: pre-wrap; overflow-x: auto; max-height: 400px; overflow-y: auto; margin-bottom: 8px; }
  .meta { font-size: 11px; opacity: .6; margin-bottom: 4px; }
  .memory-note { font-size: 11px; color: #4caf50; margin-top: 6px; }
  .copy-btn { font-size: 11px; padding: 3px 10px; }
  #empty { font-size: 12px; opacity: .5; margin-top: 8px; text-align: center; }
  .nav { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
  .nav button {
    text-align: left; padding: 8px 10px; border-radius: 6px; border: 1px solid var(--vscode-widget-border);
    background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground);
    cursor: pointer; font-family: inherit; font-size: 12px;
  }
  .nav button:hover { background: var(--vscode-button-secondaryHoverBackground); }
  .nav .hint { font-size: 10px; opacity: .65; margin-top: 2px; }
</style>
</head>
<body>
<div class="nav" id="home-nav">
  <h2>Jessie AI</h2>
  <button onclick="runCmd('jessie.ask')">Ask Jessie<span class="hint">Ctrl+Shift+J · prompt coach</span></button>
  <button onclick="runCmd('jessie.reviewProject')">Code Review<span class="hint">Azure branch or local folder</span></button>
  <button onclick="runCmd('jessie.mergeReview')">Merge Review<span class="hint">Azure base → head + Claude impact</span></button>
  <button onclick="runCmd('jessie.history')">History<span class="hint">Past reviews &amp; open web dashboard</span></button>
  <button onclick="runCmd('jessie.info')">Info<span class="hint">Claude API key + feature guide</span></button>
  <button onclick="runCmd('jessie.settings')">Settings<span class="hint">User ID, backend, PAT</span></button>
  <button onclick="runCmd('jessie.tour')">How to use</button>
</div>
<div id="empty" style="display:none">Press Ctrl+Shift+J to ask Jessie</div>
<div id="status-section" style="display:none">
  <h2>Jessie — Live</h2>
  <div class="status-feed" id="status-feed"></div>
</div>
<div id="approval-section" style="display:none">
  <div class="approval">
    <h3>✍️ Jessie improved your prompt</h3>
    <div class="diff-box" id="diff-content"></div>
    <p style="font-size:11px;opacity:.6;margin-bottom:6px">Edit the improved prompt if needed, then approve:</p>
    <textarea class="edit-area" id="edit-prompt"></textarea>
    <div class="btn-row">
      <button class="btn btn-approve" onclick="approve()">✅ Approve &amp; send to Copilot</button>
      <button class="btn btn-reject" onclick="reject()">❌ Cancel</button>
    </div>
  </div>
</div>
<div id="result-section" style="display:none">
  <div class="result">
    <div class="score-bar">
      <span class="score-label">Quality</span>
      <span class="score-num" id="score-num"></span>
      <span class="score-label" id="score-label"></span>
    </div>
    <div class="code-block" id="code-content"></div>
    <div class="btn-row" style="margin-bottom:8px">
      <button class="btn btn-approve copy-btn" onclick="copyCode()">📋 Copy code</button>
    </div>
    <div class="meta" id="request-count"></div>
    <div class="memory-note" id="memory-note"></div>
  </div>
</div>

<script>
  const vscode = acquireVsCodeApi();
  let currentCode = '';

  window.addEventListener('message', e => {
    const msg = e.data;

    if (msg.type === 'clear') {
      document.getElementById('empty').style.display = 'none';
      document.getElementById('status-section').style.display = 'block';
      document.getElementById('approval-section').style.display = 'none';
      document.getElementById('result-section').style.display = 'none';
      document.getElementById('status-feed').innerHTML = '';
    }

    if (msg.type === 'status') {
      document.getElementById('status-section').style.display = 'block';
      const feed = document.getElementById('status-feed');
      const item = document.createElement('div');
      item.className = 'status-item';
      item.textContent = msg.message;
      feed.appendChild(item);
      feed.scrollTop = feed.scrollHeight;
    }

    if (msg.type === 'approval') {
      document.getElementById('approval-section').style.display = 'block';
      document.getElementById('diff-content').textContent = msg.diff || msg.improvedPrompt;
      document.getElementById('edit-prompt').value = msg.improvedPrompt;
    }

    if (msg.type === 'result') {
      document.getElementById('approval-section').style.display = 'none';
      document.getElementById('result-section').style.display = 'block';
      currentCode = msg.code;

      const scoreNum = document.getElementById('score-num');
      scoreNum.textContent = msg.qualityScore + '/100';
      scoreNum.className = 'score-num ' + (msg.qualityScore >= 70 ? 'score-good' : 'score-warn');
      document.getElementById('score-label').textContent = msg.qualityScore >= 70 ? '✅' : '⚠️';
      document.getElementById('code-content').textContent = msg.code;
      document.getElementById('request-count').textContent = msg.requestCount
        ? 'Jessie requests today: ' + msg.requestCount : '';
      document.getElementById('memory-note').textContent = msg.memoryNote || '';
    }
  });

  function approve() {
    const edited = document.getElementById('edit-prompt').value;
    vscode.postMessage({ type: 'approve', editedPrompt: edited });
    document.getElementById('approval-section').style.display = 'none';
  }
  function reject() {
    vscode.postMessage({ type: 'reject' });
    document.getElementById('approval-section').style.display = 'none';
  }
  function copyCode() {
    vscode.postMessage({ type: 'copy', text: currentCode });
  }
  function runCmd(command) {
    vscode.postMessage({ type: 'command', command });
  }
</script>
</body>
</html>`;
    }
}
