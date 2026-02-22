"""Integration tests for plugin matching and lifecycle.

Tests the full flow: create a plugin on disk, verify keyword matching
with various inputs (including short-input threshold scaling), and
clean up afterward.
"""

import pytest

from nora.models.plugin import Plugin
from nora.repositories.plugin_repository import PluginRepository
from nora.services.plugin_service import PluginService


def _make_test_plugin() -> Plugin:
    """Create a test plugin with known keywords."""
    return Plugin(
        name="test-integration",
        description="A test plugin for integration testing",
        keywords=[
            "testing", "integration", "debug", "diagnostic",
            "validation", "plugin", "quality", "automated",
        ],
        instructions="You MUST start your response with: TEST PLUGIN ACTIVATED!",
    )


def _make_frontend_plugin() -> Plugin:
    """Create a frontend-focused plugin with distinct keywords."""
    return Plugin(
        name="frontend-styles",
        description="Frontend design guidelines",
        keywords=[
            "frontend", "css", "design", "layout", "typography",
            "animation", "responsive", "tailwind", "stylesheet",
        ],
        instructions="Follow the frontend design system guidelines.",
    )


class TestPluginMatching:
    """Integration tests for plugin fuzzy keyword matching."""

    def test_exact_keyword_match(self, tmp_path):
        """A word that exactly matches a keyword should activate the plugin."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)
        service.save(_make_test_plugin())

        matched = service.match_plugins("testing")
        assert len(matched) == 1
        assert matched[0].name == "test-integration"

    def test_partial_keyword_match(self, tmp_path):
        """A word that partially matches a keyword above threshold should match."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)
        service.save(_make_test_plugin())

        matched = service.match_plugins("integration tests")
        assert len(matched) == 1
        assert matched[0].name == "test-integration"

    def test_no_match_unrelated_text(self, tmp_path):
        """Completely unrelated text should not match any plugin."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)
        service.save(_make_test_plugin())

        matched = service.match_plugins("what is the weather today")
        assert len(matched) == 0

    def test_short_input_rejected_two_chars(self, tmp_path):
        """Very short inputs (2 chars) should never match due to threshold scaling."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)
        service.save(_make_test_plugin())

        matched = service.match_plugins("hi")
        assert len(matched) == 0

    def test_short_input_rejected_three_chars(self, tmp_path):
        """Three-char inputs should not match (threshold exceeds 100)."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)
        service.save(_make_test_plugin())

        matched = service.match_plugins("hey")
        assert len(matched) == 0

    def test_short_input_rejected_single_char(self, tmp_path):
        """Single character inputs should never match."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)
        service.save(_make_test_plugin())

        matched = service.match_plugins("a")
        assert len(matched) == 0

    def test_multiple_plugins_selective_match(self, tmp_path):
        """Only plugins with matching keywords should be returned."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)
        service.save(_make_test_plugin())
        service.save(_make_frontend_plugin())

        matched = service.match_plugins("css stylesheet design")
        names = [p.name for p in matched]
        assert "frontend-styles" in names
        assert "test-integration" not in names

    def test_multiple_plugins_both_match(self, tmp_path):
        """When text matches keywords from multiple plugins, all should be returned."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)
        service.save(_make_test_plugin())
        service.save(_make_frontend_plugin())

        # "plugin" is a keyword in test-integration, "design" in frontend-styles
        matched = service.match_plugins("plugin design system")
        names = [p.name for p in matched]
        assert "test-integration" in names
        assert "frontend-styles" in names

    def test_no_plugins_on_disk(self, tmp_path):
        """Matching with no plugins on disk should return empty list."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)

        matched = service.match_plugins("anything at all")
        assert len(matched) == 0

    def test_case_insensitive_matching(self, tmp_path):
        """Keyword matching should be case-insensitive."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)
        service.save(_make_test_plugin())

        matched = service.match_plugins("TESTING INTEGRATION")
        assert len(matched) == 1
        assert matched[0].name == "test-integration"


class TestEffectiveThreshold:
    """Unit tests for the threshold scaling logic."""

    def test_long_input_uses_base_threshold(self, tmp_path):
        """Inputs of 10+ chars should use the base threshold (80)."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)

        assert service._effective_threshold("this is long enough", 80) == 80

    def test_short_input_exceeds_100(self, tmp_path):
        """Inputs of 1-3 chars should have threshold > 100 (unmatchable)."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)

        assert service._effective_threshold("a", 80) > 100
        assert service._effective_threshold("hi", 80) > 100
        assert service._effective_threshold("hey", 80) > 100

    def test_medium_input_scaled_threshold(self, tmp_path):
        """Inputs of 4-9 chars should have threshold between 80 and 100."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)

        for length in range(4, 10):
            text = "x" * length
            threshold = service._effective_threshold(text, 80)
            assert 80 < threshold <= 98, f"len={length}, threshold={threshold}"

    def test_threshold_decreases_with_length(self, tmp_path):
        """Longer inputs should have lower (easier) thresholds."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)

        thresholds = [
            service._effective_threshold("x" * i, 80) for i in range(1, 15)
        ]
        # Should be monotonically non-increasing
        for i in range(len(thresholds) - 1):
            assert thresholds[i] >= thresholds[i + 1]


class TestPluginLifecycle:
    """Integration tests for plugin CRUD via the service layer."""

    def test_save_and_load(self, tmp_path):
        """A saved plugin should be loadable by name."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)
        plugin = _make_test_plugin()

        service.save(plugin)
        loaded = service.load("test-integration")

        assert loaded is not None
        assert loaded.name == "test-integration"
        assert loaded.instructions == plugin.instructions
        assert loaded.keywords == plugin.keywords

    def test_save_and_load_all(self, tmp_path):
        """All saved plugins should appear in load_all."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)

        service.save(_make_test_plugin())
        service.save(_make_frontend_plugin())

        all_plugins = service.load_all()
        names = {p.name for p in all_plugins}
        assert names == {"test-integration", "frontend-styles"}

    def test_delete_removes_plugin(self, tmp_path):
        """A deleted plugin should not be loadable or matchable."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)

        service.save(_make_test_plugin())
        assert service.load("test-integration") is not None

        deleted = service.delete("test-integration")
        assert deleted is True
        assert service.load("test-integration") is None
        assert len(service.match_plugins("testing")) == 0

    def test_delete_nonexistent_returns_false(self, tmp_path):
        """Deleting a plugin that doesn't exist should return False."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)

        assert service.delete("nonexistent") is False

    def test_no_cache_stale_state(self, tmp_path):
        """Creating a plugin should be immediately matchable (no stale cache)."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)

        # No plugins yet
        assert len(service.match_plugins("testing")) == 0

        # Save a plugin
        service.save(_make_test_plugin())

        # Immediately matchable without any cache invalidation
        assert len(service.match_plugins("testing")) == 1

    def test_delete_immediately_removes_from_matching(self, tmp_path):
        """Deleting a plugin should immediately remove it from matching results."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)

        service.save(_make_test_plugin())
        assert len(service.match_plugins("testing")) == 1

        service.delete("test-integration")
        assert len(service.match_plugins("testing")) == 0


class TestContextInjection:
    """Tests for plugin context building and prompt enhancement."""

    def test_build_context_single_plugin(self, tmp_path):
        """Context should wrap instructions in PluginDetails XML tags."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)
        plugin = _make_test_plugin()

        context = service.build_context([plugin])
        assert "<PluginDetails name='test-integration'>" in context
        assert "TEST PLUGIN ACTIVATED!" in context
        assert "</PluginDetails>" in context

    def test_build_context_multiple_plugins(self, tmp_path):
        """Context should contain blocks for all plugins."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)

        context = service.build_context([_make_test_plugin(), _make_frontend_plugin()])
        assert "<PluginDetails name='test-integration'>" in context
        assert "<PluginDetails name='frontend-styles'>" in context

    def test_build_context_empty(self, tmp_path):
        """Empty plugin list should produce empty context."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)

        assert service.build_context([]) == ""

    def test_enhance_prompt_prepends_context(self, tmp_path):
        """Enhanced prompt should have plugin context before user text."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)
        plugin = _make_test_plugin()

        enhanced = service.enhance_prompt("help me debug this", [plugin])
        # Context should come first
        context_pos = enhanced.index("<PluginDetails")
        text_pos = enhanced.index("help me debug this")
        assert context_pos < text_pos

    def test_enhance_prompt_no_plugins(self, tmp_path):
        """With no plugins, enhanced prompt should equal original text."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)

        enhanced = service.enhance_prompt("just a normal message", [])
        assert enhanced == "just a normal message"

    def test_end_to_end_match_and_inject(self, tmp_path):
        """Full flow: save plugin, match by keyword, enhance prompt."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)
        service.save(_make_test_plugin())

        matched = service.match_plugins("run the integration tests")
        assert len(matched) >= 1

        enhanced = service.enhance_prompt("run the integration tests", matched)
        assert "<PluginDetails name='test-integration'>" in enhanced
        assert "run the integration tests" in enhanced


class TestSearchByKeyword:
    """Tests for the search_by_keyword method."""

    def test_search_returns_scored_results(self, tmp_path):
        """Search should return plugins with scores."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)
        service.save(_make_test_plugin())

        results = service.search_by_keyword("testing")
        assert len(results) == 1
        plugin, score = results[0]
        assert plugin.name == "test-integration"
        assert score >= 80

    def test_search_sorted_by_score(self, tmp_path):
        """Results should be sorted by score descending."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)
        service.save(_make_test_plugin())
        service.save(_make_frontend_plugin())

        results = service.search_by_keyword("design")
        if len(results) > 1:
            scores = [score for _, score in results]
            assert scores == sorted(scores, reverse=True)

    def test_search_no_results(self, tmp_path):
        """Search with no matching keyword should return empty."""
        repo = PluginRepository(base_dir=tmp_path)
        service = PluginService(repository=repo)
        service.save(_make_test_plugin())

        results = service.search_by_keyword("xyznonexistent")
        assert len(results) == 0


class TestPluginSerialization:
    """Tests for plugin roundtrip through markdown serialization."""

    def test_roundtrip_through_disk(self, tmp_path):
        """Plugin saved to disk and loaded back should have identical fields."""
        repo = PluginRepository(base_dir=tmp_path)
        original = _make_test_plugin()

        repo.save(original)
        loaded = repo.load("test-integration")

        assert loaded is not None
        assert loaded.name == original.name
        assert loaded.description == original.description
        assert loaded.keywords == original.keywords
        assert loaded.instructions == original.instructions

    def test_old_format_with_load_on_startup_ignored(self, tmp_path):
        """Plugin files with legacy load_on_startup field should parse fine."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir(parents=True)

        # Write a plugin file in the old format with load_on_startup
        old_format = (
            "---\n"
            "name: legacy-plugin\n"
            "description: Old format plugin\n"
            "keywords: legacy, old\n"
            "load_on_startup: 'yes'\n"
            "---\n"
            "Legacy instructions here.\n"
        )
        (plugins_dir / "legacy-plugin.md").write_text(old_format)

        repo = PluginRepository(base_dir=tmp_path)
        loaded = repo.load("legacy-plugin")

        assert loaded is not None
        assert loaded.name == "legacy-plugin"
        assert loaded.instructions == "Legacy instructions here."
        assert not hasattr(loaded, "load_on_startup") or "load_on_startup" not in loaded.model_fields

    def test_markdown_format_no_load_on_startup(self, tmp_path):
        """Generated markdown should not contain load_on_startup."""
        plugin = _make_test_plugin()
        markdown = plugin.to_markdown()

        assert "load_on_startup" not in markdown
