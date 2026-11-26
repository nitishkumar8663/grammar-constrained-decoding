#!/usr/bin/env python3
"""Build the FROZEN adoption eval set for grammar-constrained decoding.

24 fresh scenarios, 2 per schema per split (dev 12, holdout 12). Every
value is new: no text, id, timestamp or number repeats any of the 18
demo scenarios in src/schemas.py (22 Nov 2026 demo). Prompts are rendered
with the project's own prompt_template so the wording is the contract
wording; only the values are fresh.

Expected values = the scenario values the prompt names. The scorer
checks each named field against them (value-correctness) on top of
JSON parse + full schema validation (cfg.py).
"""
import hashlib
import json
import sys

sys.path.insert(0, ".")
from schemas import ENTRIES  # noqa: E402

TEMPLATE = {e["name"]: e["prompt_template"] for e in ENTRIES}
MAXTOK = {e["name"]: e["max_tokens"] for e in ENTRIES}

# Fresh scenarios: (schema, scenario dict). Booleans as real bools here;
# the builder renders them true/false inside the prompt text.
FRESH = {
    "dev": [
        ("cloud_exec_envelope", {
            "capability": "review", "model": "muse-glimmer",
            "model_id": "muse-glimmer:30b-q4_K_M-dflash",
            "prompt_text": "Review the gateway guard diff for timeout handling.",
            "envelope_id": "ce-20261125-7d2e91a4",
            "sent_utc": "2026-11-25T14:20:00Z",
            "max_tokens": 768, "temperature": 0.4,
            "audit_id": "audit-20261125-0101",
            "reason": "review model is free"}),
        ("cloud_exec_envelope", {
            "capability": "embed", "model": "bge-m3",
            "model_id": "bge-m3:latest",
            "prompt_text": "Embed the new balcony plant notes for recall.",
            "envelope_id": "ce-20261125-3b8f05c2",
            "sent_utc": "2026-11-25T14:25:00Z",
            "max_tokens": 256, "temperature": 0.2,
            "audit_id": "audit-20261125-0102",
            "reason": "embedding model is idle"}),
        ("dispatch_request", {
            "text": "How many steps did I walk yesterday?",
            "capability": "chat", "max_tokens": 64, "temperature": 0.5,
            "voice": False}),
        ("dispatch_request", {
            "text": "Summarise the Inkling retry findings in one paragraph.",
            "capability": "chat", "max_tokens": 512, "temperature": 0.6,
            "voice": False}),
        ("memory_remember", {
            "text": "Nitish wears a RingConn smart ring.",
            "kind": "fact", "title": "ring", "author": "Nitish",
            "source": "chat", "salience": 0.6}),
        ("memory_remember", {
            "text": "The TTS morning brief goes out at 06:30.",
            "kind": "decision", "title": "morning brief time",
            "author": "Muse", "source": "eval", "salience": 0.9}),
        ("memory_recall", {
            "text": "What did Nitish decide about the overcoat?",
            "top_k": 5, "as_of": "2026-11-25T14:00:00Z"}),
        ("memory_recall", {
            "text": "When is the next Tube strike?",
            "top_k": 3, "as_of": "2026-11-25T14:05:00Z"}),
        ("voice_request", {
            "text": "Good evening. The image job finished."}),
        ("voice_request", {
            "text": "Your umbrella code arrives tomorrow morning."}),
        ("gateway_query", {
            "text": "What is the P4 memory service port?"}),
        ("gateway_query", {
            "text": "How do I check the resource manager queue?"}),
    ],
    "holdout": [
        ("cloud_exec_envelope", {
            "capability": "image", "model": "z-image-turbo",
            "model_id": "z-image-turbo",
            "prompt_text": "Render a report card figure for the gateway eval.",
            "envelope_id": "ce-20261125-e51a68d9",
            "sent_utc": "2026-11-25T15:00:00Z",
            "max_tokens": 1536, "temperature": 0.8,
            "audit_id": "audit-20261125-0201",
            "reason": "image model needs cloud fallback"}),
        ("cloud_exec_envelope", {
            "capability": "tts", "model": "indic-speak",
            "model_id": "bodhan-ai/indic-speak",
            "prompt_text": "Synthesise the morning brief for Nitish.",
            "envelope_id": "ce-20261125-90c4f7b3",
            "sent_utc": "2026-11-25T15:05:00Z",
            "max_tokens": 384, "temperature": 0.6,
            "audit_id": "audit-20261125-0202",
            "reason": "tts model is busy"}),
        ("dispatch_request", {
            "text": "What is the weather in London tomorrow?",
            "capability": "chat", "max_tokens": 128, "temperature": 0.5,
            "voice": False}),
        ("dispatch_request", {
            "text": "Read the latest message from Maa out loud.",
            "capability": "chat", "max_tokens": 256, "temperature": 0.7,
            "voice": True}),
        ("memory_remember", {
            "text": "Blunt Metro umbrella is the compact pick.",
            "kind": "preference", "title": "umbrella pick",
            "author": "Nitish", "source": "chat", "salience": 0.8}),
        ("memory_remember", {
            "text": "The small-model trial queued behind the image job.",
            "kind": "incident", "title": "trial queue",
            "author": "Jarvis", "source": "systemd", "salience": 0.5}),
        ("memory_recall", {
            "text": "Which model won the small-model trial?",
            "top_k": 5, "as_of": "2026-11-25T15:00:00Z"}),
        ("memory_recall", {
            "text": "What time is the morning brief?",
            "top_k": 3, "as_of": "2026-11-25T15:05:00Z"}),
        ("voice_request", {
            "text": "The small-model trial has a new result."}),
        ("voice_request", {
            "text": "Good night. The brief is ready for tomorrow."}),
        ("gateway_query", {
            "text": "What is the gateway cache hit rate today?"}),
        ("gateway_query", {
            "text": "What models are loaded on the box right now?"}),
    ],
}

# Expected values per scenario: the exact JSON fields the prompt names.
def expected_for(schema_name, sc):
    if schema_name == "cloud_exec_envelope":
        return {
            "schema": "tier1-cloud-exec/v1", "id": sc["envelope_id"],
            "from": "tier1-dispatcher", "to": "muse",
            "sent_utc": sc["sent_utc"], "capability": sc["capability"],
            "model": sc["model"], "model_id": sc["model_id"],
            "prompt": sc["prompt_text"], "system": None,
            "max_tokens": sc["max_tokens"], "temperature": sc["temperature"],
            "result_path": "/srv/dispatcher/"
                           "cloud_results/%s.json" % sc["envelope_id"],
            "audit_id": sc["audit_id"], "reason": sc["reason"]}
    if schema_name == "dispatch_request":
        return {"text": sc["text"], "dry_run": False,
                "capability": sc["capability"], "prefer_cloud": False,
                "max_tokens": sc["max_tokens"],
                "temperature": sc["temperature"], "timeout": None,
                "voice": sc["voice"]}
    if schema_name == "memory_remember":
        return {"text": sc["text"], "type": sc["kind"], "title": sc["title"],
                "author": sc["author"], "source": sc["source"],
                "salience": sc["salience"]}
    if schema_name == "memory_recall":
        return {"text": sc["text"], "top_k": sc["top_k"],
                "as_of": sc["as_of"]}
    if schema_name == "voice_request":
        return {"text": sc["text"], "speaker": "Amit"}
    if schema_name == "gateway_query":
        return {"text": sc["text"]}
    raise ValueError(schema_name)


def render_prompt(schema_name, sc):
    rendered = dict(sc)
    for key, val in list(rendered.items()):
        if isinstance(val, bool):
            rendered[key] = "true" if val else "false"
    return TEMPLATE[schema_name].format(**rendered)


IDENTIFYING = ("text", "prompt_text", "envelope_id", "sent_utc",
              "audit_id", "title", "reason", "model_id", "as_of")


def main():
    # Freshness check: every identifying string must be new, and no
    # rendered prompt may equal a demo prompt. (Bare numbers like
    # max_tokens 256 legitimately repeat; they are not identifying.)
    demo_values = set()
    demo_prompts = set()
    for entry in ENTRIES:
        for sc in entry["scenarios"]:
            for key in IDENTIFYING:
                if key in sc:
                    demo_values.add(str(sc[key]))
            demo_prompts.add(render_prompt(entry["name"], sc))
    out = {"seed": 20261125, "temperature": 0.5, "think": False,
           "dev": [], "holdout": []}
    for split in ("dev", "holdout"):
        for i, (schema_name, sc) in enumerate(FRESH[split]):
            for key in IDENTIFYING:
                if key in sc:
                    assert str(sc[key]) not in demo_values, (
                        "collision with demo scenario: %r" % (sc[key],))
            prompt = render_prompt(schema_name, sc)
            assert prompt not in demo_prompts, (
                "prompt repeats a demo prompt: %s" % prompt[:80])
            out[split].append({
                "id": "%s-%02d" % (split, i + 1),
                "schema": schema_name,
                "prompt": prompt,
                "expected": expected_for(schema_name, sc),
                "max_tokens": MAXTOK[schema_name],
            })
    with open("eval_set.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    blob = open("eval_set.json", "rb").read()
    print("dev %d  holdout %d  md5 %s"
          % (len(out["dev"]), len(out["holdout"]),
             hashlib.md5(blob).hexdigest()))
    print("freshness check passed: no value repeats a demo scenario")


if __name__ == "__main__":
    main()
