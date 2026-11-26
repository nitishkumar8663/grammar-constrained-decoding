"""Guided vs unguided generation clients and the schema-suite runner.

Paths:
- Ollama structured outputs (format=<json schema>): grammar-constrained
  decoding inside llama.cpp (GBNF). This is path (a) on the Spark.
- vLLM structured outputs (OpenAI-compatible /v1/completions with
  `structured_outputs: {"json": schema}`): xgrammar-backed constrained
  decoding. Probed separately by demo/run_vllm_probe.py. Note: this
  day-0 dev build REMOVED the old `guided_json` field (the server warns
  it is ignored); the current field is `structured_outputs`.
- Unguided: the same prompt, same temperature, no grammar. The baseline.

Every generation is judged by the same code: JSON parse + full schema
validation from cfg.py. Nothing is counted valid on the grammar's say-so.
"""

import json
import statistics
import time
import urllib.error
import urllib.request

from cfg import parse_json, validate_schema


def _post_json(url, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def ollama_generate(model, prompt, schema=None, temperature=0.7,
                    num_predict=256,
                    url="http://127.0.0.1:11434", timeout=300):
    """One Ollama generation. schema=None means unguided."""
    body = {"model": model, "prompt": prompt, "stream": False,
            "options": {"temperature": temperature,
                        "num_predict": num_predict}}
    if schema is not None:
        body["format"] = schema
    started = time.time()
    try:
        out = _post_json(url + "/api/generate", body, timeout)
    except urllib.error.HTTPError as exc:
        return {"text": "", "seconds": round(time.time() - started, 2),
                "error": "HTTP %d: %s" % (exc.code, exc.read()[:200].decode("utf-8", "replace")),
                "eval_count": 0, "eval_seconds": 0.0}
    except Exception as exc:  # noqa: BLE001 - record, do not crash the suite
        return {"text": "", "seconds": round(time.time() - started, 2),
                "error": str(exc)[:200], "eval_count": 0, "eval_seconds": 0.0}
    return {"text": out.get("response", ""),
            "seconds": round(time.time() - started, 2),
            "error": None,
            "eval_count": out.get("eval_count") or 0,
            "eval_seconds": round((out.get("eval_duration") or 0) / 1e9, 2)}


def _vllm_body(model, prompt, schema, temperature, max_tokens):
    """Request body for vLLM /v1/completions (kept separate for tests)."""
    body = {"model": model, "prompt": prompt, "temperature": temperature,
            "max_tokens": max_tokens, "stream": False}
    if schema is not None:
        body["structured_outputs"] = {"json": schema}
    return body


def vllm_generate(model, prompt, schema=None, temperature=0.7,
                  max_tokens=256, base_url="http://127.0.0.1:18081",
                  timeout=600):
    """One vLLM OpenAI-compatible completion. schema=None means unguided.

    This day-0 dev build REMOVED the old `guided_json` request field
    (the server warns it is ignored and output will NOT be constrained).
    The current field is top-level `structured_outputs: {"json": schema}`
    (StructuredOutputsParams in vllm.sampling_params).
    """
    body = _vllm_body(model, prompt, schema, temperature, max_tokens)
    started = time.time()
    try:
        out = _post_json(base_url + "/v1/completions", body, timeout)
    except urllib.error.HTTPError as exc:
        return {"text": "", "seconds": round(time.time() - started, 2),
                "error": "HTTP %d: %s" % (exc.code, exc.read()[:200].decode("utf-8", "replace")),
                "eval_count": 0, "eval_seconds": 0.0}
    except Exception as exc:  # noqa: BLE001 - record, do not crash the suite
        return {"text": "", "seconds": round(time.time() - started, 2),
                "error": str(exc)[:200], "eval_count": 0, "eval_seconds": 0.0}
    choice = (out.get("choices") or [{}])[0]
    usage = out.get("usage") or {}
    return {"text": choice.get("text", ""),
            "seconds": round(time.time() - started, 2),
            "error": None,
            "eval_count": usage.get("completion_tokens") or 0,
            "eval_seconds": 0.0}


def evaluate(text, schema):
    """Judge one output: (json_ok, schema_ok, [errors])."""
    obj, err = parse_json(text)
    if err is not None:
        return False, False, ["not JSON: %s" % err]
    schema_errors = validate_schema(obj, schema)
    return True, not schema_errors, schema_errors


def run_suite(generate_fn, entries, counts, temperature=0.7, label=""):
    """Run the schema suite. `counts` maps entry name -> generations.

    generate_fn(entry, index, prompt) -> generation dict (see above).
    Returns (records, summary).
    """
    records = []
    for entry in entries:
        for i in range(counts.get(entry["name"], 0)):
            from schemas import prompt_for
            prompt = prompt_for(entry, i)
            gen = generate_fn(entry, i, prompt)
            json_ok, schema_ok, errors = evaluate(gen["text"], entry["schema"])
            records.append({
                "label": label, "schema": entry["name"], "index": i,
                "seconds": gen["seconds"],
                "eval_count": gen.get("eval_count") or 0,
                "eval_seconds": gen.get("eval_seconds") or 0.0,
                "json_ok": json_ok, "schema_ok": schema_ok,
                "error": gen.get("error"), "schema_errors": errors,
                "text": gen["text"],
            })
    return records, summarize(records, label)


def summarize(records, label=""):
    n = len(records)
    ok = [r for r in records if r["schema_ok"]]
    json_ok = [r for r in records if r["json_ok"]]
    secs = [r["seconds"] for r in records]
    eval_rates = [r["eval_count"] / r["eval_seconds"]
                  for r in records
                  if r["eval_count"] and r["eval_seconds"] > 0]
    per_schema = {}
    for r in records:
        per_schema.setdefault(r["schema"], []).append(r)
    by_schema = {name: {"n": len(rs),
                        "schema_ok": sum(1 for r in rs if r["schema_ok"]),
                        "json_ok": sum(1 for r in rs if r["json_ok"])}
                 for name, rs in sorted(per_schema.items())}
    return {
        "label": label,
        "n": n,
        "json_valid": len(json_ok),
        "schema_valid": len(ok),
        "json_rate": round(len(json_ok) / n, 4) if n else 0.0,
        "schema_rate": round(len(ok) / n, 4) if n else 0.0,
        "median_seconds": round(statistics.median(secs), 2) if secs else 0.0,
        "p95_seconds": round(sorted(secs)[max(0, int(0.95 * len(secs)) - 1)], 2)
                       if secs else 0.0,
        "mean_seconds": round(statistics.mean(secs), 2) if secs else 0.0,
        "median_eval_tok_per_s": (round(statistics.median(eval_rates), 1)
                                  if eval_rates else 0.0),
        "by_schema": by_schema,
    }
