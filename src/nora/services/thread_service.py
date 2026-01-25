"""Service for conversation thread management."""

from typing import Optional, List

from nora.models.thread import Thread, Mode
from nora.models.message import Message
from nora.repositories.thread_repository import ThreadRepository
from nora.config.constants import MODE_CYCLE


class ThreadService:
    """
    Manages conversation thread lifecycle and operations.
    
    Provides high-level operations for creating, loading, and
    manipulating conversation threads.
    """
    
    def __init__(self, repository: Optional[ThreadRepository] = None) -> None:
        """
        Initialize the service.
        
        Args:
            repository: Thread repository instance. Creates default if None.
        """
        self._repository = repository or ThreadRepository()
    
    def create(self) -> Thread:
        """
        Create a new conversation thread.
        
        Returns:
            New Thread instance with generated ID.
        """
        return Thread.create()
    
    def save(self, thread: Thread) -> None:
        """
        Save a thread to disk.
        
        Args:
            thread: Thread to persist.
        """
        self._repository.save(thread)
    
    def load(self, thread_id: str) -> Thread:
        """
        Load a thread by ID.
        
        Args:
            thread_id: The thread ID to load.
            
        Returns:
            Thread instance.
        """
        return self._repository.load(thread_id)
    
    def list_all(self) -> List[Thread]:
        """
        List all threads.
        
        Returns:
            List of threads sorted by most recent first.
        """
        return self._repository.list_all()
    
    def add_message(self, thread: Thread, message: Message) -> None:
        """
        Add a message to a thread.
        
        Args:
            thread: Target thread.
            message: Message to add.
        """
        thread.messages.append(message)
    
    def add_user_message(self, thread: Thread, content: str) -> Message:
        """
        Add a user message to a thread.
        
        Args:
            thread: Target thread.
            content: Message content.
            
        Returns:
            The created Message instance.
        """
        message = Message(role="user", content=content)
        self.add_message(thread, message)
        return message
    
    def add_assistant_message(self, thread: Thread, content: str) -> Message:
        """
        Add an assistant message to a thread.
        
        Args:
            thread: Target thread.
            content: Message content.
            
        Returns:
            The created Message instance.
        """
        message = Message(role="assistant", content=content)
        self.add_message(thread, message)
        return message
    
    def add_tool_call(
        self, 
        thread: Thread, 
        tool: str, 
        parameters: dict,
        result: Optional[str] = None
    ) -> Message:
        """
        Add a tool call record to a thread.
        
        Args:
            thread: Target thread.
            tool: Tool name.
            parameters: Tool parameters.
            result: Optional tool result.
            
        Returns:
            The created Message instance.
        """
        message = Message(
            role="tool_call",
            tool=tool,
            parameters=parameters,
            result=result
        )
        self.add_message(thread, message)
        return message
    
    def get_last_assistant_message(self, thread: Thread) -> Optional[str]:
        """
        Get the content of the last assistant message.
        
        Args:
            thread: Thread to search.
            
        Returns:
            Last assistant message content or None.
        """
        for msg in reversed(thread.messages):
            if msg.role == "assistant" and msg.content:
                return msg.content
        return None
    
    def set_mode(self, thread: Thread, mode: Mode) -> None:
        """
        Set the thread mode.
        
        Args:
            thread: Target thread.
            mode: New mode (vibe, plan, act).
        """
        thread.mode = mode
    
    def cycle_mode(self, thread: Thread) -> Mode:
        """
        Cycle to the next mode.
        
        Args:
            thread: Target thread.
            
        Returns:
            The new mode.
        """
        current_idx = MODE_CYCLE.index(thread.mode)
        new_mode = MODE_CYCLE[(current_idx + 1) % len(MODE_CYCLE)]
        thread.mode = new_mode
        return new_mode
