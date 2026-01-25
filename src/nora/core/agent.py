"""Agent initialization."""

from typing import Optional
import boto3
from strands import Agent
from strands.models import BedrockModel

from nora.tools import read_file, write_file, edit_file, explore_dir, search_files, run_subagent, fetch_url
from nora.core.settings import load_mode_prompt

MODEL_ID = "us.anthropic.claude-opus-4-5-20251101-v1:0"

MODEL_NAMES = {
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": "Claude Sonnet 4.5",
    "us.anthropic.claude-opus-4-5-20251101-v1:0": "Claude Opus 4.5",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": "Claude Haiku 4.5",
    "us.qwen.qwen3-coder-480b-a35b-v1:0": "Qwen3 Coder 480B",
}


def get_model_name(model_id: str | None = None) -> str:
    return MODEL_NAMES.get(model_id or MODEL_ID, model_id or MODEL_ID)


def create_agent(messages: list[dict], profile: Optional[str] = None, mode: str = "vibe", model_id: str | None = None, hooks: list | None = None) -> Agent:
    kwargs = {"model_id": model_id or MODEL_ID}
    if profile:
        kwargs["boto_session"] = boto3.Session(profile_name=profile)
    model = BedrockModel(**kwargs)
    
    system_prompt = load_mode_prompt(mode)
    
    if mode == "plan":
        tools = [read_file, explore_dir, search_files, fetch_url]
    else:
        tools = [read_file, write_file, edit_file, explore_dir, search_files, run_subagent, fetch_url]
    
    return Agent(model=model, messages=messages, tools=tools, system_prompt=system_prompt, hooks=hooks or [])
