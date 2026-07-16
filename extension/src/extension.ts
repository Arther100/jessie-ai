/**
 * Jessie — extension/src/extension.ts
 *
 * Full flow:
 * 1. On activate → check backend health → guided setup if not running
 * 2. Developer presses Ctrl+Shift+J → sidebar opens
 * 3. Extension collects VS Code context (file, selection, error)
 * 4. POST /prepare → get improved prompt + complexity score
 * 5. Show prompt diff in sidebar → developer approves / edits / rejects
 * 6. Call Copilot via vscode.lm with complexity-matched model
 * 7. POST /resume with Copilot output → quality check
 * 8. If needs_retry → call Copilot again with retry_prompt (max 2)
 * 9. Show final result in sidebar with status feed
 */

import * as vscode from 'vscode';
import axios from 'axios';
import { JessieSidebar } from './sidebar';
import { setupWalkthrough } from './setup';
import { showTour } from './tour';
import { registerJessieChat } from './jessieChat';
import { JessieProxy } from './proxy';
import { JessieCodeReview } from './codeReview';
import { JessieMergeReview } from './mergeReview';
import { showJessieHistory, showJessieSettings } from './history';
import { showJessieInfo } from './info';

let statusBarItem: vscode.StatusBarItem;
let sidebar: JessieSidebar;

let _proxy: JessieProxy | undefined;
let _reviewer: JessieCodeReview | undefined;
let _merger: JessieMergeReview | undefined;

export function getProxy(): JessieProxy | undefined { return _proxy; }
export function getReviewer(): JessieCodeReview | undefined { return _reviewer; }
export function getMerger(): JessieMergeReview | undefined { return _merger; }

export async function activate(context: vscode.ExtensionContext) {
    registerJessieChat(context);

    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.text = '$(sparkle) Jessie';
    statusBarItem.tooltip = 'Jessie AI — click to ask';
    statusBarItem.command = 'jessie.ask';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    const backendUrlResolved = getConfig('backendUrl') || 'http://localhost:8000';
    _proxy    = new JessieProxy(statusBarItem, backendUrlResolved);
    _reviewer = new JessieCodeReview(statusBarItem, backendUrlResolved, context);
    _merger   = new JessieMergeReview(statusBarItem, context);

    sidebar = new JessieSidebar(context.extensionUri);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider('jessie.panel', sidebar)
    );

    const backendUrl = backendUrlResolved;
    const alive = await checkBackend(backendUrl);
    if (!alive) {
        setStatus('$(warning) Jessie — backend offline', 'warning');
        vscode.window.showWarningMessage(
            'Jessie backend is not running.',
            'Setup Jessie'
        ).then(choice => {
            if (choice === 'Setup Jessie') {
                vscode.commands.executeCommand('jessie.setup');
            }
        });
    } else {
        setStatus('$(sparkle) Jessie — ready');
    }

    context.subscriptions.push(
        vscode.commands.registerCommand('jessie.ask', async () => {
            const userId = getConfig('userId');
            const backendUrl = getConfig('backendUrl');

            if (!userId) {
                const entered = await vscode.window.showInputBox({
                    prompt: 'Enter your name or user ID for Jessie',
                    placeHolder: 'e.g. vijay',
                });
                if (!entered) return;
                await vscode.workspace.getConfiguration('jessie').update('userId', entered, true);
            }

            const prompt = await vscode.window.showInputBox({
                prompt: 'Ask Jessie — describe your coding task',
                placeHolder: 'e.g. fix the login error, add a button to the header...',
            });
            if (!prompt) return;

            await runJessie(prompt, userId || getConfig('userId'), backendUrl);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('jessie.setup', () => {
            setupWalkthrough(context, async () => {
                const alive = await checkBackend(getConfig('backendUrl'));
                setStatus(
                    alive ? '$(sparkle) Jessie — ready' : '$(warning) Jessie — backend offline',
                    alive ? 'normal' : 'warning'
                );
            });
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('jessie.tour', () => {
            showTour(context);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('jessie.reviewProject', async (uri?: vscode.Uri) => {
            const reviewer = getReviewer();
            if (!reviewer) { vscode.window.showErrorMessage('Jessie reviewer not initialised'); return; }
            await reviewer.startReview('command_palette', uri?.fsPath);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('jessie.reviewAzure', async () => {
            const reviewer = getReviewer();
            if (!reviewer) { vscode.window.showErrorMessage('Jessie reviewer not initialised'); return; }
            await reviewer.startAzureReview('command_palette');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('jessie.mergeReview', async () => {
            const merger = getMerger();
            if (!merger) { vscode.window.showErrorMessage('Jessie merge reviewer not initialised'); return; }
            await merger.start();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('jessie.history', async () => {
            await showJessieHistory();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('jessie.settings', async () => {
            await showJessieSettings(context);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('jessie.info', async () => {
            await showJessieInfo(context);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('jessie.showRequests', async () => {
            const userId = getConfig('userId');
            const backendUrl = getConfig('backendUrl');
            if (!userId) { vscode.window.showWarningMessage('Set jessie.userId in settings first'); return; }
            try {
                const r = await axios.get(`${backendUrl}/requests/${userId}`);
                vscode.window.showInformationMessage(
                    `Jessie — ${r.data.user_id}: ${r.data.requests_today} requests today`
                );
            } catch { vscode.window.showErrorMessage('Could not reach Jessie backend'); }
        })
    );
}


// ── Core flow ──────────────────────────────────────────────────────────────

async function runJessie(prompt: string, userId: string, backendUrl: string) {
    const editor = vscode.window.activeTextEditor;
    const openFileContent = editor?.document.getText().slice(0, 4000) || '';
    const selectedCode    = editor?.document.getText(editor.selection) || '';
    const language        = editor?.document.languageId || '';
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
    const workspaceId     = Buffer.from(workspaceFolder).toString('base64').slice(0, 12);

    sidebar.clearAndShow();

    try {
        // ── Phase 1: /prepare ────────────────────────────────────────────
        setStatus('$(loading~spin) Jessie — coaching prompt...');
        sidebar.addStatus('🚀 Jessie started...');

        const prepRes = await axios.post(`${backendUrl}/prepare`, {
            prompt, user_id: userId, workspace_id: workspaceId,
            language, open_file_content: openFileContent,
            selected_code: selectedCode, error_message: '',
        });
        const prep = prepRes.data;

        // Show live status updates from backend
        prep.status_updates?.forEach((s: string) => sidebar.addStatus(s));

        // Component reuse — no Copilot call needed
        if (prep.component_exists) {
            sidebar.showResult({
                code: prep.generated_code,
                qualityScore: 100,
                memoryNote: `Reused existing component at ${prep.component_path}`,
                promptDiff: '',
                requestCount: 0,
            });
            setStatus('$(sparkle) Jessie — done (reused component)');
            return;
        }

        // ── Prompt approval ───────────────────────────────────────────────
        setStatus('$(eye) Jessie — awaiting your approval...');
        sidebar.showPromptApproval(prep.prompt_diff, prep.improved_prompt);

        const approved = await sidebar.waitForApproval();
        if (!approved) {
            setStatus('$(sparkle) Jessie — cancelled');
            sidebar.addStatus('❌ Cancelled by developer');
            return;
        }

        const finalPrompt = approved.editedPrompt || prep.improved_prompt;
        const contextStr  = prep.context_chunks?.join('\n\n') || '';
        const copilotPrompt = contextStr
            ? `${contextStr}\n\n${finalPrompt}`
            : finalPrompt;

        // ── Phase 2: Call Copilot ─────────────────────────────────────────
        let generatedCode = '';
        let modelUsed     = '';
        let retryCount    = 0;
        let retryPrompt   = copilotPrompt;
        let qualityFeedback = '';

        while (retryCount <= 2) {
            setStatus(`$(loading~spin) Jessie — calling Copilot... (attempt ${retryCount + 1})`);
            sidebar.addStatus(`🤖 Calling Copilot (attempt ${retryCount + 1}/3)...`);

            const copilotResult = await callCopilot(retryPrompt, prep.complexity_score);
            generatedCode = copilotResult.text;
            modelUsed     = copilotResult.model;

            sidebar.addStatus(`🔎 Quality Analyser — checking output...`);

            // ── Phase 3: /resume ──────────────────────────────────────────
            const resumeRes = await axios.post(`${backendUrl}/resume`, {
                improved_prompt:  finalPrompt,
                prompt_diff:      prep.prompt_diff,
                context_chunks:   prep.context_chunks,
                complexity_score: prep.complexity_score,
                component_exists: false,
                component_path:   '',
                generated_code:   generatedCode,
                model_used:       modelUsed,
                user_id:          userId,
                workspace_id:     workspaceId,
                language,
                open_file_content: openFileContent,
                selected_code:    selectedCode,
                retry_count:      retryCount,
                quality_feedback: qualityFeedback,
            });

            const resume = resumeRes.data;
            resume.status_updates?.forEach((s: string) => sidebar.addStatus(s));

            if (!resume.needs_retry) {
                // ── Done ──────────────────────────────────────────────────
                sidebar.showResult({
                    code:         resume.final_response,
                    qualityScore: resume.quality_score,
                    memoryNote:   resume.memory_note,
                    promptDiff:   prep.prompt_diff,
                    requestCount: resume.request_count,
                });
                setStatus('$(sparkle) Jessie — done');
                return;
            }

            // Retry
            retryPrompt     = resume.retry_prompt;
            qualityFeedback = '';
            retryCount++;
        }

    } catch (err: any) {
        const msg = err.response?.data?.detail || err.message || 'Unknown error';
        sidebar.addStatus(`❌ Error: ${msg}`);
        setStatus('$(error) Jessie — error');
        if (msg.includes('backend')) {
            vscode.window.showErrorMessage('Jessie backend is not running. Run: uvicorn api.main:app --reload');
        }
    }
}


// ── Copilot caller using vscode.lm ────────────────────────────────────────

async function callCopilot(prompt: string, complexityScore: number): Promise<{ text: string; model: string }> {
    // Pick model family based on complexity
    // 1-3 → fast/cheap, 4-7 → standard, 8-10 → most capable
    const family = complexityScore <= 3
        ? 'gpt-4o-mini'
        : complexityScore <= 7
            ? 'gpt-4o'
            : 'claude-sonnet'; // most capable available in Copilot

    const models = await vscode.lm.selectChatModels({ vendor: 'copilot', family });
    const model  = models[0];

    if (!model) {
        // Fallback: any Copilot model
        const fallback = await vscode.lm.selectChatModels({ vendor: 'copilot' });
        if (!fallback[0]) throw new Error('No Copilot model available. Is GitHub Copilot enabled?');
        return callWithModel(fallback[0], prompt);
    }

    return callWithModel(model, prompt);
}

async function callWithModel(model: vscode.LanguageModelChat, prompt: string): Promise<{ text: string; model: string }> {
    const messages = [vscode.LanguageModelChatMessage.User(prompt)];
    const response = await model.sendRequest(messages, {}, new vscode.CancellationTokenSource().token);

    let text = '';
    for await (const chunk of response.text) {
        text += chunk;
    }

    return { text, model: model.name };
}


// ── Helpers ────────────────────────────────────────────────────────────────

function getConfig(key: string): string {
    return vscode.workspace.getConfiguration('jessie').get<string>(key) || '';
}

function setStatus(text: string, type: 'normal' | 'warning' | 'error' = 'normal') {
    statusBarItem.text = text;
    statusBarItem.backgroundColor = type === 'warning'
        ? new vscode.ThemeColor('statusBarItem.warningBackground')
        : type === 'error'
            ? new vscode.ThemeColor('statusBarItem.errorBackground')
            : undefined;
}

async function checkBackend(url: string): Promise<boolean> {
    try {
        await axios.get(`${url}/health`, { timeout: 3000 });
        return true;
    } catch {
        return false;
    }
}

export function deactivate() {}
