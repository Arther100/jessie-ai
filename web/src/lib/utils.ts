import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
  });
}

export function formatCost(cost: number): string {
  return `$${cost.toFixed(4)}`;
}

export function workspaceId(path: string): string {
  return btoa(path).slice(0, 12);
}

/** Parse Azure DevOps Git clone / browser URL into org / project / repo.
 * Accepts:
 * - https://dev.azure.com/{org}/{project}/_git/{repo}
 * - https://{user}@dev.azure.com/{org}/{project}/_git/{repo}  (clone URL)
 * - https://{org}.visualstudio.com/{project}/_git/{repo}
 */
export function parseAzureGitUrl(url: string): {
  org: string;
  project: string;
  repo: string;
  username?: string;
} | null {
  let raw = url.trim().replace(/\.git$/i, "");
  if (!raw) return null;

  // Strip credentials from clone URLs: https://user:pass@host/... or https://user@host/...
  let username: string | undefined;
  try {
    const u = new URL(raw);
    if (u.username) username = decodeURIComponent(u.username);
    // rebuild without userinfo so host path parsing is clean
    raw = `${u.protocol}//${u.host}${u.pathname}${u.search}${u.hash}`;
  } catch {
    // fall through to regex on original
  }

  const m =
    raw.match(/^https?:\/\/dev\.azure\.com\/([^/]+)\/([^/]+)\/_git\/([^/?#]+)/i) ||
    raw.match(/^https?:\/\/([^.]+)\.visualstudio\.com(?:\/DefaultCollection)?\/([^/]+)\/_git\/([^/?#]+)/i);
  if (!m) return null;
  return {
    org: decodeURIComponent(m[1]),
    project: decodeURIComponent(m[2]),
    repo: decodeURIComponent(m[3]),
    username,
  };
}

export function shortSha(sha: string): string {
  return sha.slice(0, 7);
}
