#!/bin/bash
# Grammar-decoding adoption eval: DEV split, all four models.
# Each model runs under its own resource-manager lease, in turn.
# Launch detached: nohup ./run_dev.sh > run_dev.log 2>&1 &
cd "$(dirname "$0")"
# SPARK_RM is the resource-manager CLI on the Spark. The eval ran
# under a lease per model; set it to the CLI path before running.
RM="${SPARK_RM:?set SPARK_RM to the resource-manager CLI path}"
$RM run --need-mem 8 --model qwen3:8b --kind grammar-eval --ttl 3600 --wait-timeout 10800 -- python3 run_adoption_eval.py qwen3:8b dev results-qwen3-8b-dev.jsonl
$RM run --need-mem 8 --model qwen3.5:9b --kind grammar-eval --ttl 3600 --wait-timeout 10800 -- python3 run_adoption_eval.py qwen3.5:9b dev results-qwen3.5-9b-dev.jsonl
$RM run --need-mem 8 --model gemma4:12b --kind grammar-eval --ttl 3600 --wait-timeout 10800 -- python3 run_adoption_eval.py gemma4:12b dev results-gemma4-12b-dev.jsonl
$RM run --need-mem 40 --model qwen3.6:35b-a3b-mtp-q8_0 --kind grammar-eval --ttl 3600 --wait-timeout 10800 -- python3 run_adoption_eval.py qwen3.6:35b-a3b-mtp-q8_0 dev results-qwen3.6-35b-dev.jsonl
$RM run --need-mem 30 --model qwen3.8:27b-mtp-q8_0 --kind grammar-eval --ttl 3600 --wait-timeout 10800 -- python3 run_adoption_eval.py qwen3.8:27b-mtp-q8_0 dev results-qwen3.8-27b-dev.jsonl
echo "DEV DONE $(date -u +%FT%TZ)"
