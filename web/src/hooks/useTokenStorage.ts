"use client";
import { useState, useCallback } from "react";

const EXPIRY_DAYS = 30;

function storageKey(platform: string) {
  return `jessie_token_${platform}`;
}

/** Prefer current profile user id; fall back to anon for older saves. */
function decryptCandidates(encoded: string, userId: string): string {
  const salts = Array.from(new Set([userId || "anon", "anon", ""]));
  for (const salt of salts) {
    try {
      const raw = atob(encoded);
      const value = raw
        .split("")
        .map((c, i) => String.fromCharCode(c.charCodeAt(0) ^ (salt || "anon").charCodeAt(i % (salt || "anon").length)))
        .join("");
      // Azure/GitHub/GitLab PATs and Anthropic keys are printable ASCII; reject garbage XOR output.
      if (value && /^[\x20-\x7E]+$/.test(value) && (value.length >= 20 || value.startsWith("sk-ant-") || value.startsWith("sk-"))) {
        return value;
      }
    } catch {
      // try next salt
    }
  }
  return "";
}

function encrypt(value: string, salt: string): string {
  const key = salt || "anon";
  return btoa(
    value
      .split("")
      .map((c, i) => String.fromCharCode(c.charCodeAt(0) ^ key.charCodeAt(i % key.length)))
      .join(""),
  );
}

export function useTokenStorage(userId: string) {
  const [, forceUpdate] = useState(0);

  const saveToken = useCallback(
    (platform: string, token: string) => {
      const entry = {
        value:   encrypt(token, userId || "anon"),
        expires: Date.now() + EXPIRY_DAYS * 86_400_000,
        plain:   false,
      };
      localStorage.setItem(storageKey(platform), JSON.stringify(entry));
      forceUpdate(n => n + 1);
    },
    [userId],
  );

  const getToken = useCallback(
    (platform: string): string => {
      try {
        const raw = localStorage.getItem(storageKey(platform));
        if (!raw) return "";
        const entry = JSON.parse(raw) as { value: string; expires: number; plain?: boolean };
        if (Date.now() > entry.expires) {
          localStorage.removeItem(storageKey(platform));
          return "";
        }
        if (entry.plain) return entry.value;
        return decryptCandidates(entry.value, userId || "anon");
      } catch {
        return "";
      }
    },
    [userId],
  );

  const deleteToken = useCallback((platform: string) => {
    localStorage.removeItem(storageKey(platform));
    forceUpdate(n => n + 1);
  }, []);

  const hasToken = useCallback(
    (platform: string) => !!getToken(platform),
    [getToken],
  );

  return { saveToken, getToken, deleteToken, hasToken };
}
