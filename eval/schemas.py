"""Schema suite, taken from the dispatcher's real service contracts.

Every schema is grounded in code that runs on the Spark today:

1. cloud_exec_envelope  - services/tier1-dispatcher/dispatcher.py,
   _emit_cloud_envelope, schema tier1-cloud-exec/v1. Every key the
   function writes is required here.
2. dispatch_request     - services/tier1-dispatcher/dispatcher.py,
   do_POST /dispatch payload: text, dry_run, capability, prefer_cloud,
   max_tokens, temperature, timeout, voice.
3. memory_remember      - services/memory-service/*.py, POST /remember:
   text, type, title, author, source, salience.
4. memory_recall        - services/memory-service/*.py, POST /recall:
   text, top_k, as_of.
5. voice_request        - services/tier1-dispatcher/dispatcher.py,
   do_POST /voice payload: text, speaker. Speaker is Amit only
   (Nitish approved Amit, rejected Kavya, 2026-11-20).
6. gateway_query        - inference-projects/project-09-.../gateway.py,
   POST /query: text.

Each entry carries three concrete scenarios so generations vary while
staying checkable: the prompt names the exact values to emit.
"""

ENTRIES = [
    {
        "name": "cloud_exec_envelope",
        "source": "services/tier1-dispatcher/dispatcher.py::_emit_cloud_envelope",
        "max_tokens": 320,
        "schema": {
            "type": "object",
            "properties": {
                "schema": {"type": "string", "const": "tier1-cloud-exec/v1"},
                "id": {"type": "string",
                       "pattern": "^ce-[0-9]{8}-[0-9a-f]{8}$"},
                "from": {"type": "string", "const": "tier1-dispatcher"},
                "to": {"type": "string", "const": "muse"},
                "sent_utc": {"type": "string",
                             "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
                                        "[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"},
                "capability": {"type": "string"},
                "model": {"type": "string"},
                "model_id": {"type": "string"},
                "prompt": {"type": "string", "minLength": 1},
                "system": {"type": ["string", "null"]},
                "max_tokens": {"type": "integer", "minimum": 1,
                               "maximum": 4096},
                "temperature": {"type": "number", "minimum": 0, "maximum": 2},
                "result_path": {"type": "string"},
                "audit_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["schema", "id", "from", "to", "sent_utc",
                         "capability", "model", "model_id", "prompt",
                         "system", "max_tokens", "temperature",
                         "result_path", "audit_id", "reason"],
            "additionalProperties": False,
        },
        "scenarios": [
            {
                "capability": "code", "model": "qwen3-coder-gate5",
                "model_id": "qwen3-coder:30b-a3b-q8_0",
                "prompt_text": "Write a Python function that retries an "
                               "Ollama call with backoff.",
                "envelope_id": "ce-20261122-9f3ac21e",
                "sent_utc": "2026-11-22T06:00:00Z",
                "max_tokens": 1024, "temperature": 0.5,
                "audit_id": "audit-20261122-0001",
                "reason": "local coder model is busy",
            },
            {
                "capability": "chat", "model": "qwen3.6",
                "model_id": "qwen3.6:35b-a3b-mtp-q8_0",
                "prompt_text": "Summarise the last three dispatcher audit "
                               "records in two sentences.",
                "envelope_id": "ce-20261122-41bd77c0",
                "sent_utc": "2026-11-22T06:05:00Z",
                "max_tokens": 512, "temperature": 0.7,
                "audit_id": "audit-20261122-0002",
                "reason": "chatter model is cold",
            },
            {
                "capability": "video", "model": "mistral-large-4",
                "model_id": "mistralai/mistral-large-4-1t-a52b",
                "prompt_text": "Draft a 10 second animated video script "
                               "about a local AI agent.",
                "envelope_id": "ce-20261122-c8021a5d",
                "sent_utc": "2026-11-22T06:10:00Z",
                "max_tokens": 2048, "temperature": 0.9,
                "audit_id": "audit-20261122-0003",
                "reason": "video capability needs cloud model",
            },
        ],
        "prompt_template": (
            "Emit exactly one JSON object, the tier1-cloud-exec/v1 envelope "
            "for a dispatcher request. Use these exact values: "
            'schema "tier1-cloud-exec/v1", id "{envelope_id}", '
            'from "tier1-dispatcher", to "muse", sent_utc "{sent_utc}", '
            'capability "{capability}", model "{model}", '
            'model_id "{model_id}", prompt "{prompt_text}", system null, '
            "max_tokens {max_tokens}, temperature {temperature}, "
            'result_path "/srv/dispatcher/'
            'cloud_results/{envelope_id}.json", audit_id "{audit_id}", '
            'reason "{reason}". Output only the JSON object, no other text.'
        ),
    },
    {
        "name": "dispatch_request",
        "source": "services/tier1-dispatcher/dispatcher.py::do_POST /dispatch",
        "max_tokens": 192,
        "schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "minLength": 1},
                "dry_run": {"type": "boolean"},
                "capability": {"type": "string"},
                "prefer_cloud": {"type": "boolean"},
                "max_tokens": {"type": ["integer", "null"],
                               "minimum": 1, "maximum": 4096},
                "temperature": {"type": "number", "minimum": 0, "maximum": 2},
                "timeout": {"type": ["integer", "null"],
                            "minimum": 1, "maximum": 600},
                "voice": {"type": "boolean"},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        "scenarios": [
            {"text": "What time is it in Delhi right now?",
             "capability": "chat", "max_tokens": 128, "temperature": 0.5,
             "voice": False},
            {"text": "Debug this traceback from the gateway service.",
             "capability": "code", "max_tokens": 1024, "temperature": 0.3,
             "voice": False},
            {"text": "Read me the morning summary out loud.",
             "capability": "chat", "max_tokens": 256, "temperature": 0.7,
             "voice": True},
        ],
        "prompt_template": (
            "Emit exactly one JSON object, a POST /dispatch request body. "
            'Use these exact values: text "{text}", dry_run false, '
            'capability "{capability}", prefer_cloud false, '
            "max_tokens {max_tokens}, temperature {temperature}, "
            "timeout null, voice {voice}. Output only the JSON object, "
            "no other text."
        ),
    },
    {
        "name": "memory_remember",
        "source": "services/memory-service: POST /remember",
        "max_tokens": 192,
        "schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "minLength": 1},
                "type": {"type": "string"},
                "title": {"type": "string"},
                "author": {"type": "string"},
                "source": {"type": "string"},
                "salience": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        "scenarios": [
            {"text": "Nitish prefers the Huawei Watch GT 7 in 46mm.",
             "kind": "preference", "title": "watch preference",
             "author": "Nitish", "source": "chat", "salience": 0.8},
            {"text": "The memory service died overnight with a clean exit.",
             "kind": "incident", "title": "memory service outage",
             "author": "Jarvis", "source": "systemd", "salience": 0.9},
            {"text": "P9 gateway threshold tuned to 0.90 after evaluation.",
             "kind": "decision", "title": "gateway threshold",
             "author": "Muse", "source": "eval", "salience": 0.7},
        ],
        "prompt_template": (
            "Emit exactly one JSON object, a POST /remember request body. "
            'Use these exact values: text "{text}", type "{kind}", '
            'title "{title}", author "{author}", source "{source}", '
            "salience {salience}. Output only the JSON object, "
            "no other text."
        ),
    },
    {
        "name": "memory_recall",
        "source": "services/memory-service: POST /recall",
        "max_tokens": 128,
        "schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "minLength": 1},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 50},
                "as_of": {"type": "string"},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        "scenarios": [
            {"text": "What is the P9 gateway threshold?", "top_k": 5,
             "as_of": "2026-11-22T06:00:00Z"},
            {"text": "Which watch did Nitish pick?", "top_k": 3,
             "as_of": "2026-11-22T06:05:00Z"},
            {"text": "Why did the memory service stop?", "top_k": 10,
             "as_of": "2026-11-22T06:10:00Z"},
        ],
        "prompt_template": (
            "Emit exactly one JSON object, a POST /recall request body. "
            'Use these exact values: text "{text}", top_k {top_k}, '
            'as_of "{as_of}". Output only the JSON object, no other text.'
        ),
    },
    {
        "name": "voice_request",
        "source": "services/tier1-dispatcher/dispatcher.py::do_POST /voice",
        "max_tokens": 128,
        "schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "minLength": 1},
                "speaker": {"type": "string", "enum": ["Amit"]},
            },
            "required": ["text", "speaker"],
            "additionalProperties": False,
        },
        "scenarios": [
            {"text": "Good morning. The gateway cache is warm."},
            {"text": "Your 9am reminder: the P4 demo runs today."},
            {"text": "All twelve projects are scoped and P4 is done."},
        ],
        "prompt_template": (
            "Emit exactly one JSON object, a POST /voice request body. "
            'Use these exact values: text "{text}", speaker "Amit". '
            "Output only the JSON object, no other text."
        ),
    },
    {
        "name": "gateway_query",
        "source": "inference-projects/project-09-semantic-gateway-cache/gateway.py: POST /query",
        "max_tokens": 96,
        "schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "minLength": 1},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        "scenarios": [
            {"text": "What is the capital of France?"},
            {"text": "Summarise the P9 gateway demo results."},
            {"text": "How do I restart the dispatcher?"},
        ],
        "prompt_template": (
            "Emit exactly one JSON object, a POST /query request body for "
            'the semantic gateway. Use this exact value: text "{text}". '
            "Output only the JSON object, no other text."
        ),
    },
]


def prompt_for(entry, index):
    """Prompt for generation `index` of an entry (cycles scenarios)."""
    scenario = entry["scenarios"][index % len(entry["scenarios"])]
    rendered = dict(scenario)
    # JSON booleans render as true/false in the prompt text.
    for key, val in list(rendered.items()):
        if isinstance(val, bool):
            rendered[key] = "true" if val else "false"
    return entry["prompt_template"].format(**rendered)
