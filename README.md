# ⚡ Jessie — AI Coding Agent (v3)

> BYOK (bring your own API key) · hosted backend · VS Code extension + optional web app.

## Hosted backend

| | |
|--|--|
| **Backend URL** | https://jessie-ai-xpv2.onrender.com |
| **Health** | https://jessie-ai-xpv2.onrender.com/health |

Users supply their own Claude / OpenAI / Gemini key. Keys are **never stored** on the server.

**Extension package:** `extension/jessie-ai-3.0.0.vsix`  
Install: `Ctrl+Shift+P` → **Extensions: Install from VSIX…**

---

## What's new in v3

- **Hosted backend** on Render (no local Python required for the extension).
- **BYOK headers** — `X-Claude-API-Key` / `X-AI-Provider` on every AI request.
- **Multi-provider** — Anthropic, OpenAI, Gemini.
- **Team isolation** via API-key hash (memory + Chroma + quota).
- **3-screen setup wizard** in the extension (welcome → key → name).
- Ticket / sprint / analytics agents (DevOps layer).

---

## Total flow (high level)

```
┌─────────────────┐     ┌──────────────────────────────┐     ┌─────────────────┐
│  Web (optional) │────▶│  https://jessie-ai-xpv2      │◀────│  VS Code ext v3 │
│                 │     │  .onrender.com               │     │  BYOK + setup   │
└─────────────────┘     └──────────────────────────────┘     └─────────────────┘
```

### Ask Jessie (Copilot)

```
@jessie / Ctrl+Shift+J → Prompt Coach → RAG → Copilot → Quality → Memory
```

### Code Review

```
API key → Azure URL+PAT+branch (or local) → clone/scan → scores + impact → report
```

### Merge Review

```
API key → Azure base+head → diff → impact → verdict + report
```

---

## Quick start (extension only)

1. Use `extension/jessie-ai-3.0.0.vsix` (build with `cd extension && npm run compile && npx vsce package`)
2. Install from VSIX in VS Code / Cursor
3. Complete setup wizard (API key + name)
4. Backend is already hosted at **https://jessie-ai-xpv2.onrender.com**

### Local backend (optional)

```bash
cd backend
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

Then set `jessie.backendUrl` to `http://localhost:8000`.

### Web (optional)

```bash
cd web
npm install
npm run dev
# → http://localhost:3000
```

Set `NEXT_PUBLIC_JESSIE_API=https://jessie-ai-xpv2.onrender.com` for the hosted API.

---

## Folder structure

```
jessie/
├── backend/          ← FastAPI (deployed to Render)
├── web/              ← Next.js (optional)
├── extension/
│   ├── jessie-ai-3.0.0.vsix
│   └── src/
└── tests/
```

---

## Settings (extension)

| Setting | Default | Description |
|---|---|---|
| `jessie.userId` | `""` | Your name |
| `jessie.backendUrl` | `https://jessie-ai-xpv2.onrender.com` | Hosted backend |
| `jessie.aiProvider` | `anthropic` | anthropic / openai / gemini |

API keys are stored in VS Code SecretStorage only.

---

## License

MIT

---

## Developed By

**Vijay Arther**, **Bala Murugan**, **Balaji**, **Anish**, **Bhuvanesh**, **Suriya Prakash**
