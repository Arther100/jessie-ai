"""
Jessie — backend/gateway/
Invisible middleware layer that sits between the developer and Claude.

Layer order on every request:
  1. QuotaManager   — enforce daily per-user request limits
  2. SemanticCache  — return instantly if a similar prompt was seen before
  3. LangGraph prep — Prompt Coach + RAG Injector (existing nodes)
  4. JessieQueue    — rate-limit concurrent Claude API calls to MAX_CONCURRENT
  5. ModelRouter    — call Claude with the right model tier + prompt caching
  6. Quality check  — Quality Analyser + Memory Writer (existing nodes)
  7. Cache write    — store result so future similar prompts hit the cache
"""
