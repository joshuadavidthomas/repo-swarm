"""
Unit tests for workflow progress tracking in InvestigateSingleRepoWorkflow.
Tests that progress queries return correct step information.
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import timedelta

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'src'))

from workflows.investigate_single_repo_workflow import InvestigateSingleRepoWorkflow


class TestWorkflowProgressTracking:
    """Tests for workflow progress tracking and queries."""

    def test_workflow_initialization_sets_progress_to_zero(self):
        """Test that workflow initializes with step 0."""
        workflow_instance = InvestigateSingleRepoWorkflow()

        assert workflow_instance._current_step == 0
        assert workflow_instance._total_steps == 8
        assert workflow_instance._step_name == "initialized"
        assert workflow_instance._status == "initialized"

    def test_get_progress_query_returns_correct_structure(self):
        """Test that get_progress query returns all required fields."""
        workflow_instance = InvestigateSingleRepoWorkflow()
        workflow_instance._repo_name = "test-repo"
        workflow_instance._current_step = 3
        workflow_instance._step_name = "checking_cache"
        workflow_instance._status = "checking_cache"

        progress = workflow_instance.get_progress()

        assert progress["current_step"] == 3
        assert progress["total_steps"] == 8
        assert progress["step_name"] == "checking_cache"
        assert progress["status"] == "checking_cache"
        assert progress["repo_name"] == "test-repo"

    def test_get_status_query_returns_current_status(self):
        """Test that get_status query returns current status string."""
        workflow_instance = InvestigateSingleRepoWorkflow()
        workflow_instance._status = "analyzing"

        status = workflow_instance.get_status()

        assert status == "analyzing"

    def test_progress_starts_at_zero(self):
        """Test that progress counter starts at 0."""
        workflow_instance = InvestigateSingleRepoWorkflow()
        progress = workflow_instance.get_progress()

        assert progress["current_step"] == 0
        assert progress["total_steps"] == 8

    def test_workflow_has_8_total_steps(self):
        """Test that total_steps is set to 8 as documented."""
        workflow_instance = InvestigateSingleRepoWorkflow()

        assert workflow_instance._total_steps == 8

    @pytest.mark.asyncio
    async def test_health_check_updates_progress_to_step_1(self):
        """Test that health check step updates progress to 1."""
        workflow_instance = InvestigateSingleRepoWorkflow()

        with patch('workflows.investigate_single_repo_workflow.workflow') as mock_workflow:
            mock_workflow.now.return_value = Mock()
            mock_workflow.execute_activity = AsyncMock(return_value={"status": "healthy", "message": "OK"})

            await workflow_instance._perform_health_check()

            assert workflow_instance._current_step == 1
            assert workflow_instance._step_name == "health_check"
            assert workflow_instance._status == "health_check"

    @pytest.mark.asyncio
    async def test_clone_repository_updates_progress_to_step_2(self):
        """Test that clone repository step updates progress to 2."""
        workflow_instance = InvestigateSingleRepoWorkflow()

        with patch('workflows.investigate_single_repo_workflow.workflow') as mock_workflow:
            mock_workflow.now.return_value = Mock()
            mock_workflow.execute_activity = AsyncMock(return_value={
                "repo_path": "/tmp/test",
                "temp_dir": "/tmp",
                "status": "success"
            })

            await workflow_instance._clone_repository("https://github.com/test/repo", "test-repo")

            assert workflow_instance._current_step == 2
            assert workflow_instance._step_name == "cloning"
            assert workflow_instance._status == "cloning"

    @pytest.mark.asyncio
    async def test_analyze_structure_updates_progress_to_step_4(self):
        """Test that analyze structure step updates progress to 4."""
        workflow_instance = InvestigateSingleRepoWorkflow()

        with patch('workflows.investigate_single_repo_workflow.workflow') as mock_workflow:
            mock_workflow.now.return_value = Mock()
            mock_workflow.execute_activity = AsyncMock(return_value={
                "repo_structure": {"files": []},
                "status": "success"
            })

            await workflow_instance._analyze_repository_structure("/tmp/test")

            assert workflow_instance._current_step == 4
            assert workflow_instance._step_name == "analyzing_structure"
            assert workflow_instance._status == "analyzing_structure"

    @pytest.mark.asyncio
    async def test_get_prompts_config_updates_progress_to_step_5(self):
        """Test that get prompts config step updates progress to 5."""
        workflow_instance = InvestigateSingleRepoWorkflow()

        with patch('workflows.investigate_single_repo_workflow.workflow') as mock_workflow:
            mock_workflow.now.return_value = Mock()
            mock_workflow.execute_activity = AsyncMock(return_value={
                "prompts_dir": "/prompts",
                "processing_order": [],
                "prompt_versions": {},
                "status": "success"
            })

            await workflow_instance._get_prompts_config("/tmp/test", "generic", "https://test.com")

            assert workflow_instance._current_step == 5
            assert workflow_instance._step_name == "getting_prompts"
            assert workflow_instance._status == "getting_prompts"

    @pytest.mark.asyncio
    async def test_read_dependencies_updates_progress_to_step_6(self):
        """Test that read dependencies step updates progress to 6."""
        workflow_instance = InvestigateSingleRepoWorkflow()
        workflow_instance._repo_name = "test-repo"

        with patch('workflows.investigate_single_repo_workflow.workflow') as mock_workflow:
            mock_workflow.now.return_value = Mock()
            mock_workflow.execute_activity = AsyncMock(return_value={
                "status": "success",
                "raw_dependencies": {},
                "formatted_content": "deps",
                "message": "OK"
            })

            await workflow_instance._read_and_cache_dependencies("/tmp/test")

            assert workflow_instance._current_step == 6
            assert workflow_instance._step_name == "reading_dependencies"
            assert workflow_instance._status == "reading_dependencies"

    @pytest.mark.asyncio
    async def test_write_results_updates_progress_to_step_8(self):
        """Test that write results step updates progress to 8."""
        workflow_instance = InvestigateSingleRepoWorkflow()

        with patch('workflows.investigate_single_repo_workflow.workflow') as mock_workflow:
            mock_workflow.now.return_value = Mock()
            mock_workflow.execute_activity = AsyncMock(return_value={
                "arch_file_path": "/tmp/arch.md",
                "status": "success"
            })

            await workflow_instance._write_analysis_results("/tmp", "/tmp/test", "analysis")

            assert workflow_instance._current_step == 8
            assert workflow_instance._step_name == "writing_results"
            assert workflow_instance._status == "writing_results"

    def test_progress_query_can_be_called_multiple_times(self):
        """Test that progress query is idempotent."""
        workflow_instance = InvestigateSingleRepoWorkflow()
        workflow_instance._current_step = 5
        workflow_instance._step_name = "getting_prompts"

        progress1 = workflow_instance.get_progress()
        progress2 = workflow_instance.get_progress()

        assert progress1 == progress2
        assert progress1["current_step"] == 5
