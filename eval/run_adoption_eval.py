#!/usr/bin/env python3
"""Adoption eval runner: guided vs unguided on one split, one model.

Usage: python3 run_adoption_eval.py <model> <dev|holdout> <out.jsonl>
Reads eval_set.json in the same dir. Uses the project's judgement code
(cfg.py) only for validation in score.py, not here; here we record the
raw text plus timing so scoring is reproducible offline.

Temp 0, think off (qwen3 models think by default; thinking output would
break the JSON before the grammar sees it). num_predict = the schema's
max_tokens from schemas.py. Own generate function (a copy of
guided.py:ollama_generate with think=false added) so the project code
stays untouched.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from schemas import ENTRIES  # noqa: E402

SCHEMA_BY_NAME = {e["name"]: e["schema"] for e in ENTRIES}
OLLAMA = "http://127.0.0.1:11434"


def generate(model, prompt, schema, num_predict, temperature):
    body = {"model": model, "prompt": prompt, "stream": False,
            "think": False,
            "options": {"temperature": temperature,
                        "num_predict": num_predict}}
    if schema is not None:
        body["format"] = schema
    started = time.time()
    try:
        req = urllib.request.Request(
            OLLAMA + "/api/generate", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            out = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return {"text": "",
                "seconds": round(time.time() - started, 2),
                "error": "HTTP %d: %s" % (
                    exc.code, exc.read()[:200].decode("utf-8", "replace")),
                "eval_count": 0, "eval_seconds": 0.0,
                "load_seconds": 0.0}
    except Exception as exc:  # noqa: BLE001 - record, do not crash the run
        return {"text": "",
                "seconds": round(time.time() - started, 2),
                "error": str(exc)[:200], "eval_count": 0, "eval_seconds": 0.0,
                "load_seconds": 0.0}
    return {"text": out.get("response", ""),
            "seconds": round(time.time() - started, 2),
            "error": None,
            "eval_count": out.get("eval_count") or 0,
            "eval_seconds": round((out.get("eval_duration") or 0) / 1e9, 2),
            "load_seconds": round((out.get("load_duration") or 0) / 1e9, 2)}


def main():
    model, split, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    with open("eval_set.json", encoding="utf-8") as f:
        eval_set = json.load(f)
    prompts = eval_set[split]
    temperature = eval_set.get("temperature", 0)
    records = []
    for p in prompts:
        schema = SCHEMA_BY_NAME[p["schema"]]
        for guided in (True, False):
            gen = generate(model, p["prompt"],
                           schema if guided else None, p["max_tokens"],
                           temperature)
            records.append({
                "model": model, "split": split, "id": p["id"],
                "schema": p["schema"],
                "mode": "guided" if guided else "unguided",
                "seconds": gen["seconds"],
                "eval_count": gen["eval_count"],
                "eval_seconds": gen["eval_seconds"],
                "load_seconds": gen["load_seconds"],
                "error": gen["error"],
                "text": gen["text"],
            })
            print("%s %s %s: %.1fs %s" % (
                p["id"], p["schema"],
                "guided" if guided else "unguided", gen["seconds"],
                ("ERR " + gen["error"]) if gen["error"] else "ok"),
                flush=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    print("wrote %s (%d records)" % (out_path, len(records)))


if __name__ == "__main__":
    main()
