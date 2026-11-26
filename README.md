# Grammar-Constrained Decoding

Structured outputs for a local dispatcher. Ollama `format=<schema>` constrained decoding, scoped to the small model, so tool calls come back as raw valid JSON.

A local AI dispatcher takes free text prompts and returns free text answers. Tool calls are different: they must come back as exact JSON that matches a schema, or the receiving service cannot use them. Left alone, models wrap JSON in fences, add preamble, or drop a field. Grammar-constrained decoding forces the output to match the schema at generation time, so the reply parses and validates on the first try.

This repo holds the code, the schemas, and the eval that decided the adoption. The adopted path is Ollama `format=<schema>`, wired into the dispatcher's small-model call path only.

## How it works

Three paths, in the order they were built.

**vLLM structured outputs.** `src/guided.py` drives a vLLM OpenAI-compatible server with `structured_outputs: {"json": schema}` (xgrammar backend). Probed by `demo/run_vllm_probe.py`.

**Ollama structured outputs.** Ollama `format=<json schema>` is grammar-constrained decoding inside llama.cpp (GBNF). Same judgement code as the vLLM path, same suite, run at full scale. This is the adopted path and the source of the headline numbers.

**Standalone CFG sampler.** `src/cfg.py` is a stdlib-only JSON grammar (a tolerant recursive-descent parser that judges complete documents, incomplete prefixes, and allowed next characters) plus a JSON Schema layer that validates the completed parts of an unfinished document. `src/sampler.py` is the token-level loop: it drives a next-token backend one token at a time and accepts a token only when the text so far plus that token is still a valid prefix of a schema-valid document. Rejected tokens are re-sampled, and after `max_retries` rejections a deterministic forced continuation is appended, so it always terminates valid. The live backend reads exactly one token per Ollama streaming call (`num_predict=1`).

## Schemas

Six schemas taken from the dispatcher's real service contracts (see `src/schemas.py` for the exact source lines):

| schema | source |
|---|---|
| `cloud_exec_envelope` | dispatcher `_emit_cloud_envelope`, tier1-cloud-exec/v1 |
| `dispatch_request` | dispatcher `do_POST /dispatch` payload |
| `memory_remember` | memory-service `POST /remember` |
| `memory_recall` | memory-service `POST /recall` |
| `voice_request` | dispatcher `do_POST /voice`, speaker Amit only |
| `gateway_query` | gateway `POST /query` |

Each schema has three concrete scenarios in the demo suite; prompts name the exact values to emit. Judgement is always the same code: JSON parse plus full schema validation (`src/cfg.py`). Nothing counts as valid on the grammar alone.

## Results

Demo, 22 Nov 2026 (recorded in `demo/evidence.txt`).

- Unit tests: **30/30 pass** (`python3 -m unittest discover -s tests`).
- Ollama guided (100 generations, gemma3:4b-it-q8_0, temp 0.7): **100/100 valid JSON, 100/100 schema-valid** (17/17, 17/17, 17/17, 17/17, 16/16, 16/16 across the six schemas). Median 1.27 s, p95 6.5 s.
- Ollama unguided (100 generations, same prompts and temperature): **0/100 directly parseable**. All 100 wrapped in ```json fences. After fence-stripping: 100/100 parse, 84/100 schema-valid. Guided beats even the repaired baseline, 100 vs 84.
- Latency overhead, guided vs unguided (median): **0.88x**. Guided is slightly faster (no fences or preamble to emit).
- Standalone CFG sampler (12 generations, token-level): **10/12 schema-valid** in 57.3 s; valid median 0.65 s. Both failures are the 15-field envelope (a pattern-constrained `id` is not steerable at prefix level).
- vLLM structured outputs probe (6 guided plus 6 unguided): **guided 6/6 schema-valid, unguided 1/6**. Guided median 1.71 s, unguided median 3.47 s.

Adoption eval, 25-26 Nov 2026 (frozen set, see `eval/EVAL-DESIGN.md` and `eval/GRAMMAR-VERDICT.md`).

- Eval set: 24 fresh scenarios, 2 per schema per split (dev 12, holdout 12), seed 20261125, temp 0.5 (the dispatcher's production default). Zero overlap with the 18 demo scenarios.
- Models: qwen3:8b, qwen3.5:9b, gemma4:12b, qwen3.6:35b (chatter), qwen3.8:27b (general). Each prompt run guided and unguided: 120 generations per split.
- Holdout (the verdict set): guided raw valid **60/60**, unguided 48/60. Gemma4:12b guided 12/12, unguided 0/12 raw valid on both dev and holdout. All four qwen3 models are 12/12 unguided already. Value-correct 12/12 everywhere. Speed worst 1.26x (chatter).
- All four pass bars hold on the holdout. **Verdict: GO, scoped to the Gemma small-slot path.** The gain exists only on the Gemma arm, so the wiring goes into the small-slot call path only, not into chatter, general, or other qwen3 paths.
- Note on the public eval set: one internal file path in the cloud_exec_envelope values is replaced with the placeholder `/srv/dispatcher/cloud_results/` in this repo. The scores were re-run after the change and are identical. The as-run set had md5 `65ac24218b66d00961dd3c9e3218a81d`; the public copy has md5 `ff00947812dc75f8de4818ed4ce216e2`.

Live wiring, 26 Nov 2026.

- Ollama `format=<schema>` is wired into the dispatcher's small-slot (gemma4-small) call path for tool-call-shaped replies, using the schemas in `wiring/tool_schemas.py`. The format is requested only when the routed model is gemma4-small and the caller names a schema explicitly (`json_schema` on `/dispatch`, `--json-schema` on the CLI). qwen3 models never receive a format.
- Live probe after the wiring: a tool-call prompt returned raw JSON, no fences, parses, schema-valid, exact values, no extra keys, in 12.0 s. A normal small prompt still answers unguided. Chatter and general ignore the schema.
- See `eval/WIRING.md` for the full record.

## Layout

- `src/cfg.py`: JSON grammar, JSON Schema validation, prefix judgements.
- `src/schemas.py`: the six-schema suite.
- `src/sampler.py`: standalone token-level CFG sampler and backends.
- `src/guided.py`: Ollama and vLLM clients, suite runner, stats.
- `tests/test_grammar.py`: stdlib unittest suite (no model needed).
- `demo/run_demo.py`: 100 guided plus 100 unguided on Ollama.
- `demo/run_sampler_demo.py`: 12 generations via the standalone sampler.
- `demo/run_vllm_probe.py`: vLLM structured-outputs probe (needs a server up).
- `demo/evidence.txt`: observed numbers with the commands used.
- `eval/`: the adoption eval. `EVAL-DESIGN.md`, `GRAMMAR-VERDICT.md`, `eval_set.json` (frozen), `build_eval_set.py`, `run_adoption_eval.py`, `score.py`, plus the per-model result files.
- `wiring/tool_schemas.py`: the six schemas as deployed in the dispatcher's small-slot path.

## Run it

```bash
python3 -m unittest discover -s tests -v
# Demo (detached; about 10 to 20 minutes for the 200-generation run):
python3 demo/run_demo.py
python3 demo/run_sampler_demo.py
```

vLLM probe (needs a vLLM server up with a structured-outputs backend):

```bash
docker run -d --name grammar-vllm --gpus all --ipc=host \
  -p 127.0.0.1:18081:8000 \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  vllm/vllm-openai:inkling-2-mini thinkingmachines/Inkling-2-Mini \
  --gpu-memory-utilization 0.5 --max-model-len 16384 --port 8000
# wait for http://127.0.0.1:18081/v1/models, then:
python3 demo/run_vllm_probe.py
docker rm -f grammar-vllm
```

Eval (needs Ollama with the five models, run from `eval/`):

```bash
cd eval
python3 score.py results-gemma4-12b-holdout.jsonl
```

## Limits, honestly stated

- Ollama structured outputs and vLLM structured outputs enforce the JSON grammar, not semantic correctness. A guided output can still carry a wrong value (for example a plausible but wrong `max_tokens`). The 100/100 claim is about valid JSON plus schema conformance, measured on the run.
- The standalone sampler's mask is exact at the character level, but its Ollama backend re-samples whole tokens and can only see one token per call. Rejection plus forced continuation keeps it exact, at a latency cost (one Ollama call per token). It also cannot steer `pattern`-constrained strings at the prefix level (a regex prefix check is not implemented): the two sampler failures are both the envelope `id` pattern. The guided paths (Ollama and vLLM) do enforce patterns, because their grammars compile the full schema.
- The vLLM probe used a reasoning model behind vLLM, which spends tokens on hidden reasoning before emitting JSON, so its guided latency is not representative of a small instruct model.
- No Llama model was used in this work. The models in the demo and eval are Gemma, Inkling-2-Mini, and Qwen3.
