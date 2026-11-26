#!/usr/bin/env python3
"""Score adoption eval records against eval_set.json.

Usage: python3 score.py <records.jsonl> [<records2.jsonl> ...]
Judgement per record (same code as the project, cfg.py):
  raw parse + full schema validation.
Repaired parse: strip ```json fences (the demo's repaired baseline).
Value-correctness: every field the prompt named must equal the expected
value (numbers with tolerance, bools type-checked, null checked).

Prints per model/mode/split: n, raw valid rate, repaired valid rate,
value-correct rate, fully-correct rate (repaired valid AND value-correct),
median wall, p95 wall, median eval tok/s, plus the failing records.
"""
import json
import re
import statistics
import sys

sys.path.insert(0, ".")
from cfg import parse_json, validate_schema  # noqa: E402

FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$",
                      re.DOTALL)


def repair(text):
    m = FENCE_RE.match(text.strip())
    return m.group(1) if m else text.strip()


def values_equal(got, want):
    if isinstance(want, bool):
        return isinstance(got, bool) and got == want
    if want is None:
        return got is None
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        return abs(float(got) - float(want)) < 1e-9
    return got == want


def score_record(rec, expected, schema):
    obj, err = parse_json(rec["text"])
    raw_ok = err is None
    raw_schema_ok = False
    if raw_ok:
        raw_schema_ok = not validate_schema(obj, schema)
    obj2, err2 = parse_json(repair(rec["text"]))
    rep_ok = err2 is None
    rep_schema_ok = False
    if rep_ok:
        rep_schema_ok = not validate_schema(obj2, schema)
    value_ok = False
    field_misses = []
    if rep_schema_ok:
        value_ok = True
        for key, want in expected.items():
            if key not in obj2 or not values_equal(obj2[key], want):
                value_ok = False
                field_misses.append(key)
    return {
        "raw_json_ok": raw_ok,
        "raw_schema_ok": raw_schema_ok,
        "repaired_json_ok": rep_ok,
        "repaired_schema_ok": rep_schema_ok,
        "value_ok": value_ok,
        "fully_correct": rep_schema_ok and value_ok,
        "field_misses": field_misses,
    }


def main():
    with open("eval_set.json", encoding="utf-8") as f:
        eval_set = json.load(f)
    expected = {}
    schema = {}
    sys.path.insert(0, ".")
    from schemas import ENTRIES
    schema_by_name = {e["name"]: e["schema"] for e in ENTRIES}
    for split in ("dev", "holdout"):
        for p in eval_set[split]:
            expected[p["id"]] = p["expected"]
            schema[p["id"]] = schema_by_name[p["schema"]]
    groups = {}
    for path in sys.argv[1:]:
        with open(path, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                key = (rec["model"], rec["mode"], rec["split"])
                s = score_record(rec, expected[rec["id"]],
                                 schema[rec["id"]])
                groups.setdefault(key, []).append((rec, s))
    for key in sorted(groups):
        rows = groups[key]
        n = len(rows)
        raw = sum(1 for _, s in rows if s["raw_schema_ok"])
        rep = sum(1 for _, s in rows if s["repaired_schema_ok"])
        val = sum(1 for _, s in rows if s["value_ok"])
        full = sum(1 for _, s in rows if s["fully_correct"])
        secs = [r["seconds"] for r, _ in rows]
        rates = [r["eval_count"] / r["eval_seconds"] for r, _ in rows
                 if r["eval_count"] and r["eval_seconds"] > 0]
        print("%s %s %s  n=%d  raw_valid %d (%.2f)  repaired_valid %d "
              "(%.2f)  value_ok %d (%.2f)  fully_correct %d (%.2f)  "
              "median_s %.2f  p95_s %.2f  median_tok_s %.1f"
              % (key[0], key[1], key[2], n, raw, raw / n, rep, rep / n,
                 val, val / n, full, full / n,
                 statistics.median(secs),
                 sorted(secs)[max(0, int(0.95 * len(secs)) - 1)],
                 statistics.median(rates) if rates else 0.0))
        for rec, s in rows:
            if not s["fully_correct"]:
                print("   FAIL %s %s: raw=%s rep=%s value=%s misses=%s "
                      "err=%s" % (
                          rec["id"], rec["schema"],
                          s["raw_schema_ok"], s["repaired_schema_ok"],
                          s["value_ok"], ",".join(s["field_misses"]),
                          rec.get("error")))
                if not s["repaired_json_ok"]:
                    print("      text: %.200s" % rec["text"].replace(
                        "\n", " "))


if __name__ == "__main__":
    main()
