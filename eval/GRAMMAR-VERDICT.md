# Grammar-Constrained Decoding: adoption verdict

Date: 26 Nov 2026 ~03:10 GMT. Trial approved by Nitish 25 Nov 22:08
(he asked the parent to pick the next adoption; this was picked over a
Complexity Router round 2).

## Verdict: GO, scoped to the Gemma small-slot path

Wire Ollama `format=<schema>` structured outputs into the dispatcher's
small-slot (gemma4-small) call path for tool-call-shaped replies. Do
NOT wire it into the chatter, general, or other qwen3 paths: the qwen3
models gain nothing from it.

## Why

The result splits by model family, and it reproduced on both the dev
set and the fresh holdout (24 fresh prompts per model in total):

- **Gemma4:12b (the live small-slot model): guided 12/12 raw valid,
  unguided 0/12 raw valid, on both dev and holdout.** All 24 unguided
  outputs are wrapped in ```json fences; all 24 guided outputs start
  with raw `{`. After fence-stripping the unguided outputs parse,
  validate, and carry the right values (12/12), so the model knows
  the content. It just cannot emit raw JSON. Guided fixes exactly
  that, at zero speed cost (median 0.85 s guided vs 0.85 s unguided).
- **All four qwen3 models (8b, 3.5:9b, chatter 35b, general 27b):
  unguided is already 12/12 raw valid on both dev and holdout.**
  Guided is also 12/12 everywhere, with the same values, at most 1.26x
  the wall time. It buys them nothing.

## Eval design (frozen, see EVAL-DESIGN.md)

- Eval set: `eval_set.json`, md5
  `ff00947812dc75f8de4818ed4ce216e2`, seed 20261125. 24 fresh scenarios
- Public copy note: one internal file path in the cloud_exec_envelope values is replaced with the placeholder `/srv/dispatcher/cloud_results/`; the as-run set had md5 `65ac24218b66d00961dd3c9e3218a81d` and the scores were re-run after the change and are identical.
  (2 per schema per split: dev 12, holdout 12), zero overlap with the
  18 demo scenarios. Six real service-contract schemas. Temp 0.5 (the
  dispatcher's production default), think off.
- Models: qwen3:8b, qwen3.5:9b, gemma4:12b, qwen3.6:35b-a3b-mtp-q8_0
  (chatter), qwen3.8:27b-mtp-q8_0 (general). Each prompt run guided
  (`format=<schema>`) and unguided. 120 generations per split.
- Scorer (`score.py`, judgement code `cfg.py`): raw parse + full schema
  validation; fence-repaired parse for a fair unguided read;
  value-correctness against the exact values the prompt names.
- The holdout was scored in full once for this verdict. An earlier
  partial read of 3 arms (01:32) was monitoring only; no tuning
  followed from it, and the eval design was frozen before the holdout
  ran. The holdout is now retired.

## Holdout results (the verdict set, temp 0.5)

| Model | Guided raw valid | Unguided raw valid | Guided value | Unguided value | Median s G / U |
|---|---|---|---|---|---|
| qwen3:8b | 12/12 | 12/12 | 12/12 | 12/12 | 1.33 / 1.31 |
| qwen3.5:9b | 12/12 | 12/12 | 12/12 | 12/12 | 1.65 / 1.39 |
| gemma4:12b | 12/12 | 0/12 | 12/12 | 12/12 repaired | 0.85 / 0.85 |
| qwen3.6:35b chatter | 12/12 | 12/12 | 12/12 | 12/12 | 0.88 / 0.70 |
| qwen3.8:27b general | 12/12 | 12/12 | 12/12 | 12/12 | 2.43 / 2.32 |

Dev (same set, same temperature) reproduced the same pattern:
qwen3:8b 12/12 both, qwen3.5 guided 11/12 (one HTTP 500, see below)
vs unguided 12/12, gemma4 12/12 vs 0/12, chatter 12/12 both,
general 12/12 both.

## Pass bars (holdout)

1. Guided raw valid per model >= 0.90 (11/12); aggregate >= 0.95
   (57/60). **PASS: 12/12 every model, 60/60 aggregate.**
2. Guided value-correct >= unguided value-correct per model.
   **PASS: 12/12 guided and 12/12 unguided (repaired) on every model.**
3. Guided raw valid minus unguided raw valid >= 0.20 aggregate.
   **PASS, exactly on the line: 60/60 (1.00) minus 48/60 (0.80) =
   0.20.** Carried entirely by gemma4 (12 points). If a single
   unguided gemma4 output had parsed raw, this bar would fail. The
   aggregate number is fragile, which is why the verdict is scoped
   per model family rather than blanket.
4. Guided median wall <= 1.5x unguided median wall per model.
   **PASS: worst 1.26x (chatter, 0.88 vs 0.70 s), rest 1.00–1.19x.**

All four bars pass, so the verdict is GO. The scope follows from bar 3:
the gain exists only on the Gemma arm.

## What the wiring is

In the dispatcher's Ollama call path (`model_router.py`), pass
`format=<schema>` for tool-call-shaped replies when the routed model
is the small slot (gemma4-small), using the schemas in
`src/schemas.py`. Nothing else changes: same prompts, same temperature
(0.5), same models. The standalone CFG sampler and the vLLM arm are
not part of this adoption. No repo push and no article until the wiring
is live and verified (adoption-gated).

## Watch items

- qwen3.5:9b + `format` returned HTTP 500 "unexpected EOF" twice in
  dev (once at temp 0, once at temp 0.5), both on guided calls;
  unguided qwen3.5 had zero errors in 24 calls, and holdout guided
  was 12/12 clean. It looks like model eviction under contention
  rather than a grammar failure, but if the small slot ever moves off
  Gemma, re-check it. It does not affect this verdict: qwen3.5 is not
  a live model for any dispatcher path.
- The general arm tests the grammar only: the eval used think=false
  for all models, which matches the chatter in production, but the
  general model has no think entry in the registry, so in production
  it thinks and the router strips `<think>` blocks after. The wiring
  for the small slot does not touch the general path, so this is a
  note, not a blocker.

## Resource-manager findings (from this trial, for the parent)

Three arms were lost to resource-manager queue behaviour and had to be
re-run by hand: queue entries die after minutes with a bogus "timed
out after 10800 s" message (gemma4 dev, qwen3.8 dev, and the first
qwen3.8 holdout attempt), and a queued head is never promoted when
memory frees unless an enqueue/release event fires. The chatter
holdout entry sat at pos 0 for 20+ minutes with 45.5 GB available
against a 36 GB need. Workaround used: kill the waiting `rm run`,
`POST /cancel` the dead entry, relaunch fresh (a fresh judgement
grants immediately). The manager's "available" figure also swings
widely (21.9 GB while `free` showed 46 GB). None of this changed the
eval outcome, but it cost hours across this trial and the small-model
trial, and it is the same queue-promotion bug recorded on 25 Nov.

## Files

- `eval/` in this repo holds EVAL-DESIGN.md, GRAMMAR-VERDICT.md (this file), eval_set.json, build_eval_set.py, run_adoption_eval.py, score.py, schemas.py, cfg.py, guided.py, run_dev.sh, run_dev_catchup.sh, run_holdout.sh, results-*-dev.jsonl (temp 0.5), results-*-dev-temp0.jsonl (the discarded temp-0 dev), and results-*-holdout.jsonl (the verdict set).
- `src/` in this repo holds the project under test (unit tests 30/30, re-verified live 25 Nov 22:11).
- At the time this verdict was written, nothing was wired live, no routing changed, no repo pushed, and no article written. The wiring has since gone live; see WIRING.md.
