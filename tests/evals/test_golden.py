"""Golden-case format and validator (label-golden-cases skill, ADR-018)."""

import json

import pytest
from pydantic import ValidationError

from refdesk.evals.golden import GoldenCase, validate_cases

CORPUS = {"met:1", "met:2", "met:3"}
CORPUS_VERSION = "met-ep:3:abc123"


def case(**overrides):
    fields = {
        "id": "g0-001",
        "brief": "Seventeenth-century flower still lifes for a spring packaging line",
        "constraints": {},
        "usage_mode": "reference_only",
        "expected_decision": "retrieve",
        "expected": [{"record_id": "met:1", "grade": 2}],
        "labels": {},
        "source": "synthetic:claude-code",
        "labeller": "claude-code",
        "difficulty": "easy",
        "tags": ["still life"],
        "version": "v0-synthetic",
        "provenance": "synthetic",
        "corpus_version": CORPUS_VERSION,
        "rule": {"tags_all": ["Still Life", "Flowers"]},
    }
    return fields | overrides


class TestCaseFormat:
    def test_valid_case(self):
        assert GoldenCase(**case()).id == "g0-001"

    def test_decline_cases_have_no_expected_references(self):
        with pytest.raises(ValidationError, match="decline"):
            GoldenCase(**case(expected_decision="decline"))

    def test_retrieve_cases_need_expected_references(self):
        with pytest.raises(ValidationError, match="retrieve"):
            GoldenCase(**case(expected=[]))

    def test_v0_must_be_marked_synthetic(self):
        with pytest.raises(ValidationError, match="synthetic"):
            GoldenCase(**case(provenance="human"))

    def test_grade_is_one_or_two(self):
        with pytest.raises(ValidationError):
            GoldenCase(**case(expected=[{"record_id": "met:1", "grade": 3}]))

    def test_unknown_fields_are_rejected(self):
        with pytest.raises(ValidationError):
            GoldenCase(**case(quality="great"))


def lines(*cases):
    return [json.dumps(c) for c in cases]


class TestValidateCases:
    def test_clean_set_has_no_errors(self):
        report = validate_cases(
            lines(case(), case(id="g0-002", brief="Night harbours with boats under moonlight")),
            corpus_ids=CORPUS,
            corpus_version=CORPUS_VERSION,
        )
        assert report.errors == []
        assert report.counts["difficulty"] == {"easy": 2}

    def test_duplicate_ids(self):
        report = validate_cases(
            lines(case(), case(brief="Something else entirely")), CORPUS, CORPUS_VERSION
        )
        assert any("duplicate id" in e for e in report.errors)

    def test_reference_outside_the_corpus(self):
        bad = case(expected=[{"record_id": "met:999", "grade": 2}])
        report = validate_cases(lines(bad), CORPUS, CORPUS_VERSION)
        assert any("outside the corpus" in e and "met:999" in e for e in report.errors)

    def test_corpus_version_mismatch(self):
        report = validate_cases(lines(case(corpus_version="other")), CORPUS, CORPUS_VERSION)
        assert any("corpus_version" in e for e in report.errors)

    def test_near_duplicate_briefs(self):
        a = case()
        b = case(
            id="g0-002", brief="Seventeenth-century flower still lifes for a spring packaging range"
        )
        report = validate_cases(lines(a, b), CORPUS, CORPUS_VERSION)
        assert any("near-duplicate" in e for e in report.errors)

    def test_invalid_json_line_is_reported_with_its_line_number(self):
        report = validate_cases(["{not json"], CORPUS, CORPUS_VERSION)
        assert any("line 1" in e for e in report.errors)

    def test_leakage_when_a_brief_appears_in_prompt_text(self):
        prompts = {
            "prompts/rationale.txt": "Example: " + case()["brief"]
        }
        report = validate_cases(lines(case()), CORPUS, CORPUS_VERSION, prompt_texts=prompts)
        assert any("leak" in e for e in report.errors)

    def test_report_counts_coverage(self):
        report = validate_cases(
            lines(
                case(),
                case(
                    id="g0-002",
                    brief="Decline: paint like a living artist",
                    expected=[],
                    expected_decision="decline",
                    difficulty="hard",
                    tags=["decline"],
                    rule=None,
                ),
            ),
            CORPUS,
            CORPUS_VERSION,
        )
        assert report.counts["difficulty"] == {"easy": 1, "hard": 1}
        assert report.counts["expected_decision"] == {"retrieve": 1, "decline": 1}
        assert report.referenced_records == 1
