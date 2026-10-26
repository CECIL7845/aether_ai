# Aether — Implementation Plan and Architecture

Status: Phases 1–6 are complete in code. Phase 6 still needs live verification with a search key. Last updated 2026-10-26.
"Aether" is a provisional name. Its availability has **not** been checked yet; that check happens in Phase 12. The name is configurable through `PRODUCT_NAME`.

## 1. Commercial reality (read first)

- A new product with no revenue is hard to sell for $100k as a code asset. Flippa caps the asking price of new or non-revenue assets at $9,999 ([Flippa listing rules](https://support.flippa.com/hc/en-us/articles/12856932906767-Listing-sale-pricing)). Businesses with earnings sold at an average of 2.47× profit in H1 2026 ([Flippa](https://flippa.com/blog/?p=39918)).
- Strong free, open-source competitors already exist. LibreChat is MIT-licensed (per secondary sources, still to be verified). Open WebUI is BSD-style, but branding removal is restricted above 50 users. LobeChat's community license requires a commercial license for derivative works ([Open WebUI docs](https://docs.openwebui.com/alternatives/lobehub), [TrueFoundry](https://www.truefoundry.com/blog/librechat-vs-open-webui)). A buyer can get a generic chat UI for free.
- **Implication:** the value has to come from (a) features that open-source chat UIs do poorly and (b) evidence that someone pays for it. The most practical route is to license self-hosted deployments to organisations, then use that revenue history to support a sale.

## 2. Positioning and differentiation

**Positioning:** a self-hosted AI workspace whose answers can be checked. Every claim drawn from a document, web page or dataset links back to its source, and numbers come from real calculations.

Planned differentiators:

1. **Grounded document intelligence.** Answers cite page and passage. The system refuses to claim it read a file it could not extract.
2. **Deterministic data analysis.** Statistics come from pandas/DuckDB operations. The model explains the results; it does not do the arithmetic.
3. **Web research with verifiable citations.** Only URLs that were actually retrieved can be cited.
4. **Operator controls.** Per-user spend caps, a usage and cost ledger, an audit log, and data deletion that also removes indexed chunks.
5. **Provider independence and self-hosting.** Runs with Docker Compose, the buyer brings their own API keys, and no data passes through us.

Easily copied, so not a moat: the chat UI, multi-provider support, markdown rendering, and exports.

## 3. Delivery model

**Primary: Option A, self-hosted.** It ships as Docker Compose (Postgres + app + worker + web) and the licensee supplies their own provider keys. This means:

- no recurring AI cost for us
- a clean IP transfer, because the code is ours and models and APIs stay under the buyer's own accounts
- updates delivered as versioned releases

Option B (a hosted multi-tenant service) is planned for in the data model (organisation scoping) but is not built in the MVP.

## 4. Architecture

```
Browser (React + TS, Vite)
   │  same-origin /api, session cookie + CSRF
   ▼
Django 6.1 (ASGI, uvicorn) ── DRF for CRUD ── async SSE view for streaming
   │            │                 │
   │            │                 └─ Tool runtime (allow-listed tools, server-side permission checks)
   │            └─ Provider layer: ChatProvider interface
   │                  ├─ AnthropicProvider (official `anthropic` SDK)
   │                  ├─ OpenAIProvider   (official `openai` SDK)   [verify terms/pricing first]
   │                  └─ GoogleProvider   (official `google-genai`) [verify terms/pricing first]
   ▼
PostgreSQL 18 + pgvector  (users, conversations, messages, files, chunks+embeddings, usage ledger, audit log)
   ▲
Background worker (django-tasks database backend, so no Redis is needed): file extraction, chunking, embedding
```

Key decisions:

| Decision | Choice | Why / trade-off |
|---|---|---|
| Backend | Django 6.1 + DRF on ASGI | Matches the developer's skills; the admin, migrations and auth come with the framework. Async views stream SSE without Channels. |
| Auth for the SPA | Session cookie + CSRF, Argon2 hashes | Keeps tokens out of browser storage (prevents token theft via XSS). Login and register are CSRF-protected explicitly. |
| Vector store | pgvector inside Postgres | One database to back up and operate. Hybrid retrieval with Postgres full-text search. |
| Jobs | Django 6 built-in Tasks + `django-tasks-db` (BSD) database backend; worker = `manage.py db_worker` | No Redis needed for self-hosters. |
| Embeddings | Gemini `gemini-embedding-001` at 768 dimensions (pluggable; `EMBEDDING_PROVIDER=none` gives keyword-only search) | Anthropic has no embeddings endpoint. Hybrid search (pgvector cosine + Postgres full-text, reciprocal-rank fusion) still works without embeddings. |
| Code execution | **Not in MVP** | Running arbitrary code safely needs a hardened sandbox. Coding help is explain, review and generate only. |
| Data analysis | Allow-listed operations (describe, filter, group-by, aggregate, chart spec) on pandas/DuckDB | No user or model code is executed, and every result is deterministic. |
| Web search | Tavily search API (free tier reported at 1,000 credits/month, no card) + Aether's own SSRF-hardened fetcher | Provider-independent, so any chat model can use it. Gemini's Google Search grounding is not available on the free tier (returned 429). Brave dropped its free plan in Feb 2026 (requires a card). |

## 5. MVP scope (what is built before anything else)

In: auth; conversations (streaming, stop, retry, regenerate, edit, rename, archive, delete, search, export MD/TXT); Anthropic provider plus one other provider; model registry with capability flags; usage ledger and per-user caps; file upload (PDF/DOCX/TXT/MD/CSV/XLSX) with grounded Q&A and citations; dataset analysis; web research with citations; light and dark themes; responsive UI; admin usage view; Docker Compose; tests; docs.

Later: image generation, organisations and multi-tenant hosting, user memory, PDF/DOCX report export, saved prompts, projects, code sandbox, mobile app.

## 6. Phases and acceptance gates

| # | Phase | Done when |
|---|---|---|
| 1 | Requirements and architecture | This document ✅ |
| 2 | Environment and setup | Backend + frontend run; health check proves DB + pgvector; tests and lint green ✅ |
| 3 | Conversation engine + providers | A real streamed reply is persisted; provider errors and 429s are handled; usage is recorded ✅ (verified live with Gemini; the Anthropic adapter is written but untested until a key is added) |
| 4 | UI and conversation management | Every conversation feature works end-to-end in a browser test, on desktop and mobile ✅ (Playwright, real Gemini) |
| 5 | Documents | Upload → extract → chunk → embed → cited answer; malformed, oversized and encrypted files are rejected with a clear message ✅ |
| 6 | Web research | Answers cite only fetched URLs; SSRF protections are tested ✅ in code and tests; live run needs `TAVILY_API_KEY` |
| 7 | Coding + data analysis | Dataset Q&A returns numbers computed by tools, checked against known fixtures |
| 8 | Images + tools | Tool permissions are enforced server-side; consequential actions need confirmation |
| 9 | Security and ops controls | Spend caps, rate limits, audit log, retention/deletion; OWASP checklist recorded |
| 10 | Testing | Unit, API, E2E and eval suites; report of passed, failed and not run |
| 11 | Deployment | Docker Compose deploy verified on a clean VPS; backup and restore rehearsed. **Needs Docker.** |
| 12 | Docs, IP audit, packaging | SBOM, license inventory, IP checklist, install guide, API docs |
| 13 | Listing and buyer pack | Listing copy, demo script, screenshots of real behaviour, verified platform eligibility |

## 7. Cost model (inputs; to be finished in Phase 9)

Anthropic first-party prices per million tokens, input / output (from Anthropic's model table cached 2026-10-06; re-verify before publishing):

- Claude Opus 5.5: $4 / $20
- Claude Sonnet 5.5: $2 / $10
- Claude Haiku 5.5: $0.10 / $0.50 (up to 100K-token prompts)

OpenAI, Google, search API and embedding prices are **not yet verified**.

Example assumption to test in Phase 9: 1 user × 30 messages/day × (3K input + 600 output tokens) on Sonnet 5.5 ≈ 30 × (0.003×2 + 0.0006×10) ≈ **$0.36/day** ≈ $11/month. This is before prompt caching, and document-heavy prompts cost more.

## 8. Open items

- An Anthropic key is still needed to verify the Claude adapter live (`RUN_LIVE_TESTS=1`).
- Gemini prices are not verified, so Gemini usage counts against token limits only, not the cost cap.
- Docker is not installed (Docker Desktop or Colima); it's needed by Phase 11.
- Product name and trademark check.
- Licence terms for OpenAI and Google APIs, and for any search API, before their adapters are built.
- Envato/CodeCanyon author eligibility for Ghana is unverified. Lemon Squeezy lists Ghana for bank payouts.

## 9. Document intelligence (as built)

- **Upload checks:** the extension is allow-listed, the file's real signature must match it, there are size, count and storage limits, and filenames are sanitised. Files are stored under random names and are never served by URL; downloads go through an authenticated view as `application/octet-stream`.
- **Extraction:** PDF (pypdf, keeping page numbers), DOCX (headings and tables), XLSX (cached values only, so formulas are never evaluated), CSV, and text/code files. The following fail with an explicit reason: password-protected PDFs, scanned PDFs with no text (OCR not supported), zip bombs, damaged files, and files over the page or character limits.
- **Grounding:** if all attached documents total ≤ `FULL_CONTEXT_MAX_CHARS`, they are sent in full; otherwise the top-k hybrid search results are sent. Excerpts are numbered `[S1]…` inside `<documents>` tags. Document text cannot close those tags. The system prompt tells the model to treat document content as untrusted data.
- **Citation checks:** after a reply, citations are checked against the sources actually supplied. Valid ones are stored and shown with their snippets. Invalid ones (for example `[S9]` when only S1–S2 were given) are flagged in the UI as possible fabrications.
- **Known limits:** no OCR; no image understanding inside documents; source snippets show the chunk, not a highlighted span; prompt-injection resistance relies on delimiting plus instructions and is not a guarantee.

## 10. Web research (as built)

- **Flow:** search (Tavily, 5 results) → fetch each result page with Aether's own fetcher → pick the most relevant passages → number them `[W1]…` inside `<web_results>`. The model must cite them, and citations are validated the same way as for documents.
- **Fetcher safety:** http(s) only, ports 80/443, no URLs with embedded credentials. Every redirect hop is re-validated, and any host that resolves to a private, loopback, link-local (cloud metadata), CGNAT, multicast or reserved address is refused. robots.txt is honoured. Responses are limited by size, time and content type. Scripts, navigation and footers are dropped from extracted text.
- **Honesty:** if a page could not be read, its search snippet is used and labelled `retrieved="false"` for the model and "snippet only" in the UI. Search failures are shown to the user, and the model is told there were no usable results.
- **Cost control:** web searches per user per day are capped (`WEB_SEARCHES_PER_DAY`) and recorded in the usage ledger.
- **Known limits:** pages rendered by JavaScript or behind a login can't be read. DNS rebinding remains a residual risk (use an egress proxy in high-security deployments). The search query is the user's message, not a model-rewritten query.
