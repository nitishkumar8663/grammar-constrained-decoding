"""Tests for grammar-constrained decoding.

Run on the Spark:  python3 -m unittest discover -s tests -v
Stdlib unittest only; no model needed except the sampler tests, which
use FakeBackend. Live-model runs live in demo/, not here.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cfg import allowed_next_chars, is_valid_prefix, parse_json, \
    partial_validate, validate_schema  # noqa: E402
from sampler import ConstrainedSampler, FakeBackend, forced_continuation  # noqa: E402
from guided import _vllm_body, evaluate, summarize  # noqa: E402
import schemas  # noqa: E402

VOICE = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "minLength": 1},
        "speaker": {"type": "string", "enum": ["Amit"]},
    },
    "required": ["text", "speaker"],
    "additionalProperties": False,
}

ENVELOPE_LITE = {
    "type": "object",
    "properties": {
        "schema": {"type": "string", "const": "tier1-cloud-exec/v1"},
        "max_tokens": {"type": "integer", "minimum": 1, "maximum": 4096},
        "temperature": {"type": "number", "minimum": 0, "maximum": 2},
    },
    "required": ["schema", "max_tokens"],
    "additionalProperties": False,
}


class TestJsonGrammar(unittest.TestCase):
    def test_valid_documents_parse(self):
        for text in ('{"a": 1}', '[1, 2.5, "x", true, false, null]',
                     '{"nested": {"list": []}}', '"just a string"', '42',
                     '{"a": "line\\nbreak \\u0041"}'):
            obj, err = parse_json(text)
            self.assertIsNone(err, text)
            self.assertIsNotNone(obj)

    def test_invalid_documents_rejected(self):
        for text in ('{"a": 1,}', "{'a': 1}", '{"a": }', '{"a" 1}',
                     '{"a": 01}', '{"a": "unterminated}', '[1, 2',
                     '{"a": tru}', '{"a": 1} extra', ''):
            _, err = parse_json(text)
            self.assertIsNotNone(err, text)

    def test_valid_prefixes_accepted(self):
        for text in ('', '{', '{"a"', '{"a":', '{"a": 1', '{"a": 1,',
                     '[1, ', '{"a": "hel', '{"a": tru', '{"a": -',
                     '{"a": 1.5e'):
            self.assertTrue(is_valid_prefix(text), text)

    def test_invalid_prefixes_rejected(self):
        for text in ('{"a": }', '{"a" 1}', "{'a'", '{"a": "x" "y"}',
                     '{"a": 1, "a": 2}', '{"a": truX}'):
            self.assertFalse(is_valid_prefix(text), text)

    def test_allowed_next_chars_object_key(self):
        self.assertEqual(allowed_next_chars('{'), set('"}'))
        # Number terminated by a space: the object now waits for , or }.
        self.assertEqual(allowed_next_chars('{"a": 1 '), set(",}"))
        # Number running to end of input can still grow: open set.
        self.assertIsNone(allowed_next_chars('{"a": 1'))

    def test_allowed_next_chars_literal(self):
        self.assertEqual(allowed_next_chars('{"a": tr'), {"u"})
        self.assertEqual(allowed_next_chars('{"a": tru'), {"e"})

    def test_allowed_next_chars_enum_string(self):
        self.assertEqual(
            allowed_next_chars('{"text": "x", "speaker": "Am', VOICE),
            {"i"})
        self.assertEqual(
            allowed_next_chars('{"text": "x", "speaker": "Amit', VOICE),
            {'"'})
        # No enum value can match this prefix: dead end.
        self.assertEqual(
            allowed_next_chars('{"text": "x", "speaker": "Bo', VOICE),
            set())
        self.assertFalse(
            is_valid_prefix('{"text": "x", "speaker": "Bo', VOICE))

    def test_allowed_next_chars_free_string_is_open(self):
        self.assertIsNone(allowed_next_chars('{"text": "hel', VOICE))


class TestSchemaValidation(unittest.TestCase):
    def test_valid_voice_object(self):
        self.assertEqual(
            validate_schema({"text": "hi", "speaker": "Amit"}, VOICE), [])

    def test_wrong_enum_rejected(self):
        errors = validate_schema({"text": "hi", "speaker": "Kavya"}, VOICE)
        self.assertTrue(any("Kavya" in e for e in errors))

    def test_missing_required_rejected(self):
        errors = validate_schema({"text": "hi"}, VOICE)
        self.assertTrue(any("speaker" in e for e in errors))

    def test_additional_property_rejected(self):
        errors = validate_schema(
            {"text": "hi", "speaker": "Amit", "extra": 1}, VOICE)
        self.assertTrue(any("extra" in e for e in errors))

    def test_const_and_ranges(self):
        ok = {"schema": "tier1-cloud-exec/v1", "max_tokens": 512,
              "temperature": 0.5}
        self.assertEqual(validate_schema(ok, ENVELOPE_LITE), [])
        bad = {"schema": "other/v1", "max_tokens": 99999, "temperature": 5}
        errors = validate_schema(bad, ENVELOPE_LITE)
        self.assertEqual(len(errors), 3)

    def test_partial_validation_skips_incomplete_tail(self):
        # Completed pair is fine; unfinished string is not judged yet.
        self.assertEqual(
            partial_validate('{"text": "hi", "speaker": "Am', VOICE), [])
        # Completed pair violates the enum: judged now, not at the end.
        self.assertTrue(
            partial_validate('{"text": "hi", "speaker": "Kavya"', VOICE))
        # Closed object missing a required key: judged at close.
        self.assertTrue(partial_validate('{"text": "hi"}', VOICE))

    def test_partial_validation_rejects_wrong_kind_tail(self):
        # A number under a string-typed key can never become valid.
        self.assertTrue(
            partial_validate('{"schema": 1', ENVELOPE_LITE))
        self.assertFalse(
            is_valid_prefix('{"schema": 1', ENVELOPE_LITE))
        # A float under an integer key can never become an integer.
        self.assertFalse(
            is_valid_prefix('{"max_tokens": 1.5', ENVELOPE_LITE))
        # An integer under an integer key is fine.
        self.assertTrue(
            is_valid_prefix('{"max_tokens": 12', ENVELOPE_LITE))
        # A string under an integer key can never become valid.
        self.assertFalse(
            is_valid_prefix('{"max_tokens": "x', ENVELOPE_LITE))
        # A literal under a string-typed key can never become valid.
        self.assertFalse(
            is_valid_prefix('{"schema": tru', ENVELOPE_LITE))
        # A string under a string-typed key is fine.
        self.assertTrue(
            is_valid_prefix('{"schema": "tier1-cloud-exec/v1',
                            ENVELOPE_LITE))


class TestForcedContinuation(unittest.TestCase):
    def test_empty_document_opens_object(self):
        self.assertEqual(forced_continuation("", VOICE), "{")

    def test_object_key_fills_first_required(self):
        self.assertEqual(forced_continuation("{", VOICE), '"text": ')

    def test_value_start_uses_property_type(self):
        self.assertEqual(
            forced_continuation('{"text": ', VOICE), '"')
        self.assertEqual(
            forced_continuation('{"text": "hi", "speaker": ', VOICE),
            '"Amit"')

    def test_after_value_closes_when_required_met(self):
        self.assertEqual(
            forced_continuation('{"text": "hi", "speaker": "Amit"', VOICE),
            "}")

    def test_complete_document_forces_nothing(self):
        self.assertEqual(
            forced_continuation('{"text": "hi", "speaker": "Amit"}', VOICE),
            "")


class TestSampler(unittest.TestCase):
    def test_clean_script_produces_valid_output(self):
        tokens = ['{', '"text"', ': ', '"Hello"', ', ', '"speaker"',
                  ': ', '"Amit"', '}']
        sampler = ConstrainedSampler(FakeBackend(tokens), VOICE)
        _, stats = sampler.generate()
        self.assertTrue(stats["schema_valid"])
        self.assertEqual(stats["rejected"], 0)
        self.assertEqual(stats["forced"], 0)

    def test_invalid_token_rejected_then_recovered(self):
        tokens = ['{', '"text"', ': ', '"Hello"', ', ', '"speaker"',
                  ': ', '"Bob"', '"Amit"', '}']
        sampler = ConstrainedSampler(FakeBackend(tokens), VOICE)
        _, stats = sampler.generate()
        self.assertTrue(stats["schema_valid"])
        self.assertEqual(stats["rejected"], 1)

    def test_repeated_rejection_falls_back_to_forced(self):
        tokens = ['}', '}', '}', '}'] + [
            '"text"', ': ', '"Hello"', ', ', '"speaker"', ': ',
            '"Amit"', '}']
        sampler = ConstrainedSampler(FakeBackend(tokens), VOICE,
                                     max_retries=2)
        _, stats = sampler.generate()
        self.assertTrue(stats["schema_valid"])
        self.assertGreater(stats["forced"], 0)

    def test_sampler_terminates_within_max_steps(self):
        sampler = ConstrainedSampler(FakeBackend(['}']), VOICE,
                                     max_steps=50, max_retries=1)
        _, stats = sampler.generate()
        self.assertLessEqual(stats["steps"], 50)

    def test_whitespace_only_tokens_rejected_outside_strings(self):
        tokens = ['{', ' ', ' ', '"text"', ': ', '"Hello"', ', ',
                  '"speaker"', ': ', '"Amit"', '}']
        sampler = ConstrainedSampler(FakeBackend(tokens), VOICE)
        _, stats = sampler.generate()
        self.assertTrue(stats["schema_valid"])
        self.assertEqual(stats["rejected"], 2)


class TestGuidedHelpers(unittest.TestCase):
    def test_vllm_body_uses_structured_outputs_not_guided_json(self):
        # The day-0 vLLM dev build removed guided_json (server warns it is
        # ignored); the current field is structured_outputs {"json": ...}.
        body = _vllm_body("m", "p", VOICE, 0.7, 128)
        self.assertNotIn("guided_json", body)
        self.assertEqual(body["structured_outputs"], {"json": VOICE})
        plain = _vllm_body("m", "p", None, 0.7, 128)
        self.assertNotIn("structured_outputs", plain)

    def test_evaluate_counts(self):
        json_ok, schema_ok, _ = evaluate('{"text": "hi", "speaker": "Amit"}',
                                         VOICE)
        self.assertTrue(json_ok and schema_ok)
        json_ok, schema_ok, _ = evaluate('{"text": "hi", "speaker": "Kavya"}',
                                         VOICE)
        self.assertTrue(json_ok and not schema_ok)
        json_ok, schema_ok, _ = evaluate('not json at all', VOICE)
        self.assertFalse(json_ok and schema_ok)

    def test_summarize_rates_and_latency(self):
        records = [
            {"schema": "voice_request", "json_ok": True, "schema_ok": True,
             "seconds": 1.0, "eval_count": 10, "eval_seconds": 0.5},
            {"schema": "voice_request", "json_ok": True, "schema_ok": False,
             "seconds": 3.0, "eval_count": 10, "eval_seconds": 1.0},
            {"schema": "gateway_query", "json_ok": False, "schema_ok": False,
             "seconds": 2.0, "eval_count": 0, "eval_seconds": 0.0},
        ]
        summary = summarize(records, "test")
        self.assertEqual(summary["n"], 3)
        self.assertAlmostEqual(summary["schema_rate"], 1 / 3, places=3)
        self.assertAlmostEqual(summary["json_rate"], 2 / 3, places=3)
        self.assertEqual(summary["median_seconds"], 2.0)
        self.assertEqual(summary["by_schema"]["voice_request"]["n"], 2)


class TestSchemaSuite(unittest.TestCase):
    def test_all_entries_well_formed(self):
        self.assertEqual(len(schemas.ENTRIES), 6)
        for entry in schemas.ENTRIES:
            self.assertIn("name", entry)
            self.assertIn("source", entry)
            self.assertIn("schema", entry)
            self.assertEqual(entry["schema"]["type"], "object")
            self.assertTrue(entry["scenarios"])
            prompt = schemas.prompt_for(entry, 0)
            self.assertIn("JSON object", prompt)
            self.assertNotIn("{", prompt.replace("{{", "").replace("}}", "")
                             .replace('{"', "").replace('"}', ""))

    def test_prompts_render_for_every_scenario(self):
        for entry in schemas.ENTRIES:
            for i in range(len(entry["scenarios"])):
                prompt = schemas.prompt_for(entry, i)
                self.assertNotIn("{capability}", prompt)
                self.assertNotIn("{text}", prompt)


if __name__ == "__main__":
    unittest.main()
