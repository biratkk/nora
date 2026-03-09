"""Tests for nora.tools.plan — plan management tools."""

from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from nora.tools.plan import (
    create_plan,
    generate_plan_name,
    read_plan,
    _fallback_plan_name,
)


class TestFallbackPlanName:
    """Tests for the _fallback_plan_name helper."""

    def test_extracts_words_from_content(self):
        name = _fallback_plan_name("Add Dark Mode Toggle to settings page")
        parts = name.split("-")
        assert len(parts) == 3
        assert all(p.isalpha() and p.islower() for p in parts)

    def test_handles_short_content(self):
        name = _fallback_plan_name("fix")
        parts = name.split("-")
        assert len(parts) == 3

    def test_handles_empty_content(self):
        name = _fallback_plan_name("")
        parts = name.split("-")
        assert len(parts) == 3


class TestGeneratePlanName:
    """Tests for generate_plan_name()."""

    @patch("nora.tools.plan.Agent")
    @patch("nora.tools.plan.BedrockModel")
    def test_generates_name_from_llm(self, MockModel, MockAgent):
        mock_agent = MagicMock()
        mock_agent.return_value = "add-dark-mode"
        MockAgent.return_value = mock_agent

        name = generate_plan_name("# Add Dark Mode\n\n1. Update theme config")
        assert name == "add-dark-mode"

    @patch("nora.tools.plan.Agent")
    @patch("nora.tools.plan.BedrockModel")
    def test_strips_whitespace(self, MockModel, MockAgent):
        mock_agent = MagicMock()
        mock_agent.return_value = "  my-plan-name  \n"
        MockAgent.return_value = mock_agent

        name = generate_plan_name("Some plan content")
        assert name == "my-plan-name"

    @patch("nora.tools.plan.Agent")
    @patch("nora.tools.plan.BedrockModel")
    def test_fallback_on_invalid_name(self, MockModel, MockAgent):
        mock_agent = MagicMock()
        mock_agent.return_value = "this is not valid!!!"
        MockAgent.return_value = mock_agent

        name = generate_plan_name("Some plan content about fixing auth")
        parts = name.split("-")
        assert len(parts) == 3

    def test_fallback_on_exception(self):
        with patch("nora.tools.plan.BedrockModel", side_effect=Exception("fail")):
            name = generate_plan_name("Some plan content about auth")
            parts = name.split("-")
            assert len(parts) == 3

    @patch("nora.tools.plan.Agent")
    @patch("nora.tools.plan.BedrockModel")
    @patch("nora.tools.plan.boto3")
    def test_uses_profile_when_provided(self, mock_boto3, MockModel, MockAgent):
        mock_agent = MagicMock()
        mock_agent.return_value = "auth-token-fix"
        MockAgent.return_value = mock_agent

        name = generate_plan_name("Fix auth tokens", profile="my-profile")
        assert name == "auth-token-fix"
        mock_boto3.Session.assert_called_once_with(profile_name="my-profile")


class TestCreatePlan:
    """Tests for the create_plan tool function."""

    @patch("nora.tools.plan._plan_path")
    @patch("nora.tools.plan.generate_plan_name")
    def test_creates_plan_successfully(self, mock_gen_name, mock_plan_path):
        mock_gen_name.return_value = "my-test-plan"
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False
        mock_plan_path.return_value = mock_path

        tool_context = MagicMock()
        tool_context.invocation_state = {}

        result = create_plan(
            tool_context=tool_context,
            content="Step 1: Do stuff\nStep 2: Do more stuff",
        )

        mock_path.write_text.assert_called_once_with(
            "Step 1: Do stuff\nStep 2: Do more stuff"
        )
        assert "my-test-plan" in result

    @patch("nora.tools.plan._plan_path")
    @patch("nora.tools.plan.generate_plan_name")
    def test_rejects_duplicate_name(self, mock_gen_name, mock_plan_path):
        mock_gen_name.return_value = "existing-plan-name"
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_plan_path.return_value = mock_path

        tool_context = MagicMock()
        tool_context.invocation_state = {}

        result = create_plan(
            tool_context=tool_context,
            content="content",
        )

        assert "already exists" in result
        mock_path.write_text.assert_not_called()


class TestReadPlan:
    """Tests for the read_plan tool function."""

    @patch("nora.tools.plan._plan_path")
    def test_reads_existing_plan(self, mock_plan_path):
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = "Step 1: Do it"
        mock_plan_path.return_value = mock_path

        result = read_plan(name="my-plan")
        assert result == "Step 1: Do it"

    @patch("nora.tools.plan._plans_dir")
    @patch("nora.tools.plan._plan_path")
    def test_returns_error_for_missing_plan(self, mock_plan_path, mock_plans_dir):
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False
        mock_plan_path.return_value = mock_path

        mock_dir = MagicMock(spec=Path)
        mock_dir.glob.return_value = []
        # For the exact path check
        exact_path = MagicMock(spec=Path)
        exact_path.exists.return_value = False
        mock_dir.__truediv__ = MagicMock(return_value=exact_path)
        mock_plans_dir.return_value = mock_dir

        result = read_plan(name="nonexistent")
        assert "not found" in result
