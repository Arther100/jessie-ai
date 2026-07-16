"use client";
import { useState, useCallback } from "react";

const BASE = process.env.NEXT_PUBLIC_JESSIE_API ?? "http://localhost:8000";

export interface SSEOptions<T> {
  onProgress?: (msg: string, pct: number) => void;
  onComplete?: (result: T) => void;
  onError?: (err: string) => void;
}

export function useSSEStream<T = unknown>(path: string) {
  const [isLoading, setIsLoading] = useState(false);
  const [updates, setUpdates]     = useState<string[]>([]);
  const [pct, setPct]             = useState(0);
  const [result, setResult]       = useState<T | null>(null);
  const [error, setError]         = useState<string | null>(null);

  const start = useCallback(
    async (body: unknown, opts: SSEOptions<T> = {}): Promise<boolean> => {
      setIsLoading(true);
      setUpdates([]);
      setPct(0);
      setResult(null);
      setError(null);

      try {
        const res = await fetch(`${BASE}${path}`, {
          method:  "POST",
          headers: { "Content-Type": "application/json" },
          body:    JSON.stringify(body),
        });

        if (!res.ok || !res.body) {
          let detail = "";
          try {
            detail = (await res.text()).trim();
          } catch {
            detail = "";
          }
          const msg = detail
            ? `HTTP ${res.status}: ${detail.slice(0, 300)}`
            : `HTTP ${res.status}. Check backend is running on ${BASE}.`;
          setError(msg);
          opts.onError?.(msg);
          return false;
        }

        const reader  = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer    = "";

        let failed = false;

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data:")) continue;
            const payload = trimmed.slice(5).trim();
            if (payload === "[DONE]") break;

            let event: { type: string; message?: string; pct?: number } & T;
            try { event = JSON.parse(payload); } catch { continue; }

            if (event.type === "progress") {
              const msg = event.message ?? "";
              const p   = event.pct ?? 0;
              setUpdates(prev => [...prev, msg]);
              setPct(p);
              opts.onProgress?.(msg, p);
            } else if (event.type === "complete") {
              setResult(event as unknown as T);
              setPct(100);
              opts.onComplete?.(event as unknown as T);
            } else if (event.type === "error") {
              const msg = (event as { message?: string }).message ?? "Unknown error";
              failed = true;
              setError(msg);
              opts.onError?.(msg);
            }
          }
        }
        return !failed;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Network error";
        setError(msg);
        opts.onError?.(msg);
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    [path],
  );

  const reset = useCallback(() => {
    setIsLoading(false);
    setUpdates([]);
    setPct(0);
    setResult(null);
    setError(null);
  }, []);

  return { start, reset, isLoading, updates, pct, result, error };
}
