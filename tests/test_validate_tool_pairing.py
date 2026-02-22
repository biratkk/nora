"""Tests for _validate_tool_pairing and cancellation message handling.

These tests verify that the message repair logic correctly handles
the various states messages can be in after an agent cancellation:
- Dangling toolUse with no toolResult
- Complete tool pairs preserved
- Orphaned toolResults dropped
- Multiple tools with partial completion
"""

import pytest

from nora.repositories.run_repository import RunRepository


def _user(text: str) -> dict:
    return {"role": "user", "content": [{"text": text}]}


def _assistant(text: str) -> dict:
    return {"role": "assistant", "content": [{"text": text}]}


def _assistant_tool_use(tool_use_id: str, name: str, tool_input: dict | None = None) -> dict:
    return {
        "role": "assistant",
        "content": [
            {
                "toolUse": {
                    "toolUseId": tool_use_id,
                    "name": name,
                    "input": tool_input or {},
                }
            }
        ],
    }


def _assistant_text_and_tool(text: str, tool_use_id: str, name: str) -> dict:
    return {
        "role": "assistant",
        "content": [
            {"text": text},
            {
                "toolUse": {
                    "toolUseId": tool_use_id,
                    "name": name,
                    "input": {},
                }
            },
        ],
    }


def _user_tool_result(tool_use_id: str, output: str = "ok", status: str = "success") -> dict:
    return {
        "role": "user",
        "content": [
            {
                "toolResult": {
                    "toolUseId": tool_use_id,
                    "status": status,
                    "content": [{"text": output}],
                }
            }
        ],
    }


def _synthetic_error_result(tool_use_id: str) -> dict:
    """What _validate_tool_pairing injects for dangling toolUse blocks."""
    return {
        "toolResult": {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": "Tool execution was interrupted."}],
        }
    }


validate = RunRepository._validate_tool_pairing


class TestValidateToolPairing:
    """Tests for RunRepository._validate_tool_pairing."""

    def test_empty_messages(self):
        assert validate([]) == []

    def test_no_tools_passthrough(self):
        """Plain conversation without tools is returned unchanged."""
        msgs = [_user("hello"), _assistant("hi")]
        assert validate(msgs) == msgs

    def test_complete_tool_pair_preserved(self):
        """A matched toolUse + toolResult pair passes through."""
        msgs = [
            _user("do something"),
            _assistant_tool_use("t1", "Read"),
            _user_tool_result("t1", "file contents"),
            _assistant("done"),
        ]
        result = validate(msgs)
        assert result == msgs

    def test_dangling_tool_use_gets_synthetic_result(self):
        """Cancel mid-tool: toolUse with no toolResult gets an error injected."""
        msgs = [
            _user("do something"),
            _assistant_tool_use("t1", "Read"),
        ]
        result = validate(msgs)
        assert len(result) == 3
        # The injected message should be a user message with synthetic error
        synthetic = result[2]
        assert synthetic["role"] == "user"
        assert len(synthetic["content"]) == 1
        assert synthetic["content"][0] == _synthetic_error_result("t1")

    def test_cancel_after_first_tool_preserves_completed(self):
        """Cancel during tool C: A and B results preserved, C gets synthetic."""
        msgs = [
            _user("do A, B, C"),
            _assistant_tool_use("t1", "ToolA"),
            _user_tool_result("t1", "result A"),
            _assistant_tool_use("t2", "ToolB"),
            _user_tool_result("t2", "result B"),
            _assistant_tool_use("t3", "ToolC"),
            # No toolResult for t3 — cancelled
        ]
        result = validate(msgs)
        assert len(result) == 7
        # First 6 messages unchanged
        assert result[:6] == msgs[:6]
        # 7th is synthetic error for t3
        assert result[6]["role"] == "user"
        assert result[6]["content"][0] == _synthetic_error_result("t3")

    def test_cancel_during_first_tool(self):
        """Cancel during the very first tool call."""
        msgs = [
            _user("do something"),
            _assistant_tool_use("t1", "Subagent"),
            # Cancelled — no result
        ]
        result = validate(msgs)
        assert len(result) == 3
        assert result[0] == msgs[0]
        assert result[1] == msgs[1]
        assert result[2]["content"][0] == _synthetic_error_result("t1")

    def test_orphaned_tool_result_dropped(self):
        """A toolResult without a matching toolUse is dropped."""
        msgs = [
            _user("hello"),
            _assistant("thinking"),
            _user_tool_result("orphan_id", "stale result"),
            _assistant("done"),
        ]
        result = validate(msgs)
        # The orphaned toolResult message should be skipped entirely
        # (all its content was orphaned → empty → skip)
        assert len(result) == 3
        assert result[0] == msgs[0]
        assert result[1] == msgs[1]
        assert result[2] == msgs[3]  # "done"

    def test_multiple_parallel_tools_one_missing(self):
        """Multiple toolUse in one assistant message, one result missing."""
        msgs = [
            _user("research"),
            {
                "role": "assistant",
                "content": [
                    {"toolUse": {"toolUseId": "t1", "name": "SubA", "input": {}}},
                    {"toolUse": {"toolUseId": "t2", "name": "SubB", "input": {}}},
                    {"toolUse": {"toolUseId": "t3", "name": "SubC", "input": {}}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"toolResult": {"toolUseId": "t1", "status": "success", "content": [{"text": "r1"}]}},
                    {"toolResult": {"toolUseId": "t2", "status": "success", "content": [{"text": "r2"}]}},
                    # t3 missing — cancelled
                ],
            },
        ]
        result = validate(msgs)
        # t1 and t2 results preserved in user message, t3 gets flushed
        # The original user message keeps t1 and t2, then a synthetic for t3
        assert len(result) == 4  # user, assistant, user(t1+t2), user(t3 synthetic)
        # Check t1 and t2 are in the user message
        user_results = result[2]["content"]
        result_ids = {c["toolResult"]["toolUseId"] for c in user_results}
        assert result_ids == {"t1", "t2"}
        # t3 synthetic
        assert result[3]["role"] == "user"
        assert result[3]["content"][0] == _synthetic_error_result("t3")

    def test_text_and_tool_in_assistant_message(self):
        """Assistant message with both text and toolUse, cancelled."""
        msgs = [
            _user("help"),
            _assistant_text_and_tool("I'll read the file", "t1", "Read"),
            # Cancelled before result
        ]
        result = validate(msgs)
        assert len(result) == 3
        # Assistant message preserved as-is
        assert result[1] == msgs[1]
        # Synthetic result injected
        assert result[2]["content"][0] == _synthetic_error_result("t1")

    def test_cancel_mid_model_response_no_tools(self):
        """Cancel during model streaming (no tools involved) - nothing to repair."""
        msgs = [
            _user("write me a long essay"),
            # Agent was streaming text, cancelled — partial text may or may not be here
        ]
        result = validate(msgs)
        assert result == msgs

    def test_complete_conversation_unchanged(self):
        """A fully complete conversation passes through unchanged."""
        msgs = [
            _user("step 1"),
            _assistant_tool_use("t1", "Read"),
            _user_tool_result("t1", "file A"),
            _assistant_tool_use("t2", "Write"),
            _user_tool_result("t2", "written"),
            _assistant("All done"),
        ]
        result = validate(msgs)
        assert result == msgs
