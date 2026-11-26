"""Demo: guided vs unguided schema-suite run on Ollama structured outputs.

Runs 100 guided generations (Ollama format=<json schema>) and 100
unguided generations (same prompts, same temperature, no grammar) across
the 6 real dispatcher/memory/voice/gateway schemas, then judges every
output with the same code: JSON parse + full schema validation.

Writes: demo/results_guided.jsonl, demo/results_unguided.jsonl,
         demo/summary.json
Run detached (takes ~10-20 min): see README.md.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from guided import ollama_generate, run_suite  # noqa: E402
from schemas import ENTRIES  # noqa: E402

MODEL = "gemma3:4b-it-q8_0"
TEMPERATURE = 0.7
COUNTS = {"cloud_exec_envelope": 17, "dispatch_request": 17,
          "memory_remember": 17, "memory_recall": 17,
          "voice_request": 16, "gateway_query": 16}


def make_generate(guided):
    def generate_fn(entry, index, prompt):
        return ollama_generate(
            MODEL, prompt,
            schema=entry["schema"] if guided else None,
            temperature=TEMPERATURE, num_predict=entry["max_tokens"])
    return generate_fn


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    started = time.time()
    all_summaries = {}
    for guided in (True, False):
        label = "guided" if guided else "unguided"
        print("=== %s: %d generations ===" % (label, sum(COUNTS.values())),
              flush=True)
        records, summary = run_suite(make_generate(guided), ENTRIES, COUNTS,
                                     temperature=TEMPERATURE, label=label)
        path = os.path.join(here, "results_%s.jsonl" % label)
        with open(path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
        all_summaries[label] = summary
        print(json.dumps(summary, indent=2), flush=True)
    guided_s = all_summaries["guided"]
    unguided_s = all_summaries["unguided"]
    overhead = None
    if unguided_s["median_seconds"]:
        overhead = round(guided_s["median_seconds"]
                         / unguided_s["median_seconds"], 2)
    all_summaries["latency_overhead_guided_vs_unguided_median"] = overhead
    all_summaries["model"] = MODEL
    all_summaries["temperature"] = TEMPERATURE
    all_summaries["wall_seconds"] = round(time.time() - started, 1)
    with open(os.path.join(here, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, indent=2)
    print("WALL %.1fs  OVERHEAD x%s" % (time.time() - started, overhead),
          flush=True)


if __name__ == "__main__":
    main()
