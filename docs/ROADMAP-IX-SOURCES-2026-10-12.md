# Chapter IX source check — 2026-10-12

Chapter IX "The voice of the outpost" (G01–G46) was written on 2026-10-12 from working knowledge. This document records the check of its technical claims against primary documentation, done the same day by four background research passes (one per group of sub-blocks) through Context7 and background HTTP; no browser was opened, no mission was executed. Every "wording should change" row below was applied to `docs/COURSE-ROADMAP.md` in the same commit; "confirmed" rows needed no change; "not confirmed" rows stay in the roadmap as the course's own policy and are listed at the end so an author can close them before writing the mission.

Reading snapshots are not dependency pins: before a G mission is authored, re-read the source for the version actually selected (release gate 7).

Headline findings:

- The Model Context Protocol is at revision **2026-07-28**; transports are stdio and Streamable HTTP (HTTP+SSE deprecated since 2025-03-26), authorization is OAuth 2.1 with resource indicators and applies to HTTP transports only. G30 now pins that.
- OpenAI marks `seed` and `system_fingerprint` **deprecated** and best-effort; vLLM and llama.cpp do not promise bit-for-bit reproducibility across batch composition, hardware or version. G02 says so.
- The OpenTelemetry GenAI semantic conventions moved to `open-telemetry/semantic-conventions-genai` and every page is **Status: Development**; they define `gen_ai.prompt.name`/`gen_ai.prompt.version`, `retrieval` and `execute_tool` spans and keep message content opt-in. G35 names the status.
- PostgreSQL full-text ranking (`ts_rank`, `ts_rank_cd`) is **not BM25**; SQLite FTS5 `bm25()` is, with lower = better. G17 was corrected.
- On macOS the realistic local servers are llama.cpp and Ollama; vLLM CPU wheels exist for x86/Arm Linux and Apple silicon support is experimental without wheels. G38 says so.
- Ollama silently truncates an over-long prompt from the front (keeping system messages and the last message) while llama.cpp, vLLM and OpenAI refuse. G01 uses that as a transfer case.

## Calling the model (G01–G06)

| Mission | Claim checked | Verdict | Source | Applied / note |
| --- | --- | --- | --- | --- |
| G01 | `usage` carries `prompt_tokens`, `completion_tokens`, `total_tokens` (+ `prompt_tokens_details.cached_tokens`) on OpenAI, llama.cpp, vLLM and Ollama `/v1` | confirmed | OpenAI API reference (chat/completions create, streaming events); llama.cpp `tools/server/README.md`; Ollama `docs/api/openai-compatibility.mdx` | — |
| G01 | `finish_reason` includes `length` | confirmed: `stop`, `length`, `tool_calls`, `content_filter`; llama.cpp maps stop type `limit` → `length`; Ollama `done_reason` `length`/`stop` | same + llama.cpp `server-task.cpp` | — |
| G01 | logged tokens reconcile with response usage under streaming | wording changed | OpenAI streaming events: usage only with `stream_options.include_usage`, last chunk, may be missing if the stream is cut | Verification names `stream_options.include_usage` |
| G01 | over-window prompt refused before sending | confirmed design; servers differ | OpenAI "Managing tokens"; vLLM 400 "maximum context length"; llama.cpp `ERROR_TYPE_EXCEED_CONTEXT_SIZE`; Ollama drops messages from the front (`server/prompt.go`) | Transfer adds the silently truncating server |
| G01 | local token counting | wording changed | OpenAI token-counting guide: tiktoken is for plain text; tools/schemas/images add tokens; context window = prompt + generated | Objective says "prompt plus reserved output" |
| G02 | what a seed guarantees | confirmed, stronger than written | OpenAI chat create: `seed` deprecated, best effort; `system_fingerprint` deprecated; vLLM reproducibility page (batch invariance only); llama.cpp README (`seed` −1, batch size affects logits) | Verification states the deprecation |
| G03 | prompt-only versus constrained decoding | wording changed | OpenAI Structured Outputs (`response_format` `json_schema` + `strict`; subset: all fields required, `additionalProperties:false`, refusals and truncation escape the schema); llama.cpp JSON schema → GBNF grammar; vLLM structured outputs (xgrammar/guidance/outlines, `guided_*` removed in v0.12.0); Ollama `format` + `response_format` | Verification says "schema-enforced output" and names the mechanisms |
| G03 | syntactic vs domain validity | confirmed | OpenAI: "Structured Outputs can still contain mistakes" | — |
| G04 | 429 + `Retry-After` | confirmed | OpenAI rate-limits guide: `Retry-After` on 429/503, treat as minimum, add jitter; do not retry quota/billing errors; count SDK retries | Verification adds "quota and billing errors are not retried" |
| G04 | interrupted streams | confirmed | same guide: do not replay a stream after consuming output | — |
| G04 | `Retry-After` from local servers | not confirmed | not in llama.cpp/vLLM/Ollama docs | fault adapter behaviour only |
| G05 | prompt versioning, delimited data | confirmed as practice | OpenAI Responses `prompt {id, version}`; OWASP LLM01:2025 "separate and clearly denote untrusted content"; OpenAI prompt-engineering guide (XML tags) | — |
| G06 | context under a budget | confirmed | OpenAI "Managing tokens"; Ollama truncation keeps system + last message | Verification adds "including the reserved output tokens" |

## Measuring the voice (G07–G13)

| Mission | Claim checked | Verdict | Source | Applied / note |
| --- | --- | --- | --- | --- |
| G07 | reading 50–100 traces, first-failure label | wording changed | Hamel Husain & Shreya Shankar, AI Evals FAQ (2026-09-18): start with 100 diverse traces, annotate at least the first 30 by hand; open then axial coding; first failure per trace | Objective: "at least 100 traces (the first 30 annotated by hand)" |
| G08 | held-out hygiene, few-shot leakage | confirmed | Hamel, LLM-as-a-Judge guide (2024-10-29, mod. 2026-09-01): train 10–20% (few-shot source), dev 40–45%, test 40–45% frozen; 30–50 pass and fail per split | — |
| G09 | Wilson interval / bootstrap | confirmed | Wikipedia, binomial proportion CI; Miller, "Adding Error Bars to Evals", arXiv 2411.00640 (CLT SE suffices; bootstrap rarely needed) | — |
| G09 | paired comparison; "+2 on 30 cases" | confirmed | Miller: paired SE wherever practicable; clustered SEs 3× larger; ~969 questions for δ=0.03 at 80% power; never lower temperature to cut variance | Verification spells out "per-case paired differences with a standard error" |
| G10 | binary judge, TPR/TNR | confirmed | Hamel judge guide + FAQ; Anthropic develop-tests (code > LLM > human grading; grade with a different model) | — |
| G10 | order-swap and length-bias probes | wording changed | Zheng et al., MT-Bench, arXiv 2306.05685 §3.3–3.4: position bias → swap and require both orders; verbosity bias | Verification: "order-swap (for pairwise judgments)" |
| G11 | evals as CI gate with noise tolerance | confirmed; spend cap is course policy | Hamel FAQ: small purpose-built CI set, deterministic checks first, judge nightly or per release; OpenAI Evals platform read-only 2026-10-31, shutdown 2026-11-30 | do not reference the OpenAI Evals platform |
| G12 | model choice on a measured frontier | confirmed as practice | Hamel FAQ (error analysis before model switching); Miller (same questions, paired) | — |
| G13 | ablation of harness components | principle confirmed, not a named methodology | Anthropic, Building effective agents (2024-12-19): add complexity only when it demonstrably improves outcomes | — |

## The archive (G14–G22)

| Mission | Claim checked | Verdict | Source | Applied / note |
| --- | --- | --- | --- | --- |
| G14 | cosine vs normalized dot product | confirmed | OpenAI embeddings FAQ (vectors normalized to length 1); sbert semantic_textual_similarity | — |
| G14 | refuse vectors from another model | confirmed as practice, no vendor rule | Pinecone quickstart; sbert msmarco-v5 notes; pgvector README v0.8.7 (partial index per `model_id`) | Artifact keyed by model id, version and dimension |
| G15 | "any maintained parser" handles tables | wording changed | Docling (TableFormer, provenance page/bbox); PyMuPDF `find_tables` (≥1.23.0); pdfplumber `extract_tables` (machine-generated PDFs); pypdf `extract_text` has no table API; unstructured OSS "not designed for production" | Alt names parsers that return cells and location |
| G16 | chunking compared by recall@k / MRR | confirmed | Chroma, "Evaluating Chunking Strategies for Retrieval" (2024-07-03); sbert `InformationRetrievalEvaluator` | — |
| G17 | BM25 via SQLite FTS5 | confirmed | sqlite.org/fts5.html: `bm25()`, hidden `rank`, lower is better | Alt notes the sign |
| G17 | PostgreSQL full-text search as BM25 | wording changed | PostgreSQL 18 textsearch-controls: `ts_rank` frequency-based, `ts_rank_cd` cover density; "only examples" | Alt says "not BM25" |
| G18 | RRF, k=60 | confirmed | Cormack, Clarke, Büttcher, SIGIR 2009; Elasticsearch `rank_constant` 60; OpenSearch (2.19); pgvector-python `rrf.py` | Artifact cites the origin |
| G18 | rerank only if it pays | confirmed | sbert retrieve & rerank | — |
| G19 | HNSW/IVFFlat, recall vs exact, build time | confirmed | pgvector README v0.8.7 (exact by default; `hnsw.ef_search` 40; `ivfflat.probes` 1) | — |
| G19 | post-filtering returns fewer than k | confirmed | pgvector README: iterative index scans since 0.8.0 (`hnsw.iterative_scan`, `hnsw.max_scan_tuples`) | Alt adds iterative scans / partial index / partition |
| G19 | sqlite-vec / faiss on CPU | confirmed | sqlite-vec README (v0.1.10-alpha.4, pre-v1); faiss README (BLAS only, GPU optional) | sqlite-vec is pre-v1 |
| G20 | faithfulness by a judge | confirmed | RAGAS faithfulness; TruLens RAG triad groundedness | — |
| G21 | atomic reversible index swap | confirmed (PostgreSQL) | PostgreSQL 18 `ALTER INDEX … RENAME` in a transaction; `REINDEX CONCURRENTLY` cannot run in a transaction block | Alt says so; SQLite path unchecked |
| G22 | rewrite / decomposition / hypothetical answer | confirmed | HyDE, arXiv 2212.10496; Ma et al., arXiv 2305.14283; self-ask, arXiv 2210.03350 | Alt names HyDE |

## Hands of the voice (G23–G30)

| Mission | Claim checked | Verdict | Source | Applied / note |
| --- | --- | --- | --- | --- |
| G23 | native tool calling: `tools[].function.parameters`, `message.tool_calls[]`, `finish_reason: "tool_calls"`, `strict` | confirmed | OpenAI API reference (Chat Completions, `FunctionDefinition.strict`) | — |
| G23 | local servers support the contract | confirmed with caveats | llama.cpp `docs/function-calling.md` (`--jinja`, `tool_choice`, parallel calls off by default); vLLM tool_calling (`--enable-auto-tool-choice --tool-call-parser`); Ollama openai-compatibility (tools yes) ; `strict` not documented by llama.cpp/Ollama | Verification: validity measured per server, validator stays mandatory |
| G24 | execution accuracy = equal result sets | confirmed | BIRD, arXiv 2305.03111 §5 (EX); Spider test-suite evaluator (`--etype exec`) | Verification cites BIRD |
| G24 | read-only role + timeout | confirmed (timeout) / corrected (role) | PostgreSQL 18 runtime-config-client: `statement_timeout`; `default_transaction_read_only` is only a default a transaction can flip | Verification: privileges, not `default_transaction_read_only` |
| G25 | idempotency keys | confirmed | Stripe idempotent requests; IETF draft-ietf-httpapi-idempotency-key-header-07 (expired I-D) | — |
| G25 | server-issued confirmation | confirmed as methodology | OWASP LLM06:2025 (complete mediation); OpenAI practical guide to building agents; MCP 2026-07-28 `input_required` + `requestState` | — |
| G26 | workflow patterns | confirmed | Anthropic, Building effective agents (prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer); OpenAI guide: single agent first | Objective uses the source's names |
| G27 | step budget / stop conditions | confirmed | Anthropic (max iterations); OpenAI Agents SDK `max_turns` | — |
| G27 | time/token/spend reservation, loop detection | course policy, no primary source | — | kept as the course's contract |
| G28 | compaction + durable notes | confirmed | Anthropic, Effective context engineering for AI agents (2025-09-29); Claude API compaction (beta `compact-2026-09-04`); OpenAI Responses `context_management` compaction | Alt: provider compaction optional, local policy in learner code |
| G29 | pass@k / pass^k, state grading | confirmed | τ-bench, arXiv 2406.12045 (pass^k = E[C(c,k)/C(n,k)]; final DB equals goal DB) | Artifact: "(τ-bench; n ≥ k repeats)" |
| G29 | forbidden-action detector | confirmed | AgentDojo, arXiv 2406.13352 §3.4 (targeted ASR) | — |
| G30 | MCP revision and transports | wording changed | modelcontextprotocol.io/specification/versioning: current 2026-07-28; stdio + Streamable HTTP; HTTP+SSE deprecated 2025-03-26; 2026-07-28 removed the GET stream and protocol-level sessions | Objective pins the revision |
| G30 | official client lists and calls tools | confirmed, headless note | MCP Inspector `--cli --method tools/list` / `tools/call`; web mode opens a browser unless `MCP_AUTO_OPEN_ENABLED=false` | Verification: Inspector in `--cli` mode |
| G30 | malformed requests rejected | confirmed | spec schema: `-32602 InvalidParams` | Verification names the code |
| G30 | scoped access | confirmed for HTTP only | spec Authorization: OAuth 2.1, RFC 8707/9728, 403 `insufficient_scope`; stdio takes credentials from the environment | Alt rewritten per transport |
| G30 | official SDKs | confirmed | modelcontextprotocol.io/docs/sdk: TypeScript, Python, C#, Go, Rust, Ruby (tier 1) | — |

## Guarding the voice (G31–G34)

| Mission | Claim checked | Verdict | Source | Applied / note |
| --- | --- | --- | --- | --- |
| G31 | injection contained by architecture | confirmed | OWASP LLM01:2025; Willison, Dual LLM pattern (2023-04-25); CaMeL, arXiv 2503.18813 (77% AgentDojo tasks with provable security vs 84% undefended); lethal trifecta (2025-06-16) | Alt names Dual LLM, CaMeL, lethal trifecta |
| G31 | attack success rate | confirmed | AgentDojo §3.4 | — |
| G32 | encode before HTML/SQL/shell | confirmed | OWASP LLM05:2025 (treat the model as any other user; shell is the course's extension) | — |
| G32 | Markdown image exfiltration | confirmed | Willison, exfiltration-attacks tag: Imprompter (2024-10), Superhuman (2026-01, allow-listed host abused), Copilot Cowork (2026-05) | Fail adds the allow-listed-host case |
| G33 | system prompt non-secret | confirmed | OWASP LLM07:2025; LLM02:2025 | — |
| G33 | canary tokens | course technique, no primary definition | promptfoo `prompt-extraction`, garak `leakreplay` are related, not canaries | kept |
| G34 | red-team suite as regression gate | confirmed | promptfoo red-team docs (`owasp:llm`, CI); garak (NVIDIA, Apache-2.0); PyRIT moved to github.com/microsoft/PyRIT (Azure/PyRIT archived 2026-03-27) | — |

## Running and designing the voice (G35–G46)

| Mission | Claim checked | Verdict | Source | Applied / note |
| --- | --- | --- | --- | --- |
| G35 | GenAI semantic conventions | confirmed, wording changed | open-telemetry/semantic-conventions-genai (README, client-inference, gen-ai-spans, gen-ai-agent-spans; main, Status: Development) | Objective names the status |
| G35 | spans for model, retrieval, tool | confirmed | inference CLIENT span `{op} {model}`; `retrieval {gen_ai.data_source.id}`; `execute_tool {gen_ai.tool.name}`; agent spans | — |
| G35 | attributes model, tokens, prompt version | confirmed | `gen_ai.request.model`, `gen_ai.usage.input_tokens`/`output_tokens`, `gen_ai.prompt.name`/`version` | — |
| G35 | content capture off by default | confirmed | `gen_ai.input.messages`/`output.messages`/`system_instructions` are Opt-In; env var is instrumentation-level | — |
| G35 | rerank span | wording changed | no `rerank` operation name; custom values allowed | Transfer says "custom `gen_ai.operation.name`" |
| G36 | streaming, prefix cache, cache keys | confirmed | OpenAI prompt caching (default on, whole prefix, ≥1,024 tokens, `cached_tokens`, any model change invalidates); llama.cpp `--cache-prompt`; vLLM APC + `cache_salt` | — |
| G37 | routing / cascades | confirmed | FrugalGPT, arXiv 2305.05176; RouteLLM, arXiv 2406.18665 | — |
| G38 | local CPU serving, quantization, concurrency | confirmed, wording changed | llama.cpp README + wiki (Q8_0 8 bpw, Q4_K 4.5, Q5_K 5.5, Q6_K 6.56; `--parallel`); Ollama FAQ (`OLLAMA_NUM_PARALLEL`, RAM ∝ parallel × context); vLLM CPU (x86/Arm Linux; Apple silicon experimental, no wheels) | Alt and Verification updated |
| G39 | pinned vs floating alias; retirement | confirmed (OpenAI), partial (Ollama) | OpenAI deprecations (snapshots vs aliases; ≥6 months notice for GA); Ollama tags default to `latest`, mutability not documented | Fail says "dated snapshot or digest" |
| G39 | shadow / canary / rollback | confirmed | SRE Workbook, Canarying Releases | — |
| G40 | trace sampling | confirmed | opentelemetry.io sampling (tail sampling keeps errors) | — |
| G40 | input drift | not confirmed | — | reworded to "input distribution change against the authoring baseline" |
| G41 | degrade on outage / quota | confirmed as policy | Ollama 503 beyond `OLLAMA_MAX_QUEUE`; OpenAI quota error codes not fetched | — |
| G42 | token capacity arithmetic | inputs confirmed | Ollama RAM scaling; Anthropic (agents ≈4× chat tokens, multi-agent ≈15×) | — |
| G43 | prompt vs RAG vs long context vs fine-tune | confirmed | OpenAI optimizing-llm-accuracy; Li et al., arXiv 2407.16833 (long context wins on quality, RAG cheaper, Self-Route) | — |
| G45 | distillation held-out hygiene | standard practice, no source fetched | — | — |
| G46 | orchestrator / workers | confirmed | Anthropic multi-agent research system (2025-06-13; ≈15× tokens); Building effective agents | — |

## Sources read

Grouped by provider; all fetched 2026-10-12 unless dated otherwise.

- OpenAI, developers.openai.com (platform.openai.com redirects there): API reference for Chat Completions (create, streaming events, `FunctionDefinition.strict`) and Responses (`prompt {id, version}`, `truncation`, `context_management`); guides on structured outputs, rate limits, token counting, advanced usage, prompt engineering, prompt caching, streaming responses, deprecations, optimizing LLM accuracy, embeddings, evals (platform deprecation dates).
- llama.cpp, github.com/ggml-org/llama.cpp (master): README, `tools/server/README.md`, `docs/function-calling.md`, `tools/llama-bench`, wiki Tensor-Encoding-Schemes; server source via Context7 (`server-common.cpp`, `server-task.cpp`, `server-context.cpp`).
- vLLM, docs.vllm.ai (stable, refs v0.12.0): structured_outputs, reproducibility, tool_calling, prefix_caching design, automatic_prefix_caching, CPU installation.
- Ollama, github.com/ollama/ollama (main): `docs/api.md`, `docs/api/openai-compatibility.mdx`, `docs/capabilities/structured-outputs.mdx`, `docs/faq.mdx`; `server/prompt.go` via Context7.
- Evaluation methodology: Hamel Husain & Shreya Shankar, AI Evals FAQ (hamel.dev, 2026-09-18); Hamel Husain, LLM-as-a-Judge (2024-10-29, mod. 2026-09-01), Your AI product needs evals (2024-03-29), Field guide (2025-03-24); Zheng et al., MT-Bench, arXiv 2306.05685; Miller, Adding Error Bars to Evals, arXiv 2411.00640; Wikipedia, binomial proportion confidence interval; Anthropic, develop-tests (platform.claude.com).
- Retrieval: sbert.net (semantic textual similarity, retrieve & rerank, InformationRetrievalEvaluator, msmarco-v5 notes); Pinecone bring-your-own-vectors quickstart; Docling supported formats; PyMuPDF `page.html`; pdfplumber README; pypdf docs; unstructured OSS overview; Chroma, Evaluating Chunking Strategies (2024-07-03); sqlite.org/fts5.html; PostgreSQL 18 textsearch-controls, sql-reindex, sql-alterindex, sql-begin, runtime-config-client; Cormack et al., SIGIR 2009 RRF; Elasticsearch RRF reference; OpenSearch hybrid search RRF; pgvector README v0.8.7 and pgvector-python `rrf.py`; sqlite-vec README; faiss README and wiki; RAGAS faithfulness; TruLens RAG triad; arXiv 2212.10496 (HyDE), 2305.14283 (query rewriting), 2210.03350 (self-ask).
- Agents and tools: Anthropic, Building effective agents (2024-12-19), Effective context engineering for AI agents (2025-09-29), How we built our multi-agent research system (2025-06-13), Claude API compaction; OpenAI, A practical guide to building agents (PDF), Agents SDK running_agents; τ-bench, arXiv 2406.12045; AgentDojo, arXiv 2406.13352; BIRD, arXiv 2305.03111; Spider test-suite evaluator (github.com/taoyds/test-suite-sql-eval); Stripe idempotent requests; IETF draft-ietf-httpapi-idempotency-key-header-07 (expired).
- MCP, modelcontextprotocol.io: specification/versioning; 2026-07-28 basic/transports, basic/authorization, server/tools, schema; docs/tools/inspector; docs/sdk.
- Security: OWASP Top 10 for LLM Applications 2025 (LLM01, LLM02, LLM05, LLM06, LLM07); CaMeL, arXiv 2503.18813; Simon Willison, Dual LLM pattern (2023-04-25), The lethal trifecta (2025-06-16), exfiltration-attacks tag; promptfoo red-team docs; garak (github.com/NVIDIA/garak); PyRIT (github.com/microsoft/PyRIT).
- Operations: open-telemetry/semantic-conventions-genai (main); opentelemetry-python-contrib `opentelemetry-instrumentation-openai-v2` README; opentelemetry.io sampling concepts; FrugalGPT, arXiv 2305.05176; RouteLLM, arXiv 2406.18665; Li et al., arXiv 2407.16833; Google SRE Workbook, Canarying Releases.

## Still open before authoring

- `Retry-After` emission by llama.cpp, vLLM or Ollama (G04): not documented; probe live or keep it to the fault adapter.
- llama-server `/tokenize` and tokenizer parity for local models (G01): not fetched.
- Ollama `/v1/chat/completions` `response_format` `json_schema` field shape (G03): only a one-sentence statement found; probe live.
- `strict` tool schemas on llama.cpp, vLLM and Ollama (G23): not documented; the validator is mandatory regardless.
- PostgreSQL `GRANT` page for a SELECT-only role (G24): not fetched; the enforcement point is derived from the config page.
- An explicit vendor rule against mixing embedding models (G14): only practice sources (Pinecone, sbert).
- Atomic index swap and ANN capabilities in SQLite/sqlite-vec (G19, G21): not checked.
- Cross-encoder CPU latency numbers (G18): measure inside the mission.
- A PostgreSQL BM25 extension within the no-paid-service policy (G17): not checked; only needed if BM25 must live in PostgreSQL.
- Time/token/spend reservation and loop detection (G27), canary tokens (G33), spend cap in CI (G11), ablation table (G13), distillation hygiene (G45), input distribution change (G40): the course's own contracts, not published methodology.
- OpenAI quota error codes (`insufficient_quota`) for G41's out-of-quota detection: not fetched.
- GenAI metric names (`gen_ai.client.token.usage`, `gen_ai.client.operation.duration`) for G35: page truncated; re-read `gen-ai-metrics.md`.
- Whether Ollama's `latest` tag can move (G39): pin by explicit tag or digest regardless.
- vLLM automatic prefix caching default in V1 (G36): treat as "enable explicitly".
