# Jessie AI — VS Code Extension (v3.0.0)

**Hosted backend URL:** https://jessie-ai-xpv2.onrender.com

Health check: https://jessie-ai-xpv2.onrender.com/health

Bring your own Claude / OpenAI / Gemini API key. Keys stay on your device (SecretStorage) and are never saved on the server.

## Install (VSIX)

1. Download / use `jessie-ai-3.0.0.vsix` from this folder.
2. In VS Code or Cursor:
   - `Ctrl+Shift+P` → **Extensions: Install from VSIX…**
   - Select `jessie-ai-3.0.0.vsix`
3. Reload the window if asked.

Default setting `jessie.backendUrl` is already set to:

```text
https://jessie-ai-xpv2.onrender.com
```

## First-run setup (~60 seconds)

On activate, Jessie opens a 3-screen wizard:

1. **Welcome** — shows backend URL + online status  
2. **API key** — Anthropic / OpenAI / Gemini → Validate (`POST /verify`)  
3. **Your name** — saved as `jessie.userId`

Status bar:
- `Jessie — API key needed` → click to setup  
- `Jessie — ready (Anthropic)` → good to go  

## Commands

| Command | What |
|---------|------|
| `Jessie: Setup Jessie` | Re-run wizard |
| `Jessie: Update API Key` | Change key |
| `Jessie: Check API Key Status` | Masked key + valid/invalid |
| `Jessie: Ask Jessie` | `Ctrl+Shift+J` |
| `Jessie: Code Review` | `Ctrl+Shift+R` |
| `Jessie: Merge Review` | `Ctrl+Shift+M` |

## Settings

| Setting | Default |
|---------|---------|
| `jessie.backendUrl` | `https://jessie-ai-xpv2.onrender.com` |
| `jessie.userId` | (set in setup) |
| `jessie.aiProvider` | `anthropic` |

## Package from source

```bash
cd extension
npm install
npm run compile
npx vsce package --allow-missing-repository
```

Output: `jessie-ai-3.0.0.vsix`

## Note (Render free tier)

First request after idle can take ~50s while the server wakes up.
