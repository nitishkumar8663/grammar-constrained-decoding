"""Demo: standalone CFG sampler over Ollama, token by token.

Runs 2 generations per schema (12 total) through ConstrainedSampler with
the real OllamaTokenBackend: every token is accepted only if the text so
far stays a valid prefix of a schema-valid document; rejections are
re-sampled and forced continuations fill gaps. Records acceptance /
rejection / forced counts and latency per generation.

Writes: demo/results_sampler.jsonl
Run detached (each generation is one Ollama call per token): see README.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sampler import ConstrainedSampler, OllamaTokenBackend  # noqa: E402
from schemas import ENTRIES  # noqa: E402

MODEL = "gemma3:4b-it-q8_0"


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    backend = OllamaTokenBackend(model=MODEL, temperature=0.7)
    records = []
    started = time.time()
    for entry in ENTRIES:
        for i in range(2):
            sampler = ConstrainedSampler(backend, entry["schema"],
                                         max_steps=400, max_retries=3)
            # Seed with "{" (forced for these object schemas): the raw
            # backend continues the document text directly.
            text, stats = sampler.generate(seed="{")
            stats.pop("text", None)
            records.append({"schema": entry["name"], "index": i, **stats,
                            "text": text})
            print("%s #%d valid=%s steps=%d rej=%d forced=%d %.1fs :: %s"
                  % (entry["name"], i, stats["schema_valid"],
                     stats["steps"], stats["rejected"], stats["forced"],
                     stats["seconds"], text[:160]), flush=True)
    path = os.path.join(here, "results_sampler.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    valid = sum(1 for r in records if r["schema_valid"])
    print("SAMPLER %d/%d schema-valid in %.1fs"
          % (valid, len(records), time.time() - started), flush=True)


if __name__ == "__main__":
    main()
