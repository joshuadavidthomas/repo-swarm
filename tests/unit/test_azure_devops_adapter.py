"""
Unit tests for Azure DevOps adapter in GitRepositoryManager.
Tests Azure DevOps URL detection, credential helper, and repository listing.
"""

import pytest
import os
from unittest.mock import Mock, patch
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'src'))

from investigator.core.git_manager import GitRepositoryManager


class TestAzureDevOpsURLDetection:
    """Tests for Azure DevOps URL detection."""

    def test_detects_dev_azure_com_url(self):
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        assert manager._is_azure_devops_url("https://dev.azure.com/org/project/_git/repo") is True

    def test_detects_visualstudio_url(self):
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        assert manager._is_azure_devops_url("https://org.visualstudio.com/project/_git/repo") is True

    def test_rejects_github_url(self):
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        assert manager._is_azure_devops_url("https://github.com/user/repo") is False


class TestAzureDevOpsCredentialHelper:
    """Tests for Azure DevOps credential helper (replaces _add_authentication)."""

    def test_get_credentials_with_azure_pat(self):
        mock_logger = Mock()
        with patch.dict(os.environ, {'AZURE_DEVOPS_PAT': 'my-pat-token'}):
            manager = GitRepositoryManager(mock_logger)
            url = "https://dev.azure.com/org/project/_git/repo"
            creds = manager._get_credentials_for_url(url)
            assert creds == ('', 'my-pat-token')

    def test_get_credentials_without_azure_pat(self):
        mock_logger = Mock()
        with patch.dict(os.environ, {}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            url = "https://dev.azure.com/org/project/_git/repo"
            creds = manager._get_credentials_for_url(url)
            assert creds is None

    def test_write_credential_store_for_azure(self):
        mock_logger = Mock()
        with patch.dict(os.environ, {'AZURE_DEVOPS_PAT': 'my-pat-token'}):
            manager = GitRepositoryManager(mock_logger)
            url = "https://dev.azure.com/org/project/_git/repo"
            cred_path = manager._write_credential_store(url)
            try:
                assert cred_path is not None
                with open(cred_path) as f:
                    content = f.read()
                assert 'my-pat-token' in content
                assert 'dev.azure.com' in content
            finally:
                if cred_path and os.path.exists(cred_path):
                    os.remove(cred_path)

    def test_get_credentials_visualstudio_url(self):
        mock_logger = Mock()
        with patch.dict(os.environ, {'AZURE_DEVOPS_PAT': 'my-pat-token'}):
            manager = GitRepositoryManager(mock_logger)
            url = "https://org.visualstudio.com/project/_git/repo"
            creds = manager._get_credentials_for_url(url)
            assert creds == ('', 'my-pat-token')


class TestAzureDevOpsRepositoryListing:
    """Tests for Azure DevOps repository listing."""

    def test_list_repos_missing_pat(self):
        mock_logger = Mock()
        with patch.dict(os.environ, {}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            result = manager.list_azure_devops_repositories()
            assert result['status'] == 'error'

    def test_list_repos_missing_org(self):
        mock_logger = Mock()
        with patch.dict(os.environ, {'AZURE_DEVOPS_PAT': 'token'}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            result = manager.list_azure_devops_repositories()
            assert result['status'] == 'error'
            assert 'organization' in result['message'].lower()
