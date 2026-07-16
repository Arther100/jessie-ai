/**
 * Jessie — extension/src/proxy.ts
 * HTTP + SSE client for the Jessie gateway /proxy endpoint.
 *
 * JessieProxy is the single point of contact between the VS Code extension
 * and the Jessie backend gateway.  It:
 *
 *   1. Checks backend health every 30 s (cached).  If offline → returns null
 *      so the caller can fall back to direct Copilot / Claude unchanged.
 *
 *   2. Sends developer prompts to POST /proxy as a JSON body.
 *
 *   3. Reads the SSE stream, parsing each  data: {...}  frame:
 *        "status" frames  → update VS Code status bar text in real time
 *        "result"  frame  → resolve the promise with the final response
 *        "error"   frame  → reject with a descriptive error
 *
 *   4. Provides getWorkspaceId() and getUserId() helpers used by callers
 *      to fill the request body without duplicating the logic.
 *
 * Usage:
 *   const proxy = new JessieProxy(statusBarItem, "http://localhost:8000");
 *   const response = await proxy.interceptAndProcess(prompt, context);
 *   if (response === null) { fallback to Copilot }
 */

import * as vscode from 'vscode';
import * as crypto from 'crypto';

// ── Types matching the Python SSE events ──────────────────────────────────

interface StatusEvent {
    type:    'status';
    message: string;
}

interface ResultEvent {
    type:          'result';
    response:      string;
    model:         string;
    cache_hit:     boolean;
    quality_score: number;
    tokens_saved:  number;
    cost_estimate: number;
    memory_note:   string;
}

interface ErrorEvent {
    type:    'error';
    code:    string;
    message: string;
}

type SSEEvent = StatusEvent | ResultEvent | ErrorEvent;

export interface ProxyResult {
    response:     string;
    model:        string;
    cacheHit:     boolean;
    qualityScore: number;
    tokensSaved:  number;
    costEstimate: number;
    memoryNote:   string;
}

export interface PromptContext {
    language:         string;
    openFileContent:  string;
    selectedCode:     string;
    errorMessage?:    string;
    priority?:        number;   // 0 = normal, 1 = senior dev (queue priority)
}

// ── JessieProxy ───────────────────────────────────────────────────────────

export class JessieProxy {
    private _alive:          boolean | null = null;
    private _lastHealthCheck = 0;
    private readonly _HEALTH_TTL = 30_000;   // 30 s

    constructor(
        private readonly _statusBar: vscode.StatusBarItem,
        private readonly _backendUrl: string,
    ) {}

    /**
     * Main entry point.
     *
     * Sends `prompt` + editor context to the Jessie gateway and returns the
     * optimised response string.  Updates the status bar at each pipeline stage.
     *
     * Returns null if:
     *   - The backend is offline (caller should fall back to Copilot/Claude)
     *   - The gateway returns a quota-exceeded or API error
     *
     * Never throws — all errors are caught and logged.
     */
    async interceptAndProcess(
        prompt:  string,
        context: PromptContext,
    ): Promise<string | null> {
        if (!await this.isBackendAlive()) {
            return null;
        }

        const body = {
            prompt,
            user_id:           this.getUserId(),
            workspace_id:      this.getWorkspaceId(),
            language:          context.language,
            open_file_content: context.openFileContent.slice(0, 3000),
            selected_code:     context.selectedCode,
            error_message:     context.errorMessage ?? '',
            priority:          context.priority ?? 0,
        };

        try {
            const result = await this._streamProxy(body);
            return result.response;
        } catch (err: any) {
            this._setStatus(`$(warning) Jessie — ${err.message ?? 'error'}`);
            console.error('[Jessie proxy]', err);
            return null;
        }
    }

    /**
     * Check whether the Jessie backend is reachable.
     * Result is cached for _HEALTH_TTL ms to avoid hammering /health.
     */
    async isBackendAlive(): Promise<boolean> {
        const now = Date.now();
        if (this._alive !== null && now - this._lastHealthCheck < this._HEALTH_TTL) {
            return this._alive;
        }
        try {
            const res = await fetch(`${this._backendUrl}/health`, {
                signal: AbortSignal.timeout(2000),
            });
            this._alive = res.ok;
        } catch {
            this._alive = false;
        }
        this._lastHealthCheck = now;
        return this._alive!;
    }

    /** Invalidate the cached health status immediately. */
    invalidateHealthCache(): void {
        this._alive = null;
        this._lastHealthCheck = 0;
    }

    /** MD5 hash of the workspace root path — used as project isolation key. */
    getWorkspaceId(): string {
        const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '';
        return crypto.createHash('md5').update(folder).digest('hex').slice(0, 12);
    }

    /** User ID from the jessie.userId VS Code setting. */
    getUserId(): string {
        return (
            vscode.workspace
                .getConfiguration('jessie')
                .get<string>('userId') ?? 'anonymous'
        );
    }

    // ── Private ─────────────────────────────────────────────────────────────

    /**
     * POST /proxy and consume the SSE stream.
     * Yields status events to the status bar; resolves with the result event.
     */
    private async _streamProxy(body: Record<string, unknown>): Promise<ProxyResult> {
        const res = await fetch(`${this._backendUrl}/proxy`, {
            method:  'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept':       'text/event-stream',
            },
            body:   JSON.stringify(body),
            signal: AbortSignal.timeout(360_000),   // 6 min hard timeout
        });

        if (!res.ok) {
            throw new Error(`Backend returned HTTP ${res.status}`);
        }

        const reader  = res.body?.getReader();
        if (!reader) {
            throw new Error('No response body received from backend');
        }

        const decoder = new TextDecoder();
        let   buffer  = '';
        let   result: ProxyResult | null = null;

        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines  = buffer.split('\n');
                buffer       = lines.pop() ?? '';   // keep incomplete line

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const payload = line.slice(6).trim();
                    if (!payload || payload === '[DONE]') continue;

                    let event: SSEEvent;
                    try {
                        event = JSON.parse(payload) as SSEEvent;
                    } catch {
                        continue;   // malformed frame — skip
                    }

                    if (event.type === 'status') {
                        this._setStatus(event.message);

                    } else if (event.type === 'result') {
                        result = {
                            response:     event.response,
                            model:        event.model,
                            cacheHit:     event.cache_hit,
                            qualityScore: event.quality_score,
                            tokensSaved:  event.tokens_saved,
                            costEstimate: event.cost_estimate,
                            memoryNote:   event.memory_note,
                        };

                    } else if (event.type === 'error') {
                        // Quota exceeded — surface clearly; others are silent fallbacks
                        if (event.code === 'quota_exceeded') {
                            vscode.window.showWarningMessage(
                                `Jessie: ${event.message}`
                            );
                        }
                        throw new Error(`${event.code}: ${event.message}`);
                    }
                }
            }
        } finally {
            reader.cancel().catch(() => {});
        }

        if (!result) {
            throw new Error('Jessie gateway returned no result');
        }
        return result;
    }

    private _setStatus(text: string): void {
        this._statusBar.text = text;
    }
}
