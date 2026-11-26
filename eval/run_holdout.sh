#!/bin/bash
# Grammar-decoding adoption eval: HOLDOUT split, all four models.
# Run ONLY after the dev split is scored. Holdout is scored exactly
# once and retired.
# Launch detached: nohup ./run_holdout.sh > run_holdout.log 2>&1 &
cd "$(dirname "$0")"
# SPARK_RM is the resource-manager CLI on the Spark. The eval ran
# under a lease per model; set it to the CLI path before running.
RM="${SPARK_RM:?set SPARK_RM to the resource-manager CLI path}"
$RM run --need-mem 8 --model qwen3:8b --kind grammar-eval --ttl 3600 --wait-timeout 10800 -- python3 run_adoption_eval.py qwen3:8b holdout results-qwen3-8b-holdout.jsonl
$RM run --need-mem 8 --model qwen3.5:9b --kind grammar-eval --ttl 3600 --wait-timeout 10800 -- python3 run_adoption_eval.py qwen3.5:9b holdout results-qwen3.5-9b-holdout.jsonl
$RM run --need-mem 8 --model gemma4:12b --kind grammar-eval --ttl 3600 --wait-timeout 10800 -- python3 run_adoption_eval.py gemma4:12b holdout results-gemma4-12b-holdout.jsonl
$RM run --need-mem 40 --model qwen3.6:35b-a3b-mtp-q8_0 --kind grammar-eval --ttl 3600 --wait-timeout 10800 -- python3 run_adoption_eval.py qwen3.6:35b-a3b-mtp-q8_0 holdout results-qwen3.6-35b-holdout.jsonl
$RM run --need-mem 30 --model qwen3.8:27b-mtp-q8_0 --kind grammar-eval --ttl 3600 --wait-timeout 10800 -- python3 run_adoption_eval.py qwen3.8:27b-mtp-q8_0 holdout results-qwen3.8-27b-holdout.jsonl
echo "HOLDOUT DONE $(date -u +%FT%TZ)"
