/**
 * Shared Azure DevOps helpers for Jessie extension (parity with web app).
 */

import * as vscode from 'vscode';
import axios from 'axios';
import {
  API_KEY_SECRET,
  clearApiKey,
  getApiKey,
  storeApiKey,
  promptForApiKey,
} from './apiKeys';

const SECRET_KEY = 'jessie.azurePat';
/** @deprecated use API_KEY_SECRET from apiKeys — kept for re-exports */
const CLAUDE_SECRET_KEY = API_KEY_SECRET;

export interface AzureRepoRef {
  org: string;
  project: string;
  repo: string;
}

export function parseAzureGitUrl(url: string): AzureRepoRef | null {
  let raw = url.trim().replace(/\.git$/i, '');
  if (!raw) return null;

  try {
    const u = new URL(raw);
    raw = `${u.protocol}//${u.host}${u.pathname}${u.search}${u.hash}`;
  } catch {
    // keep raw
  }

  const m =
    raw.match(/^https?:\/\/dev\.azure\.com\/([^/]+)\/([^/]+)\/_git\/([^/?#]+)/i) ||
    raw.match(/^https?:\/\/([^.]+)\.visualstudio\.com(?:\/DefaultCollection)?\/([^/]+)\/_git\/([^/?#]+)/i);
  if (!m) return null;
  return {
    org: decodeURIComponent(m[1]),
    project: decodeURIComponent(m[2]),
    repo: decodeURIComponent(m[3]),
  };
}

export function workspaceIdFrom(parts: string): string {
  return Buffer.from(parts).toString('base64').slice(0, 12);
}

export async function getStoredPat(context: vscode.ExtensionContext): Promise<string> {
  return (await context.secrets.get(SECRET_KEY)) || '';
}

export async function storePat(context: vscode.ExtensionContext, token: string): Promise<void> {
  await context.secrets.store(SECRET_KEY, token);
}

export async function clearPat(context: vscode.ExtensionContext): Promise<void> {
  await context.secrets.delete(SECRET_KEY);
}

export async function getStoredClaudeKey(context: vscode.ExtensionContext): Promise<string> {
  return getApiKey(context);
}

export async function storeClaudeKey(context: vscode.ExtensionContext, key: string): Promise<void> {
  await storeApiKey(context, key);
}

export async function clearClaudeKey(context: vscode.ExtensionContext): Promise<void> {
  await clearApiKey(context);
}

/** Prompt for API key if not saved. Returns empty string if cancelled. */
export async function ensureClaudeApiKey(context: vscode.ExtensionContext): Promise<string> {
  const existing = await getApiKey(context);
  if (existing) return existing;
  return (await promptForApiKey(context)) || '';
}

export function getBackendUrl(): string {
  return vscode.workspace.getConfiguration('jessie').get<string>('backendUrl') || 'https://jessie-ai-xpv2.onrender.com';
}

export function getUserId(): string {
  return vscode.workspace.getConfiguration('jessie').get<string>('userId') || 'anonymous';
}

/** Collect Azure URL + PAT + load branches (same as web Connect). */
export async function promptAzureConnection(
  context: vscode.ExtensionContext,
): Promise<{ ref: AzureRepoRef; url: string; token: string; branches: string[] } | undefined> {
  const cfg = vscode.workspace.getConfiguration('jessie');
  const lastUrl = cfg.get<string>('azureGitUrl') || '';

  const url = await vscode.window.showInputBox({
    prompt: 'Azure project clone URL',
    placeHolder: 'https://user@dev.azure.com/{org}/{project}/_git/{repo}',
    value: lastUrl,
    ignoreFocusOut: true,
  });
  if (!url) return;

  const ref = parseAzureGitUrl(url);
  if (!ref) {
    vscode.window.showErrorMessage(
      'Unrecognized clone URL. Example: https://user@dev.azure.com/{org}/{project}/_git/{repo}',
    );
    return;
  }

  const saved = await getStoredPat(context);
  const token = await vscode.window.showInputBox({
    prompt: 'Password (or Azure Personal Access Token)',
    password: true,
    value: saved ? '********' : '',
    placeHolder: saved ? 'Press Enter to reuse saved password, or paste a new one' : 'Password / PAT',
    ignoreFocusOut: true,
  });
  if (token === undefined) return;

  const resolvedToken = token === '********' || token.trim() === '' ? saved : token.trim();
  if (!resolvedToken) {
    vscode.window.showErrorMessage('Azure PAT is required.');
    return;
  }

  const backendUrl = getBackendUrl();
  let branches: string[] = [];
  try {
    const res = await axios.post(
      `${backendUrl}/merge/branches`,
      {
        platform: 'azure',
        repo: ref.repo,
        token: resolvedToken,
        azure_org: ref.org,
        azure_project: ref.project,
      },
      { timeout: 30_000 },
    );
    branches = res.data?.branches ?? [];
  } catch (err: any) {
    const detail = err.response?.data?.detail || err.message || 'Failed to load branches';
    vscode.window.showErrorMessage(`Connect failed: ${detail}`);
    return;
  }

  if (!branches.length) {
    vscode.window.showErrorMessage('No branches returned. Check repo name and PAT scopes (Code Read).');
    return;
  }

  await storePat(context, resolvedToken);
  await cfg.update('azureGitUrl', url.trim(), true);

  return { ref, url: url.trim(), token: resolvedToken, branches };
}

export async function pickBranch(
  branches: string[],
  title: string,
  preferred?: string,
): Promise<string | undefined> {
  const items = branches.map(b => ({
    label: b,
    description: preferred && b === preferred ? 'suggested' : undefined,
  }));
  const pick = await vscode.window.showQuickPick(items, {
    title,
    placeHolder: title,
    ignoreFocusOut: true,
    matchOnDescription: true,
  });
  return pick?.label;
}
