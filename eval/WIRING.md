# Grammar-constrained decoding: live wiring record

Date: 26 Nov 2026 ~03:20 GMT. Verdict GO (GRAMMAR-VERDICT.md), scoped to
the Gemma small slot. Wired live, no repo push, no article.

## What changed (in the dispatcher's service directory)

- `tool_schemas.py` (new): the six service-contract schemas copied
  verbatim from the trial (`schemas.py`), verified identical on write.
  `get_schema(name)` / `max_tokens_for(name)` / `SCHEMA_NAMES`.
- `model_router.py`: `chat(..., format=None)`. The Ollama `/api/chat`
  payload gets `"format": <schema>` ONLY when the candidate actually
  called is `gemma4-small`. qwen3 models and the NIM fallback never
  receive one. CLI `generate` gains `--format-schema <name>`.
- `dispatcher.py`: `json_schema` threaded through CLI `run`
  (`--json-schema`), HTTP POST /dispatch (`"json_schema"`), `dispatch()`,
  `_dispatch_inner()`, `_full_path()`. The format is requested ONLY when
  the effective capability is `small` AND the policy pick is
  `gemma4-small`; anything else is ignored and recorded in the audit
  record (`json_schema_ignored`: `unknown-schema` / `not-small-slot` /
  `tool-schemas-unavailable`). `out`/`record` carry `json_schema` and
  `format_applied`; the latter is corrected after generation so it is
  only true if Gemma actually answered.
- Tests: 3 new router checks (format sent to gemma4-small, not to
  qwen3-chatter, absent when not requested), 5 new dispatcher checks
  (small + schema, chatter + schema, unknown schema, no schema,
  dry-run would-apply). Full suites: test_model_router 40/40,
  test_dispatcher_router 72/72, test_tier1 48/48.
- Backups: `dispatcher.py.bak-20261126-grammar`,
  `model_router.py.bak-20261126-grammar` (same dir).

## Trigger

Explicit only. A caller asks for a structured reply by naming a schema
(`--json-schema dispatch_request` / `"json_schema": "dispatch_request"`).
There is no heuristic sniffing of "tool-call-shaped" text: the small
slot's heuristic only claims short factual Q&A, and a tool-call prompt
does not match it, so callers use explicit `--capability small` plus
`--json-schema`. A guided call needs the explicit capability.

## Live probes (after restart 03:12:50 GMT, /health ok)

1. Guided small, fresh dispatch_request values: raw JSON, no fences,
   parses, schema-valid, exact values, no extra keys. gemma4-small,
   format_applied true, 12.0 s model latency.
2. Normal small ("what is the capital of Norway?"): "Oslo.", unguided,
   format_applied false, 42.9 s (box contended).
3. Chatter + json_schema ("tell me a joke about a penguin"): normal
   joke, qwen3-chatter, format_applied false, audit
   json_schema_ignored "not-small-slot", 17.6 s.
4. General ("what is 2+2?", --capability general): "4.",
   qwen3.8-general, format_applied false, 18.6 s.
- Gateway + memory: all four services active; memory /recall live
  (balcony plants top-1); probes show memory used (5 recalled, 2 notes)
  and gateway answering (miss/stored). One transient gateway store
  failure on probe 2 ("miss-store-failed"); probes 1/3/4 stored fine.
  Pre-existing gateway behaviour, not caused by this change.

## Caveats

- The trial eval used Ollama `/api/generate`; this wiring uses the
  dispatcher's `/api/chat`. Probe 1 proves `/api/chat` + `format`
  constrains gemma4 live, so the mechanism transfers.
- Latencies above are wall model latencies under a busy box (qwen3.8
  resident, other jobs running), not clean benchmarks.
- SSH was flaky during the probes (two foreground calls hung after the
  remote work completed); state was verified from files/audit, nothing
  was re-run blind.
