# Grammar-Constrained Decoding: adoption eval design

Date: 25 Nov 2026. Trial approved by Nitish 25 Nov 22:08 (he asked the
parent to pick the next adoption; this was picked over a Complexity
Router round 2, which failed its first eval on hard recall).

## Adoption candidate

Ollama `format=<json schema>` structured outputs, wired into the
dispatcher's Ollama call path for tool-call-shaped replies (envelope,
dispatch, voice) using the six real service-contract schemas in the
project's `src/schemas.py`. That is the only wiring under consideration.

Out of scope for this trial:
- The standalone CFG sampler (`src/sampler.py`): a learning artifact.
  One Ollama call per token, cannot steer `pattern` strings at prefix
  level, 10/12 in the demo. Not the adoption candidate.
- The vLLM structured-outputs arm: the demo already probed it (6/6
  guided vs 1/6 unguided on Inkling-2-Mini). A fresh vLLM trial needs
  the separate Inkling retry approval, which is still pending.
- No live routing changes, no repo push, no article until a GO verdict.

## Prior evidence (22 Nov demo, NOT the eval)

- Ollama guided, gemma3:4b-it-q8_0, temp 0.7, 100 generations:
  100/100 valid JSON, 100/100 schema-valid. Median 1.27 s.
- Ollama unguided, same prompts: 0/100 directly parseable (all wrapped
  in ```json fences). After fence-stripping: 100/100 parse, 84/100
  schema-valid. Guided beats the repaired baseline 100 vs 84.
- Latency overhead guided vs unguided median: 0.88x (guided faster,
  no fences to emit).
- Unit tests: 30/30 pass (re-verified live 25 Nov 22:11).

The demo proves the mechanism works on one small model. It does not
prove it works on the box's live models, at temp 0, on fresh prompts,
or without degrading the values emitted. That is what this eval does.

## Eval set (frozen)

- `eval_set.json`, md5 `ff00947812dc75f8de4818ed4ce216e2` (temp 0.5 build; the
  temp-0 build was md5 `a99103d1eeac2376867970395f242380`), seed 20261125.
- Public copy note: one internal file path in the cloud_exec_envelope values is replaced with the placeholder `/srv/dispatcher/cloud_results/`; the as-run set had md5 `65ac24218b66d00961dd3c9e3218a81d` and the scores were re-run after the change and are identical.
- 24 fresh scenarios, 2 per schema per split: dev 12, holdout 12.
- Every identifying value (texts, envelope ids, timestamps, audit ids,
  titles, reasons, model ids) is new; the builder asserts no overlap
  with any of the 18 demo scenarios and no rendered prompt repeats a
  demo prompt. Prompts are rendered with the project's own
  `prompt_template`, so the wording is the contract wording.
- The six schemas are the project's real service contracts
  (cloud_exec_envelope, dispatch_request, memory_remember, memory_recall,
  voice_request, gateway_query).
- Generation: temp 0.5, think off, num_predict = the schema's max_tokens.
  Temp 0.5 is the dispatcher's production default
  (`dispatcher.py` do_POST /dispatch: `payload.get("temperature", 0.5)`;
  `model_router.py` route(): `temperature=0.5`).

## Temperature amendment (25 Nov 22:40)

The first dev run used temp 0 and was discarded as the verdict basis:
at temp 0, qwen3:8b scored 12/12 raw valid guided AND unguided, and
qwen3.5:9b 11/12 guided (one HTTP 500 "unexpected EOF" on dev-01, a
model/server error under contention, not a grammar failure) vs 12/12
unguided. At temp 0 the models emit clean JSON without any grammar, so
temp 0 eliminates the problem guided decoding solves. The temp-0 dev
files are kept as a diagnostic (`results-*-dev-temp0.jsonl` on the
Spark, `results-*-dev.jsonl` on the VM). The verdict rests on temp 0.5.

## Models

- qwen3:8b (5.2 GB), small-slot baseline.
- qwen3.5:9b (6.6 GB), small-slot challenger.
- gemma4:12b (8.0 GB), small-slot challenger.
- qwen3.6:35b-a3b-mtp-q8_0 (38.7 GB), the live chatter.
- qwen3.8:27b-mtp-q8_0 (30.0 GB), the live general model. Added
  25 Nov: small work today goes to chatter or general, so the verdict
  must cover both live models. The small-slot arms answer whether a
  future slot could do this job. (Update 25 Nov 22:52, after this
  trial started: a small slot was CREATED, registry entry gemma4-small
  (gemma4:12b) with a short-factual-Q&A heuristic, verified live. So
  the gemma4 arm is now the live small-slot model, and the qwen3:8b /
  qwen3.5:9b arms are challengers to it.)

Each model runs every prompt twice: guided (`format=<schema>`) and
unguided (same prompt, no grammar). 12 prompts x 2 modes x 5 models =
120 generations per split, 240 total.

Caveat: the eval uses think=false for all models. That matches the
chatter in production (registry: think false, native API honours it).
The general model has no think entry in the registry, so in production
it thinks and the router strips `<think>` blocks after. The general arm
therefore tests the grammar, not the production think behaviour.

## Scorer (`score.py`, judgement code `cfg.py`)

Per record:
- raw valid: output parses as JSON AND passes full schema validation.
- repaired valid: same after stripping ```json fences (the demo's
  repaired baseline, so the unguided arm gets a fair quality read).
- value-correct: every field the prompt named equals the expected
  value (numbers with tolerance, booleans type-checked, null checked).
- fully-correct: repaired valid AND value-correct.
- Speed: wall seconds and eval tok/s per generation.

## Dev results (temp 0.5, 3 of 5 models)

Scored 25 Nov ~23:26. The qwen3 family emits clean JSON unguided at
the production temperature too.

- qwen3:8b guided 12/12 raw valid, 12/12 value-correct; unguided 12/12,
  12/12. Median 1.34 s guided vs 1.33 s unguided.
- qwen3.5:9b guided 11/12 raw valid, 11/12 value-correct; unguided
  12/12, 12/12. The one guided failure (dev-09 voice_request) is an
  HTTP 500 "unexpected EOF", a model/server error, not a grammar
  failure. Second such error on this model + format (the first was
  dev-01 at temp 0); unguided qwen3.5 had zero errors in 24 calls.
- qwen3.6:35b (chatter) guided 12/12, 12/12; unguided 12/12, 12/12.
  Median 0.91 s guided vs 0.76 s unguided (1.2x, inside the 1.5x bar).
- gemma4:12b and qwen3.8:27b dev did NOT run: the resource-manager
  queue entries died after minutes with a bogus "timed out after
  10800 s" message (same failure as the small-model trial). Re-queued
  as a catch-up driver 25 Nov ~23:30. The gemma4 arm is the most
  important remaining one: it is the live small-slot model, and the
  demo showed the Gemma family (gemma3:4b, temp 0.7) at 0/100 unguided
  raw valid, so it may actually need the grammar where the qwen3
  models do not.

## Dev results (temp 0.5): gemma4 (catch-up, scored 25 Nov ~23:45)

- gemma4:12b guided 12/12 raw valid, 12/12 value-correct; unguided
  **0/12 raw valid**, 12/12 repaired valid, 12/12 value-correct.
  Median 0.86 s guided vs 0.83 s unguided. All 12 unguided outputs
  start with ```json fences; all 12 guided outputs start with raw `{`.
  Guided fixes exactly the fence problem, at zero speed cost.
- The picture is now split by model family, not by temperature:
  qwen3 models (8b, 3.5, 3.6) emit clean JSON unguided at temp 0.5;
  guided buys them nothing. Gemma4 (the live small-slot model) cannot
  emit raw JSON unguided at all; guided buys it everything. The
  adoption therefore has a specific home: the small-slot (Gemma) call
  path, not a blanket change.
- qwen3.8:27b dev still running in the catch-up driver at the time of
  writing.

Bar 3 on dev so far: guided raw valid 47/48 vs unguided 36/48, a
0.23 gap, carried entirely by gemma4 (12 points). The qwen3 arms
contribute nothing to it. The verdict rests on the holdout; the
per-model bars will split by family, and the recommendation will need
to be scoped to the Gemma small slot rather than blanket.

## Pass bars (holdout only; dev is diagnostic)

1. Guided raw valid rate per model >= 0.90 (11/12); aggregate >= 0.95
   (57/60 across the five models).
2. Guided value-correct rate >= unguided value-correct rate, per model
   (constraining must not degrade the values emitted).
3. Guided raw valid minus unguided raw valid >= 0.20 aggregate
   (guided must buy at least 20 points; the control must show a real
   problem).
4. Guided median wall time <= 1.5x unguided median wall time, per model.

Verdict GO only if all four hold on the holdout. The holdout is scored
exactly once and retired. Any failure names the bar it failed.

## Holdout results and verdict (26 Nov ~03:10)

All four bars pass on the holdout (see GRAMMAR-VERDICT.md for the full
tables). Guided raw valid 60/60 aggregate; unguided 48/60; the 0.20
gap is carried entirely by gemma4 (guided 12/12, unguided 0/12 raw,
reproduced on dev and holdout). Value-correctness 12/12 everywhere;
speed worst 1.26x (chatter). **Verdict: GO, scoped to the Gemma
small-slot path.** Wire `format=<schema>` into the dispatcher's
small-slot (gemma4-small) call path only; do not wire it into the
chatter, general, or other qwen3 paths. The holdout is retired.

## Execution

Every heavy step runs under a resource-manager lease (`rm run`).
Small models: `--need-mem 8`. Chatter: `--need-mem 40`.
Dev first, then holdout. Nothing is wired live at any point.
