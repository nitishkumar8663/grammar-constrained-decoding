#!/bin/bash
# Grammar-decoding adoption eval: DEV catch-up for the two arms the
# 22:44 dev driver lost to resource-manager queue timeouts
# (gemma4:12b, qwen3.8:27b). Temp 0.5.
# Launch detached: nohup ./run_dev_catchup.sh > run_dev_catchup.log 2>&1 &
cd "$(dirname "$0")"
# SPARK_RM is the resource-manager CLI on the Spark. The eval ran
# under a lease per model; set it to the CLI path before running.
RM="${SPARK_RM:?set SPARK_RM to the resource-manager CLI path}"
$RM run --need-mem 8 --model gemma4:12b --kind grammar-eval --ttl 3600 --wait-timeout 10800 -- python3 run_adoption_eval.py gemma4:12b dev results-gemma4-12b-dev.jsonl
$RM run --need-mem 30 --model qwen3.8:27b-mtp-q8_0 --kind grammar-eval --ttl 3600 --wait-timeout 10800 -- python3 run_adoption_eval.py qwen3.8:27b-mtp-q8_0 dev results-qwen3.8-27b-dev.jsonl
echo "DEV-CATCHUP DONE $(date -u +%FT%TZ)"
