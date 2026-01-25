"""Thread persistence operations."""

from datetime import datetime
from pathlib import Path

from nora.models.thread import Thread

ROOT_PROJECT_NORA_DIR = Path.cwd() / ".nora"
THREADS_DIR = ROOT_PROJECT_NORA_DIR / Path("threads")


def save_thread(thread: Thread) -> None:
    ROOT_PROJECT_NORA_DIR.mkdir(exist_ok=True)
    THREADS_DIR.mkdir(exist_ok=True)
    thread.updated = datetime.now().isoformat()
    if not thread.name:
        thread.name = thread._generate_name()
    path = THREADS_DIR / f"thread_{thread.id}.json"
    path.write_text(thread.model_dump_json(indent=2))


def load_thread(thread_id: str) -> Thread:
    path = THREADS_DIR / f"thread_{thread_id}.json"
    if path.exists():
        return Thread.model_validate_json(path.read_text())
    return Thread(id=thread_id, created=thread_id)


def list_threads() -> list[Thread]:
    if not THREADS_DIR.exists():
        return []
    threads = []
    for f in sorted(THREADS_DIR.glob("thread_*.json"), reverse=True):
        threads.append(Thread.model_validate_json(f.read_text()))
    return threads
