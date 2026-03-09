"""Service for plan management."""

from typing import Optional, List

from nora.models.plan import Plan
from nora.repositories.plan_repository import PlanRepository


class PlanService:
    """
    Manages plan lifecycle and operations.
    
    Plans capture feature specifications that can be executed in edit/act mode.
    """
    
    def __init__(self, repository: Optional[PlanRepository] = None) -> None:
        """
        Initialize the service.
        
        Args:
            repository: Plan repository instance. Creates default if None.
        """
        self._repository = repository or PlanRepository()
    
    def create(self, name: str, content: str) -> Plan:
        """
        Create a plan with the given name.
        
        Args:
            name: The plan name (e.g., 'auth-session-refactor').
            content: Plan content in markdown.
            
        Returns:
            Created Plan instance.
        """
        return self._repository.save(name, content)
    
    def exists(self, name: str) -> bool:
        """
        Check if a plan exists.
        
        Args:
            name: Plan name.
            
        Returns:
            True if the plan exists.
        """
        return self._repository.exists(name)
    
    def load(self, name: str) -> Optional[Plan]:
        """
        Load a plan by name.
        
        Args:
            name: Plan name to load.
            
        Returns:
            Plan instance or None if not found.
        """
        return self._repository.load(name)
    
    def list_all(self) -> List[Plan]:
        """
        List all plans.
        
        Returns:
            List of plans sorted by most recent first.
        """
        return self._repository.list_all()
    
    @staticmethod
    def get_implementation_prompt(plan_name: str) -> str:
        """
        Generate prompt for implementing a plan.
        
        Args:
            plan_name: Name of the plan to implement.
            
        Returns:
            Implementation prompt string.
        """
        return f"Execute plan: {plan_name}"
