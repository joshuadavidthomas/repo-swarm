"""
Unit tests for Bitbucket adapter in GitRepositoryManager.
Tests Bitbucket URL detection, credential helper, and repository listing.
"""

import pytest
import os
from unittest.mock import Mock, patch
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'src'))

from investigator.core.git_manager import GitRepositoryManager


class TestBitbucketURLDetection:
    """Tests for Bitbucket URL detection."""

    def test_detects_bitbucket_org(self):
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        assert manager._is_bitbucket_url("https://bitbucket.org/user/repo") is True

    def test_detects_self_hosted_bitbucket(self):
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        assert manager._is_bitbucket_url("https://bitbucket.company.com/scm/proj/repo.git") is True

    def test_rejects_github(self):
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        assert manager._is_bitbucket_url("https://github.com/user/repo") is False


class TestBitbucketCredentialHelper:
    """Tests for Bitbucket credential helper (replaces _add_authentication)."""

    def test_get_credentials_with_bitbucket_credentials(self):
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'BITBUCKET_USERNAME': 'bb-user',
            'BITBUCKET_APP_PASSWORD': 'bb-app-pass'
        }):
            manager = GitRepositoryManager(mock_logger)
            url = "https://bitbucket.org/user/repo"
            creds = manager._get_credentials_for_url(url)
            assert creds == ('bb-user', 'bb-app-pass')

    def test_get_credentials_without_bitbucket_credentials(self):
        mock_logger = Mock()
        with patch.dict(os.environ, {}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            url = "https://bitbucket.org/user/repo"
            creds = manager._get_credentials_for_url(url)
            assert creds is None

    def test_write_credential_store_for_bitbucket(self):
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'BITBUCKET_USERNAME': 'bb-user',
            'BITBUCKET_APP_PASSWORD': 'bb-app-pass'
        }):
            manager = GitRepositoryManager(mock_logger)
            url = "https://bitbucket.org/user/repo"
            cred_path = manager._write_credential_store(url)
            try:
                assert cred_path is not None
                with open(cred_path) as f:
                    content = f.read()
                assert 'bb-user' in content
                assert 'bb-app-pass' in content
                assert 'bitbucket.org' in content
            finally:
                if cred_path and os.path.exists(cred_path):
                    os.remove(cred_path)

    def test_get_credentials_partial_bitbucket_credentials(self):
        """Only username without app password should return None."""
        mock_logger = Mock()
        with patch.dict(os.environ, {'BITBUCKET_USERNAME': 'bb-user'}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            url = "https://bitbucket.org/user/repo"
            creds = manager._get_credentials_for_url(url)
            assert creds is None


class TestBitbucketRepositoryListing:
    """Tests for Bitbucket repository listing."""

    def test_list_repos_missing_credentials(self):
        mock_logger = Mock()
        with patch.dict(os.environ, {}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            result = manager.list_bitbucket_repositories()
            assert result['status'] == 'error'
