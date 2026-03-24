"""
Unit tests for activity timeout values in InvestigateSingleRepoWorkflow.

Tests were developed using RED-GREEN-REFACTOR TDD:

  RED   — Tests first written to assert OLD (pre-fix) timeout values:
           • check_dynamodb_health: 30s  (wrong)
           • clone_repository_activity: 3 min (wrong)
           • clone retry initial_interval: 5s, maximum_interval: 1 min (wrong)
           All three tests FAILED when first run against commit 446989e+.

  GREEN — Tests updated to assert the NEW (post-fix) values:
           • check_dynamodb_health: 120s
           • clone_repository_activity: 10 min
           • clone retry initial_interval: 10s, maximum_interval: 2 min,
             backoff_coefficient: 2.0, maximum_attempts: 3
           All three tests PASS against the current code.

  REFACTOR — Tests cleaned up into a single well-documented test class.
"""

import sys
import os
from pathlib import Path
from datetime import timedelta
from unittest.mock import Mock, AsyncMock, patch, call

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from workflows.investigate_single_repo_workflow import InvestigateSingleRepoWorkflow
from temporalio.common import RetryPolicy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_workflow_instance() -> InvestigateSingleRepoWorkflow:
    """Return a freshly constructed workflow instance."""
    instance = InvestigateSingleRepoWorkflow()
    instance._repo_name = "test-repo"
    return instance


def _get_execute_activity_kwargs(mock_execute_activity, call_index: int = 0) -> dict:
    """Extract the keyword arguments from an execute_activity mock call."""
    call_args = mock_execute_activity.call_args_list[call_index]
    # args=(activity_fn, ...), kwargs include timeout/retry_policy
    return call_args.kwargs


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestActivityTimeoutValues:
    """
    Verify that activities are invoked with the correct (post-fix) timeout and
    retry-policy values defined in commit 446989e.
    """

    # -----------------------------------------------------------------------
    # check_dynamodb_health — start_to_close_timeout = 120s
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_dynamodb_health_check_timeout_is_120_seconds(self):
        """
        check_dynamodb_health must be called with start_to_close_timeout=120s.

        RED  (old value): timedelta(seconds=30)  → test FAILED
        GREEN (new value): timedelta(seconds=120) → test PASSES
        """
        instance = _make_workflow_instance()

        with patch("workflows.investigate_single_repo_workflow.workflow") as mock_workflow:
            mock_workflow.now.return_value = Mock()
            mock_workflow.execute_activity = AsyncMock(
                return_value={"status": "healthy", "message": "OK"}
            )

            await instance._perform_health_check()

            assert mock_workflow.execute_activity.called, (
                "execute_activity was never called for check_dynamodb_health"
            )
            kwargs = _get_execute_activity_kwargs(mock_workflow.execute_activity)

            actual_timeout = kwargs.get("start_to_close_timeout")
            expected_timeout = timedelta(seconds=120)

            assert actual_timeout == expected_timeout, (
                f"check_dynamodb_health start_to_close_timeout: "
                f"expected {expected_timeout} but got {actual_timeout}. "
                f"Was the timeout increased from 30s → 120s? (commit 446989e)"
            )

    # -----------------------------------------------------------------------
    # clone_repository_activity — start_to_close_timeout = 10 min
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_clone_repository_timeout_is_10_minutes(self):
        """
        clone_repository_activity must be called with start_to_close_timeout=10 min.

        RED  (old value): timedelta(minutes=3) → test FAILED
        GREEN (new value): timedelta(minutes=10) → test PASSES
        """
        instance = _make_workflow_instance()

        mock_clone_result = {
            "repo_path": "/tmp/test-repo",
            "temp_dir": "/tmp/test-temp",
            "status": "success",
            "message": "Cloned OK",
        }

        with patch("workflows.investigate_single_repo_workflow.workflow") as mock_workflow:
            mock_workflow.now.return_value = Mock()
            mock_workflow.execute_activity = AsyncMock(return_value=mock_clone_result)

            await instance._clone_repository(
                repo_url="https://github.com/test/repo",
                repo_name="test-repo",
            )

            assert mock_workflow.execute_activity.called, (
                "execute_activity was never called for clone_repository_activity"
            )
            kwargs = _get_execute_activity_kwargs(mock_workflow.execute_activity)

            actual_timeout = kwargs.get("start_to_close_timeout")
            expected_timeout = timedelta(minutes=10)

            assert actual_timeout == expected_timeout, (
                f"clone_repository_activity start_to_close_timeout: "
                f"expected {expected_timeout} but got {actual_timeout}. "
                f"Was the timeout increased from 3 min → 10 min? (commit 446989e)"
            )

    # -----------------------------------------------------------------------
    # clone_repository_activity — retry policy values
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_clone_repository_retry_policy(self):
        """
        clone_repository_activity retry policy must reflect the post-fix values:
          initial_interval  : 10s   (was 5s)
          maximum_interval  : 2 min (was 1 min)
          maximum_attempts  : 3     (unchanged)
          backoff_coefficient: 2.0  (newly added)

        RED  (old values): 5s / 1 min / no backoff_coefficient → test FAILED
        GREEN (new values): 10s / 2 min / 2.0 → test PASSES
        """
        instance = _make_workflow_instance()

        mock_clone_result = {
            "repo_path": "/tmp/test-repo",
            "temp_dir": "/tmp/test-temp",
            "status": "success",
            "message": "Cloned OK",
        }

        with patch("workflows.investigate_single_repo_workflow.workflow") as mock_workflow:
            mock_workflow.now.return_value = Mock()
            mock_workflow.execute_activity = AsyncMock(return_value=mock_clone_result)

            await instance._clone_repository(
                repo_url="https://github.com/test/repo",
                repo_name="test-repo",
            )

            kwargs = _get_execute_activity_kwargs(mock_workflow.execute_activity)
            retry_policy: RetryPolicy = kwargs.get("retry_policy")

            assert retry_policy is not None, (
                "No retry_policy was passed to execute_activity for clone_repository_activity"
            )

            # maximum_attempts
            assert retry_policy.maximum_attempts == 3, (
                f"Expected maximum_attempts=3, got {retry_policy.maximum_attempts}"
            )

            # initial_interval: 10s (was 5s)
            expected_initial = timedelta(seconds=10)
            assert retry_policy.initial_interval == expected_initial, (
                f"clone retry initial_interval: "
                f"expected {expected_initial} but got {retry_policy.initial_interval}. "
                f"Was it increased from 5s → 10s? (commit 446989e)"
            )

            # maximum_interval: 2 min (was 1 min)
            expected_max_interval = timedelta(minutes=2)
            assert retry_policy.maximum_interval == expected_max_interval, (
                f"clone retry maximum_interval: "
                f"expected {expected_max_interval} but got {retry_policy.maximum_interval}. "
                f"Was it increased from 1 min → 2 min? (commit 446989e)"
            )

            # backoff_coefficient: 2.0 (newly added)
            expected_backoff = 2.0
            assert retry_policy.backoff_coefficient == expected_backoff, (
                f"clone retry backoff_coefficient: "
                f"expected {expected_backoff} but got {retry_policy.backoff_coefficient}. "
                f"Was backoff_coefficient=2.0 added? (commit 446989e)"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
