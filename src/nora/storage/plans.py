"""Plan persistence operations."""

import re
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel

PLANS_DIR = Path.cwd() / ".nora" / "plans"


class Plan(BaseModel):
    id: str
    description: str
    content: str
    created: datetime
    thread_id: str


def generate_description(content: str) -> str:
    first_line = content.strip().split("\n")[0]
    clean = re.sub(r"[^a-z0-9\s]", "", first_line.lower())
    words = clean.split()[:4]
    return "-".join(words)[:20] or "plan"


def save_plan(thread_id: str, content: str) -> Plan:
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    plan_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    desc = generate_description(content)
    plan = Plan(id=plan_id, description=desc, content=content, created=datetime.now(), thread_id=thread_id)
    path = PLANS_DIR / f"{plan_id}-{desc}.md"
    path.write_text(content)
    return plan
