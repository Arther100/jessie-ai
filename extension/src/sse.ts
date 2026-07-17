/**
 * Minimal SSE client for Jessie review/merge endpoints.
 * Pass BYOK headers via `headers` (X-Claude-API-Key, X-AI-Provider, …).
 */

export type SseHandler = (event: Record<string, unknown>) => void;

export async function streamSse(
  url: string,
  body: unknown,
  onEvent: SseHandler,
  headers?: Record<string, string>,
): Promise<Record<string, unknown>> {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(headers || {}),
    },
    body: JSON.stringify(body),
  });

  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => 'no body');
    throw new Error(`HTTP ${response.status}: ${text.slice(0, 400)}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith('data:')) continue;
      const payload = trimmed.slice(5).trim();
      if (payload === '[DONE]') {
        return { type: 'error', code: 'no_result', message: 'Stream ended without result' };
      }
      let event: Record<string, unknown>;
      try {
        event = JSON.parse(payload);
      } catch {
        continue;
      }
      if (event.type === 'complete' || event.type === 'error') {
        return event;
      }
      onEvent(event);
    }
  }

  return { type: 'error', code: 'stream_closed', message: 'Stream closed unexpectedly' };
}
