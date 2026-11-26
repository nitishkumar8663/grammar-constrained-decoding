"""Probe: vLLM guided_json (xgrammar) vs unguided, small sample.

Expects a vLLM OpenAI-compatible server already running (see README.md
for the exact docker run command) on --base-url (default
http://127.0.0.1:18081) serving --model (default
thinkingmachines/Inkling-2-Mini). Runs 3 guided + 3 unguided
generations on two schemas and records the guided-decoding backend line
from the server container logs.

Writes: demo/results_vllm.jsonl
Usage: python3 demo/run_vllm_probe.py [--base-url URL] [--model NAME]
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from guided import evaluate, vllm_generate  # noqa: E402
from schemas import ENTRIES, prompt_for  # noqa: E402


def backend_line(container="p4-vllm"):
    try:
        out = subprocess.run(
            ["docker", "logs", container], capture_output=True, text=True,
            timeout=60).stdout
    except Exception as exc:  # noqa: BLE001 - log line is best-effort
        return "docker logs failed: %s" % exc
    hits = []
    for line in out.splitlines():
        low = line.lower()
        if ("structured" in low and "backend" in low) or \
                ("guided" in low and "backend" in low) or \
                "guided decoding" in low or "xgrammar" in low:
            hits.append(line.strip())
    return " | ".join(hits[:3]) if hits else \
        "no structured-output backend line found in container logs"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18081")
    parser.add_argument("--model", default="thinkingmachines/Inkling-2-Mini")
    parser.add_argument("--container", default="p4-vllm")
    args = parser.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    chosen = [e for e in ENTRIES
              if e["name"] in ("voice_request", "memory_recall")]
    records = []
    for entry in chosen:
        for i in range(3):
            prompt = prompt_for(entry, i)
            for guided in (True, False):
                gen = vllm_generate(
                    args.model, prompt,
                    schema=entry["schema"] if guided else None,
                    temperature=0.7, max_tokens=entry["max_tokens"],
                    base_url=args.base_url)
                json_ok, schema_ok, errors = evaluate(gen["text"],
                                                      entry["schema"])
                records.append({
                    "label": "vllm-guided" if guided else "vllm-unguided",
                    "schema": entry["name"], "index": i,
                    "seconds": gen["seconds"],
                    "eval_count": gen.get("eval_count") or 0,
                    "eval_seconds": gen.get("eval_seconds") or 0.0,
                    "json_ok": json_ok, "schema_ok": schema_ok,
                    "error": gen.get("error"), "schema_errors": errors,
                    "text": gen["text"],
                })
                print("%s %s #%d guided=%s json=%s schema=%s %.1fs err=%s"
                      % (entry["name"], args.model, i, guided, json_ok,
                         schema_ok, gen["seconds"], gen.get("error")),
                      flush=True)
    with open(os.path.join(here, "results_vllm.jsonl"), "w",
              encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    guided_ok = sum(1 for r in records
                    if r["label"] == "vllm-guided" and r["schema_ok"])
    unguided_ok = sum(1 for r in records
                      if r["label"] == "vllm-unguided" and r["schema_ok"])
    print("VLLM guided %d/6 schema-valid, unguided %d/6 schema-valid"
          % (guided_ok, unguided_ok))
    print("BACKEND: %s" % backend_line(args.container))


if __name__ == "__main__":
    main()
