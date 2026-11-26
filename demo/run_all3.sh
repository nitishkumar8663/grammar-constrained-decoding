#!/bin/bash
# Demo driver 3: sampler re-run with the tail type check, then restore roster.
set -u
P="$(cd "$(dirname "$0")/.." && pwd)"
cd "$P"
echo "=== sampler rerun 3 $(date -u +%FT%TZ) ==="
python3 demo/run_sampler_demo.py > /tmp/grammar-sampler3.log 2>&1
echo "sampler3 exit: $?"
ollama stop gemma3:4b-it-q8_0 2>&1 | tail -1
ollama ps > /tmp/grammar-final-roster3.log 2>&1; cat /tmp/grammar-final-roster3.log
curl -s -m 5 http://127.0.0.1:18795/health; echo " <- gateway health"
echo "DRIVER3 DONE $(date -u +%FT%TZ)" > /tmp/grammar-driver3.done
