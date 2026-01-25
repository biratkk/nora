"""Repository for plan persistence."""

from datetime import datetime
from pathlib import Path
from typing import Optional, List

from nora.config.constants import NORA_DIR_NAME, PLANS_DIR_NAME
from nora.models.plan import Plan
from nora.utils.text import generate_plan_description


class PlanRepository:
    """
    Handles persistence of plans to disk.
    
    Plans are stored as markdown files in $CWD/.nora/plans/.
    """
    
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        """
        Initialize the repository.
        
        Args:
            base_dir: Base directory for plans. Defaults to $CWD/.nora.
        """
        cwd_nora = Path.cwd() / NORA_DIR_NAME
        self._base_dir = base_dir or cwd_nora
        self._plans_dir = self._base_dir / PLANS_DIR_NAME
    
    @property
    def plans_dir(self) -> Path:
        """Get the plans directory path."""
        return self._plans_dir
    
    def _ensure_dirs(self) -> None:
        """Ensure the plans directory exists."""
        self._plans_dir.mkdir(parents=True, exist_ok=True)
    
    def save(self, thread_id: str, content: str) -> Plan:
        """
        Save a plan to disk.
        
        Generates a timestamp-based ID and description from content.
        
        Args:
            thread_id: The source thread ID.
            content: The plan content in markdown.
            
        Returns:
            The created Plan instance.
        """
        self._ensure_dirs()
        
        plan_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        description = generate_plan_description(content)
        
        plan = Plan(
            id=plan_id,
            description=description,
            content=content,
            created=datetime.now(),
            thread_id=thread_id
        )
        
        path = self._plans_dir / plan.get_filename()
        path.write_text(content)
        
        return plan
    
    def load(self, plan_id: str) -> Optional[Plan]:
        """
        Load a plan by ID.
        
        Args:
            plan_id: The plan ID to load.
            
        Returns:
            Plan instance or None if not found.
        """
        if not self._plans_dir.exists():
            return None
        
        for path in self._plans_dir.glob(f"{plan_id}-*.md"):
            content = path.read_text()
            filename = path.stem
            description = filename.replace(f"{plan_id}-", "")
            
            return Plan(
                id=plan_id,
                description=description,
                content=content,
                created=datetime.fromtimestamp(path.stat().st_ctime),
                thread_id=""
            )
        
        return None
    
    def list_all(self) -> List[Plan]:
        """
        List all plans, sorted by most recent first.
        
        Returns:
            List of Plan instances.
        """
        if not self._plans_dir.exists():
            return []
        
        plans: List[Plan] = []
        
        for path in sorted(self._plans_dir.glob("*.md"), reverse=True):
            filename = path.stem
            parts = filename.split("-", 1)
            if len(parts) != 2:
                continue
            
            plan_id, description = parts
            content = path.read_text()
            
            plans.append(Plan(
                id=plan_id,
                description=description,
                content=content,
                created=datetime.fromtimestamp(path.stat().st_ctime),
                thread_id=""
            ))
        
        return plans
