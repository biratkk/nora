"""Ask tool for gathering structured user input during planning."""

import logging
from typing import Any

from strands import tool
from strands.types.tools import ToolContext

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 7
MAX_OPTIONS = 4


@tool(name="Ask", context=True)
def ask_user(tool_context: ToolContext, questions: list[dict]) -> str:
    """Ask the user structured multiple-choice questions.

    Use this to gather specific preferences, requirements, or decisions
    from the user. Each question can have up to 4 predefined options.
    The user can also provide a custom answer via an "Other" option
    that is always available.

    Args:
        questions: List of question objects, each with 'question' (str)
                   and 'options' (list of up to 4 strings).
                   Maximum 7 questions per call.
    """
    if not questions:
        return "Error: No questions provided"

    if len(questions) > MAX_QUESTIONS:
        logger.warning(
            "Ask tool received %d questions, truncating to %d",
            len(questions),
            MAX_QUESTIONS,
        )
        questions = questions[:MAX_QUESTIONS]

    for q in questions:
        opts = q.get("options", [])
        if len(opts) > MAX_OPTIONS:
            logger.warning(
                "Question '%s' has %d options, truncating to %d",
                q.get("question", ""),
                len(opts),
                MAX_OPTIONS,
            )
            q["options"] = opts[:MAX_OPTIONS]

    invocation_state = getattr(tool_context, "invocation_state", {}) or {}
    client = invocation_state.get("client")

    if client is not None:
        # ACP path — fall back to plain text questions
        return _ask_plain_text(questions)

    # TUI path — interrupt flow
    return tool_context.interrupt("ask-confirm", reason={"questions": questions})


def _ask_plain_text(questions: list[dict]) -> str:
    """Format questions as plain text for non-TUI contexts."""
    lines = []
    for i, q in enumerate(questions, 1):
        lines.append(f"Q{i}: {q.get('question', '')}")
        opts = q.get("options", [])
        for j, opt in enumerate(opts, 1):
            lines.append(f"  {j}. {opt}")
        lines.append(f"  {len(opts) + 1}. Other (custom answer)")
        lines.append("")
    return "Please answer the following questions:\n\n" + "\n".join(lines)
