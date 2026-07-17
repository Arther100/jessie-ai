"use client";

import { useEffect, useState } from "react";
import { verifyApiKey } from "@/lib/api";
import {
  AiProvider,
  getApiKey,
  hasApiKey,
  saveApiKey,
} from "@/lib/keyStorage";

const PROVIDERS: { id: AiProvider; label: string; placeholder: string }[] = [
  { id: "anthropic", label: "Anthropic", placeholder: "sk-ant-..." },
  { id: "openai", label: "OpenAI", placeholder: "sk-..." },
  { id: "gemini", label: "Gemini", placeholder: "AIza..." },
];

export function ApiKeyModal({ forceOpen = false }: { forceOpen?: boolean }) {
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState<AiProvider>("anthropic");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState(false);

  useEffect(() => {
    if (forceOpen || !hasApiKey()) setOpen(true);
    const onNeed = () => setOpen(true);
    window.addEventListener("jessie:api-key-required", onNeed);
    return () => window.removeEventListener("jessie:api-key-required", onNeed);
  }, [forceOpen]);

  if (!open) return null;

  const ph = PROVIDERS.find((p) => p.id === provider)?.placeholder || "sk-ant-...";

  async function start() {
    const trimmed = key.trim();
    if (!trimmed) {
      setErr(true);
      setMsg("Enter an API key to continue.");
      return;
    }
    setBusy(true);
    setMsg("Checking key...");
    setErr(false);
    const result = await verifyApiKey(trimmed, provider);
    setBusy(false);
    if (!result.valid) {
      setErr(true);
      setMsg(result.message);
      return;
    }
    saveApiKey(trimmed, provider);
    setMsg(result.message);
    setErr(false);
    setTimeout(() => setOpen(false), 400);
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: "rgba(0,0,0,0.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 440,
          background: "var(--card, #111)",
          color: "var(--fg, #eee)",
          borderRadius: 12,
          padding: 28,
          border: "1px solid var(--border, #333)",
        }}
      >
        <h2 style={{ margin: "0 0 8px", fontSize: "1.35rem" }}>Welcome to Jessie AI</h2>
        <p style={{ margin: "0 0 16px", opacity: 0.85, fontSize: 14, lineHeight: 1.5 }}>
          Enter your Claude API key to get started. Your key is stored only in your browser —
          never on Jessie servers.
        </p>

        <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
          {PROVIDERS.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => {
                setProvider(p.id);
                setKey("");
                setMsg("");
              }}
              style={{
                padding: "6px 12px",
                borderRadius: 6,
                border: provider === p.id ? "1px solid var(--accent, #6cf)" : "1px solid #444",
                background: provider === p.id ? "rgba(100,180,255,0.15)" : "transparent",
                color: "inherit",
                cursor: "pointer",
              }}
            >
              {p.label}
            </button>
          ))}
        </div>

        <input
          type="password"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder={ph}
          autoComplete="off"
          style={{
            width: "100%",
            boxSizing: "border-box",
            padding: "10px 12px",
            marginBottom: 12,
            borderRadius: 6,
            border: "1px solid #444",
            background: "#0a0a0a",
            color: "inherit",
          }}
        />

        <a
          href="https://console.anthropic.com"
          target="_blank"
          rel="noreferrer"
          style={{ fontSize: 13, display: "inline-block", marginBottom: 16 }}
        >
          Get a Claude API key →
        </a>

        {msg && (
          <p style={{ fontSize: 13, color: err ? "#f66" : "#6c6", margin: "0 0 12px" }}>{msg}</p>
        )}

        <button
          type="button"
          disabled={busy}
          onClick={start}
          style={{
            width: "100%",
            padding: "12px 16px",
            borderRadius: 8,
            border: "none",
            background: "#3b82f6",
            color: "#fff",
            fontWeight: 600,
            cursor: busy ? "default" : "pointer",
            opacity: busy ? 0.7 : 1,
          }}
        >
          {busy ? "Checking…" : "Start using Jessie →"}
        </button>

        {getApiKey() && (
          <button
            type="button"
            onClick={() => setOpen(false)}
            style={{
              width: "100%",
              marginTop: 8,
              padding: 8,
              background: "transparent",
              border: "none",
              color: "#888",
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}
