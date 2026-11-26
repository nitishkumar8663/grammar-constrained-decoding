"""Context-free grammar machinery for JSON, stdlib only.

Two layers:

1. A JSON grammar (tolerant recursive-descent parser) that judges complete
   documents, incomplete prefixes, and the set of characters that may
   legally follow an incomplete document. This is the CFG side: a partial
   document is a *valid prefix* iff some completion of it is a valid JSON
   document (plus the schema-prefix rules below).

2. A JSON Schema layer (subset: type, const, enum, properties, required,
   additionalProperties, pattern, minimum/maximum, minLength/maxLength,
   items, minItems/maxItems, anyOf/oneOf) that validates complete documents
   and, for incomplete documents, validates every *completed* part while
   skipping the incomplete tail. A completed string that violates an enum
   is rejected even though the document is unfinished; an incomplete
   string is only rejected when no enum value can still match its prefix.

Sentinel: INCOMPLETE marks a value whose text ran out mid-value.
"""

import re

INCOMPLETE = object()


class _Invalid(Exception):
    pass


# ---------------------------------------------------------------------------
# Full JSON Schema validation (complete documents)
# ---------------------------------------------------------------------------

def _type_name(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _type_matches(value, expected):
    actual = _type_name(value)
    if expected == "number":
        return actual in ("integer", "number")
    if expected == "integer":
        return actual == "integer"
    return actual == expected


def validate_schema(obj, schema, path="$"):
    """Return a list of error strings; empty list means valid."""
    errors = []
    if not isinstance(schema, dict):
        return errors
    if "const" in schema and obj != schema["const"]:
        errors.append("%s: value %r != const %r" % (path, obj, schema["const"]))
    if "enum" in schema and obj not in schema["enum"]:
        errors.append("%s: value %r not in enum %r" % (path, obj, schema["enum"]))
    if "type" in schema:
        expected = schema["type"]
        types = expected if isinstance(expected, list) else [expected]
        if not any(_type_matches(obj, t) for t in types):
            errors.append("%s: type %s, expected %s"
                          % (path, _type_name(obj), expected))
            return errors
    if isinstance(obj, str):
        if "minLength" in schema and len(obj) < schema["minLength"]:
            errors.append("%s: string shorter than minLength %d"
                          % (path, schema["minLength"]))
        if "maxLength" in schema and len(obj) > schema["maxLength"]:
            errors.append("%s: string longer than maxLength %d"
                          % (path, schema["maxLength"]))
        if "pattern" in schema:
            if not re.search(schema["pattern"], obj):
                errors.append("%s: string %r does not match pattern %r"
                              % (path, obj, schema["pattern"]))
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        if "minimum" in schema and obj < schema["minimum"]:
            errors.append("%s: %r < minimum %r" % (path, obj, schema["minimum"]))
        if "maximum" in schema and obj > schema["maximum"]:
            errors.append("%s: %r > maximum %r" % (path, obj, schema["maximum"]))
    if isinstance(obj, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in obj:
                errors.append("%s: missing required key %r" % (path, key))
        for key, val in obj.items():
            if key in props:
                errors.extend(validate_schema(val, props[key],
                                              "%s.%s" % (path, key)))
            elif schema.get("additionalProperties") is False:
                errors.append("%s: additional property %r not allowed"
                              % (path, key))
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(validate_schema(val, schema["additionalProperties"],
                                              "%s.%s" % (path, key)))
    if isinstance(obj, list):
        if "minItems" in schema and len(obj) < schema["minItems"]:
            errors.append("%s: array shorter than minItems %d"
                          % (path, schema["minItems"]))
        if "maxItems" in schema and len(obj) > schema["maxItems"]:
            errors.append("%s: array longer than maxItems %d"
                          % (path, schema["maxItems"]))
        if isinstance(schema.get("items"), dict):
            for i, item in enumerate(obj):
                errors.extend(validate_schema(item, schema["items"],
                                              "%s[%d]" % (path, i)))
    if "anyOf" in schema:
        if not any(not validate_schema(obj, sub) for sub in schema["anyOf"]):
            errors.append("%s: value matches no anyOf branch" % path)
    if "oneOf" in schema:
        hits = sum(1 for sub in schema["oneOf"]
                   if not validate_schema(obj, sub))
        if hits != 1:
            errors.append("%s: value matches %d oneOf branches, expected 1"
                          % (path, hits))
    return errors


def parse_json(text):
    """Parse a complete JSON document.

    Returns (obj, None) on success, (None, error_string) on failure.
    Uses the stdlib parser for the verdict; the grammar parser below is
    what judges prefixes.
    """
    import json
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


# ---------------------------------------------------------------------------
# Tolerant partial parser: JSON grammar over an incomplete document
# ---------------------------------------------------------------------------

_WS = " \t\n\r"
_VALUE_START = set('{"["tfn-0123456789')
_DIGITS = set("0123456789")
_HEX = set("0123456789abcdefABCDEF")
_ESCAPES = set('"/\\bfnrtu')


class PartialResult:
    def __init__(self, value, complete, tail, error=None):
        self.value = value        # tree; INCOMPLETE marks the unfinished node
        self.complete = complete  # True iff the document closed cleanly
        self.tail = tail          # None, or dict describing the unfinished tail
        self.error = error        # string, or None


class _ClosedDict(dict):
    """A dict whose closing brace was seen: required keys apply to it."""


class _ClosedList(list):
    """A list whose closing bracket was seen."""


class _PartialParser:
    def __init__(self, text):
        self.s = text
        self.n = len(text)
        self.i = 0

    def error(self, msg):
        raise _Invalid("%s at offset %d" % (msg, self.i))

    def skip_ws(self):
        while self.i < self.n and self.s[self.i] in _WS:
            self.i += 1

    def at_end(self):
        self.skip_ws()
        return self.i >= self.n

    def peek(self):
        return self.s[self.i] if self.i < self.n else None

    def parse(self):
        self.skip_ws()
        if self.i >= self.n:
            return PartialResult(INCOMPLETE, False,
                                 {"kind": "value-start"})
        try:
            value, complete, tail = self.parse_value()
        except _Invalid as exc:
            return PartialResult(None, False, None, error=str(exc))
        if complete:
            self.skip_ws()
            if self.i < self.n:
                return PartialResult(None, False, None,
                                     error="trailing characters at offset %d"
                                           % self.i)
            return PartialResult(value, True, None)
        return PartialResult(value, False, tail)

    def parse_value(self):
        """Returns (value, complete, tail)."""
        self.skip_ws()
        if self.i >= self.n:
            return INCOMPLETE, False, {"kind": "value-start"}
        ch = self.s[self.i]
        if ch == "{":
            return self.parse_object()
        if ch == "[":
            return self.parse_array()
        if ch == '"':
            return self.parse_string()
        if ch in "tfn":
            return self.parse_literal()
        if ch == "-" or ch in _DIGITS:
            return self.parse_number()
        self.error("unexpected character %r" % ch)

    def parse_object(self):
        self.i += 1  # consume '{'
        obj = {}
        self.skip_ws()
        if self.i >= self.n:
            return obj, False, {"kind": "object-key", "obj": obj}
        if self.s[self.i] == "}":
            self.i += 1
            return _ClosedDict(obj), True, None
        while True:
            self.skip_ws()
            if self.i >= self.n:
                return obj, False, {"kind": "object-key", "obj": obj}
            if self.s[self.i] != '"':
                self.error("expected object key string, got %r" % self.s[self.i])
            key, key_complete, key_tail = self.parse_string()
            if not key_complete:
                return obj, False, {"kind": "string-key",
                                    "partial": key, "obj": obj}
            if key in obj:
                self.error("duplicate key %r" % key)
            self.skip_ws()
            if self.i >= self.n:
                return obj, False, {"kind": "object-colon", "key": key,
                                    "obj": obj}
            if self.s[self.i] != ":":
                self.error("expected ':' after key %r" % key)
            self.i += 1
            value, complete, tail = self.parse_value()
            if not complete:
                if tail is not None:
                    tail = dict(tail)
                    tail.setdefault("key", key)
                    tail["obj"] = obj
                return obj, False, tail
            obj[key] = value
            self.skip_ws()
            if self.i >= self.n:
                return obj, False, {"kind": "object-after-value", "obj": obj}
            if self.s[self.i] == ",":
                self.i += 1
                continue
            if self.s[self.i] == "}":
                self.i += 1
                return _ClosedDict(obj), True, None
            self.error("expected ',' or '}' in object")

    def parse_array(self):
        self.i += 1  # consume '['
        arr = []
        self.skip_ws()
        if self.i >= self.n:
            return arr, False, {"kind": "array-value-start", "arr": arr}
        if self.s[self.i] == "]":
            self.i += 1
            return _ClosedList(arr), True, None
        while True:
            value, complete, tail = self.parse_value()
            if not complete:
                if tail is not None:
                    tail = dict(tail)
                    tail["arr"] = arr
                return arr, False, tail
            arr.append(value)
            self.skip_ws()
            if self.i >= self.n:
                return arr, False, {"kind": "array-after-value", "arr": arr}
            if self.s[self.i] == ",":
                self.i += 1
                continue
            if self.s[self.i] == "]":
                self.i += 1
                return _ClosedList(arr), True, None
            self.error("expected ',' or ']' in array")

    def parse_string(self):
        """Returns (str, complete, tail). Tail kind 'string' when cut short."""
        self.i += 1  # consume opening quote
        out = []
        while True:
            if self.i >= self.n:
                return "".join(out), False, {"kind": "string",
                                             "partial": "".join(out)}
            ch = self.s[self.i]
            if ch == '"':
                self.i += 1
                return "".join(out), True, None
            if ch == "\\":
                self.i += 1
                if self.i >= self.n:
                    return "".join(out), False, {"kind": "escape",
                                                 "partial": "".join(out)}
                esc = self.s[self.i]
                if esc not in _ESCAPES:
                    self.error("invalid escape '\\%s'" % esc)
                if esc == "u":
                    self.i += 1
                    hexpart = ""
                    for _ in range(4):
                        if self.i >= self.n:
                            return "".join(out), False, {
                                "kind": "unicode-escape",
                                "partial": "".join(out), "hex": hexpart}
                        h = self.s[self.i]
                        if h not in _HEX:
                            self.error("invalid \\u hex digit %r" % h)
                        hexpart += h
                        self.i += 1
                    out.append(chr(int(hexpart, 16)))
                    continue
                self.i += 1
                out.append({"n": "\n", "t": "\t", "r": "\r", "b": "\b",
                            "f": "\f"}.get(esc, esc))
                continue
            if ord(ch) < 0x20:
                self.error("control character in string")
            out.append(ch)
            self.i += 1

    def parse_literal(self):
        for word in ("true", "false", "null"):
            if self.s.startswith(word, self.i):
                self.i += len(word)
                return {"true": True, "false": False, "null": None}[word], True, None
            if word.startswith(self.s[self.i:]):
                got = self.s[self.i:]
                self.i = self.n
                return INCOMPLETE, False, {"kind": "literal",
                                           "expected": word, "partial": got}
        self.error("invalid literal")

    def parse_number(self):
        start = self.i
        if self.peek() == "-":
            self.i += 1
            if self.i >= self.n:
                return INCOMPLETE, False, {"kind": "number",
                                           "partial": self.s[start:self.i]}
        if self.i >= self.n:
            return INCOMPLETE, False, {"kind": "number",
                                       "partial": self.s[start:self.i]}
        if self.s[self.i] == "0":
            self.i += 1
        elif self.s[self.i] in "123456789":
            while self.i < self.n and self.s[self.i] in _DIGITS:
                self.i += 1
        else:
            self.error("invalid number")
        if self.i < self.n and self.s[self.i] == ".":
            self.i += 1
            if self.i >= self.n or self.s[self.i] not in _DIGITS:
                if self.i >= self.n:
                    return INCOMPLETE, False, {
                        "kind": "number", "partial": self.s[start:self.i]}
                self.error("expected digit after decimal point")
            while self.i < self.n and self.s[self.i] in _DIGITS:
                self.i += 1
        if self.i < self.n and self.s[self.i] in "eE":
            self.i += 1
            if self.i < self.n and self.s[self.i] in "+-":
                self.i += 1
            if self.i >= self.n or self.s[self.i] not in _DIGITS:
                if self.i >= self.n:
                    return INCOMPLETE, False, {
                        "kind": "number", "partial": self.s[start:self.i]}
                self.error("expected digit in exponent")
            while self.i < self.n and self.s[self.i] in _DIGITS:
                self.i += 1
        if self.i >= self.n:
            # Number ran to end of input: it could still grow, so incomplete.
            return INCOMPLETE, False, {"kind": "number",
                                       "partial": self.s[start:self.i]}
        text = self.s[start:self.i]
        try:
            value = float(text) if any(c in text for c in ".eE") else int(text)
        except ValueError:
            self.error("invalid number %r" % text)
        return value, True, None


def partial_parse(text):
    """Parse a possibly-incomplete JSON document."""
    return _PartialParser(text).parse()


# ---------------------------------------------------------------------------
# Schema-aware prefix judgements
# ---------------------------------------------------------------------------

def _subschema_for_key(schema, key):
    if not isinstance(schema, dict):
        return {}
    props = schema.get("properties", {})
    if key in props:
        return props[key]
    if isinstance(schema.get("additionalProperties"), dict):
        return schema["additionalProperties"]
    return {}


def _validate_partial_value(value, schema, path="$"):
    """Validate completed parts of a partial tree. INCOMPLETE is skipped."""
    if value is INCOMPLETE:
        return []
    errors = []
    if not isinstance(schema, dict):
        return errors
    if isinstance(value, dict):
        props = schema.get("properties", {})
        if isinstance(value, _ClosedDict):
            for key in schema.get("required", []):
                if key not in value:
                    errors.append("%s: missing required key %r" % (path, key))
        for key, val in value.items():
            if val is INCOMPLETE:
                continue
            if key in props:
                errors.extend(_validate_partial_value(val, props[key],
                                                      "%s.%s" % (path, key)))
            elif schema.get("additionalProperties") is False:
                errors.append("%s: additional property %r not allowed"
                              % (path, key))
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(_validate_partial_value(
                    val, schema["additionalProperties"], "%s.%s" % (path, key)))
        # Required keys are enforced only for a closed object; the caller
        # handles that by re-validating the complete document.
    elif isinstance(value, list):
        if isinstance(schema.get("items"), dict):
            for i, item in enumerate(value):
                if item is INCOMPLETE:
                    continue
                errors.extend(_validate_partial_value(item, schema["items"],
                                                      "%s[%d]" % (path, i)))
    elif isinstance(value, str):
        if "const" in schema and value != schema["const"]:
            errors.append("%s: value %r != const %r" % (path, value, schema["const"]))
        if "enum" in schema and value not in schema["enum"]:
            errors.append("%s: value %r not in enum %r" % (path, value, schema["enum"]))
        if "type" in schema and not _type_matches(value, schema["type"]):
            errors.append("%s: type string, expected %s" % (path, schema["type"]))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append("%s: string %r does not match pattern %r"
                          % (path, value, schema["pattern"]))
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append("%s: string shorter than minLength %d"
                          % (path, schema["minLength"]))
    elif isinstance(value, bool) or value is None:
        if "type" in schema and not _type_matches(value, schema["type"]):
            errors.append("%s: type %s, expected %s"
                          % (path, _type_name(value), schema["type"]))
        if "const" in schema and value != schema["const"]:
            errors.append("%s: value %r != const %r" % (path, value, schema["const"]))
        if "enum" in schema and value not in schema["enum"]:
            errors.append("%s: value %r not in enum %r" % (path, value, schema["enum"]))
    elif isinstance(value, (int, float)):
        if "type" in schema and not _type_matches(value, schema["type"]):
            errors.append("%s: type %s, expected %s"
                          % (path, _type_name(value), schema["type"]))
        if "minimum" in schema and value < schema["minimum"]:
            errors.append("%s: %r < minimum %r" % (path, value, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append("%s: %r > maximum %r" % (path, value, schema["maximum"]))
        if "enum" in schema and value not in schema["enum"]:
            errors.append("%s: value %r not in enum %r" % (path, value, schema["enum"]))
    return errors


def _subschema_for_tail(tail, schema, kind):
    """Subschema for the unfinished node described by a parse tail.

    For value tails (number, string, literal) the node is the value
    itself: key -> that property, "arr" -> the array item schema, else
    the root schema. For container tails (object-*, array-*) the node
    is the container: a "key" on the tail is the container's own key
    (set by its parent), else the root schema.
    """
    if not isinstance(schema, dict):
        return {}
    key = tail.get("key")
    if kind in ("number", "string", "escape", "unicode-escape", "literal"):
        if key is not None:
            return _subschema_for_key(schema, key)
        if "arr" in tail:
            return schema.get("items", {})
        return schema
    if key is not None:
        return _subschema_for_key(schema, key)
    return schema


def _tail_type_errors(result, schema):
    """Type errors for the unfinished tail node itself.

    The tree check only judges completed values, but an unfinished value
    already has a known JSON kind (number, string, literal, object,
    array). A number under a string-typed key, a float under an integer
    key, or a literal under a string key can never become valid, so the
    prefix is dead even though the value is incomplete. Without this,
    a sampler accepts digit after digit after `"schema": ` forever.
    """
    if result.complete or result.error:
        return []
    tail = result.tail or {}
    kind = tail.get("kind")
    # "object-colon" tails carry the key *inside* the container, not the
    # container's own key, so the container's schema cannot be derived
    # from the tail; skip the container check there.
    if kind == "object-colon":
        return []
    subschema = _subschema_for_tail(tail, schema, kind)
    if not isinstance(subschema, dict) or not subschema:
        return []
    types = subschema.get("type")
    has_type = types is not None
    type_list = (types if isinstance(types, list) else [types]) \
        if has_type else []

    def allows(wanted):
        return not type_list or wanted in type_list

    if kind == "number":
        partial = tail.get("partial", "")
        if not allows("integer") and not allows("number"):
            return ["type: number cannot satisfy %s" % (types,)]
        if allows("integer") and not allows("number"):
            if any(c in partial for c in ".eE"):
                return ["type: %r is not an integer" % partial]
        return []
    if kind == "literal":
        expected = tail.get("expected", "")
        need = "boolean" if expected in ("true", "false") else "null"
        if not allows(need):
            return ["type: literal %s cannot satisfy %s" % (expected, types)]
        if "const" in subschema:
            const_val = {"true": True, "false": False,
                         "null": None}[expected]
            if const_val != subschema["const"]:
                return ["literal %s != const %r" % (expected,
                                                    subschema["const"])]
        return []
    if kind in ("string", "escape", "unicode-escape"):
        if not allows("string"):
            return ["type: string cannot satisfy %s" % (types,)]
        return []
    if kind in ("object-key", "object-colon", "object-after-value"):
        if not allows("object"):
            return ["type: object cannot satisfy %s" % (types,)]
        return []
    if kind in ("array-value-start", "array-after-value"):
        if not allows("array"):
            return ["type: array cannot satisfy %s" % (types,)]
        return []
    return []


def partial_validate(text, schema):
    """Errors in the completed parts of an incomplete document.

    Empty list means: no completed part violates the schema yet, and the
    unfinished tail can still grow into a schema-valid value.
    """
    result = partial_parse(text)
    if result.error:
        return [result.error]
    if result.complete:
        return validate_schema(result.value, schema)
    return (_validate_partial_value(result.value, schema)
            + _tail_type_errors(result, schema))


def is_valid_prefix(text, schema=None):
    """True iff `text` can still be completed into a schema-valid document."""
    result = partial_parse(text)
    if result.error:
        return False
    if schema is not None:
        if partial_validate(text, schema):
            return False
        # An unfinished string under an enum/const must still be extendable.
        tail = result.tail or {}
        if tail.get("kind") == "string":
            key = tail.get("key")
            subschema = _subschema_for_key(schema, key) if key else schema
            allowed_values = []
            if "const" in subschema:
                allowed_values = [subschema["const"]]
            elif "enum" in subschema:
                allowed_values = subschema["enum"]
            if allowed_values:
                partial = tail.get("partial", "")
                if not any(isinstance(v, str) and v.startswith(partial)
                           for v in allowed_values):
                    return False
    return True


def allowed_next_chars(text, schema=None):
    """Set of characters that may legally follow `text`, or None for an
    open set (free string content, numbers). Empty set means no legal
    continuation: the prefix is already invalid.
    """
    result = partial_parse(text)
    if result.error:
        return set()
    if result.complete:
        return set(" \t\n\r")
    tail = result.tail or {}
    kind = tail.get("kind")
    if kind == "value-start":
        return set(_VALUE_START)
    if kind == "object-key":
        return set('"}')
    if kind == "object-colon":
        return {":"}
    if kind == "object-after-value":
        return set(",}")
    if kind == "array-value-start":
        return set(_VALUE_START) | {"]"}
    if kind == "array-after-value":
        return set(",]")
    if kind == "string-key":
        return None  # key text is free; closing quote always an option
    if kind == "string":
        if schema is not None:
            key = tail.get("key")
            subschema = _subschema_for_key(schema, key) if key else schema
            allowed_values = []
            if "const" in subschema:
                allowed_values = [subschema["const"]]
            elif "enum" in subschema:
                allowed_values = subschema["enum"]
            if allowed_values:
                partial = tail.get("partial", "")
                nxt = set()
                for v in allowed_values:
                    if isinstance(v, str) and v.startswith(partial):
                        if len(v) > len(partial):
                            nxt.add(v[len(partial)])
                        else:
                            nxt.add('"')
                return nxt
        return None
    if kind == "literal":
        expected = tail.get("expected", "")
        partial = tail.get("partial", "")
        if len(partial) < len(expected):
            return {expected[len(partial)]}
        return set()
    if kind == "escape":
        return set(_ESCAPES)
    if kind == "unicode-escape":
        return set(_HEX)
    if kind == "number":
        return None
    return None
