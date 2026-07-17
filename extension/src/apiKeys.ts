/**
 * Jessie — extension/src/apiKeys.ts
 * BYOK API key helpers. Keys live ONLY in VS Code SecretStorage.
 * Never write keys to settings.json or disk.
 */

import * as vscode from 'vscode';

export const API_KEY_SECRET = 'jessie_claude_api_key';
/** Legacy secret name — migrated once on read. */
const LEGACY_API_KEY_SECRET = 'jessie.claudeApiKey';

export type AiProvider = 'anthropic' | 'openai' | 'gemini';

export function getBackendUrl(): string {
  return (
    vscode.workspace.getConfiguration('jessie').get<string>('backendUrl') ||
    'https://jessie-ai-xpv2.onrender.com'
  ).replace(/\/$/, '');
}

export function getUserId(): string {
  return vscode.workspace.getConfiguration('jessie').get<string>('userId') || '';
}

export function getProvider(): AiProvider {
  const p = vscode.workspace.getConfiguration('jessie').get<string>('aiProvider') || 'anthropic';
  if (p === 'openai' || p === 'gemini') return p;
  return 'anthropic';
}

export async function getApiKey(context: vscode.ExtensionContext): Promise<string> {
  let key = (await context.secrets.get(API_KEY_SECRET)) || '';
  if (!key) {
    const legacy = (await context.secrets.get(LEGACY_API_KEY_SECRET)) || '';
    if (legacy) {
      await context.secrets.store(API_KEY_SECRET, legacy);
      key = legacy;
    }
  }
  return key;
}

export async function storeApiKey(context: vscode.ExtensionContext, key: string): Promise<void> {
  await context.secrets.store(API_KEY_SECRET, key.trim());
}

export async function clearApiKey(context: vscode.ExtensionContext): Promise<void> {
  await context.secrets.delete(API_KEY_SECRET);
  try {
    await context.secrets.delete(LEGACY_API_KEY_SECRET);
  } catch {
    /* ignore */
  }
}

export function maskKey(key: string): string {
  if (!key || key.length < 8) return '••••';
  return `${key.slice(0, 7)}••••••••••••${key.slice(-4)}`;
}

export async function buildAuthHeaders(
  context: vscode.ExtensionContext,
  workspaceId: string,
): Promise<Record<string, string>> {
  const apiKey = await getApiKey(context);
  return {
    'Content-Type': 'application/json',
    'X-Claude-API-Key': apiKey,
    'X-AI-Provider': getProvider(),
    'X-User-Id': getUserId() || 'anonymous',
    'X-Workspace-Id': workspaceId || 'default',
  };
}

export async function verifyApiKey(
  backendUrl: string,
  apiKey: string,
  provider: AiProvider,
  userId?: string,
): Promise<{ ok: boolean; model?: string; message: string }> {
  try {
    const res = await fetch(`${backendUrl.replace(/\/$/, '')}/verify`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Claude-API-Key': apiKey,
        'X-AI-Provider': provider,
        'X-User-Id': userId || getUserId() || 'setup',
        'X-Workspace-Id': 'setup',
      },
      signal: AbortSignal.timeout(90_000), // Render free tier cold start can be slow
    });

    if (res.status === 404) {
      return {
        ok: false,
        message:
          'Backend /verify not found (404). Redeploy the latest Jessie backend to Render, then retry.',
      };
    }

    let data: {
      valid?: boolean;
      model?: string;
      message?: string;
      error?: string;
      detail?: unknown;
    } = {};
    try {
      data = (await res.json()) as typeof data;
    } catch {
      return { ok: false, message: `Backend returned HTTP ${res.status} with no JSON body.` };
    }

    if (res.ok && data.valid) {
      return { ok: true, model: data.model, message: data.message || 'API key is valid ✓' };
    }

    const detailMsg =
      typeof data.detail === 'object' && data.detail && 'message' in (data.detail as object)
        ? String((data.detail as { message?: string }).message)
        : typeof data.detail === 'string'
          ? data.detail
          : '';

    return {
      ok: false,
      message:
        data.message ||
        detailMsg ||
        `API key rejected (HTTP ${res.status}). Check your key and try again.`,
    };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes('aborted') || msg.includes('Timeout') || msg.includes('timeout')) {
      return {
        ok: false,
        message:
          'Timed out talking to Jessie backend. Wake the Render service (open /health in a browser), wait ~1 min, then retry.',
      };
    }
    return { ok: false, message: `Could not reach Jessie backend: ${msg}` };
  }
}

export async function promptForApiKey(
  context: vscode.ExtensionContext,
): Promise<string | undefined> {
  const provider = getProvider();
  const placeholder =
    provider === 'openai' ? 'sk-...' : provider === 'gemini' ? 'AIza...' : 'sk-ant-...';

  const key = await vscode.window.showInputBox({
    title: 'Jessie — API Key',
    prompt: `Enter your ${provider} API key (stored only in VS Code SecretStorage)`,
    password: true,
    placeHolder: placeholder,
    ignoreFocusOut: true,
  });
  if (!key?.trim()) return undefined;

  const backend = getBackendUrl();
  const result = await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: 'Jessie — Checking key...' },
    async () => verifyApiKey(backend, key.trim(), provider),
  );

  if (!result.ok) {
    vscode.window.showErrorMessage(`Jessie: ${result.message}`);
    return undefined;
  }

  await storeApiKey(context, key.trim());
  vscode.window.showInformationMessage(`Jessie: ${result.message}`);
  return key.trim();
}

export async function handleApiKeyRequired(
  context: vscode.ExtensionContext,
): Promise<void> {
  const choice = await vscode.window.showWarningMessage(
    'Jessie needs your Claude API key.',
    'Add API key',
    'Get a key →',
  );
  if (choice === 'Add API key') {
    await promptForApiKey(context);
  } else if (choice === 'Get a key →') {
    vscode.env.openExternal(vscode.Uri.parse('https://console.anthropic.com'));
  }
}
