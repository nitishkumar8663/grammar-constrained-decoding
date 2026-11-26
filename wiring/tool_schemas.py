#!/usr/bin/env python3
"""Tool-call JSON schemas for the dispatcher's small slot.

Copied verbatim from the grammar-constrained-decoding adoption trial
(team/grammar-decoding-adoption/schemas.py, the project's six real
service contracts). The trial verdict (GRAMMAR-VERDICT.md, 26 Nov
2026) is GO scoped to the Gemma small slot: Ollama `format=<schema>`
is applied ONLY when the routed model is gemma4-small, for
tool-call-shaped replies requested via `json_schema` on /dispatch or
`--json-schema` on the CLI. qwen3 models emit clean JSON unguided, so
the router never applies a format to them (see model_router.chat).

Only the schema dicts and their token budgets live here; the trial's
prompt templates and scenarios stay in the trial directory.
"""

SCHEMAS = {'cloud_exec_envelope': {'max_tokens': 320, 'schema': {'type': 'object', 'properties': {'schema': {'type': 'string', 'const': 'tier1-cloud-exec/v1'}, 'id': {'type': 'string', 'pattern': '^ce-[0-9]{8}-[0-9a-f]{8}$'}, 'from': {'type': 'string', 'const': 'tier1-dispatcher'}, 'to': {'type': 'string', 'const': 'muse'}, 'sent_utc': {'type': 'string', 'pattern': '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'}, 'capability': {'type': 'string'}, 'model': {'type': 'string'}, 'model_id': {'type': 'string'}, 'prompt': {'type': 'string', 'minLength': 1}, 'system': {'type': ['string', 'null']}, 'max_tokens': {'type': 'integer', 'minimum': 1, 'maximum': 4096}, 'temperature': {'type': 'number', 'minimum': 0, 'maximum': 2}, 'result_path': {'type': 'string'}, 'audit_id': {'type': 'string'}, 'reason': {'type': 'string'}}, 'required': ['schema', 'id', 'from', 'to', 'sent_utc', 'capability', 'model', 'model_id', 'prompt', 'system', 'max_tokens', 'temperature', 'result_path', 'audit_id', 'reason'], 'additionalProperties': False}}, 'dispatch_request': {'max_tokens': 192, 'schema': {'type': 'object', 'properties': {'text': {'type': 'string', 'minLength': 1}, 'dry_run': {'type': 'boolean'}, 'capability': {'type': 'string'}, 'prefer_cloud': {'type': 'boolean'}, 'max_tokens': {'type': ['integer', 'null'], 'minimum': 1, 'maximum': 4096}, 'temperature': {'type': 'number', 'minimum': 0, 'maximum': 2}, 'timeout': {'type': ['integer', 'null'], 'minimum': 1, 'maximum': 600}, 'voice': {'type': 'boolean'}}, 'required': ['text'], 'additionalProperties': False}}, 'memory_remember': {'max_tokens': 192, 'schema': {'type': 'object', 'properties': {'text': {'type': 'string', 'minLength': 1}, 'type': {'type': 'string'}, 'title': {'type': 'string'}, 'author': {'type': 'string'}, 'source': {'type': 'string'}, 'salience': {'type': 'number', 'minimum': 0, 'maximum': 1}}, 'required': ['text'], 'additionalProperties': False}}, 'memory_recall': {'max_tokens': 128, 'schema': {'type': 'object', 'properties': {'text': {'type': 'string', 'minLength': 1}, 'top_k': {'type': 'integer', 'minimum': 1, 'maximum': 50}, 'as_of': {'type': 'string'}}, 'required': ['text'], 'additionalProperties': False}}, 'voice_request': {'max_tokens': 128, 'schema': {'type': 'object', 'properties': {'text': {'type': 'string', 'minLength': 1}, 'speaker': {'type': 'string', 'enum': ['Amit']}}, 'required': ['text', 'speaker'], 'additionalProperties': False}}, 'gateway_query': {'max_tokens': 96, 'schema': {'type': 'object', 'properties': {'text': {'type': 'string', 'minLength': 1}}, 'required': ['text'], 'additionalProperties': False}}}


SCHEMA_NAMES = sorted(SCHEMAS)


def get_schema(name):
    """Schema dict for a tool-call shape, or None for an unknown name."""
    entry = SCHEMAS.get(name)
    return entry["schema"] if entry else None


def max_tokens_for(name):
    """Suggested num_predict budget for a schema, or None."""
    entry = SCHEMAS.get(name)
    return entry["max_tokens"] if entry else None
