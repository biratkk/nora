"""Repository for thread persistence."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from nora.config.constants import NORA_DIR_NAME, THREADS_DIR_NAME
from nora.models.thread import Thread


class ThreadRepository:
    """
    Handles persistence of conversation threads to disk.
    
    Threads are stored as JSON files in $CWD/.nora/threads/.
    """
    
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        """
        Initialize the repository.
        
        Args:
            base_dir: Base directory for threads. Defaults to $CWD/.nora.
        """
        cwd_nora = Path.cwd() / NORA_DIR_NAME
        self._base_dir = base_dir or cwd_nora
        self._threads_dir = self._base_dir / THREADS_DIR_NAME
    
    @property
    def threads_dir(self) -> Path:
        """Get the threads directory path."""
        return self._threads_dir
    
    def _ensure_dirs(self) -> None:
        """Ensure the threads directory exists."""
        self._base_dir.mkdir(exist_ok=True)
        self._threads_dir.mkdir(exist_ok=True)
    
    def _get_thread_path(self, thread_id: str) -> Path:
        """Get the file path for a thread."""
        return self._threads_dir / f"thread_{thread_id}.json"
    
    def save(self, thread: Thread) -> None:
        """
        Save a thread to disk.
        
        Updates the thread's updated timestamp and generates a name if missing.
        
        Args:
            thread: Thread instance to persist.
        """
        self._ensure_dirs()
        
        thread.updated = datetime.now().isoformat()
        if not thread.name:
            thread.name = thread._generate_name()
        
        path = self._get_thread_path(thread.id)
        path.write_text(thread.model_dump_json(indent=2))
    
    def load(self, thread_id: str) -> Thread:
        """
        Load a thread from disk.
        
        Args:
            thread_id: The thread ID to load.
            
        Returns:
            Thread instance, or a new thread with the given ID if not found.
        """
        path = self._get_thread_path(thread_id)
        
        if path.exists():
            return Thread.model_validate_json(path.read_text())
        
        return Thread(id=thread_id, created=thread_id)
    
    def list_all(self) -> list[Thread]:
        """
        List all threads, sorted by most recent first.
        
        Returns:
            List of Thread instances.
        """
        if not self._threads_dir.exists():
            return []
        
        threads: list[Thread] = []
        
        for path in sorted(self._threads_dir.glob("thread_*.json"), reverse=True):
            try:
                threads.append(Thread.model_validate_json(path.read_text()))
            except Exception:
                continue
        
        return threads
    
    def exists(self, thread_id: str) -> bool:
        """
        Check if a thread exists.
        
        Args:
            thread_id: The thread ID to check.
            
        Returns:
            True if thread file exists.
        """
        return self._get_thread_path(thread_id).exists()
    
    def delete(self, thread_id: str) -> bool:
        """
        Delete a thread from disk.
        
        Args:
            thread_id: The thread ID to delete.
            
        Returns:
            True if thread was deleted, False if it didn't exist.
        """
        path = self._get_thread_path(thread_id)
        
        if path.exists():
            path.unlink()
            return True
        
        return False
