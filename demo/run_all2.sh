#!/bin/bash
# Demo driver 2: sampler re-run (raw mode), then corrected vLLM probe.
set -u
P="$(cd "$(dirname "$0")/.." && pwd)"
cd "$P"
echo "=== STEP 1 sampler rerun $(date -u +%FT%TZ) ==="
python3 demo/run_sampler_demo.py > /tmp/grammar-sampler2.log 2>&1
echo "sampler2 exit: $?"
echo "=== STEP 2 stop gemma, start vllm $(date -u +%FT%TZ) ==="
ollama stop gemma3:4b-it-q8_0 2>&1 | tail -1
docker rm -f grammar-vllm 2>/dev/null || true
docker run -d --name grammar-vllm --gpus all --ipc=host \
  -p 127.0.0.1:18081:8000 \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  vllm/vllm-openai:inkling-2-mini thinkingmachines/Inkling-2-Mini \
  --gpu-memory-utilization 0.3 --max-model-len 8192 --port 8000 \
  > /tmp/grammar-vllm-start2.log 2>&1
echo "vllm container: $(head -c 80 /tmp/grammar-vllm-start2.log)"
READY=0
for i in $(seq 1 100); do
  if curl -sf -m 5 http://127.0.0.1:18081/v1/models >/dev/null 2>&1; then READY=1; echo "vllm READY after ${i}x15s"; break; fi
  sleep 15
done
if [ "$READY" = "1" ]; then
  docker logs grammar-vllm 2>&1 | grep -i -m 5 -E "structured|guided|xgrammar" | tee /tmp/grammar-vllm-guided-lines2.log
  python3 demo/run_vllm_probe.py > /tmp/grammar-vllm-probe2.log 2>&1
  echo "probe2 exit: $?"
else
  echo "vllm NOT READY after 25 min" | tee /tmp/grammar-vllm-probe2.log
  docker logs --tail 30 grammar-vllm >> /tmp/grammar-vllm-probe2.log 2>&1
fi
docker rm -f grammar-vllm 2>&1 | tail -1
echo "=== STEP 3 roster restore $(date -u +%FT%TZ) ==="
ollama stop gemma3:4b-it-q8_0 2>&1 | tail -1
ollama ps > /tmp/grammar-final-roster2.log 2>&1; cat /tmp/grammar-final-roster2.log
curl -s -m 5 http://127.0.0.1:18795/health; echo " <- gateway health"
curl -s -m 5 http://127.0.0.1:18791/health; echo " <- dispatcher health"
free -g | head -2
echo "DRIVER2 DONE $(date -u +%FT%TZ)" > /tmp/grammar-driver2.done
