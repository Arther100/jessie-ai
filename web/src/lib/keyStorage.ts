/**
 * Jessie — web/src/lib/keyStorage.ts
 *
 * Browser storage for BYOK API keys.
 * NOTE: btoa reverse is obfuscation only — NOT real encryption.
 * For stronger security, use the VS Code extension (SecretStorage).
 * Keys are never sent to Jessie servers except as request headers
 * during AI calls, and are never persisted server-side.
 */

const KEY_NAME = "jessie_api_key";
const PROVIDER_NAME = "jessie_provider";
const USER_NAME = "jessie_user_id";
const WORKSPACE_NAME = "jessie_workspace_id";

export type AiProvider = "anthropic" | "openai" | "gemini";

function obfuscate(key: string): string {
  // Obfuscation only — not secure encryption
  return btoa(key.split("").reverse().join(""));
}

function deobfuscate(enc: string): string {
  return atob(enc).split("").reverse().join("");
}

export function saveApiKey(key: string, provider: AiProvider): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(KEY_NAME, obfuscate(key.trim()));
  localStorage.setItem(PROVIDER_NAME, provider);
}

export function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  const enc = localStorage.getItem(KEY_NAME);
  if (!enc) return null;
  try {
    return deobfuscate(enc);
  } catch {
    return null;
  }
}

export function getProvider(): AiProvider {
  if (typeof window === "undefined") return "anthropic";
  const p = localStorage.getItem(PROVIDER_NAME) || "anthropic";
  if (p === "openai" || p === "gemini") return p;
  return "anthropic";
}

export function clearApiKey(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(KEY_NAME);
  localStorage.removeItem(PROVIDER_NAME);
}

export function getUserId(): string {
  if (typeof window === "undefined") return "web_user";
  return localStorage.getItem(USER_NAME) || "web_user";
}

export function setUserId(id: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(USER_NAME, id);
}

export function getWorkspaceId(): string {
  if (typeof window === "undefined") return "web";
  return localStorage.getItem(WORKSPACE_NAME) || "web";
}

export function setWorkspaceId(id: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(WORKSPACE_NAME, id);
}

export function maskKey(key: string): string {
  if (!key || key.length < 8) return "••••";
  return `${key.slice(0, 7)}••••••••••••${key.slice(-4)}`;
}

export function hasApiKey(): boolean {
  return !!getApiKey();
}
