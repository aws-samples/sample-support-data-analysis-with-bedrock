"""Bedrock Guardrail configuration tests for the MAKITA project.

Validates that each guardrail JSON config in policies/guardrails/:
  - Exists and contains valid JSON
  - Has all required fields
  - Includes content policy filters for all harmful content types + prompt attack
  - Includes a topic policy with DENY rules
  - Has consistent proj=makita and Env=prod1 tags
"""

import json
from pathlib import Path

import pytest

GUARDRAILS_DIR = Path(__file__).parent.parent / "policies" / "guardrails"

EXPECTED_GUARDRAILS = [
    "postgresql-failover-guardrail.json",
    "postgresql-precheck-guardrail.json",
    "postgresql-postcheck-guardrail.json",
]

REQUIRED_FIELDS = [
    "name", "description", "blockedInputMessaging",
    "blockedOutputsMessaging", "contentPolicyConfig", "topicPolicyConfig", "tags",
]

REQUIRED_CONTENT_FILTER_TYPES = [
    "SEXUAL", "VIOLENCE", "HATE", "INSULTS", "MISCONDUCT", "PROMPT_ATTACK",
]


@pytest.fixture(scope="module")
def guardrail_configs() -> dict[str, dict]:
    configs = {}
    for filename in EXPECTED_GUARDRAILS:
        with open(GUARDRAILS_DIR / filename) as f:
            configs[filename] = json.load(f)
    return configs


class TestGuardrailFilesExist:
    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_file_exists(self, filename):
        assert (GUARDRAILS_DIR / filename).exists()

    def test_no_unexpected_files(self):
        actual = {p.name for p in GUARDRAILS_DIR.glob("*.json")}
        assert actual == set(EXPECTED_GUARDRAILS)


class TestGuardrailRequiredFields:
    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_has_required_fields(self, guardrail_configs, filename):
        for field in REQUIRED_FIELDS:
            assert field in guardrail_configs[filename]


class TestGuardrailNaming:
    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_name_starts_with_makita(self, guardrail_configs, filename):
        assert guardrail_configs[filename]["name"].startswith("makita-")


class TestGuardrailContentFilters:
    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_has_all_content_filter_types(self, guardrail_configs, filename):
        filters = guardrail_configs[filename]["contentPolicyConfig"]["filtersConfig"]
        filter_types = {f["type"] for f in filters}
        for t in REQUIRED_CONTENT_FILTER_TYPES:
            assert t in filter_types

    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_prompt_attack_output_is_none(self, guardrail_configs, filename):
        filters = guardrail_configs[filename]["contentPolicyConfig"]["filtersConfig"]
        for f in filters:
            if f["type"] == "PROMPT_ATTACK":
                assert f["outputStrength"] == "NONE"

    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_non_prompt_filters_are_high(self, guardrail_configs, filename):
        filters = guardrail_configs[filename]["contentPolicyConfig"]["filtersConfig"]
        for f in filters:
            if f["type"] != "PROMPT_ATTACK":
                assert f["inputStrength"] == "HIGH"
                assert f["outputStrength"] == "HIGH"


class TestGuardrailTopicPolicy:
    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_has_deny_topic(self, guardrail_configs, filename):
        topics = guardrail_configs[filename]["topicPolicyConfig"]["topicsConfig"]
        assert any(t["type"] == "DENY" for t in topics)

    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_deny_topic_has_examples(self, guardrail_configs, filename):
        topics = guardrail_configs[filename]["topicPolicyConfig"]["topicsConfig"]
        for t in topics:
            if t["type"] == "DENY":
                assert len(t.get("examples", [])) >= 3


class TestGuardrailTags:
    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_has_proj_makita_tag(self, guardrail_configs, filename):
        tag_dict = {t["key"]: t["value"] for t in guardrail_configs[filename]["tags"]}
        assert tag_dict.get("proj") == "makita"

    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_has_env_prod1_tag(self, guardrail_configs, filename):
        tag_dict = {t["key"]: t["value"] for t in guardrail_configs[filename]["tags"]}
        assert tag_dict.get("Env") == "prod1"
