# Jessie AI — VS Code Extension v2.0.0

> Copilot coaching + Azure **Code Review** & **Merge Review** with Claude impact analysis.  
> Shares the same Jessie backend as the web app (`localhost:8000`).

**Package:** `jessie-ai-2.0.0.vsix`

---

## What's new in v2

| Area | What changed |
|---|---|
| **Claude API key** | Mandatory for reviews. Configure in **Jessie: Info** (SecretStorage). Each user supplies their own key — not a shared server key. |
| **Info panel** | New **Jessie: Info** command — Claude key setup, feature guide, backend status (parity with web **Settings → Info**). |
| **Code Review** | Azure clone URL + password/PAT + branch (same as web). Also supports local workspace folder. Flutter/Dart aware scoring + Claude project impact. |
| **Merge Review** | Azure base → head diff. Claude explains UI changes, functionality, risks, missing coverage + test checklist. Open report / impact markdown. |
| **History** | Browse past code & merge reviews; open web dashboard. |
| **Web parity** | Same `/review/start` and `/merge/review` APIs as the Jessie web app. |

---

## Total flow

### A) Ask Jessie (Copilot coach) — unchanged core

```
You: Ctrl+Shift+J  or  @jessie in Copilot Chat
        ↓
[1] Supervisor     — language, workspace ID
[2] Prompt Coach   — rewrite + complexity 1–10
[3] RAG Injector   — memory reuse or codebase chunks
[4] Copilot call   — model by complexity
[5] Quality check  — score ≥ 70 or retry
[6] Memory writer  — save reusable patterns
        ↓
You get production-ready code in the Jessie sidebar
```

### B) Code Review (v2)

```
Jessie: Code Review  (Ctrl+Shift+R)
        ↓
[1] Claude key     — Info panel / prompt if missing (sk-ant-…)
[2] Source         — Azure URL + PAT + branch  OR  local folder
[3] Backend        — shallow clone (Azure) → CodeReviewAgent
[4] Claude         — layer scores (frontend/backend/db) + impact
[5] Result         — Open Report + Open Impact (markdown)
```

### C) Merge Review (v2)

```
Jessie: Merge Review  (Ctrl+Shift+M)
        ↓
[1] Claude key     — required
[2] Azure connect  — org / project / repo + PAT
[3] Branches       — BASE (target) + HEAD (feature)
[4] Backend        — fetch diff + commits
[5] Claude impact  — UI · functionality · risks · missing · checklist
[6] Result         — score, verdict, Open Report / Impact
```

### D) Shared setup (web + extension)

```
1. Start backend:  cd backend && python -m uvicorn api.main:app --reload --port 8000
2. (Optional) Web:  cd web && npm run dev   → http://localhost:3000
3. Extension:       Install jessie-ai-2.0.0.vsix
4. Info:            Jessie: Info → Add Claude API key
5. Settings:        jessie.userId, jessie.backendUrl, Azure PAT (saved securely)
```

---

## Prerequisites

| Requirement | Version |
|---|---|
| VS Code | ≥ 1.90 |
| GitHub Copilot | Installed + signed in (for Ask Jessie) |
| Python | ≥ 3.9 (Jessie backend) |
| Anthropic Claude API key | Required for Code / Merge Review |
| Azure DevOps PAT | Code (Read) for Azure clone / merge diff |

---

## Install from VSIX (v2)

1. Open VS Code → Extensions (`Ctrl+Shift+X`)
2. **⋯** menu → **Install from VSIX...**
3. Select `jessie-ai-2.0.0.vsix`
4. Reload when prompted
5. Start the backend (see below)
6. Run **Jessie: Info** → add your Claude key

### Build / package from source

```bash
cd extension
npm install
npm run compile
npx vsce package
# → jessie-ai-2.0.0.vsix
```

---

## Backend setup

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn api.main:app --reload --port 8000
```

Or: `Ctrl+Shift+P` → **Jessie: Setup Jessie Backend**

Health check: `http://localhost:8000/health`

---

## Commands & shortcuts

| Command | Shortcut | Description |
|---|---|---|
| Jessie: Ask Jessie | `Ctrl+Shift+J` | Prompt coach → Copilot |
| Jessie: Code Review | `Ctrl+Shift+R` | Azure branch or local folder |
| Jessie: Code Review (Azure Branch) | — | Azure-only path |
| Jessie: Merge Review | `Ctrl+Shift+M` | Azure base → head + Claude impact |
| Jessie: History | — | Past reviews / open web |
| Jessie: Info (Claude key) | — | **Add Claude key** + feature guide |
| Jessie: Settings | — | User ID, backend URL, clear PAT/key |
| Jessie: Setup Jessie Backend | — | Guided backend install |
| Jessie: How to Use Jessie | — | Interactive tour |

Sidebar (Activity Bar ⚡): Ask · Code Review · Merge Review · History · **Info** · Settings · How to use

---

## Settings

| Setting | Default | Description |
|---|---|---|
| `jessie.userId` | `""` | Quota / history attribution |
| `jessie.backendUrl` | `http://localhost:8000` | Jessie FastAPI server |
| `jessie.webAppUrl` | `http://localhost:3000` | Web dashboard / History |
| `jessie.azureGitUrl` | `""` | Last used Azure clone URL |

Secrets (not in settings.json):

- Azure PAT → VS Code SecretStorage  
- Claude API key → VS Code SecretStorage (via **Info**)

---

## Web app parity

| Feature | Web | Extension v2 |
|---|---|---|
| Claude key (mandatory for reviews) | Settings → **Info** | **Jessie: Info** |
| Code Review (Azure URL + PAT + branch) | Yes | Yes |
| Code Review (local folder) | — | Yes |
| Merge Review (Azure base → head + impact) | Yes | Yes |
| Impact report | DOCX + tabs | Markdown Open Impact |
| History | `/history` | History command + open web |
| Same backend APIs | Yes | Yes |

---

## Troubleshooting

**Claude API key is required**  
→ `Jessie: Info` → Add Claude key (`sk-ant-…`). Same key concept as web Info tab.

**Backend offline**  
```bash
cd backend
python -m uvicorn api.main:app --reload --port 8000
```

**Azure clone / branches fail**  
→ PAT needs **Code (Read)**. Paste full clone URL:  
`https://dev.azure.com/{org}/{project}/_git/{repo}`  
(or with `user@` prefix).

**No Copilot model**  
→ Install/sign in to GitHub Copilot (Ask Jessie only).

---

## License

MIT

---

## Developed By

**Vijay Arther**, **Balamurugan**, **Balaji**, **Anish Kumar**, **Bhuvanesh**, **Suriya Prakash**
