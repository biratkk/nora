"""Service for plugin management and matching."""

from pathlib import Path
from typing import Optional, List, Tuple

import boto3
from strands import Agent
from strands.models import BedrockModel
from thefuzz import fuzz

from nora.config.constants import PLUGIN_MATCH_THRESHOLD
from nora.models.plugin import Plugin
from nora.repositories.plugin_repository import PluginRepository


class PluginService:
    """
    Manages plugin lifecycle and keyword matching.
    
    Provides operations for loading plugins and matching them
    against user input using fuzzy keyword matching.
    Reads directly from disk on every operation — no caching.
    """
    
    def __init__(self, repository: Optional[PluginRepository] = None) -> None:
        """
        Initialize the service.
        
        Args:
            repository: Plugin repository instance. Creates default if None.
        """
        self._repository = repository or PluginRepository()
    
    def load_all(self) -> List[Plugin]:
        """
        Load all plugins from disk.
        
        Returns:
            List of Plugin instances.
        """
        return self._repository.load_all()
    
    def save(self, plugin: Plugin) -> Path:
        """
        Save a plugin to disk.
        
        Args:
            plugin: Plugin to persist.
            
        Returns:
            Path to the created plugin file.
        """
        return self._repository.save(plugin)
    
    def load(self, name: str) -> Optional[Plugin]:
        """
        Load a single plugin by name.
        
        Args:
            name: The plugin name.
            
        Returns:
            Plugin instance or None if not found.
        """
        return self._repository.load(name)
    
    def delete(self, name: str) -> bool:
        """
        Delete a plugin by name.
        
        Args:
            name: The plugin name.
            
        Returns:
            True if deleted, False if not found.
        """
        return self._repository.delete(name)
    
    def _effective_threshold(self, text: str, base_threshold: int) -> int:
        """
        Scale match threshold based on input length.
        
        Short inputs get a higher threshold to prevent false positives
        from partial_ratio substring matching (e.g. "hi" matching "matching").
        Inputs shorter than 4 characters are effectively blocked (threshold > 100).
        
        Args:
            text: User input text.
            base_threshold: Base threshold (e.g. 80).
            
        Returns:
            Effective threshold. May exceed 100 to block very short inputs.
        """
        length = len(text.strip())
        penalty = max(0, (10 - length) * 3)
        return base_threshold + penalty
    
    def match_plugins(
        self, 
        text: str, 
        threshold: int = PLUGIN_MATCH_THRESHOLD
    ) -> List[Plugin]:
        """
        Find plugins matching the given text using fuzzy keyword matching.
        
        Reads all plugins from disk on every call. Short inputs require
        a higher match score to prevent false positives.
        
        Args:
            text: User input text to match against.
            threshold: Base minimum match score (0-100).
            
        Returns:
            List of matching Plugin instances.
        """
        effective = self._effective_threshold(text, threshold)
        plugins = self._repository.load_all()
        matched: List[Plugin] = []
        text_lower = text.lower()
        
        for plugin in plugins:
            if self._plugin_matches(plugin, text_lower, effective):
                matched.append(plugin)
        
        return matched
    
    def search_by_keyword(
        self,
        keyword: str,
        threshold: int = PLUGIN_MATCH_THRESHOLD,
    ) -> List[Tuple[Plugin, int]]:
        """
        Search all plugins by keyword, returning matches with scores.
        
        Args:
            keyword: Keyword to search for.
            threshold: Minimum match score (0-100).
            
        Returns:
            List of (Plugin, best_score) tuples, sorted by score descending.
        """
        all_plugins = self._repository.load_all()
        keyword_lower = keyword.lower()
        results: List[Tuple[Plugin, int]] = []
        
        for plugin in all_plugins:
            best_score = 0
            for kw in plugin.keywords:
                score = fuzz.partial_ratio(kw.lower(), keyword_lower)
                if score > best_score:
                    best_score = score
            if best_score >= threshold:
                results.append((plugin, best_score))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results
    
    def _plugin_matches(
        self, 
        plugin: Plugin, 
        text_lower: str, 
        threshold: int
    ) -> bool:
        """
        Check if a plugin matches the text.
        
        Args:
            plugin: Plugin to check.
            text_lower: Lowercase user input.
            threshold: Minimum match score.
            
        Returns:
            True if any keyword matches above threshold.
        """
        for keyword in plugin.keywords:
            ratio = fuzz.partial_ratio(keyword.lower(), text_lower)
            if ratio >= threshold:
                return True
        return False
    
    def build_context(self, plugins: List[Plugin]) -> str:
        """
        Build context string from matched plugins.
        
        Args:
            plugins: List of plugins to include.
            
        Returns:
            Combined plugin context blocks.
        """
        if not plugins:
            return ""
        
        blocks = [plugin.to_context_block() for plugin in plugins]
        return "\n\n".join(blocks) + "\n\n"
    
    def enhance_prompt(self, text: str, plugins: List[Plugin]) -> str:
        """
        Enhance user prompt with plugin context.
        
        Args:
            text: Original user text.
            plugins: Matched plugins to inject.
            
        Returns:
            Enhanced prompt with plugin context prepended.
        """
        context = self.build_context(plugins)
        return context + text
    
    @staticmethod
    def generate_metadata(
        name: str,
        instructions: str,
        profile: Optional[str] = None,
    ) -> Tuple[str, List[str]]:
        """
        Generate plugin description and keywords using an LLM.
        
        Spins up a lightweight Strands agent (Sonnet model, no tools)
        to produce a one-line description and up to 30 keywords.
        
        Args:
            name: Plugin name.
            instructions: Plugin instruction text.
            profile: Optional AWS profile name.
            
        Returns:
            Tuple of (description, keywords_list).
        """
        kwargs = {"model_id": "us.anthropic.claude-sonnet-4-5-20250929-v1:0"}
        if profile:
            kwargs["boto_session"] = boto3.Session(profile_name=profile)
        model = BedrockModel(**kwargs)
        
        prompt = (
            f"Given this plugin name and instructions, generate:\n"
            f"1. A brief one-sentence description (max 100 chars)\n"
            f"2. Up to 30 relevant keywords that would help match user queries to this plugin\n"
            f"\n"
            f"Plugin Name: {name}\n"
            f"\n"
            f"Instructions:\n"
            f"{instructions}\n"
            f"\n"
            f"Respond in this exact format (no extra text):\n"
            f"DESCRIPTION: <one sentence description>\n"
            f"KEYWORDS: <comma-separated keywords>"
        )
        
        agent = Agent(
            model=model,
            tools=[],
            system_prompt=(
                "You are a helpful assistant that generates metadata for plugins. "
                "Respond only in the exact format requested."
            ),
        )
        
        result = agent(prompt)
        response = str(result)
        
        description = ""
        keywords: List[str] = []
        
        for line in response.strip().split("\n"):
            if line.startswith("DESCRIPTION:"):
                description = line.replace("DESCRIPTION:", "").strip()
            elif line.startswith("KEYWORDS:"):
                keywords_str = line.replace("KEYWORDS:", "").strip()
                keywords = [k.strip() for k in keywords_str.split(",") if k.strip()][:30]
        
        return description, keywords
