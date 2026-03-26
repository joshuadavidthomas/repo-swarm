"""
Unit tests for GitLab adapter in GitRepositoryManager.
Tests GitLab URL detection, credential helper, and repository listing.
"""

import pytest
import os
from unittest.mock import Mock, patch
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'src'))

from investigator.core.git_manager import GitRepositoryManager


class TestGitLabURLDetection:
    """Tests for GitLab URL detection."""

    def test_detects_gitlab_com(self):
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        assert manager._is_gitlab_url("https://gitlab.com/user/repo") is True

    def test_detects_self_hosted_gitlab(self):
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        assert manager._is_gitlab_url("https://gitlab.company.com/group/repo") is True

    def test_rejects_github(self):
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        assert manager._is_gitlab_url("https://github.com/user/repo") is False


class TestGitLabCredentialHelper:
    """Tests for GitLab credential helper (replaces _add_authentication)."""

    def test_get_credentials_with_gitlab_token(self):
        mock_logger = Mock()
        with patch.dict(os.environ, {'GITLAB_TOKEN': 'glpat-abc123'}):
            manager = GitRepositoryManager(mock_logger)
            url = "https://gitlab.com/user/repo"
            creds = manager._get_credentials_for_url(url)
            assert creds == ('oauth2', 'glpat-abc123')

    def test_get_credentials_without_gitlab_token(self):
        mock_logger = Mock()
        with patch.dict(os.environ, {}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            url = "https://gitlab.com/user/repo"
            creds = manager._get_credentials_for_url(url)
            assert creds is None

    def test_write_credential_store_for_gitlab(self):
        mock_logger = Mock()
        with patch.dict(os.environ, {'GITLAB_TOKEN': 'glpat-abc123'}):
            manager = GitRepositoryManager(mock_logger)
            url = "https://gitlab.com/user/repo"
            cred_path = manager._write_credential_store(url)
            try:
                assert cred_path is not None
                with open(cred_path) as f:
                    content = f.read()
                assert 'oauth2' in content
                assert 'glpat-abc123' in content
                assert 'gitlab.com' in content
            finally:
                if cred_path and os.path.exists(cred_path):
                    os.remove(cred_path)

    def test_get_credentials_self_hosted_gitlab(self):
        mock_logger = Mock()
        with patch.dict(os.environ, {'GITLAB_TOKEN': 'glpat-abc123'}):
            manager = GitRepositoryManager(mock_logger)
            url = "https://gitlab.company.com/group/repo"
            creds = manager._get_credentials_for_url(url)
            assert creds == ('oauth2', 'glpat-abc123')


class TestGitLabRepositoryListing:
    """Tests for GitLab repository listing."""

    def test_list_repos_missing_token(self):
        mock_logger = Mock()
        with patch.dict(os.environ, {}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            result = manager.list_gitlab_repositories()
            assert result['status'] == 'error'
