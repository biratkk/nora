"""Trust policy models for shell command authorization."""

from typing import Optional
from pydantic import BaseModel, Field


class Policy(BaseModel):
    """
    A single trust policy rule for shell command execution.
    
    Policies define which commands are trusted and under what conditions.
    """
    
    args: list[str] = Field(default_factory=list, description="Base arguments that must match (prefix)")
    default_trusted: bool = Field(default=False, description="Whether args alone is trusted")
    trust_all_arguments: bool = Field(default=False, description="Whether any additional arguments are allowed")
    trust_all_threads: bool = Field(default=False, description="Whether this policy applies to all threads")
    trusted_threads: list[str] = Field(default_factory=list, description="Thread IDs where this policy applies")
    trusted_arguments: list[str] = Field(default_factory=list, description="Specific additional arguments that are trusted")


class TrustPolicyFile(BaseModel):
    """
    Trust policy file for a specific program.
    
    Stored at $CWD/.nora/trust/<program>.json
    """
    
    program: str = Field(..., description="The executable name")
    policies: list[Policy] = Field(default_factory=list, description="List of policy rules")
    
    def add_policy(self, policy: Policy) -> None:
        """Add a policy to the file."""
        self.policies.append(policy)
    
    def find_matching_policy(
        self, 
        args: list[str], 
        thread_id: str
    ) -> Optional[Policy]:
        """
        Find a policy that allows the given command.
        
        Args:
            args: The command arguments to check.
            thread_id: The current thread ID.
            
        Returns:
            The first matching policy that allows the command, or None.
        """
        for policy in self.policies:
            if self._policy_matches(policy, args, thread_id):
                return policy
        return None
    
    def _policy_matches(
        self, 
        policy: Policy, 
        args: list[str], 
        thread_id: str
    ) -> bool:
        """
        Check if a policy allows the given command.
        
        Args:
            policy: The policy to check.
            args: The command arguments.
            thread_id: The current thread ID.
            
        Returns:
            True if the policy allows the command.
        """
        # Check thread permission first
        if not policy.trust_all_threads:
            if thread_id not in policy.trusted_threads:
                return False
        
        policy_args = policy.args
        
        # Check if policy args is a prefix of command args
        if len(args) < len(policy_args):
            return False
        
        for i, policy_arg in enumerate(policy_args):
            if args[i] != policy_arg:
                return False
        
        # Get additional arguments beyond policy args
        additional_args = args[len(policy_args):]
        
        # If no additional args, check if base command is trusted
        if not additional_args:
            return policy.default_trusted
        
        # If there are additional args, check if they're allowed
        if policy.trust_all_arguments:
            return True
        
        # Check if additional args are in trusted arguments
        # All additional args must be in trusted_arguments
        for arg in additional_args:
            if arg not in policy.trusted_arguments:
                return False
        
        return True
