/**
 * Jessie History + Settings helpers (web History / Settings parity).
 */

import * as vscode from 'vscode';
import axios from 'axios';
import {
  clearClaudeKey,
  clearPat,
  ensureClaudeApiKey,
  getBackendUrl,
  parseAzureGitUrl,
  workspaceIdFrom,
} from './azure';

export async function showJessieHistory(): Promise<void> {
  const kind = await vscode.window.showQuickPick(
    [
      { label: '$(search) Code Review history', mode: 'review' as const },
      { label: '$(git-merge) Merge Review history', mode: 'merge' as const },
      { label: '$(link-external) Open web Dashboard', mode: 'web' as const },
    ],
    { title: 'Jessie History', placeHolder: 'What do you want to open?' },
  );
  if (!kind) return;

  if (kind.mode === 'web') {
    const web =
      vscode.workspace.getConfiguration('jessie').get<string>('webAppUrl') ||
      'http://localhost:3000';
    await vscode.env.openExternal(vscode.Uri.parse(web));
    return;
  }

  const cfg = vscode.workspace.getConfiguration('jessie');
  const url = cfg.get<string>('azureGitUrl') || '';
  const parsed = parseAzureGitUrl(url);
  const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || 'workspace';
  const workspaceId = parsed
    ? workspaceIdFrom(`${parsed.org}/${parsed.project}/${parsed.repo}`)
    : workspaceIdFrom(folder);

  const backendUrl = getBackendUrl();
  try {
    if (kind.mode === 'review') {
      const res = await axios.get(`${backendUrl}/review/history/${workspaceId}`);
      const rows: any[] = res.data || [];
      if (!rows.length) {
        vscode.window.showInformationMessage('No code review history for this workspace yet.');
        return;
      }
      const pick = await vscode.window.showQuickPick(
        rows.map(r => ({
          label: `${r.overall_score}/100 (${r.date})`,
          description: `${r.total_issues} issues · ${r.critical_count} critical`,
          detail: r.report_path,
        })),
        { title: 'Code Review history', matchOnDescription: true, matchOnDetail: true },
      );
      if (pick?.detail) {
        await vscode.commands.executeCommand('vscode.open', vscode.Uri.file(pick.detail));
      }
      return;
    }

    const res = await axios.get(`${backendUrl}/merge/history/${workspaceId}`);
    const rows: any[] = res.data || [];
    if (!rows.length) {
      vscode.window.showInformationMessage('No merge review history for this workspace yet.');
      return;
    }
    const pick = await vscode.window.showQuickPick(
      rows.map(r => ({
        label: `${r.verdict} · ${r.overall_score}/100 (${r.date})`,
        description: `${r.total_issues} issues · ${r.critical_count} critical`,
        detail: r.report_path,
      })),
      { title: 'Merge Review history', matchOnDescription: true, matchOnDetail: true },
    );
    if (pick?.detail) {
      await vscode.commands.executeCommand('vscode.open', vscode.Uri.file(pick.detail));
    }
  } catch (err: any) {
    vscode.window.showErrorMessage(
      `Could not load history: ${err.response?.data?.detail || err.message}`,
    );
  }
}

export async function showJessieSettings(context: vscode.ExtensionContext): Promise<void> {
  const action = await vscode.window.showQuickPick(
    [
      { label: '$(person) Set user ID', id: 'user' as const },
      { label: '$(server) Set backend URL', id: 'backend' as const },
      { label: '$(link) Set web app URL', id: 'web' as const },
      { label: '$(hubot) Set Claude API key', id: 'claude' as const },
      { label: '$(info) Open Info (Claude + features)', id: 'info' as const },
      { label: '$(key) Clear saved Azure PAT', id: 'clearPat' as const },
      { label: '$(trash) Clear saved Claude API key', id: 'clearClaude' as const },
      { label: '$(gear) Open VS Code Jessie settings', id: 'open' as const },
      { label: '$(pulse) My request count today', id: 'requests' as const },
    ],
    { title: 'Jessie Settings' },
  );
  if (!action) return;

  const cfg = vscode.workspace.getConfiguration('jessie');
  if (action.id === 'open') {
    await vscode.commands.executeCommand('workbench.action.openSettings', 'jessie');
    return;
  }
  if (action.id === 'info') {
    await vscode.commands.executeCommand('jessie.info');
    return;
  }
  if (action.id === 'user') {
    const v = await vscode.window.showInputBox({
      prompt: 'Jessie user ID',
      value: cfg.get<string>('userId') || '',
    });
    if (v !== undefined) await cfg.update('userId', v, true);
    return;
  }
  if (action.id === 'backend') {
    const v = await vscode.window.showInputBox({
      prompt: 'Jessie backend URL',
      value: cfg.get<string>('backendUrl') || 'http://localhost:8000',
    });
    if (v !== undefined) await cfg.update('backendUrl', v, true);
    return;
  }
  if (action.id === 'web') {
    const v = await vscode.window.showInputBox({
      prompt: 'Jessie web app URL',
      value: cfg.get<string>('webAppUrl') || 'http://localhost:3000',
    });
    if (v !== undefined) await cfg.update('webAppUrl', v, true);
    return;
  }
  if (action.id === 'clearPat') {
    await clearPat(context);
    vscode.window.showInformationMessage('Saved Azure PAT cleared.');
    return;
  }
  if (action.id === 'claude') {
    const key = await ensureClaudeApiKey(context);
    if (key) vscode.window.showInformationMessage('Claude API key saved securely.');
    return;
  }
  if (action.id === 'clearClaude') {
    await clearClaudeKey(context);
    vscode.window.showInformationMessage('Saved Claude API key cleared.');
    return;
  }
  if (action.id === 'requests') {
    await vscode.commands.executeCommand('jessie.showRequests');
  }
}
