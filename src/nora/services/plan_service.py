"""Service for plan management."""

from typing import Optional, List, Union

from nora.models.plan import Plan
from nora.models.thread import Thread
from nora.acp.models.session import Session
from nora.repositories.plan_repository import PlanRepository


class PlanService:
    """
    Manages plan lifecycle and operations.
    
    Plans capture feature specifications from plan mode that can
    be executed in act mode.
    """
    
    def __init__(self, repository: Optional[PlanRepository] = None) -> None:
        """
        Initialize the service.
        
        Args:
            repository: Plan repository instance. Creates default if None.
        """
        self._repository = repository or PlanRepository()
    
    def create_from_thread(self, thread: Thread, content: str) -> Plan:
        """
        Create a plan from thread content.
        
        Args:
            thread: Source thread.
            content: Plan content in markdown.
            
        Returns:
            Created Plan instance.
        """
        return self._repository.save(thread.id, content)
    
    def create_from_session(self, session: Session, content: str) -> Plan:
        """
        Create a plan from session content.
        
        Args:
            session: Source session.
            content: Plan content in markdown.
            
        Returns:
            Created Plan instance.
        """
        return self._repository.save(str(session.id), content)
    
    def save_and_link(self, thread: Thread, content: str) -> Plan:
        """
        Save a plan and link it to the thread.
        
        Updates the thread's plan_id and mode.
        
        Args:
            thread: Thread to link.
            content: Plan content.
            
        Returns:
            Created Plan instance.
        """
        plan = self.create_from_thread(thread, content)
        thread.plan_id = plan.id
        thread.mode = "edit"
        return plan
    
    def save_and_link_session(self, session: Session, content: str) -> Plan:
        """
        Save a plan and link it to the session.
        
        Updates the session's plan_id. The caller is responsible for
        switching to 'act' mode on the next run.
        
        Args:
            session: Session to link.
            content: Plan content.
            
        Returns:
            Created Plan instance.
        """
        plan = self.create_from_session(session, content)
        session.metadata.plan_id = plan.id
        return plan
    
    def load(self, plan_id: str) -> Optional[Plan]:
        """
        Load a plan by ID.
        
        Args:
            plan_id: Plan ID to load.
            
        Returns:
            Plan instance or None if not found.
        """
        return self._repository.load(plan_id)
    
    def list_all(self) -> List[Plan]:
        """
        List all plans.
        
        Returns:
            List of plans sorted by most recent first.
        """
        return self._repository.list_all()
    
    def get_implementation_prompt(self, plan: Plan) -> str:
        """
        Generate prompt for implementing a plan.
        
        Args:
            plan: Plan to implement.
            
        Returns:
            Implementation prompt string.
        """
        return f"Implementing Plan: {plan.id}-{plan.description}"
