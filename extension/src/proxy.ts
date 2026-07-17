/**
 * Jessie — extension/src/proxy.ts
 * HTTP + SSE client for the Jessie gateway /proxy endpoint.
 * All requests include BYOK headers (X-Claude-API-Key, X-AI-Provider, …).
 */

import * as vscode from 'vscode';
import * as crypto from 'crypto';
import {
  buildAuthHeaders,
  getApiKey,
  getProvider,
  getUserId,
  handleApiKeyRequired,
  promptForApiKey,
} from './apiKeys';

interface StatusEvent {
  type: 'status';
  message: string;
}

interface ResultEvent {
  type: 'result';
  response: string;
  model: string;
  cache_hit: boolean;
  quality_score: number;
  tokens_saved: number;
  cost_estimate: number;
  memory_note: string;
}

interface ErrorEvent {
  type: 'error';
  code: string;
  message: string;
}

type SSEEvent = StatusEvent | ResultEvent | ErrorEvent;

export interface ProxyResult {
  response: string;
  model: string;
  cacheHit: boolean;
  qualityScore: number;
  tokensSaved: number;
  costEstimate: number;
  memoryNote: string;
}

export interface PromptContext {
  language: string;
  openFileContent: string;
  selectedCode: string;
  errorMessage?: string;
  priority?: number;
}

export class JessieProxy {
  private _alive: boolean | null = null;
  private _lastHealthCheck = 0;
  private readonly _HEALTH_TTL = 30_000;
  private _context: vscode.ExtensionContext | undefined;

  constructor(
    private readonly _statusBar: vscode.StatusBarItem,
    private readonly _backendUrl: string,
  ) {}

  /** Attach extension context so SecretStorage is available. */
  setContext(context: vscode.ExtensionContext): void {
    this._context = context;
  }

  async interceptAndProcess(
    prompt: string,
    context: PromptContext,
  ): Promise<string | null> {
    if (!await this.isBackendAlive()) {
      return null;
    }

    if (!this._context) {
      console.error('[Jessie proxy] Extension context not set');
      return null;
    }

    let apiKey = await getApiKey(this._context);
    if (!apiKey) {
      apiKey = (await promptForApiKey(this._context)) || '';
      if (!apiKey) return null;
    }

    const body = {
      prompt,
      user_id: this.getUserId(),
      workspace_id: this.getWorkspaceId(),
      language: context.language,
      open_file_content: context.openFileContent.slice(0, 3000),
      selected_code: context.selectedCode,
      error_message: context.errorMessage ?? '',
      priority: context.priority ?? 0,
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

  invalidateHealthCache(): void {
    this._alive = null;
    this._lastHealthCheck = 0;
  }

  getWorkspaceId(): string {
    const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '';
    return crypto.createHash('md5').update(folder).digest('hex').slice(0, 12);
  }

  getUserId(): string {
    return getUserId() || 'anonymous';
  }

  getProvider(): string {
    return getProvider();
  }

  private async _streamProxy(body: Record<string, unknown>): Promise<ProxyResult> {
    if (!this._context) {
      throw new Error('Extension context not set');
    }

    const headers = await buildAuthHeaders(this._context, this.getWorkspaceId());
    headers['Accept'] = 'text/event-stream';

    // Headers sent on every /proxy call:
    // X-Claude-API-Key, X-AI-Provider, X-User-Id, X-Workspace-Id
    const res = await fetch(`${this._backendUrl}/proxy`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(360_000),
    });

    if (res.status === 401) {
      let detail: { error?: string } = {};
      try {
        detail = (await res.json()) as { error?: string };
      } catch {
        /* ignore */
      }
      if (detail.error === 'api_key_required' || !headers['X-Claude-API-Key']) {
        await handleApiKeyRequired(this._context);
        this._setStatus('$(warning) Jessie — API key needed');
        throw new Error('api_key_required');
      }
      this._setStatus('$(error) Jessie — invalid API key');
      throw new Error('invalid_api_key');
    }

    if (!res.ok) {
      throw new Error(`Backend returned HTTP ${res.status}`);
    }

    const reader = res.body?.getReader();
    if (!reader) {
      throw new Error('No response body received from backend');
    }

    const decoder = new TextDecoder();
    let buffer = '';
    let result: ProxyResult | null = null;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6).trim();
          if (!payload || payload === '[DONE]') continue;

          let event: SSEEvent;
          try {
            event = JSON.parse(payload) as SSEEvent;
          } catch {
            continue;
          }

          if (event.type === 'status') {
            this._setStatus(event.message);
          } else if (event.type === 'result') {
            result = {
              response: event.response,
              model: event.model,
              cacheHit: event.cache_hit,
              qualityScore: event.quality_score,
              tokensSaved: event.tokens_saved,
              costEstimate: event.cost_estimate,
              memoryNote: event.memory_note,
            };
          } else if (event.type === 'error') {
            if (event.code === 'quota_exceeded') {
              vscode.window.showWarningMessage(`Jessie: ${event.message}`);
            }
            if (event.code === 'api_key_required' || event.code === 'invalid_key') {
              await handleApiKeyRequired(this._context);
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
