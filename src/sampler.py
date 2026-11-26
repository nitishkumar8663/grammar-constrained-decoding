"""Standalone CFG sampler: a token-level constrained decoding loop.

The sampler owns no model. It drives a *next-token backend* one token at
a time and accepts a token only when the text-so-far plus that token is
still a valid prefix of a schema-valid JSON document (see cfg.py). A
rejected token is re-sampled; after `max_retries` rejections on one step
the sampler appends the deterministic forced continuation instead, so it
always terminates with a valid document.

Backends:
- OllamaTokenBackend: real model. Uses Ollama /api/generate with
  stream=true and num_predict=1, so each call returns exactly the
  model's next token for the prompt, which ends with the partial JSON.
- FakeBackend: deterministic script of tokens, for unit tests.
"""

import json
import time
import urllib.request

from cfg import allowed_next_chars, is_valid_prefix, parse_json, \
    partial_parse, validate_schema


class OllamaTokenBackend:
    """Next-token backend over Ollama's streaming generate endpoint.

    Uses raw mode (no chat template): the prompt is exactly the partial
    JSON text, so the model's next token is a direct continuation of the
    document. With the chat template the model instead starts a fresh
    reply (leading whitespace, markdown fences), which the grammar mask
    cannot distinguish from real progress.
    """

    def __init__(self, url="http://127.0.0.1:11434", model="gemma3:4b-it-q8_0",
                 temperature=0.7, timeout=120):
        self.url = url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def next_token(self, partial):
        """Return the model's next token after `partial`, or None."""
        body = {"model": self.model, "prompt": partial, "stream": True,
                "raw": True,
                "options": {"temperature": self.temperature, "num_predict": 1}}
        req = urllib.request.Request(
            self.url + "/api/generate", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        token = None
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            for line in resp:
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except ValueError:
                    continue
                piece = chunk.get("response") or ""
                if piece:
                    token = piece
                    break
                if chunk.get("done"):
                    break
        return token


class FakeBackend:
    """Deterministic backend: yields tokens from a script, then repeats
    the last token forever (so a sampler can always finish)."""

    def __init__(self, tokens):
        self.tokens = list(tokens)
        self.calls = 0

    def next_token(self, partial):
        self.calls += 1
        if self.calls <= len(self.tokens):
            return self.tokens[self.calls - 1]
        return self.tokens[-1] if self.tokens else None


def forced_continuation(text, schema):
    """Deterministic characters to append when sampling keeps failing.

    Derived from the grammar tail state plus the schema, so the result
    stays a valid prefix. Returns "" when the document is complete.
    """
    result = partial_parse(text)
    if result.error or result.complete:
        return ""
    tail = result.tail or {}
    kind = tail.get("kind")
    if kind == "value-start":
        # A value is expected here: use the subschema for the current key
        # (object value), the array item schema, or the root schema.
        subschema = schema if isinstance(schema, dict) else {}
        key = tail.get("key")
        if key is not None and isinstance(schema, dict):
            subschema = schema.get("properties", {}).get(key, {})
        elif "arr" in tail and isinstance(schema, dict):
            subschema = schema.get("items", {})
        if "const" in subschema:
            value = subschema["const"]
            return json.dumps(value) if not isinstance(value, str) else '"%s"' % value
        if "enum" in subschema and subschema["enum"]:
            value = subschema["enum"][0]
            return json.dumps(value) if not isinstance(value, str) else '"%s"' % value
        stype = subschema.get("type") if isinstance(subschema, dict) else None
        if stype == "object":
            return "{"
        if stype == "array":
            return "["
        if stype == "string":
            return '"'
        if stype in ("integer", "number"):
            return "0"
        if stype == "boolean":
            return "true"
        if stype == "null":
            return "null"
        return "{"
    if kind == "object-key":
        obj = tail.get("obj", {})
        required = []
        if isinstance(schema, dict):
            required = schema.get("required", [])
            props = schema.get("properties", {})
        else:
            props = {}
        missing = [k for k in required if k not in obj]
        if missing:
            return '"%s": ' % missing[0]
        remaining = [k for k in props if k not in obj]
        if remaining:
            return '"%s": ' % remaining[0]
        return "}"
    if kind == "object-colon":
        return ": "
    if kind == "object-after-value":
        obj = tail.get("obj", {})
        required = schema.get("required", []) if isinstance(schema, dict) else []
        if any(k not in obj for k in required):
            return ", "
        return "}"
    if kind == "array-value-start":
        return "]"
    if kind == "array-after-value":
        return "]"
    if kind == "string":
        partial = tail.get("partial", "")
        key = tail.get("key")
        subschema = {}
        if isinstance(schema, dict):
            subschema = schema.get("properties", {}).get(key, {})
        allowed = []
        if "const" in subschema:
            allowed = [subschema["const"]]
        elif "enum" in subschema:
            allowed = subschema["enum"]
        if allowed:
            for value in allowed:
                if isinstance(value, str) and value.startswith(partial):
                    if len(value) > len(partial):
                        return value[len(partial):len(partial) + 1]
                    return '"'
            return '"'
        return "x"
    if kind == "string-key":
        return '"'
    if kind == "literal":
        expected = tail.get("expected", "")
        partial = tail.get("partial", "")
        if len(partial) < len(expected):
            return expected[len(partial)]
        return ""
    if kind == "escape":
        return '"'
    if kind == "unicode-escape":
        return "0"
    if kind == "number":
        return "0"
    return ""


class ConstrainedSampler:
    """Token-level CFG sampler over a next-token backend."""

    def __init__(self, backend, schema, max_steps=400, max_retries=3):
        self.backend = backend
        self.schema = schema
        self.max_steps = max_steps
        self.max_retries = max_retries

    def generate(self, seed=""):
        """Returns (text, stats). Stats: steps, accepted, rejected,
        forced, seconds, valid_json, schema_valid."""
        text = seed
        stats = {"steps": 0, "accepted": 0, "rejected": 0, "forced": 0}
        started = time.time()
        while stats["steps"] < self.max_steps:
            obj, err = parse_json(text)
            if err is None and not validate_schema(obj, self.schema):
                break
            stats["steps"] += 1
            accepted_here = False
            for _ in range(self.max_retries + 1):
                token = self.backend.next_token(text)
                if not token:
                    stats["rejected"] += 1
                    continue
                # Progress rule: a whitespace-only token outside a string
                # is a valid prefix but never advances the document, so
                # the sampler could spin on spaces forever. Reject it.
                tail = partial_parse(text).tail or {}
                if (not token.strip()
                        and tail.get("kind") != "string"):
                    stats["rejected"] += 1
                    continue
                if is_valid_prefix(text + token, self.schema):
                    text += token
                    stats["accepted"] += 1
                    accepted_here = True
                    break
                stats["rejected"] += 1
            if not accepted_here:
                forced = forced_continuation(text, self.schema)
                if not forced:
                    break
                text += forced
                stats["forced"] += 1
        stats["seconds"] = round(time.time() - started, 2)
        obj, err = parse_json(text)
        stats["valid_json"] = err is None
        stats["schema_valid"] = bool(
            stats["valid_json"] and not validate_schema(obj, self.schema))
        stats["text"] = text
        return text, stats
