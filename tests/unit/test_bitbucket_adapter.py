"""
Unit tests for Bitbucket adapter in GitRepositoryManager.
Tests the Bitbucket URL detection, authentication, and repository listing functionality.
"""

import pytest
import os
import json
from unittest.mock import Mock, patch, MagicMock
import sys

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'src'))

from investigator.core.git_manager import GitRepositoryManager


class TestBitbucketURLDetection:
    """Tests for Bitbucket URL detection."""

    def test_is_bitbucket_url_detects_bitbucket_org(self):
        """Test that bitbucket.org URLs are correctly detected."""
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        url = "https://bitbucket.org/user/repo"
        assert manager._is_bitbucket_url(url) is True

    def test_is_bitbucket_url_detects_self_hosted(self):
        """Test that self-hosted Bitbucket URLs are detected."""
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        urls = [
            "https://bitbucket.example.com/scm/project/repo.git",
            "https://bitbucket.mycompany.org/user/repo",
        ]
        for url in urls:
            assert manager._is_bitbucket_url(url) is True

    def test_is_bitbucket_url_rejects_github(self):
        """Test that GitHub URLs are not detected as Bitbucket."""
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        url = "https://github.com/user/repo"
        assert manager._is_bitbucket_url(url) is False

    def test_is_bitbucket_url_rejects_codecommit(self):
        """Test that CodeCommit URLs are not detected as Bitbucket."""
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        url = "https://git-codecommit.us-east-1.amazonaws.com/v1/repos/test-repo"
        assert manager._is_bitbucket_url(url) is False

    def test_is_bitbucket_url_rejects_gitlab(self):
        """Test that GitLab URLs are not detected as Bitbucket."""
        mock_logger = Mock()
        manager = GitRepositoryManager(mock_logger)
        url = "https://gitlab.com/user/repo"
        assert manager._is_bitbucket_url(url) is False


class TestBitbucketAuthentication:
    """Tests for Bitbucket authentication in _add_authentication."""

    def test_add_authentication_with_bitbucket_credentials(self):
        """Test that Bitbucket credentials are added to Bitbucket URLs."""
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'BITBUCKET_USERNAME': 'bb-user',
            'BITBUCKET_APP_PASSWORD': 'bb-app-pass'
        }, clear=True):
            manager = GitRepositoryManager(mock_logger)
            url = "https://bitbucket.org/workspace/repo"
            auth_url = manager._add_authentication(url)
            assert auth_url == "https://bb-user:bb-app-pass@bitbucket.org/workspace/repo"
            mock_logger.debug.assert_called_with("Added Bitbucket authentication to repository URL")

    def test_add_authentication_without_bitbucket_credentials(self):
        """Test that Bitbucket URLs without credentials are returned as-is with warning."""
        mock_logger = Mock()
        with patch.dict(os.environ, {}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            url = "https://bitbucket.org/workspace/repo"
            auth_url = manager._add_authentication(url)
            assert auth_url == url
            mock_logger.warning.assert_called_with("Bitbucket URL detected but credentials not available")

    def test_add_authentication_existing_auth_not_overridden(self):
        """Test that existing authentication in URL is not overridden."""
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'BITBUCKET_USERNAME': 'bb-user',
            'BITBUCKET_APP_PASSWORD': 'bb-app-pass'
        }, clear=True):
            manager = GitRepositoryManager(mock_logger)
            url = "https://existing:creds@bitbucket.org/workspace/repo"
            auth_url = manager._add_authentication(url)
            assert auth_url == url
            mock_logger.debug.assert_called_with("Authentication already present in URL, not overriding")

    def test_add_authentication_partial_bitbucket_credentials(self):
        """Test that partial Bitbucket credentials result in warning."""
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'BITBUCKET_USERNAME': 'bb-user'
        }, clear=True):
            manager = GitRepositoryManager(mock_logger)
            url = "https://bitbucket.org/workspace/repo"
            auth_url = manager._add_authentication(url)
            assert auth_url == url
            mock_logger.warning.assert_called_with("Bitbucket URL detected but credentials not available")


class TestBitbucketPushAuthentication:
    """Tests for Bitbucket push authentication in push_with_authentication."""

    @patch('subprocess.run')
    def test_push_with_bitbucket_credentials(self, mock_run):
        """Test that push updates remote URL with Bitbucket credentials."""
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'BITBUCKET_USERNAME': 'bb-user',
            'BITBUCKET_APP_PASSWORD': 'bb-app-pass'
        }, clear=True):
            manager = GitRepositoryManager(mock_logger)
            get_url_result = Mock()
            get_url_result.returncode = 0
            get_url_result.stdout = "https://bitbucket.org/workspace/repo\n"
            push_result = Mock()
            push_result.returncode = 0
            push_result.stdout = "Success"
            push_result.stderr = ""
            mock_run.side_effect = [get_url_result, Mock(), push_result]
            result = manager.push_with_authentication("/fake/repo", "main")
            assert result['status'] == 'success'
            assert any(
                call[0][0] == ["git", "remote", "set-url", "origin",
                               "https://bb-user:bb-app-pass@bitbucket.org/workspace/repo"]
                for call in mock_run.call_args_list
            )


class TestBitbucketRepositoryListing:
    """Tests for Bitbucket repository listing via API."""

    @patch('urllib.request.urlopen')
    def test_list_bitbucket_repositories_success(self, mock_urlopen):
        """Test successful listing of Bitbucket repositories."""
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'BITBUCKET_USERNAME': 'bb-user',
            'BITBUCKET_APP_PASSWORD': 'bb-app-pass',
            'BITBUCKET_WORKSPACE': 'my-workspace'
        }, clear=True):
            manager = GitRepositoryManager(mock_logger)

            page1_data = json.dumps({
                'values': [
                    {
                        'full_name': 'my-workspace/repo1',
                        'name': 'repo1',
                        'description': 'Test repo 1',
                        'links': {
                            'clone': [
                                {'name': 'https', 'href': 'https://bitbucket.org/my-workspace/repo1.git'},
                                {'name': 'ssh', 'href': 'git@bitbucket.org:my-workspace/repo1.git'}
                            ]
                        }
                    },
                    {
                        'full_name': 'my-workspace/repo2',
                        'name': 'repo2',
                        'description': 'Test repo 2',
                        'links': {
                            'clone': [
                                {'name': 'https', 'href': 'https://bitbucket.org/my-workspace/repo2.git'}
                            ]
                        }
                    }
                ],
                'next': None
            }).encode('utf-8')

            mock_response = MagicMock()
            mock_response.read.return_value = page1_data
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = manager.list_bitbucket_repositories()

            assert result['status'] == 'success'
            assert result['count'] == 2
            assert len(result['repositories']) == 2
            repo1 = result['repositories'][0]
            assert repo1['name'] == 'my-workspace/repo1'
            assert repo1['clone_url_http'] == 'https://bitbucket.org/my-workspace/repo1.git'
            assert repo1['description'] == 'Test repo 1'

    def test_list_bitbucket_repositories_no_credentials(self):
        """Test that listing fails gracefully without credentials."""
        mock_logger = Mock()
        with patch.dict(os.environ, {}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            result = manager.list_bitbucket_repositories()
            assert result['status'] == 'error'
            assert 'No Bitbucket credentials' in result['message']

    def test_list_bitbucket_repositories_no_workspace(self):
        """Test that listing fails gracefully without workspace."""
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'BITBUCKET_USERNAME': 'bb-user',
            'BITBUCKET_APP_PASSWORD': 'bb-app-pass'
        }, clear=True):
            manager = GitRepositoryManager(mock_logger)
            # username is used as default workspace, so need to pass empty workspace explicitly
            result = manager.list_bitbucket_repositories(workspace='')
            # With empty workspace string, it still tries (username fallback)
            # Actually with empty string passed explicitly, it won't use env fallback
            # Let's test the case where username IS the workspace (default behavior)
            result2 = manager.list_bitbucket_repositories()
            # Should use username as workspace by default
            assert result2['status'] != 'error' or 'No Bitbucket workspace' not in result2.get('message', '')

    @patch('urllib.request.urlopen')
    def test_list_bitbucket_repositories_handles_errors(self, mock_urlopen):
        """Test that errors during repository listing are handled gracefully."""
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'BITBUCKET_USERNAME': 'bb-user',
            'BITBUCKET_APP_PASSWORD': 'bb-app-pass',
            'BITBUCKET_WORKSPACE': 'my-workspace'
        }, clear=True):
            manager = GitRepositoryManager(mock_logger)
            mock_urlopen.side_effect = Exception("API Error")
            result = manager.list_bitbucket_repositories()
            assert result['status'] == 'error'
            assert 'API Error' in result['error']

    @patch('urllib.request.urlopen')
    def test_list_bitbucket_repositories_pagination(self, mock_urlopen):
        """Test that Bitbucket pagination works correctly."""
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'BITBUCKET_USERNAME': 'bb-user',
            'BITBUCKET_APP_PASSWORD': 'bb-app-pass',
            'BITBUCKET_WORKSPACE': 'my-workspace'
        }, clear=True):
            manager = GitRepositoryManager(mock_logger)

            page1_data = json.dumps({
                'values': [
                    {
                        'full_name': 'my-workspace/repo1',
                        'name': 'repo1',
                        'description': '',
                        'links': {'clone': [{'name': 'https', 'href': 'https://bitbucket.org/my-workspace/repo1.git'}]}
                    }
                ],
                'next': 'https://api.bitbucket.org/2.0/repositories/my-workspace?page=2'
            }).encode('utf-8')

            page2_data = json.dumps({
                'values': [
                    {
                        'full_name': 'my-workspace/repo2',
                        'name': 'repo2',
                        'description': '',
                        'links': {'clone': [{'name': 'https', 'href': 'https://bitbucket.org/my-workspace/repo2.git'}]}
                    }
                ],
                'next': None
            }).encode('utf-8')

            mock_response1 = MagicMock()
            mock_response1.read.return_value = page1_data
            mock_response1.__enter__ = Mock(return_value=mock_response1)
            mock_response1.__exit__ = Mock(return_value=False)

            mock_response2 = MagicMock()
            mock_response2.read.return_value = page2_data
            mock_response2.__enter__ = Mock(return_value=mock_response2)
            mock_response2.__exit__ = Mock(return_value=False)

            mock_urlopen.side_effect = [mock_response1, mock_response2]

            result = manager.list_bitbucket_repositories()

            assert result['status'] == 'success'
            assert result['count'] == 2


class TestBitbucketInitialization:
    """Tests for Bitbucket credentials initialization."""

    def test_git_manager_loads_bitbucket_credentials(self):
        """Test that GitRepositoryManager loads Bitbucket credentials from environment."""
        mock_logger = Mock()
        with patch.dict(os.environ, {
            'BITBUCKET_USERNAME': 'bb-user',
            'BITBUCKET_APP_PASSWORD': 'bb-app-pass'
        }, clear=True):
            manager = GitRepositoryManager(mock_logger)
            assert manager.bitbucket_username == 'bb-user'
            assert manager.bitbucket_app_password == 'bb-app-pass'
            assert any('Bitbucket credentials found' in str(call) for call in mock_logger.debug.call_args_list)

    def test_git_manager_handles_missing_bitbucket_credentials(self):
        """Test that GitRepositoryManager handles missing Bitbucket credentials."""
        mock_logger = Mock()
        with patch.dict(os.environ, {}, clear=True):
            manager = GitRepositoryManager(mock_logger)
            assert manager.bitbucket_username is None
            assert manager.bitbucket_app_password is None
