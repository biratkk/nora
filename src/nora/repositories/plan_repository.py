"""Repository for plan persistence."""

from pathlib import Path
from typing import Optional, List

from nora.config.constants import NORA_DIR_NAME, PLANS_DIR_NAME
from nora.models.plan import Plan


class PlanRepository:
    """
    Handles persistence of plans to disk.
    
    Plans are stored as markdown files in $CWD/.nora/plans/.
    New plans use 3-word hyphenated names (e.g., 'auth-session-refactor.md').
    Legacy timestamp-based plans are still readable.
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
    
    def save(self, name: str, content: str) -> Plan:
        """
        Save a plan to disk.
        
        Args:
            name: The plan name (e.g., 'auth-session-refactor').
            content: The plan content in markdown.
            
        Returns:
            The created Plan instance.
        """
        self._ensure_dirs()
        
        plan = Plan(name=name, content=content)
        path = self._plans_dir / plan.get_filename()
        path.write_text(content)
        
        return plan
    
    def exists(self, name: str) -> bool:
        """
        Check if a plan exists.
        
        Args:
            name: The plan name.
            
        Returns:
            True if the plan file exists.
        """
        return (self._plans_dir / f"{name}.md").exists()
    
    def load(self, name: str) -> Optional[Plan]:
        """
        Load a plan by name.
        
        Supports both new-style 3-word names and legacy timestamp-based names.
        
        Args:
            name: The plan name to load.
            
        Returns:
            Plan instance or None if not found.
        """
        # Try exact match first
        path = self._plans_dir / f"{name}.md"
        if path.exists():
            content = path.read_text()
            return Plan(name=name, content=content)
        
        # Try legacy glob (timestamp prefix match)
        if self._plans_dir.exists():
            for legacy_path in self._plans_dir.glob(f"{name}*.md"):
                content = legacy_path.read_text()
                return Plan(
                    name=legacy_path.stem,
                    content=content,
                    id=name,
                    description=legacy_path.stem.replace(f"{name}-", ""),
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
            content = path.read_text()
            plans.append(Plan(name=path.stem, content=content))
        
        return plans
