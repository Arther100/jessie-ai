import * as vscode from 'vscode';

export function showTour(context: vscode.ExtensionContext) {
    const panel = vscode.window.createWebviewPanel(
        'jessieTour',
        'Jessie — How to Use',
        vscode.ViewColumn.One,
        { enableScripts: true }
    );
    panel.webview.html = getTourHtml();
}

function getTourHtml(): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  body {
    font-family: var(--vscode-font-family);
    color: var(--vscode-foreground);
    background: var(--vscode-editor-background);
    margin: 0; padding: 0;
    display: flex; flex-direction: column; height: 100vh;
  }
  .slide { display: none; flex-direction: column; justify-content: center;
           align-items: flex-start; padding: 48px 64px; flex: 1; max-width: 680px; }
  .slide.active { display: flex; }
  .step-badge { font-size: 11px; font-weight: 600; letter-spacing: .1em;
                text-transform: uppercase; color: var(--vscode-textLink-foreground);
                margin-bottom: 12px; }
  h1 { font-size: 28px; font-weight: 700; margin-bottom: 16px;
       color: var(--vscode-foreground); line-height: 1.2; }
  p  { font-size: 14px; line-height: 1.7; color: var(--vscode-descriptionForeground);
       margin-bottom: 14px; }
  .highlight { color: var(--vscode-foreground); font-weight: 600; }
  .kbd { display: inline-block; padding: 2px 8px; border-radius: 4px;
         border: 1px solid var(--vscode-widget-border);
         background: var(--vscode-editor-background);
         font-family: var(--vscode-editor-font-family);
         font-size: 12px; color: var(--vscode-foreground); }
  .flow { display: flex; align-items: center; gap: 10px; margin: 20px 0; flex-wrap: wrap; }
  .flow-step { background: var(--vscode-input-background); border: 1px solid var(--vscode-widget-border);
               border-radius: 6px; padding: 8px 14px; font-size: 13px; }
  .flow-arrow { color: var(--vscode-textLink-foreground); font-size: 18px; }
  .tip { background: var(--vscode-inputValidation-infoBackground, rgba(0,120,212,.15));
         border-left: 3px solid var(--vscode-textLink-foreground);
         padding: 10px 14px; border-radius: 0 6px 6px 0;
         font-size: 13px; margin-top: 14px; }

  /* Nav */
  .nav { display: flex; align-items: center; justify-content: space-between;
         padding: 16px 64px 24px; border-top: 1px solid var(--vscode-widget-border); }
  .dots { display: flex; gap: 6px; }
  .dot { width: 8px; height: 8px; border-radius: 50%;
         background: var(--vscode-widget-border); cursor: pointer; transition: background .2s; }
  .dot.active { background: var(--vscode-textLink-foreground); }
  .btn { padding: 8px 20px; border: none; border-radius: 6px; font-size: 13px;
         cursor: pointer; font-family: inherit; }
  .btn-primary { background: var(--vscode-button-background);
                 color: var(--vscode-button-foreground); }
  .btn-primary:hover { background: var(--vscode-button-hoverBackground); }
  .btn-secondary { background: var(--vscode-button-secondaryBackground);
                   color: var(--vscode-button-secondaryForeground); }
  .btn-secondary:hover { opacity: .8; }
</style>
</head>
<body>

<!-- Slide 1: What is Jessie -->
<div class="slide active" id="slide-0">
  <div class="step-badge">1 of 6 — Overview</div>
  <h1>⚡ Welcome to Jessie</h1>
  <p>Jessie is an <span class="highlight">AI coding agent</span> that sits between you and GitHub Copilot. Instead of sending your raw prompt directly, Jessie:</p>
  <div class="flow">
    <div class="flow-step">Your idea</div>
    <div class="flow-arrow">→</div>
    <div class="flow-step">🧠 Jessie coaches it</div>
    <div class="flow-arrow">→</div>
    <div class="flow-step">🤖 Copilot generates</div>
    <div class="flow-arrow">→</div>
    <div class="flow-step">✅ Quality checked</div>
  </div>
  <p>You get better code, with less back-and-forth.</p>
</div>

<!-- Slide 2: How to trigger -->
<div class="slide" id="slide-1">
  <div class="step-badge">2 of 6 — Triggering Jessie</div>
  <h1>Three ways to ask Jessie</h1>
  <p><span class="kbd">Ctrl+Shift+J</span> &nbsp;/&nbsp; <span class="kbd">Cmd+Shift+J</span><br>
     The fastest way — works from anywhere in VS Code.</p>
  <p>Or open the <span class="highlight">Jessie panel</span> in the Activity Bar (⚡ icon on the left sidebar), then use the Command Palette:</p>
  <p><span class="kbd">Ctrl+Shift+P</span> → type <span class="highlight">Ask Jessie</span></p>
  <div class="tip">💡 Tip: You don't need to open a file first — but if you have one open, Jessie automatically reads up to 4,000 characters of context from it.</div>
</div>

<!-- Slide 3: Writing your prompt -->
<div class="slide" id="slide-2">
  <div class="step-badge">3 of 6 — Writing prompts</div>
  <h1>Just describe what you want</h1>
  <p>You don't need to write perfect prompts. Jessie will improve them. Write naturally:</p>
  <p style="margin-left:16px">
    ✅ <em>"fix the login error"</em><br>
    ✅ <em>"add a date picker to the booking form"</em><br>
    ✅ <em>"refactor this function to be async"</em>
  </p>
  <p>Jessie will enrich your prompt with:</p>
  <p style="margin-left:16px">
    • The file you have open and any selected code<br>
    • Relevant patterns from your codebase memory<br>
    • Your team's coding conventions
  </p>
  <div class="tip">💡 Tip: Select the specific code you want to change before pressing Ctrl+Shift+J — Jessie will focus on just that part.</div>
</div>

<!-- Slide 4: Approving prompts -->
<div class="slide" id="slide-3">
  <div class="step-badge">4 of 6 — Prompt approval</div>
  <h1>Review before Copilot sees it</h1>
  <p>After Jessie improves your prompt, it shows you a <span class="highlight">diff in the sidebar</span> so you stay in control:</p>
  <p style="margin-left:16px">
    <strong>✅ Approve</strong> — sends the improved prompt to Copilot as-is<br>
    <strong>✏️ Edit then Approve</strong> — tweak the prompt in the text area first<br>
    <strong>❌ Cancel</strong> — abort the request entirely
  </p>
  <div class="tip">💡 Tip: If Jessie's improvement misses the point, edit it directly in the text area — your edit is what Copilot receives.</div>
</div>

<!-- Slide 5: Reading results -->
<div class="slide" id="slide-4">
  <div class="step-badge">5 of 6 — Reading results</div>
  <h1>What you get back</h1>
  <p>The Jessie sidebar shows the result with three pieces of information:</p>
  <p style="margin-left:16px">
    <strong>Quality score (0–100)</strong> — Jessie checks the output before showing it. If it scores below 70, Jessie automatically retries (up to 2 times).<br><br>
    <strong>Generated code</strong> — ready to copy with one click.<br><br>
    <strong>Memory note</strong> — if Jessie saved or reused a pattern from your codebase, it tells you here.
  </p>
  <div class="tip">💡 Tip: If a component already exists in your codebase, Jessie will skip Copilot entirely and reuse it.</div>
</div>

<!-- Slide 6: Settings -->
<div class="slide" id="slide-5">
  <div class="step-badge">6 of 6 — Settings</div>
  <h1>Settings &amp; Claude</h1>
  <p>Open <span class="kbd">Jessie: Info</span> from the sidebar to add your <strong>Claude API key</strong> (required for Code Review &amp; Merge Review — same as web Settings → Info).</p>
  <p style="margin-left:16px;margin-top:10px">
    Also set via <span class="kbd">Ctrl+,</span> → search <span class="highlight">jessie</span>:<br><br>
    <strong>jessie.userId</strong> — your name or team ID for quotas.<br><br>
    <strong>jessie.backendUrl</strong> — defaults to <code>http://localhost:8000</code>.
  </p>
  <div class="tip">🎉 You're all set! Press <span class="kbd">Ctrl+Shift+J</span> to ask Jessie, or run Code / Merge Review.</div>
</div>

<!-- Nav bar -->
<div class="nav">
  <button class="btn btn-secondary" id="prev-btn" onclick="prev()" style="visibility:hidden">← Back</button>
  <div class="dots">
    <div class="dot active" onclick="goTo(0)"></div>
    <div class="dot" onclick="goTo(1)"></div>
    <div class="dot" onclick="goTo(2)"></div>
    <div class="dot" onclick="goTo(3)"></div>
    <div class="dot" onclick="goTo(4)"></div>
    <div class="dot" onclick="goTo(5)"></div>
  </div>
  <button class="btn btn-primary" id="next-btn" onclick="next()">Next →</button>
</div>

<script>
  let current = 0;
  const total = 6;

  function goTo(n) {
    document.getElementById('slide-' + current).classList.remove('active');
    document.querySelectorAll('.dot')[current].classList.remove('active');
    current = n;
    document.getElementById('slide-' + current).classList.add('active');
    document.querySelectorAll('.dot')[current].classList.add('active');
    document.getElementById('prev-btn').style.visibility = current === 0 ? 'hidden' : 'visible';
    document.getElementById('next-btn').textContent = current === total - 1 ? '✅ Done' : 'Next →';
  }
  function next() {
    if (current < total - 1) { goTo(current + 1); }
    else { window.close(); }
  }
  function prev() { if (current > 0) goTo(current - 1); }
</script>
</body>
</html>`;
}
