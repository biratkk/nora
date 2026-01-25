"""Repository for trust policy persistence."""

from pathlib import Path
from typing import Optional

from nora.config.constants import NORA_DIR_NAME
from nora.models.trust_policy import TrustPolicyFile, Policy


TRUST_DIR_NAME = "trust"


class TrustRepository:
    """
    Handles persistence of trust policies to disk.
    
    Policies are stored as JSON files in $CWD/.nora/trust/<program>.json.
    """
    
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        """
        Initialize the repository.
        
        Args:
            base_dir: Base directory for trust policies. Defaults to $CWD/.nora.
        """
        cwd_nora = Path.cwd() / NORA_DIR_NAME
        self._base_dir = base_dir or cwd_nora
        self._trust_dir = self._base_dir / TRUST_DIR_NAME
    
    @property
    def trust_dir(self) -> Path:
        """Get the trust directory path."""
        return self._trust_dir
    
    def _ensure_dirs(self) -> None:
        """Ensure the trust directory exists."""
        self._base_dir.mkdir(exist_ok=True)
        self._trust_dir.mkdir(exist_ok=True)
    
    def _get_policy_path(self, program: str) -> Path:
        """Get the file path for a program's trust policy."""
        # Sanitize program name for filesystem
        safe_name = program.replace("/", "_").replace("\\", "_")
        return self._trust_dir / f"{safe_name}.json"
    
    def load(self, program: str) -> TrustPolicyFile:
        """
        Load trust policy for a program.
        
        Args:
            program: The program name.
            
        Returns:
            TrustPolicyFile instance, or a new empty policy if not found.
        """
        path = self._get_policy_path(program)
        
        if path.exists():
            try:
                return TrustPolicyFile.model_validate_json(path.read_text())
            except Exception:
                pass
        
        return TrustPolicyFile(program=program)
    
    def save(self, policy_file: TrustPolicyFile) -> None:
        """
        Save a trust policy to disk.
        
        Args:
            policy_file: TrustPolicyFile instance to persist.
        """
        self._ensure_dirs()
        path = self._get_policy_path(policy_file.program)
        path.write_text(policy_file.model_dump_json(indent=2))
    
    def add_policy(
        self, 
        program: str, 
        policy: Policy
    ) -> TrustPolicyFile:
        """
        Add a policy to a program's trust file.
        
        Args:
            program: The program name.
            policy: The policy to add.
            
        Returns:
            Updated TrustPolicyFile.
        """
        policy_file = self.load(program)
        policy_file.add_policy(policy)
        self.save(policy_file)
        return policy_file
    
    def exists(self, program: str) -> bool:
        """
        Check if a trust policy file exists.
        
        Args:
            program: The program name.
            
        Returns:
            True if policy file exists.
        """
        return self._get_policy_path(program).exists()
    
    def delete(self, program: str) -> bool:
        """
        Delete a trust policy file.
        
        Args:
            program: The program name.
            
        Returns:
            True if file was deleted, False if it didn't exist.
        """
        path = self._get_policy_path(program)
        
        if path.exists():
            path.unlink()
            return True
        
        return False
