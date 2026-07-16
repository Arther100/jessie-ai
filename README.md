# ⚡ Jessie — AI Coding Agent (v2)

> Copilot coaching + Azure **Code Review** & **Merge Review** with Claude impact analysis.  
> Web app and VS Code extension share the same Jessie backend.

**Extension package:** `extension/jessie-ai-2.0.0.vsix`  
**[Marketplace](https://marketplace.visualstudio.com/items?itemName=VijayArther.jessie-ai)** (when published)

---

## What's new in v2

- **Claude API key (mandatory for reviews)** — each user adds their own key (web **Info** / extension **Jessie: Info**). Not a shared server secret for Code/Merge Review.
- **Code Review** — Azure clone URL + PAT + branch; Flutter/Dart aware; Claude layer scores + project impact.
- **Merge Review** — Azure base → head; Claude UI / functionality / risks / missing coverage; downloadable impact (web DOCX).
- **Web ↔ Extension parity** — same `/review/start` and `/merge/review` APIs; Info surfaces for Claude setup.
- **History** — past code & merge reviews on web and in the extension.

---

## Total flow (high level)

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Web app :3000  │────▶│  Backend :8000   │◀────│  VS Code ext v2 │
│  Review / Merge │     │  FastAPI + agents│     │  Same APIs      │
│  Info + Claude  │     │  Claude per-user │     │  Info + Claude  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

### Ask Jessie (Copilot)

```
@jessie / Ctrl+Shift+J → Prompt Coach → RAG → Copilot → Quality → Memory
```

### Code Review

```
Claude key → Azure URL+PAT+branch (or local in extension) → clone/scan → Claude scores + impact → report
```

### Merge Review

```
Claude key → Azure base+head → diff → Claude impact → verdict + report
```

---

## How Ask Jessie works

```
@jessie "add a date picker to the booking form"
        ↓
[1] SUPERVISOR      — detects language, sets up workspace memory scope
        ↓
[2] PROMPT COACH    — scores quality, classifies complexity (1–10),
                      rewrites prompt with file context + constraints
        ↓
[3] RAG INJECTOR    — checks project memory (component exists? reuse it)
                      otherwise: scans codebase, injects top 4 files
        ↓
[4] COPILOT CALL    — model chosen by complexity score:
                      1–3 → gpt-4o-mini  |  4–7 → gpt-4o  |  8–10 → claude-sonnet
        ↓
[5] QUALITY CHECK   — scores output 0–100 against 7-point rubric
                      score < 70 → auto retry × 2 with failure feedback
        ↓
[6] MEMORY WRITER   — saves new component to project memory
                      next time anyone asks → reused instantly, Copilot skipped
```

---

## Quick start

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn api.main:app --reload --port 8000
```

### 2. Web (optional)

```bash
cd web
npm install
npm run dev
# → http://localhost:3000  → Info tab → add Claude key
```

### 3. Extension v2

1. Extensions → **Install from VSIX...** → `extension/jessie-ai-2.0.0.vsix`
2. **Jessie: Info** → add Anthropic Claude key (`sk-ant-…`)
3. Set `jessie.userId` in Settings
4. Run **Code Review** / **Merge Review** / **Ask Jessie**

---

## Folder structure

```
jessie/
├── backend/
│   ├── api/                     ← /prepare, /resume, /review, /merge, /health
│   ├── agents/
│   │   ├── code_reviewer/       ← Project review + Claude impact
│   │   ├── merge_reviewer/      ← Diff + Claude UI/functionality impact
│   │   ├── prompt_coach/
│   │   ├── rag_injector/
│   │   ├── quality_analyser/
│   │   └── memory_writer/
│   ├── gateway/                 ← ModelRouter (per-user Claude key for reviews)
│   └── requirements.txt
├── web/                         ← Next.js dashboard, Review, Merge, Info
├── extension/
│   ├── jessie-ai-2.0.0.vsix     ← Packaged extension v2
│   ├── src/
│   │   ├── extension.ts
│   │   ├── codeReview.ts
│   │   ├── mergeReview.ts
│   │   ├── info.ts              ← Claude key + feature guide
│   │   ├── azure.ts
│   │   ├── jessieChat.ts
│   │   └── sidebar.ts
│   └── README.md
└── tests/
```

---

## Memory — 3 isolated layers

```
project:{workspace_id}:{topic}  →  scoped to ONE repo only (zero cross-project leakage)
user:{user_id}:{topic}          →  personal per developer
team:global:{topic}             →  universal rules (future)
```

---

## Quality rubric (0–100) — Ask Jessie

| Check | Points |
|---|---|
| Has real code (not just explanation) | +20 |
| No TODOs or placeholder stubs | +15 |
| Has error handling | +15 |
| Matches detected language | +15 |
| Correct scope (not a full file dump) | +15 |
| Has comments/explanation | +10 |
| Under 150 lines | +10 |

Score ≥ 70 → delivered. Score < 70 → auto retry with failure feedback (max 2×).

---

## Settings

| Setting | Default | Description |
|---|---|---|
| `jessie.userId` | `""` | Your name or team ID |
| `jessie.backendUrl` | `http://localhost:8000` | Backend URL |
| `jessie.webAppUrl` | `http://localhost:3000` | Web app URL |

Claude API key and Azure PAT are stored locally (browser / VS Code secrets), not in `settings.json`.

---

## License

MIT

---

## Developed By

**Vijay Arther**, **Bala Murugan**, **Balaji**, **Anish**, **Bhuvanesh**, **Suriya Prakash**
