import * as vscode from 'vscode';
import axios from 'axios';
import { getProxy, getReviewer, getMerger } from './extension';

export function registerJessieChat(context: vscode.ExtensionContext) {
    const participant = vscode.chat.createChatParticipant('jessie', handleChat);
    participant.iconPath = vscode.Uri.joinPath(context.extensionUri, 'media', 'jessie.svg');
    context.subscriptions.push(participant);
}

async function handleChat(
    request: vscode.ChatRequest,
    _chatContext: vscode.ChatContext,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken
) {
    const lower = request.prompt.toLowerCase();

    const MERGE_KEYWORDS = [
        'merge review', 'review merge', 'review pr', 'pull request review',
        'branch diff', 'compare branches', 'merge impact',
    ];
    if (MERGE_KEYWORDS.some(kw => lower.includes(kw))) {
        const merger = getMerger();
        if (merger) {
            stream.markdown('🔀 **Starting Merge Review** (Azure URL → branches → Claude impact)…\n\n');
            await merger.start();
            return;
        }
    }

    const REVIEW_KEYWORDS = [
        'review', 'audit', 'check my code', 'analyse', 'analyze',
        'scan project', 'code quality', 'find issues',
    ];
    const isReviewRequest = REVIEW_KEYWORDS.some(kw => lower.includes(kw));
    if (isReviewRequest) {
        const reviewer = getReviewer();
        if (reviewer) {
            await reviewer.handleChatTrigger(request.prompt, stream);
            return;
        }
    }

    const cfg        = vscode.workspace.getConfiguration('jessie');
    const backendUrl = cfg.get<string>('backendUrl') || 'https://jessie-ai-xpv2.onrender.com';
    const userId     = cfg.get<string>('userId') || 'anonymous';

    const editor          = vscode.window.activeTextEditor;
    const openFileContent = editor?.document.getText().slice(0, 4000) || '';
    const selectedCode    = editor?.document.getText(editor.selection) || '';
    const language        = editor?.document.languageId || '';
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
    const workspaceId     = Buffer.from(workspaceFolder).toString('base64').slice(0, 12);

    // ── Gateway path: route through full pipeline via /proxy SSE ─────────────
    // Prefer the gateway (Claude direct) when backend is alive.
    // Falls back to Copilot path below if backend is offline.
    const proxy = getProxy();
    if (proxy && await proxy.isBackendAlive()) {
        const editor          = vscode.window.activeTextEditor;
        const openFileContent = editor?.document.getText().slice(0, 3000) ?? '';
        const selectedCode    = editor?.document.getText(editor.selection) ?? '';
        const language        = editor?.document.languageId ?? '';

        const gatewayResponse = await proxy.interceptAndProcess(request.prompt, {
            language,
            openFileContent,
            selectedCode,
        });

        if (gatewayResponse !== null) {
            stream.markdown(gatewayResponse);
            return;
        }
        // null → fall through to Copilot path
        stream.markdown(
            `> ⚠️ Jessie gateway error — falling back to direct Copilot\n\n`
        );
    }

    // ── Phase 1: Prepare (prompt coach + RAG) ────────────────────────────────
    stream.progress('Jessie — coaching your prompt...');

    let prep: any;
    try {
        const res = await axios.post(`${backendUrl}/prepare`, {
            prompt:            request.prompt,
            user_id:           userId,
            workspace_id:      workspaceId,
            language,
            open_file_content: openFileContent,
            selected_code:     selectedCode,
            error_message:     '',
        });
        prep = res.data;
    } catch {
        stream.markdown(
            `❌ **Jessie backend is not running.**\n\n` +
            `Start it: \`Ctrl+Shift+P\` → **Jessie: Setup Jessie Backend**\n\n` +
            `Or manually:\n\`\`\`\ncd d:\\jessie_v2\\jessie\\backend\npython -m uvicorn api.main:app --reload\n\`\`\``
        );
        return;
    }

    // Component reuse — no Copilot call needed
    if (prep.component_exists) {
        stream.markdown(`♻️ **Reusing existing component** at \`${prep.component_path}\`\n\n\`\`\`${language}\n${prep.generated_code}\n\`\`\``);
        return;
    }

    // Show brief coaching summary
    stream.markdown(`✍️ **Prompt coached** — added ${language ? `\`${language}\` context, ` : ''}file context & output constraints\n\n`);

    const copilotPrompt = prep.context_chunks?.length
        ? `${prep.context_chunks.join('\n\n')}\n\n${prep.improved_prompt}`
        : prep.improved_prompt;

    // ── Phase 2: Copilot → quality check loop (auto retry ×2) ────────────────
    let generatedCode = '';
    let modelUsed     = '';

    for (let attempt = 0; attempt <= 2; attempt++) {
        if (attempt > 0) {
            stream.progress(`Quality check failed — retrying (${attempt}/2)...`);
        } else {
            stream.progress(`Jessie — calling Copilot (model chosen for complexity ${prep.complexity_score}/10)...`);
        }

        const result = await callCopilot(copilotPrompt, prep.complexity_score, token);
        if (!result) {
            stream.markdown(`❌ No Copilot model found. Make sure **GitHub Copilot** is installed and signed in.`);
            return;
        }
        generatedCode = result.text;
        modelUsed     = result.model;

        stream.progress('Jessie — quality checking output...');

        let resume: any;
        try {
            const res = await axios.post(`${backendUrl}/resume`, {
                improved_prompt:   prep.improved_prompt,
                prompt_diff:       prep.prompt_diff,
                context_chunks:    prep.context_chunks,
                complexity_score:  prep.complexity_score,
                component_exists:  false,
                component_path:    '',
                generated_code:    generatedCode,
                model_used:        modelUsed,
                user_id:           userId,
                workspace_id:      workspaceId,
                language,
                open_file_content: openFileContent,
                selected_code:     selectedCode,
                retry_count:       attempt,
                quality_feedback:  '',
            });
            resume = res.data;
        } catch {
            // Resume unavailable — show raw Copilot output
            stream.markdown(generatedCode);
            return;
        }

        if (!resume.needs_retry) {
            const scoreEmoji = resume.quality_score >= 70 ? '✅' : '⚠️';
            stream.markdown(
                `${scoreEmoji} **Quality ${resume.quality_score}/100** · \`${modelUsed}\`\n\n` +
                (resume.final_response || generatedCode)
            );
            if (resume.memory_note) {
                stream.markdown(`\n\n💾 *${resume.memory_note}*`);
            }
            return;
        }
    }

    // Max retries — show best attempt
    stream.markdown(`⚠️ **Quality below threshold after 2 retries — best result:**\n\n${generatedCode}`);
}

async function callCopilot(
    prompt: string,
    complexity: number,
    token: vscode.CancellationToken
): Promise<{ text: string; model: string } | null> {
    const family = complexity <= 3 ? 'gpt-4o-mini'
        : complexity <= 7          ? 'gpt-4o'
        :                            'claude-sonnet';

    let models = await vscode.lm.selectChatModels({ vendor: 'copilot', family });
    if (!models.length) {
        models = await vscode.lm.selectChatModels({ vendor: 'copilot' });
    }
    if (!models.length) return null;

    const model    = models[0];
    const messages = [vscode.LanguageModelChatMessage.User(prompt)];
    const response = await model.sendRequest(messages, {}, token);

    let text = '';
    for await (const chunk of response.text) { text += chunk; }
    return { text, model: model.name };
}
