"""
Unit tests for GitLab adapter in GitRepositoryManager.
Tests the GitLab URL detection, authentication, and repository listing functionality.
"""

import pytest
import os
import json
from unittest.mock import Mock, patch, MagicMock
import sys

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'src'))

from investigator.core.git_manager import GitRepositoryManager


class TestGitLabURLDetection:
    """Tests for GitLab URL detection."""

    def test_is_gitlab_url_detects_gitlab_com(self):
        """Test that gitlab.com URLs are correctly detected."""
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        url = "https://gitlab.com/user/repo"
        assert manager._is_gitlab_url(url) is True

    def test_is_gitlab_url_detects_self_hosted(self):
        """Test that self-hosted GitLab URLs are detected."""
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        urls = [
            "https://gitlab.example.com/user/repo",
            "https://gitlab.mycompany.org/group/project",
        ]
        for url in urls:
            assert manager._is_gitlab_url(url) is True

    def test_is_gitlab_url_rejects_github(self):
        """Test that GitHub URLs are not detected as GitLab."""
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        url = "https://github.com/user/repo"
        assert manager._is_gitlab_url(url) is False

    def test_is_gitlab_url_rejects_codecommit(self):
        """Test that CodeCommit URLs are not detected as GitLab."""
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        url = "https://git-codecommit.us-east-1.amazonaws.com/v1/repos/test-repo"
        assert manager._is_gitlab_url(url) is False

    def test_is_gitlab_url_rejects_bitbucket(self):
        """Test that Bitbucket URLs are not detected as GitLab."""
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        url = "https://bitbucket.org/user/repo"
        assert manager._is_gitlab_url(url) is False


class TestGitLabAuthentication:
    """Tests for GitLab authentication in _add_authentication."""

    def test_add_authentication_with_gitlab_token(self):
        """Test that GitLab token is added to GitLab URLs."""
        mock_logger = Mock()
        with patch.dict(os.environ, {'GITLAB_TOKEN': 'glpat-test-token'}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            url = "https://gitlab.com/user/repo"
            auth_url = manager._add_authentication(url)
            assert auth_url == "https://oauth2:glpat-test-token@gitlab.com/user/repo"
            mock_logger.debug.assert_called_with("Added GitLab token authentication to repository URL")

    def test_add_authentication_without_gitlab_token(self):
        """Test that GitLab URLs without token are returned as-is with warning."""
        mock_logger = Mock()
        with patch.dict(os.environ, {}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            url = "https://gitlab.com/user/repo"
            auth_url = manager._add_authentication(url)
            assert auth_url == url
            mock_logger.warning.assert_called_with("GitLab URL detected but token not available")

    def test_add_authentication_existing_auth_not_overridden(self):
        """Test that existing authentication in URL is not overridden."""
        mock_logger = Mock()
        with patch.dict(os.environ, {'GITLAB_TOKEN': 'glpat-test-token'}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            url = "https://oauth2:existing-token@gitlab.com/user/repo"
            auth_url = manager._add_authentication(url)
            assert auth_url == url
            mock_logger.debug.assert_called_with("Authentication already present in URL, not overriding")

    def test_add_authentication_self_hosted_gitlab(self):
        """Test that authentication works for self-hosted GitLab."""
        mock_logger = Mock()
        with patch.dict(os.environ, {'GITLAB_TOKEN': 'glpat-test-token'}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            url = "https://gitlab.example.com/group/project"
            auth_url = manager._add_authentication(url)
            assert auth_url == "https://oauth2:glpat-test-token@gitlab.example.com/group/project"


class TestGitLabPushAuthentication:
    """Tests for GitLab push authentication in push_with_authentication."""

    @patch('subprocess.run')
    def test_push_with_gitlab_token(self, mock_run):
        """Test that push updates remote URL with GitLab token."""
        mock_logger = Mock()
        with patch.dict(os.environ, {'GITLAB_TOKEN': 'glpat-test-token'}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            get_url_result = Mock()
            get_url_result.returncode = 0
            get_url_result.stdout = "https://gitlab.com/user/repo\n"
            push_result = Mock()
            push_result.returncode = 0
            push_result.stdout = "Success"
            push_result.stderr = ""
            mock_run.side_effect = [get_url_result, Mock(), push_result]
            result = manager.push_with_authentication("/fake/repo", "main")
            assert result['status'] == 'success'
            assert any(
                call[0][0] == ["git", "remote", "set-url", "origin",
                               "https://oauth2:glpat-test-token@gitlab.com/user/repo"]
                for call in mock_run.call_args_list
            )


class TestGitLabRepositoryListing:
    """Tests for GitLab repository listing via API."""

    @patch('urllib.request.urlopen')
    def test_list_gitlab_repositories_success(self, mock_urlopen):
        """Test successful listing of GitLab repositories."""
        mock_logger = Mock()
        with patch.dict(os.environ, {'GITLAB_TOKEN': 'glpat-test-token'}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            page1_data = json.dumps([
                {
                    'path_with_namespace': 'user/repo1',
                    'name': 'repo1',
                    'http_url_to_repo': 'https://gitlab.com/user/repo1.git',
                    'description': 'Test repo 1'
                },
                {
                    'path_with_namespace': 'user/repo2',
                    'name': 'repo2',
                    'http_url_to_repo': 'https://gitlab.com/user/repo2.git',
                    'description': 'Test repo 2'
                }
            ]).encode('utf-8')
            page2_data = json.dumps([]).encode('utf-8')

            mock_response1 = MagicMock()
            mock_response1.read.return_value = page1_data
            mock_response1.__enter__ = Mock(return_value=mock_response1)
            mock_response1.__exit__ = Mock(return_value=False)

            mock_response2 = MagicMock()
            mock_response2.read.return_value = page2_data
            mock_response2.__enter__ = Mock(return_value=mock_response2)
            mock_response2.__exit__ = Mock(return_value=False)

            mock_urlopen.side_effect = [mock_response1, mock_response2]

            result = manager.list_gitlab_repositories()

            assert result['status'] == 'success'
            assert result['count'] == 2
            assert len(result['repositories']) == 2
            repo1 = result['repositories'][0]
            assert repo1['name'] == 'user/repo1'
            assert repo1['clone_url_http'] == 'https://gitlab.com/user/repo1.git'
            assert repo1['description'] == 'Test repo 1'

    def test_list_gitlab_repositories_no_token(self):
        """Test that listing fails gracefully without token."""
        mock_logger = Mock()
        with patch.dict(os.environ, {}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            result = manager.list_gitlab_repositories()
            assert result['status'] == 'error'
            assert 'No GitLab token' in result['message']

    @patch('urllib.request.urlopen')
    def test_list_gitlab_repositories_handles_errors(self, mock_urlopen):
        """Test that errors during repository listing are handled gracefully."""
        mock_logger = Mock()
        with patch.dict(os.environ, {'GITLAB_TOKEN': 'glpat-test-token'}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            mock_urlopen.side_effect = Exception("API Error")
            result = manager.list_gitlab_repositories()
            assert result['status'] == 'error'
            assert 'API Error' in result['error']

    @patch('urllib.request.urlopen')
    def test_list_gitlab_repositories_custom_base_url(self, mock_urlopen):
        """Test listing from a self-hosted GitLab instance."""
        mock_logger = Mock()
        with patch.dict(os.environ, {'GITLAB_TOKEN': 'glpat-test-token'}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            page_data = json.dumps([]).encode('utf-8')
            mock_response = MagicMock()
            mock_response.read.return_value = page_data
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response
            result = manager.list_gitlab_repositories(base_url="https://gitlab.example.com")
            assert result['status'] == 'success'
            call_args = mock_urlopen.call_args[0][0]
            assert 'gitlab.example.com' in call_args.full_url


class TestGitLabInitialization:
    """Tests for GitLab credentials initialization."""

    def test_git_manager_loads_gitlab_token(self):
        """Test that GitRepositoryManager loads GitLab token from environment."""
        mock_logger = Mock()
        with patch.dict(os.environ, {'GITLAB_TOKEN': 'glpat-test-token'}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            assert manager.gitlab_token == 'glpat-test-token'
            assert any('GitLab token found' in str(call) for call in mock_logger.debug.call_args_list)

    def test_git_manager_handles_missing_gitlab_token(self):
        """Test that GitRepositoryManager handles missing GitLab token."""
        mock_logger = Mock()
        with patch.dict(os.environ, {}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            assert manager.gitlab_token is None

    def test_git_manager_loads_all_provider_credentials(self):
        """Test that GitRepositoryManager can load credentials for all providers."""
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'GITHUB_TOKEN': 'github-token',
            'CODECOMMIT_USERNAME': 'cc-user',
            'CODECOMMIT_PASSWORD': 'cc-pass',
            'GITLAB_TOKEN': 'glpat-test-token',
            'BITBUCKET_USERNAME': 'bb-user',
            'BITBUCKET_APP_PASSWORD': 'bb-pass',
            'AZURE_DEVOPS_PAT': 'azure-pat'
        }):
            manager = GitRepositoryManager(mock_logger)
            assert manager.github_token == 'github-token'
            assert manager.codecommit_username == 'cc-user'
            assert manager.gitlab_token == 'glpat-test-token'
            assert manager.bitbucket_username == 'bb-user'
            assert manager.azure_devops_pat == 'azure-pat'
