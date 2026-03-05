"""
Unit tests for Azure DevOps adapter in GitRepositoryManager.
Tests the Azure DevOps URL detection, authentication, and repository listing functionality.
"""

import pytest
import os
import json
from unittest.mock import Mock, patch, MagicMock
import sys

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'src'))

from investigator.core.git_manager import GitRepositoryManager


class TestAzureDevOpsURLDetection:
    """Tests for Azure DevOps URL detection."""

    def test_is_azure_devops_url_detects_dev_azure_com(self):
        """Test that dev.azure.com URLs are correctly detected."""
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        url = "https://dev.azure.com/org/project/_git/repo"
        assert manager._is_azure_devops_url(url) is True

    def test_is_azure_devops_url_detects_visualstudio_com(self):
        """Test that visualstudio.com URLs are detected."""
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        urls = [
            "https://org.visualstudio.com/project/_git/repo",
            "https://myorg.visualstudio.com/DefaultCollection/_git/repo",
        ]
        for url in urls:
            assert manager._is_azure_devops_url(url) is True

    def test_is_azure_devops_url_rejects_github(self):
        """Test that GitHub URLs are not detected as Azure DevOps."""
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        url = "https://github.com/user/repo"
        assert manager._is_azure_devops_url(url) is False

    def test_is_azure_devops_url_rejects_codecommit(self):
        """Test that CodeCommit URLs are not detected as Azure DevOps."""
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        url = "https://git-codecommit.us-east-1.amazonaws.com/v1/repos/test-repo"
        assert manager._is_azure_devops_url(url) is False

    def test_is_azure_devops_url_rejects_gitlab(self):
        """Test that GitLab URLs are not detected as Azure DevOps."""
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        url = "https://gitlab.com/user/repo"
        assert manager._is_azure_devops_url(url) is False

    def test_is_azure_devops_url_rejects_bitbucket(self):
        """Test that Bitbucket URLs are not detected as Azure DevOps."""
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        url = "https://bitbucket.org/user/repo"
        assert manager._is_azure_devops_url(url) is False


class TestAzureDevOpsAuthentication:
    """Tests for Azure DevOps authentication in _add_authentication."""

    def test_add_authentication_with_azure_pat(self):
        """Test that Azure DevOps PAT is added to Azure DevOps URLs."""
        mock_logger = Mock()
        with patch.dict(os.environ, {'AZURE_DEVOPS_PAT': 'azure-pat-token'}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            url = "https://dev.azure.com/org/project/_git/repo"
            auth_url = manager._add_authentication(url)
            assert auth_url == "https://:azure-pat-token@dev.azure.com/org/project/_git/repo"
            mock_logger.debug.assert_called_with("Added Azure DevOps PAT authentication to repository URL")

    def test_add_authentication_without_azure_pat(self):
        """Test that Azure DevOps URLs without PAT are returned as-is with warning."""
        mock_logger = Mock()
        with patch.dict(os.environ, {}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            url = "https://dev.azure.com/org/project/_git/repo"
            auth_url = manager._add_authentication(url)
            assert auth_url == url
            mock_logger.warning.assert_called_with("Azure DevOps URL detected but PAT not available")

    def test_add_authentication_existing_auth_not_overridden(self):
        """Test that existing authentication in URL is not overridden."""
        mock_logger = Mock()
        with patch.dict(os.environ, {'AZURE_DEVOPS_PAT': 'azure-pat-token'}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            url = "https://user:existing-pat@dev.azure.com/org/project/_git/repo"
            auth_url = manager._add_authentication(url)
            assert auth_url == url
            mock_logger.debug.assert_called_with("Authentication already present in URL, not overriding")

    def test_add_authentication_visualstudio_url(self):
        """Test that authentication works for visualstudio.com URLs."""
        mock_logger = Mock()
        with patch.dict(os.environ, {'AZURE_DEVOPS_PAT': 'azure-pat-token'}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            url = "https://org.visualstudio.com/project/_git/repo"
            auth_url = manager._add_authentication(url)
            assert auth_url == "https://:azure-pat-token@org.visualstudio.com/project/_git/repo"


class TestAzureDevOpsPushAuthentication:
    """Tests for Azure DevOps push authentication in push_with_authentication."""

    @patch('subprocess.run')
    def test_push_with_azure_pat(self, mock_run):
        """Test that push updates remote URL with Azure DevOps PAT."""
        mock_logger = Mock()
        with patch.dict(os.environ, {'AZURE_DEVOPS_PAT': 'azure-pat-token'}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            get_url_result = Mock()
            get_url_result.returncode = 0
            get_url_result.stdout = "https://dev.azure.com/org/project/_git/repo\n"
            push_result = Mock()
            push_result.returncode = 0
            push_result.stdout = "Success"
            push_result.stderr = ""
            mock_run.side_effect = [get_url_result, Mock(), push_result]
            result = manager.push_with_authentication("/fake/repo", "main")
            assert result['status'] == 'success'
            assert any(
                call[0][0] == ["git", "remote", "set-url", "origin",
                               "https://:azure-pat-token@dev.azure.com/org/project/_git/repo"]
                for call in mock_run.call_args_list
            )


class TestAzureDevOpsRepositoryListing:
    """Tests for Azure DevOps repository listing via API."""

    @patch('urllib.request.urlopen')
    def test_list_azure_devops_repositories_success(self, mock_urlopen):
        """Test successful listing of Azure DevOps repositories."""
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'AZURE_DEVOPS_PAT': 'azure-pat-token',
            'AZURE_DEVOPS_ORG': 'my-org',
            'AZURE_DEVOPS_PROJECT': 'my-project'
        }, clear=True):
            manager = GitRepositoryManager(mock_logger)

            api_data = json.dumps({
                'value': [
                    {
                        'name': 'repo1',
                        'remoteUrl': 'https://dev.azure.com/my-org/my-project/_git/repo1',
                        'project': {'description': 'Test project'}
                    },
                    {
                        'name': 'repo2',
                        'remoteUrl': 'https://dev.azure.com/my-org/my-project/_git/repo2',
                        'project': {'description': 'Test project'}
                    }
                ]
            }).encode('utf-8')

            mock_response = MagicMock()
            mock_response.read.return_value = api_data
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = manager.list_azure_devops_repositories()

            assert result['status'] == 'success'
            assert result['count'] == 2
            assert len(result['repositories']) == 2
            repo1 = result['repositories'][0]
            assert repo1['name'] == 'repo1'
            assert repo1['clone_url_http'] == 'https://dev.azure.com/my-org/my-project/_git/repo1'
            assert repo1['description'] == 'Test project'

    def test_list_azure_devops_repositories_no_pat(self):
        """Test that listing fails gracefully without PAT."""
        mock_logger = Mock()
        with patch.dict(os.environ, {}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            result = manager.list_azure_devops_repositories()
            assert result['status'] == 'error'
            assert 'No Azure DevOps PAT' in result['message']

    def test_list_azure_devops_repositories_no_org(self):
        """Test that listing fails gracefully without organization."""
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'AZURE_DEVOPS_PAT': 'azure-pat-token'
        }, clear=True):
            manager = GitRepositoryManager(mock_logger)
            result = manager.list_azure_devops_repositories()
            assert result['status'] == 'error'
            assert 'No Azure DevOps organization' in result['message']

    def test_list_azure_devops_repositories_no_project(self):
        """Test that listing fails gracefully without project."""
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'AZURE_DEVOPS_PAT': 'azure-pat-token',
            'AZURE_DEVOPS_ORG': 'my-org'
        }, clear=True):
            manager = GitRepositoryManager(mock_logger)
            result = manager.list_azure_devops_repositories()
            assert result['status'] == 'error'
            assert 'No Azure DevOps project' in result['message']

    @patch('urllib.request.urlopen')
    def test_list_azure_devops_repositories_handles_errors(self, mock_urlopen):
        """Test that errors during repository listing are handled gracefully."""
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'AZURE_DEVOPS_PAT': 'azure-pat-token',
            'AZURE_DEVOPS_ORG': 'my-org',
            'AZURE_DEVOPS_PROJECT': 'my-project'
        }, clear=True):
            manager = GitRepositoryManager(mock_logger)
            mock_urlopen.side_effect = Exception("API Error")
            result = manager.list_azure_devops_repositories()
            assert result['status'] == 'error'
            assert 'API Error' in result['error']

    @patch('urllib.request.urlopen')
    def test_list_azure_devops_repositories_returns_correct_structure(self, mock_urlopen):
        """Test that repository listing returns correct data structure."""
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'AZURE_DEVOPS_PAT': 'azure-pat-token',
            'AZURE_DEVOPS_ORG': 'my-org',
            'AZURE_DEVOPS_PROJECT': 'my-project'
        }, clear=True):
            manager = GitRepositoryManager(mock_logger)

            api_data = json.dumps({
                'value': [
                    {
                        'name': 'test-repo',
                        'remoteUrl': 'https://dev.azure.com/my-org/my-project/_git/test-repo',
                        'project': {'description': 'Test'}
                    }
                ]
            }).encode('utf-8')

            mock_response = MagicMock()
            mock_response.read.return_value = api_data
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = manager.list_azure_devops_repositories()

            assert 'status' in result
            assert 'count' in result
            assert 'repositories' in result
            assert isinstance(result['repositories'], list)
            repo = result['repositories'][0]
            assert 'name' in repo
            assert 'clone_url_http' in repo
            assert 'description' in repo


class TestAzureDevOpsInitialization:
    """Tests for Azure DevOps credentials initialization."""

    def test_git_manager_loads_azure_devops_pat(self):
        """Test that GitRepositoryManager loads Azure DevOps PAT from environment."""
        mock_logger = Mock()
        with patch.dict(os.environ, {'AZURE_DEVOPS_PAT': 'azure-pat-token'}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            assert manager.azure_devops_pat == 'azure-pat-token'
            assert any('Azure DevOps PAT found' in str(call) for call in mock_logger.debug.call_args_list)

    def test_git_manager_handles_missing_azure_devops_pat(self):
        """Test that GitRepositoryManager handles missing Azure DevOps PAT."""
        mock_logger = Mock()
        with patch.dict(os.environ, {}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            assert manager.azure_devops_pat is None
