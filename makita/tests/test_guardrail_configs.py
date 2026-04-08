"""
Bedrock Guardrail configuration tests for the MAKITA project.

Validates that each guardrail JSON config in policies/guardrails/:
  - Exists and contains valid JSON
  - Has all required fields (name, description, blockedInputMessaging, etc.)
  - Includes content policy filters for all harmful content types + prompt attack
  - Includes a topic policy with DENY rules
  - Has consistent proj=makita and Env=prod1 tags

Each config file maps 1:1 to an MCP server and is deployed by deploy_agentcore.py.
"""

import json
from pathlib import Path

import pytest

GUARDRAILS_DIR = Path(__file__).parent.parent / "policies" / "guardrails"

EXPECTED_GUARDRAILS = [
    "postgresql-failover-guardrail.json",
    "postgresql-precheck-guardrail.json",
    "postgresql-postcheck-guardrail.json",
    "aws-support-stub-guardrail.json",
    "servicenow-stub-guardrail.json",
]

REQUIRED_FIELDS = [
    "name",
    "description",
    "blockedInputMessaging",
    "blockedOutputsMessaging",
    "contentPolicyConfig",
    "topicPolicyConfig",
    "tags",
]

REQUIRED_CONTENT_FILTER_TYPES = [
    "SEXUAL",
    "VIOLENCE",
    "HATE",
    "INSULTS",
    "MISCONDUCT",
    "PROMPT_ATTACK",
]


@pytest.fixture(scope="module")
def guardrail_configs() -> dict[str, dict]:
    configs = {}
    for filename in EXPECTED_GUARDRAILS:
        path = GUARDRAILS_DIR / filename
        with open(path) as f:
            configs[filename] = json.load(f)
    return configs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGuardrailFilesExist:
    """Every expected guardrail config must exist."""

    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_file_exists(self, filename):
        path = GUARDRAILS_DIR / filename
        assert path.exists(), f"Missing guardrail config: {path}"

    def test_no_unexpected_files(self):
        actual = {p.name for p in GUARDRAILS_DIR.glob("*.json")}
        expected = set(EXPECTED_GUARDRAILS)
        assert actual == expected, f"Unexpected files: {actual - expected}"


class TestGuardrailRequiredFields:
    """Each config must have all required top-level fields."""

    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_has_required_fields(self, guardrail_configs, filename):
        config = guardrail_configs[filename]
        for field in REQUIRED_FIELDS:
            assert field in config, f"{filename} missing field: {field}"


class TestGuardrailNaming:
    """Each guardrail name must start with makita-."""

    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_name_starts_with_makita(self, guardrail_configs, filename):
        name = guardrail_configs[filename]["name"]
        assert name.startswith("makita-"), f"{filename}: name '{name}' must start with makita-"


class TestGuardrailContentFilters:
    """Each config must include content filters for all harmful content types."""

    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_has_all_content_filter_types(self, guardrail_configs, filename):
        config = guardrail_configs[filename]
        filters = config["contentPolicyConfig"]["filtersConfig"]
        filter_types = {f["type"] for f in filters}
        for expected_type in REQUIRED_CONTENT_FILTER_TYPES:
            assert expected_type in filter_types, (
                f"{filename} missing content filter: {expected_type}"
            )

    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_prompt_attack_output_is_none(self, guardrail_configs, filename):
        config = guardrail_configs[filename]
        filters = config["contentPolicyConfig"]["filtersConfig"]
        for f in filters:
            if f["type"] == "PROMPT_ATTACK":
                assert f["outputStrength"] == "NONE", (
                    f"{filename}: PROMPT_ATTACK outputStrength must be NONE"
                )

    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_non_prompt_filters_are_high(self, guardrail_configs, filename):
        config = guardrail_configs[filename]
        filters = config["contentPolicyConfig"]["filtersConfig"]
        for f in filters:
            if f["type"] != "PROMPT_ATTACK":
                assert f["inputStrength"] == "HIGH", (
                    f"{filename}: {f['type']} inputStrength must be HIGH"
                )
                assert f["outputStrength"] == "HIGH", (
                    f"{filename}: {f['type']} outputStrength must be HIGH"
                )


class TestGuardrailTopicPolicy:
    """Each config must have at least one DENY topic."""

    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_has_deny_topic(self, guardrail_configs, filename):
        config = guardrail_configs[filename]
        topics = config["topicPolicyConfig"]["topicsConfig"]
        deny_topics = [t for t in topics if t["type"] == "DENY"]
        assert len(deny_topics) >= 1, f"{filename} has no DENY topics"

    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_deny_topic_has_examples(self, guardrail_configs, filename):
        config = guardrail_configs[filename]
        topics = config["topicPolicyConfig"]["topicsConfig"]
        for t in topics:
            if t["type"] == "DENY":
                assert len(t.get("examples", [])) >= 3, (
                    f"{filename}: DENY topic '{t['name']}' needs at least 3 examples"
                )


class TestGuardrailTags:
    """Each config must have proj=makita and Env=prod1 tags."""

    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_has_proj_makita_tag(self, guardrail_configs, filename):
        tags = guardrail_configs[filename]["tags"]
        tag_dict = {t["key"]: t["value"] for t in tags}
        assert tag_dict.get("proj") == "makita", f"{filename} missing proj=makita tag"

    @pytest.mark.parametrize("filename", EXPECTED_GUARDRAILS)
    def test_has_env_prod1_tag(self, guardrail_configs, filename):
        tags = guardrail_configs[filename]["tags"]
        tag_dict = {t["key"]: t["value"] for t in tags}
        assert tag_dict.get("Env") == "prod1", f"{filename} missing Env=prod1 tag"
