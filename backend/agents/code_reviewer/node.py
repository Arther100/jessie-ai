"""
Jessie — backend/agents/code_reviewer/node.py

CodeReviewAgent: walks an entire project folder, classifies files into
Frontend / Backend / Database layers, calls Claude on each layer
(concurrently, with a semaphore), and returns structured findings
ready for ReviewScorer and MarkdownReporter.

Key design decisions:
  - Uses ModelRouter directly (bypasses the gateway queue — review is a
    deliberate bulk operation, not a developer's one-shot prompt).
  - Calls are limited to BATCH_CONCURRENCY simultaneous requests via asyncio.Semaphore.
  - All files are truncated to MAX_CHARS_PER_FILE before batching so no
    single Claude call exceeds practical context limits.
  - Every error is caught and logged; the pipeline always produces a
    partial report rather than crashing.
  - on_progress callback receives dicts that the SSE endpoint forwards
    to the VS Code extension in real time.
"""

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Callable, Optional

from core.state import AgentState
from gateway.model_router import ModelRouter

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", "out", "coverage", ".jessie", ".next",
    "target", ".pytest_cache", ".mypy_cache", "eggs", ".eggs",
    "reviews",   # don't review our own review reports
}

FRONTEND_EXTS = {
    ".tsx", ".ts", ".jsx", ".js", ".html", ".css", ".scss", ".vue",
    ".dart",  # Flutter / Dart UI
    ".svelte",
}
BACKEND_EXTS = {
    ".py", ".java", ".go", ".rs", ".cs", ".rb", ".php",
    ".kt", ".kts", ".scala",
}

DB_NAME_RE = re.compile(
    r"(model|schema|migration|migrate|seed|fixture)",
    re.IGNORECASE,
)

MAX_CHARS_PER_FILE  = 2_800    # enough for Flutter widgets without huge responses
MAX_CHARS_PER_BATCH = 8_000    # keep Claude JSON responses parseable (avoid truncation)
BATCH_CONCURRENCY   = 2        # slightly lower to reduce parallel truncated outputs

FRONTEND_CATEGORIES = [
    "security", "performance", "accessibility",
    "structure", "hardcoded_config", "dead_code", "advanced_flows",
]
BACKEND_CATEGORIES = [
    "security", "performance", "error_handling", "api_design",
    "structure", "hardcoded_config", "dead_code", "advanced_flows",
]
DB_CATEGORIES = [
    "security", "performance", "schema_design",
    "migrations", "transactions",
    "hardcoded_config", "dead_code", "advanced_flows",
]

# ── JSON schema appended to every system prompt ────────────────────────────

_JSON_SCHEMA = """

Respond with ONLY valid JSON — no text before or after the JSON object.

Required format:
{
  "categories": {
    "<category_name>": {
      "score": <integer 0-100>,
      "issues": [
        {
          "severity": "critical|high|medium|low",
          "file": "<filename only, no path>",
          "line": <integer, 0 if unknown>,
          "rule": "<RULE_IDENTIFIER e.g. HARDCODED_WEIGHT>",
          "title": "<concise issue title>",
          "detail": "<what is wrong and why it matters>",
          "fix": "<how to fix it>",
          "example_before": "<bad code snippet, single line preferred>",
          "example_after": "<fixed code snippet, single line preferred>"
        }
      ]
    }
  }
}

You MUST return an entry for EVERY category listed in the instructions above.
Scoring guide:  100=clean, 90-99=minor style issues, 75-89=a few real issues,
50-74=significant problems, below 50=critical/blocking problems.
Return score>=90 and empty issues list when a category is genuinely clean.
Only report real issues — do not invent problems that aren't there.
Keep JSON compact: max 3 issues per category; example_before/after under 120 chars each.
Category keys MUST be lowercase snake_case exactly as listed above.
"""

# ── System prompts ─────────────────────────────────────────────────────────

FRONTEND_SYSTEM = (
    "You are a senior frontend / Flutter engineer doing a thorough, DETAILED code review. "
    "Analyse the provided files for issues in these seven categories. "
    "When files are Dart/Flutter, EVERY finding must include a Flutter-specific fix "
    "(Widget rebuild, const constructors, Provider/Riverpod/Bloc, BuildContext async gaps, "
    "setState after dispose, GlobalKey misuse, Theme.of, MediaQuery, ListView.builder, etc.). "
    "example_before and example_after MUST be real Dart snippets when reviewing .dart files.\n\n"
    "SECURITY (weight 20%): XSS / unsafe HTML; hardcoded API keys or tokens; secrets in source; "
    "sensitive data in SharedPreferences/localStorage without encryption; missing input validation; "
    "In Flutter: storing tokens in plain SharedPreferences, printing secrets, insecure http:// APIs, "
    "WebView javascriptMode unrestricted without sanitisation.\n\n"
    "PERFORMANCE (weight 15%): Missing memoisation; heavy work on UI thread; "
    "In Flutter: missing const constructors; rebuilding large subtrees; ListView(children:) instead of "
    "ListView.builder; Opacity/ClipRRect overuse; images without cacheWidth/cacheHeight; "
    "unnecessary setState; not using RepaintBoundary where needed.\n\n"
    "ACCESSIBILITY (weight 10%): Missing semantics / labels; low contrast; "
    "In Flutter: missing Semantics / ExcludeSemantics; IconButton without tooltip; "
    "textScaleFactor ignored; hard-coded sizes that break large text.\n\n"
    "STRUCTURE (weight 15%): Unclear module boundaries; oversized widgets/files; business logic in UI; "
    "In Flutter: God widgets (>300 lines); UI+API+state mixed in one StatefulWidget; "
    "no separation of models/services/widgets; deep nested Builders.\n\n"
    "HARDCODED_CONFIG (weight 15%): Magic numbers, colors, strings, weights, URLs, feature flags "
    "inlined instead of Theme/constants/env; "
    "In Flutter: Color(0xFF...) scattered instead of ThemeData; hardcoded API base URLs; "
    "literal padding/spacing instead of design tokens.\n\n"
    "DEAD_CODE (weight 10%): Unused imports/vars/widgets; unreachable branches; commented-out blocks; "
    "In Flutter: unused packages in pubspec still imported; obsolete StatefulWidget state fields.\n\n"
    "ADVANCED_FLOWS (weight 15%): Multi-step flows missing loading/error/empty/retry; races; "
    "In Flutter: async gap using BuildContext after await without mounted check; "
    "Navigator after dispose; incomplete Form validation; missing refresh on pull-to-refresh failure."
    + _JSON_SCHEMA
)

BACKEND_SYSTEM = (
    "You are a senior backend engineer and security researcher doing a thorough code review. "
    "Analyse the provided files for issues in these eight categories:\n\n"
    "SECURITY (weight 20%): SQL injection; hardcoded secrets; missing input validation; "
    "broken auth; pickle.loads on user data; path traversal; endpoints without rate limiting.\n\n"
    "PERFORMANCE (weight 10%): N+1 queries; blocking calls inside async; O(n²) complexity; "
    "no caching for expensive work; list endpoints without pagination.\n\n"
    "ERROR_HANDLING (weight 10%): Bare except; stack traces leaked to clients; silent failures; "
    "missing retries on transient errors; unhandled async exceptions.\n\n"
    "API_DESIGN (weight 10%): Wrong HTTP status codes; inconsistent response shapes; "
    "business logic in route handlers; missing request validation; no versioning strategy.\n\n"
    "STRUCTURE (weight 15%): Unclear layering (router/service/repo mixed); circular imports; "
    "god modules; missing DTOs/models; shared utilities poorly placed; inconsistent package "
    "layout; tight coupling that makes flows hard to extend.\n\n"
    "HARDCODED_CONFIG (weight 15%): Magic numbers/strings — weights, quotas, timeouts, retry "
    "counts, status maps, role lists, URLs, feature flags — hardcoded in functions instead of "
    "constants, settings, or env; duplicated literals; scoring/weight tables embedded in code.\n\n"
    "DEAD_CODE (weight 10%): Unused imports/functions/classes; unreachable branches; "
    "commented-out handlers; obsolete feature flags; duplicate endpoints never wired; "
    "leftover debug print/log paths.\n\n"
    "ADVANCED_FLOWS (weight 10%): Multi-step business flows (checkout, import, auth, merge, "
    "webhook pipelines) missing idempotency, rollback, partial-failure handling, or "
    "compensation; race conditions; missing state transitions; no timeout/cancellation; "
    "edge cases (empty input, retries, concurrent updates) not covered."
    + _JSON_SCHEMA
)

DATABASE_SYSTEM = (
    "You are a senior database architect and DBA doing a thorough code review. "
    "Analyse the provided files for issues in these eight categories:\n\n"
    "SECURITY (weight 20%): Plaintext passwords/PII; raw SQL with user input; over-privileged "
    "DB users; missing row-level security; sensitive columns without encryption.\n\n"
    "PERFORMANCE (weight 15%): Missing indexes on FK/WHERE/ORDER BY; SELECT *; unbounded "
    "queries; N+1 ORM lazy-loading.\n\n"
    "SCHEMA_DESIGN (weight 15%): Wrong types; missing NOT NULL/UNIQUE/FK; inconsistent naming.\n\n"
    "MIGRATIONS (weight 10%): Missing down/rollback; destructive DROP without backup; "
    "no zero-downtime plan; irreversible changes.\n\n"
    "TRANSACTIONS (weight 10%): Multi-step writes without transactions; wrong isolation; "
    "deadlock risk; no optimistic locking.\n\n"
    "HARDCODED_CONFIG (weight 10%): Magic seed data, status enums, weight/score constants, "
    "or environment-specific values hardcoded in SQL/migrations instead of config/seed tables.\n\n"
    "DEAD_CODE (weight 10%): Unused tables/columns still referenced; obsolete migrations left "
    "as active code paths; commented-out SQL; unused seed fixtures.\n\n"
    "ADVANCED_FLOWS (weight 10%): Complex multi-table write flows without clear transaction "
    "boundaries; partial migration failure handling; concurrent update races; missing "
    "compensating steps for failed batches."
    + _JSON_SCHEMA
)


# ── Main agent class ───────────────────────────────────────────────────────

class CodeReviewAgent:
    """
    Walks a project folder, classifies files, and reviews each layer with Claude.

    Usage (from the review API):
        agent = CodeReviewAgent()
        results = await agent.review_project(
            folder_path = "/absolute/path/to/project",
            user_id     = "vijay",
            on_progress = lambda e: queue.put_nowait(e),
        )
    """

    def __init__(self):
        self._sem = asyncio.Semaphore(BATCH_CONCURRENCY)

    # ── Public ─────────────────────────────────────────────────────────────

    async def review_project(
        self,
        folder_path: str,
        user_id:     str = "unknown",
        on_progress: Optional[Callable] = None,
        claude_api_key: str = "",
        provider: str = "anthropic",
    ) -> dict:
        """
        Full project review.  Returns:
        {
          "frontend": {"categories": {...}},
          "backend":  {"categories": {...}},
          "database": {"categories": {...}},
          "meta": {"total_files": int, "tokens_used": int, "cost_estimate": float, ...}
        }
        """

        def _emit(event: dict):
            if on_progress:
                try:
                    on_progress(event)
                except Exception:
                    pass

        _emit({"type": "progress", "message": "Scanning project files...", "pct": 16})

        fe_files, be_files, db_files, skipped, other_exts = self._collect_files(folder_path)
        total    = len(fe_files) + len(be_files) + len(db_files)
        is_large = total >= 20

        _emit({
            "type":        "progress",
            "message":     f"Found {total} files — frontend:{len(fe_files)} backend:{len(be_files)} db:{len(db_files)}",
            "files_found": total,
            "pct":         20,
        })

        if total == 0:
            sample = ", ".join(f"{ext}×{n}" for ext, n in sorted(other_exts.items(), key=lambda x: -x[1])[:12])
            raise ValueError(
                "No reviewable source files found after clone. "
                "Jessie currently scans frontend/backend/db extensions "
                "(including .dart for Flutter). "
                + (f"Seen in repo: {sample}." if sample else "The folder may be empty or only contain ignored dirs.")
            )

        key = (claude_api_key or "").strip()
        if not key:
            raise ValueError(
                "API key is required. Include X-Claude-API-Key header."
            )
        router        = ModelRouter(api_key=key, provider=provider or "anthropic")
        tokens_used   = 0
        cost_estimate = 0.0

        frontend_result = {}
        backend_result  = {}
        db_result       = {}

        if fe_files:
            _emit({"type": "progress", "message": f"Reviewing frontend ({len(fe_files)} files)...",
                   "layer": "frontend", "pct": 25})
            frontend_result, tu, ce = await self._review_layer(
                fe_files, FRONTEND_SYSTEM, FRONTEND_CATEGORIES,
                router, is_large, "frontend", _emit, project_root=folder_path,
            )
            tokens_used   += tu
            cost_estimate += ce
            _emit({"type": "progress", "message": "Frontend review complete ✓",
                   "layer": "frontend", "pct": 48})

        if be_files:
            _emit({"type": "progress", "message": f"Reviewing backend ({len(be_files)} files)...",
                   "layer": "backend", "pct": 52})
            backend_result, tu, ce = await self._review_layer(
                be_files, BACKEND_SYSTEM, BACKEND_CATEGORIES,
                router, is_large, "backend", _emit, project_root=folder_path,
            )
            tokens_used   += tu
            cost_estimate += ce
            _emit({"type": "progress", "message": "Backend review complete ✓",
                   "layer": "backend", "pct": 72})

        if db_files:
            _emit({"type": "progress", "message": f"Reviewing database ({len(db_files)} files)...",
                   "layer": "database", "pct": 75})
            db_result, tu, ce = await self._review_layer(
                db_files, DATABASE_SYSTEM, DB_CATEGORIES,
                router, is_large, "database", _emit, project_root=folder_path,
            )
            tokens_used   += tu
            cost_estimate += ce
            _emit({"type": "progress", "message": "Database review complete ✓",
                   "layer": "database", "pct": 82})

        _emit({"type": "progress", "message": "Claude is building impact analysis...", "pct": 85})
        impact = await self._claude_project_impact(
            frontend_result, backend_result, db_result, total, router,
        )
        tokens_used += int(impact.get("tokens_used") or 0)
        cost_estimate += float(impact.get("cost_estimate") or 0)

        return {
            "frontend": frontend_result,
            "backend":  backend_result,
            "database": db_result,
            "impact_analysis": impact,
            "meta": {
                "total_files":    total,
                "frontend_files": len(fe_files),
                "backend_files":  len(be_files),
                "db_files":       len(db_files),
                "tokens_used":    tokens_used,
                "cost_estimate":  round(cost_estimate, 5),
                "skipped_files":  skipped,
                "is_flutter":     any(str(f).lower().endswith(".dart") for f in fe_files),
            },
        }

    # ── File collection ─────────────────────────────────────────────────────

    def _collect_files(self, root: str):
        fe, be, db, skipped = [], [], [], []
        other_exts: dict[str, int] = {}
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs
                       if d not in SKIP_DIRS and not d.startswith(".")]
            for fname in files:
                full = os.path.join(dirpath, fname)
                ext  = Path(fname).suffix.lower()
                stem = Path(fname).stem.lower()

                try:
                    if os.path.getsize(full) > 300_000:
                        skipped.append(full)
                        continue
                except OSError:
                    skipped.append(full)
                    continue

                if ext == ".sql" or (ext in BACKEND_EXTS and DB_NAME_RE.search(stem)):
                    db.append(full)
                elif ext in FRONTEND_EXTS:
                    fe.append(full)
                elif ext in BACKEND_EXTS:
                    be.append(full)
                else:
                    key = ext or "(noext)"
                    other_exts[key] = other_exts.get(key, 0) + 1

        return fe, be, db, skipped, other_exts

    # ── Layer reviewer ──────────────────────────────────────────────────────

    async def _review_layer(
        self,
        files:      list,
        sys_prompt: str,
        categories: list,
        router:     ModelRouter,
        is_large:   bool,
        layer_name: str,
        emit:       Callable,
        project_root: str = "",
    ) -> tuple:
        batches = self._batch_files(files)
        root = Path(project_root).resolve() if project_root else None

        def _rel_label(fp: str) -> str:
            """Safe relative path — Windows fails relpath across different drives (C: vs D:)."""
            try:
                p = Path(fp).resolve()
                if root:
                    return str(p.relative_to(root)).replace("\\", "/")
            except Exception:
                pass
            try:
                return os.path.relpath(fp).replace("\\", "/")
            except ValueError:
                return Path(fp).name

        async def _process(batch_files: list, idx: int) -> tuple:
            parts = []
            for fp in batch_files:
                try:
                    text = Path(fp).read_text(encoding="utf-8", errors="ignore")
                    text = text[:MAX_CHARS_PER_FILE]
                    rel  = _rel_label(fp)
                    parts.append(f"--- {rel} ---\n{text}")
                except Exception as exc:
                    logger.warning(f"Skipping unreadable file {fp}: {exc}")

            if not parts:
                return {}, 0, 0.0

            content = "\n\n".join(parts)
            prompt  = (
                f"Review these {layer_name} source files:\n\n{content}\n\n"
                "Return ONLY the JSON response as specified in your instructions. "
                "For every issue include a concrete Flutter/Dart or framework-specific fix "
                "in example_before / example_after when possible."
            )
            # Always use Sonnet (complexity 6) — security checks need it.
            complexity = 6

            async with self._sem:
                for attempt in range(2):
                    try:
                        result = await router.call_claude(
                            prompt=prompt,
                            complexity_score=complexity,
                            system_prompt=sys_prompt,
                        )
                        tok  = result.get("tokens_in", 0) + result.get("tokens_out", 0)
                        cost = result.get("cost_estimate", 0.0)
                        parsed = self._extract_json(result.get("response", ""))
                        emit({
                            "type":    "progress",
                            "message": f"{layer_name} batch {idx+1}/{len(batches)} done",
                            "layer":   layer_name,
                        })
                        return parsed, tok, cost
                    except Exception as exc:
                        if attempt == 0:
                            logger.warning(f"{layer_name} batch {idx} failed, retrying: {exc}")
                            await asyncio.sleep(2)
                        else:
                            logger.error(f"{layer_name} batch {idx} failed after retry: {exc}")
                            return {}, 0, 0.0

            return {}, 0, 0.0

        tasks   = [_process(b, i) for i, b in enumerate(batches)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        total_tok  = 0
        total_cost = 0.0
        parsed_results = []

        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Batch task raised: {r}")
                continue
            parsed, tok, cost = r
            if parsed:
                parsed_results.append(parsed)
            total_tok  += tok
            total_cost += cost

        merged = self._merge_results(parsed_results, categories)
        return merged, total_tok, total_cost

    # ── Claude project impact (UI-facing summary of findings) ───────────────

    async def _claude_project_impact(
        self,
        frontend: dict,
        backend: dict,
        database: dict,
        total_files: int,
        router: ModelRouter,
    ) -> dict:
        """Summarise review findings into impact / missing / change plan via Claude."""
        empty = {
            "summary": "",
            "must_change": [],
            "missing": [],
            "file_changes": [],
            "test_checklist": [],
            "recommendation": "needs_changes",
            "model": "",
            "error": "",
            "tokens_used": 0,
            "cost_estimate": 0.0,
        }

        def _issue_lines(layer: str, layer_data: dict) -> list[str]:
            lines = []
            for cat, data in (layer_data.get("categories") or {}).items():
                for iss in (data.get("issues") or [])[:8]:
                    lines.append(
                        f"[{layer}/{cat}] {iss.get('severity','medium').upper()} "
                        f"{iss.get('file','?')}: {iss.get('title','')} — {iss.get('detail','')[:180]}"
                    )
            return lines

        findings = (
            _issue_lines("frontend", frontend)
            + _issue_lines("backend", backend)
            + _issue_lines("database", database)
        )
        prompt = (
            f"Project review covered {total_files} source files.\n"
            f"Raw findings ({len(findings)} listed):\n"
            + ("\n".join(findings[:40]) if findings else "(no automated findings — still give a short honest summary)")
            + "\n\nIf this is a Flutter/Dart project, phrase must_change and file_changes as concrete Dart fixes "
            "(const widgets, mounted checks, ListView.builder, Theme tokens, etc.).\n"
            "Respond with ONLY valid JSON:\n"
            "{\n"
            '  "summary": "2-4 sentences on project health",\n'
            '  "must_change": [{"severity":"high|medium|low","title":"...","detail":"...","file":"...","fix":"..."}],\n'
            '  "missing": [{"title":"...","detail":"...","file":"..."}],\n'
            '  "file_changes": [{"file":"...","changes":["what to change 1","what to change 2"]}],\n'
            '  "test_checklist": ["..."],\n'
            '  "recommendation": "approve|needs_changes"\n'
            "}\n"
            "Rules: must_change max 8, missing max 5, file_changes max 10. Be specific about files."
        )
        system = (
            "You are Jessie, a senior engineer writing a clear impact report from a code review. "
            "Explain what is missing, what must change, and which files need edits. No markdown fences."
        )
        try:
            result = await router.call_claude(
                prompt=prompt,
                complexity_score=5,
                system_prompt=system,
            )
            parsed = self._extract_json(result.get("response", ""))
            if not parsed:
                empty["summary"] = "Claude impact could not be parsed."
                empty["error"] = "parse_failed"
                empty["model"] = result.get("model", "")
                return empty
            return {
                "summary": parsed.get("summary", ""),
                "must_change": (parsed.get("must_change") or [])[:8],
                "missing": (parsed.get("missing") or [])[:5],
                "file_changes": (parsed.get("file_changes") or [])[:10],
                "test_checklist": (parsed.get("test_checklist") or [])[:8],
                "recommendation": parsed.get("recommendation", "needs_changes"),
                "model": result.get("model", ""),
                "tokens_used": (result.get("tokens_in") or 0) + (result.get("tokens_out") or 0),
                "cost_estimate": result.get("cost_estimate") or 0.0,
                "error": "",
            }
        except Exception as exc:
            logger.exception("Project impact analysis failed")
            empty["summary"] = f"Impact analysis unavailable: {exc}"
            empty["error"] = str(exc)
            return empty

    # ── Batching ───────────────────────────────────────────────────────────

    def _batch_files(self, files: list) -> list:
        """Group files so total truncated content ≤ MAX_CHARS_PER_BATCH."""
        batches, current, current_size = [], [], 0

        for fp in files:
            try:
                size = min(os.path.getsize(fp), MAX_CHARS_PER_FILE)
            except OSError:
                size = MAX_CHARS_PER_FILE

            if current and current_size + size > MAX_CHARS_PER_BATCH:
                batches.append(current)
                current, current_size = [], 0

            current.append(fp)
            current_size += size

        if current:
            batches.append(current)

        return batches or [[]]

    # ── Result merging ─────────────────────────────────────────────────────

    def _merge_results(self, results: list, expected_categories: list) -> dict:
        """Average category scores and concatenate issues across batches."""
        if not results:
            return {"categories": {}}

        cat_scores = {c: [] for c in expected_categories}
        cat_issues = {c: [] for c in expected_categories}
        expected_set = set(expected_categories)

        for r in results:
            normalized = self._normalize_categories(r, expected_set)
            for cat in expected_categories:
                data = normalized.get(cat)
                if data:
                    cat_scores[cat].append(int(data.get("score", 50)))
                    cat_issues[cat].extend(data.get("issues", []) or [])

        merged = {"categories": {}}
        for cat in expected_categories:
            scores = cat_scores[cat]
            if not scores:
                continue
            avg = round(sum(scores) / len(scores))
            merged["categories"][cat] = {
                "score":  avg,
                "issues": cat_issues[cat],
            }

        return merged

    def _normalize_categories(self, parsed: dict, expected: set[str]) -> dict:
        """Accept categories nested or top-level; normalize key casing."""
        if not isinstance(parsed, dict):
            return {}
        raw = parsed.get("categories")
        if not isinstance(raw, dict):
            # Claude sometimes returns category keys at the top level
            if any(self._norm_key(k) in expected for k in parsed.keys()):
                raw = parsed
            else:
                return {}
        out: dict = {}
        for key, data in raw.items():
            nk = self._norm_key(str(key))
            if nk not in expected or not isinstance(data, dict):
                continue
            issues = data.get("issues") or []
            if not isinstance(issues, list):
                issues = []
            try:
                score = int(data.get("score", 50))
            except (TypeError, ValueError):
                score = 50
            out[nk] = {"score": max(0, min(100, score)), "issues": issues}
        return out

    @staticmethod
    def _norm_key(key: str) -> str:
        return key.strip().lower().replace(" ", "_").replace("-", "_")

    # ── JSON extraction ─────────────────────────────────────────────────────

    def _extract_json(self, text: str) -> dict:
        """
        Robustly extract JSON from Claude's response.
        Handles fences, nested objects, trailing commas, and mild truncation.
        """
        if not text or not text.strip():
            return {}

        candidates: list[str] = []

        # 1) Fenced ```json ... ``` (greedy inner)
        for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE):
            inner = m.group(1).strip()
            if inner.startswith("{"):
                candidates.append(inner)

        # 2) Whole text if it looks like JSON
        stripped = text.strip()
        if stripped.startswith("{"):
            candidates.append(stripped)

        # 3) Outermost balanced object
        start = text.find("{")
        if start != -1:
            depth = 0
            in_str = False
            esc = False
            for i, ch in enumerate(text[start:], start):
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[start : i + 1])
                        break
            else:
                # Truncated — take from first brace to end and try to repair
                candidates.append(text[start:])

        for cand in candidates:
            parsed = self._try_load_json(cand)
            if parsed:
                return parsed

        logger.warning(
            "Could not parse JSON from Claude response (len=%s preview=%r)",
            len(text),
            text[:240].replace("\n", " "),
        )
        return {}

    def _try_load_json(self, raw: str) -> dict:
        raw = raw.strip()
        if not raw:
            return {}
        # Strip BOM / leading junk before first {
        idx = raw.find("{")
        if idx > 0:
            raw = raw[idx:]

        attempts = [raw]
        # Remove trailing commas before } or ]
        fixed = re.sub(r",\s*([}\]])", r"\1", raw)
        attempts.append(fixed)
        attempts.append(self._close_truncated_json(fixed))

        for attempt in attempts:
            try:
                data = json.loads(attempt)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
        return {}

    @staticmethod
    def _close_truncated_json(s: str) -> str:
        """Best-effort close for truncated JSON objects/arrays."""
        if not s:
            return s
        out = s.rstrip()
        # Close an open string
        # crude: odd number of unescaped quotes
        quote_count = 0
        esc = False
        for ch in out:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                quote_count += 1
        if quote_count % 2 == 1:
            out += '"'

        out = re.sub(r",\s*$", "", out)
        stack: list[str] = []
        in_str = False
        esc = False
        for ch in out:
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in "{[":
                stack.append("}" if ch == "{" else "]")
            elif ch in "}]" and stack and stack[-1] == ch:
                stack.pop()
        while stack:
            out += stack.pop()
        return out


# ── LangGraph node wrapper ─────────────────────────────────────────────────

async def code_reviewer_node(state: AgentState) -> AgentState:
    """
    Async LangGraph node.  Only executes when state["review_triggered"] is True.
    Stores results in state["review_results"] for downstream nodes.
    """
    if not state.get("review_triggered"):
        return state

    agent   = CodeReviewAgent()
    results = await agent.review_project(
        folder_path = state.get("review_target_path", "."),
        user_id     = state.get("user_id", "unknown"),
    )

    return {
        **state,
        "review_results": results,
        "status_updates": list(state.get("status_updates", [])) + ["✅ Code review complete"],
    }
