"""
Git repository management for the Claude Investigator.
"""

import os
import shutil
import subprocess
import tempfile
from urllib.parse import urlparse, urlunparse, quote
from .utils import Utils


class GitRepositoryManager:
    """Handles Git repository operations."""

    def __init__(self, logger):
        self.logger = logger
        self.github_token = os.getenv('GITHUB_TOKEN')
        self.codecommit_username = os.getenv('CODECOMMIT_USERNAME')
        self.codecommit_password = os.getenv('CODECOMMIT_PASSWORD')

        self.gitlab_token = os.getenv('GITLAB_TOKEN')
        self.bitbucket_username = os.getenv('BITBUCKET_USERNAME')
        self.bitbucket_app_password = os.getenv('BITBUCKET_APP_PASSWORD')
        self.azure_devops_pat = os.getenv('AZURE_DEVOPS_PAT')

        if self.github_token:
            self.logger.debug("GitHub token found in environment")
        if self.codecommit_username and self.codecommit_password:
            self.logger.debug("CodeCommit credentials found in environment")
        if self.gitlab_token:
            self.logger.debug("GitLab token found in environment")
        if self.bitbucket_username and self.bitbucket_app_password:
            self.logger.debug("Bitbucket credentials found in environment")
        if self.azure_devops_pat:
            self.logger.debug("Azure DevOps PAT found in environment")
    
    def _is_codecommit_url(self, url: str) -> bool:
        """
        Check if a URL is a CodeCommit repository URL.

        Args:
            url: Repository URL to check

        Returns:
            True if URL is a CodeCommit URL, False otherwise
        """
        return 'git-codecommit' in url and 'amazonaws.com' in url

    def _is_gitlab_url(self, url: str) -> bool:
        """
        Check if a URL is a GitLab repository URL.

        Args:
            url: Repository URL to check

        Returns:
            True if URL is a GitLab URL, False otherwise
        """
        parsed = urlparse(url)
        hostname = parsed.hostname or ''
        return 'gitlab.com' in url or 'gitlab.' in hostname

    def _is_bitbucket_url(self, url: str) -> bool:
        """
        Check if a URL is a Bitbucket repository URL.

        Args:
            url: Repository URL to check

        Returns:
            True if URL is a Bitbucket URL, False otherwise
        """
        parsed = urlparse(url)
        hostname = parsed.hostname or ''
        return 'bitbucket.org' in url or 'bitbucket.' in hostname

    def _is_azure_devops_url(self, url: str) -> bool:
        """
        Check if a URL is an Azure DevOps repository URL.

        Args:
            url: Repository URL to check

        Returns:
            True if URL is an Azure DevOps URL, False otherwise
        """
        return 'dev.azure.com' in url or 'visualstudio.com' in url

    def _sanitize_url_for_logging(self, url: str) -> str:
        """
        Remove sensitive information from URLs for safe logging.
        
        Args:
            url: URL that may contain authentication tokens or passwords
            
        Returns:
            Sanitized URL safe for logging
        """
        # If it's not a URL, return as is
        if not url or not url.startswith(('http://', 'https://')):
            return url
        
        parsed = urlparse(url)
        
        # Remove authentication info from the URL
        if parsed.username or parsed.password:
            # Reconstruct URL without auth
            sanitized_netloc = parsed.hostname or ''
            if parsed.port:
                sanitized_netloc += f":{parsed.port}"
            
            sanitized_url = urlunparse((
                parsed.scheme,
                sanitized_netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment
            ))
            
            # Add indication that auth was present
            return f"{sanitized_url} (authentication hidden)"
        
        # Check if token is embedded in the URL string (e.g., after @)
        if self.github_token and self.github_token in url:
            return url.replace(self.github_token, '***HIDDEN***')
        
        return url
    

    def _strip_credentials_from_remote(self, repo_dir: str) -> None:
        """
        Remove embedded credentials from the git remote URL in .git/config.
        
        After clone/update, credentials may persist in the remote URL.
        This strips them to prevent credential leakage via .git/config.
        """
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=repo_dir, capture_output=True, text=True
            )
            if result.returncode != 0:
                return
            
            current_url = result.stdout.strip()
            parsed = urlparse(current_url)
            
            if parsed.username or parsed.password:
                clean_netloc = parsed.hostname or ''
                if parsed.port:
                    clean_netloc += f":{parsed.port}"
                clean_url = urlunparse((
                    parsed.scheme, clean_netloc, parsed.path,
                    parsed.params, parsed.query, parsed.fragment
                ))
                subprocess.run(
                    ["git", "remote", "set-url", "origin", clean_url],
                    cwd=repo_dir, check=True
                )
                self.logger.debug("Stripped credentials from git remote URL")
        except Exception as e:
            self.logger.debug(f"Could not strip credentials from remote: {e}")

    def clone_or_update(self, repo_location: str, target_dir: str) -> str:
        """
        Clone a repository or update it if it already exists.
        
        Uses git credential helper to inject authentication — credentials
        are never embedded in URLs, preventing leakage in logs, error
        messages, process listings, and workflow history.
        
        Args:
            repo_location: URL or path to the repository
            target_dir: Directory to clone/update the repository
            
        Returns:
            Path to the repository
        """
        # Set up credential helper (creds stay out of URLs)
        cred_path = None
        if repo_location.startswith(('http://', 'https://')):
            cred_path = self._write_credential_store(repo_location)
            if cred_path:
                self._configure_git_credential_helper(cred_path)

        try:
            if self._is_existing_repo(target_dir):
                result = self._update_repository(target_dir, repo_location)
            else:
                result = self._clone_repository(repo_location, target_dir)
            return result
        finally:
            if cred_path:
                self._cleanup_credential_store(cred_path)
    
    def _get_credentials_for_url(self, repo_url: str) -> tuple[str, str] | None:
        """
        Get the username and password for a repository URL based on provider.

        Returns:
            Tuple of (username, password) or None if no credentials available.
        """
        if self._is_codecommit_url(repo_url):
            if self.codecommit_username and self.codecommit_password:
                return (self.codecommit_username, self.codecommit_password)
        elif 'github.com' in repo_url:
            if self.github_token:
                return ('x-access-token', self.github_token)
        elif self._is_gitlab_url(repo_url):
            if self.gitlab_token:
                return ('oauth2', self.gitlab_token)
        elif self._is_bitbucket_url(repo_url):
            if self.bitbucket_username and self.bitbucket_app_password:
                return (self.bitbucket_username, self.bitbucket_app_password)
        elif self._is_azure_devops_url(repo_url):
            if self.azure_devops_pat:
                return ('', self.azure_devops_pat)
        return None

    def _write_credential_store(self, repo_url: str) -> str | None:
        """
        Write a temporary git credential store file for the given repo URL.

        Credentials are stored in a temp file using the git credential store format:
        https://user:pass@host — git reads this file instead of embedding creds in URLs.

        Returns:
            Path to the temp credential file, or None if no credentials available.
        """
        creds = self._get_credentials_for_url(repo_url)
        if not creds:
            return None

        username, password = creds
        parsed = urlparse(repo_url)
        host = parsed.hostname or ''

        # Build credential store entry: protocol://user:pass@host
        entry = f"{parsed.scheme}://{quote(username, safe='')}:{quote(password, safe='')}@{host}"

        # Write to a secure temp file (fd-based, not world-readable)
        fd, cred_path = tempfile.mkstemp(prefix='git-creds-', suffix='.store')
        try:
            os.write(fd, (entry + '\n').encode())
        finally:
            os.close(fd)
        os.chmod(cred_path, 0o600)

        provider = self._detect_provider_name(repo_url)
        self.logger.debug(f"Configured git credential store for {provider}")
        return cred_path

    def _configure_git_credential_helper(self, cred_path: str, work_dir: str = None) -> None:
        """Configure git to use the credential store file."""
        cmd = ["git", "config", "--global", "credential.helper", f"store --file={cred_path}"]
        subprocess.run(cmd, cwd=work_dir, check=True, capture_output=True)

    def _cleanup_credential_store(self, cred_path: str) -> None:
        """Securely remove the temporary credential store file and reset git config."""
        try:
            if cred_path and os.path.exists(cred_path):
                os.remove(cred_path)
            # Reset credential helper to avoid stale references
            subprocess.run(
                ["git", "config", "--global", "--unset", "credential.helper"],
                capture_output=True
            )
        except Exception as e:
            self.logger.debug(f"Credential cleanup note: {e}")

    def _detect_provider_name(self, url: str) -> str:
        """Return a human-readable provider name for logging (no secrets)."""
        if self._is_codecommit_url(url):
            return "CodeCommit"
        if 'github.com' in url:
            return "GitHub"
        if self._is_gitlab_url(url):
            return "GitLab"
        if self._is_bitbucket_url(url):
            return "Bitbucket"
        if self._is_azure_devops_url(url):
            return "Azure DevOps"
        return "unknown"

    def _sanitize_error_message(self, error_msg: str) -> str:
        """
        Remove ALL known credentials from an error message.

        Checks all configured tokens/passwords, not just GitHub.
        """
        secrets = [
            self.github_token,
            self.codecommit_password,
            self.codecommit_username,
            self.gitlab_token,
            self.bitbucket_app_password,
            self.bitbucket_username,
            self.azure_devops_pat,
        ]
        for secret in secrets:
            if secret and secret in error_msg:
                error_msg = error_msg.replace(secret, '***')
        return error_msg
    
    def _is_existing_repo(self, repo_dir: str) -> bool:
        """Check if a directory contains a valid Git repository."""
        return os.path.exists(repo_dir) and os.path.exists(os.path.join(repo_dir, '.git'))
    
    def _update_repository(self, repo_dir: str, repo_location: str) -> str:
        """Update an existing repository with latest changes.
        
        Authentication is handled by the git credential helper configured
        in clone_or_update — no need to embed creds in remote URLs.
        """
        self.logger.info(f"Repository already exists at: {repo_dir}")
        try:
            import git
            repo = git.Repo(repo_dir)
            self.logger.info("Pulling latest changes from remote repository")

            origin = repo.remotes.origin
            origin.fetch()
            origin.pull()

            self.logger.info(f"Repository successfully updated at: {repo_dir}")
            return repo_dir

        except Exception as e:
            import git
            if isinstance(e, git.exc.GitCommandError):
                self.logger.warning(f"Failed to pull latest changes: {self._sanitize_error_message(str(e))}")
                self.logger.info("Falling back to cloning the repository")
                shutil.rmtree(repo_dir)
                raise
            else:
                raise
    
    def _clone_repository(self, repo_location: str, target_dir: str) -> str:
        """Clone a new repository.
        
        Authentication is handled by the git credential helper — the URL
        passed here should be clean (no embedded credentials).
        """
        self._ensure_clean_directory(target_dir)
        
        try:
            import git
            safe_url = self._sanitize_url_for_logging(repo_location)
            self.logger.info(f"Cloning repository from: {safe_url}")
            
            provider = self._detect_provider_name(repo_location)
            if self._get_credentials_for_url(repo_location):
                self.logger.info(f"Using {provider} authentication via credential helper")
            
            git.Repo.clone_from(repo_location, target_dir)
            self.logger.info(f"Repository successfully cloned to: {target_dir}")
            return target_dir
            
        except Exception as e:
            import git
            if isinstance(e, git.exc.GitCommandError):
                sanitized = self._sanitize_error_message(str(e))
                self.logger.error(f"Git clone failed: {sanitized}")
                
                # Check if it's a resource issue (exit code -9 or similar)
                if "exit code(-9)" in str(e) or "Killed" in str(e):
                    self.logger.warning("Detected potential resource issue, attempting shallow clone")
                    if os.path.exists(target_dir):
                        shutil.rmtree(target_dir, ignore_errors=True)
                    
                    try:
                        return self._shallow_clone_fallback(repo_location, target_dir)
                    except Exception as shallow_error:
                        shallow_msg = self._sanitize_error_message(str(shallow_error))
                        self.logger.error(f"Shallow clone also failed: {shallow_msg}")
                        raise Exception(f"Failed to clone repository even with shallow clone: {shallow_msg}")
                
                if "Authentication failed" in str(e):
                    provider = self._detect_provider_name(repo_location)
                    raise Exception(f"Failed to clone repository: Authentication failed for {provider}. Check credentials.")
                
                raise Exception(f"Failed to clone repository: {sanitized}")
            else:
                raise
    
    def _shallow_clone_fallback(self, repo_location: str, target_dir: str) -> str:
        """
        Perform a shallow clone as a fallback when normal clone fails due to resource constraints.
        
        Authentication is handled by the git credential helper — URLs stay clean.
        """
        self.logger.info("Attempting shallow clone with depth=1 to reduce memory usage")
        self._ensure_clean_directory(target_dir)
        
        cmd = [
            'git', 'clone',
            '--depth', '1',
            '--single-branch',
            '--no-tags',
            repo_location,
            target_dir
        ]
        
        safe_url = self._sanitize_url_for_logging(repo_location)
        self.logger.debug(f"Shallow clone target: {safe_url}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                check=True
            )
            
            self.logger.info(f"Repository successfully shallow cloned to: {target_dir}")
            return target_dir
            
        except subprocess.CalledProcessError as e:
            if e.returncode == -9 or "Killed" in e.stderr:
                self.logger.error("Even shallow clone was killed - severe resource constraints")
                return self._minimal_clone_fallback(repo_location, target_dir)
            
            error_msg = self._sanitize_error_message(e.stderr)
            raise Exception(f"Shallow clone failed: {error_msg}")
        except subprocess.TimeoutExpired:
            raise Exception("Shallow clone timed out after 10 minutes")
    
    def _minimal_clone_fallback(self, repo_location: str, target_dir: str) -> str:
        """
        Perform a minimal clone with aggressive optimizations for constrained environments.
        
        Authentication is handled by the git credential helper.
        """
        self.logger.info("Attempting minimal clone with aggressive optimizations")
        os.makedirs(target_dir, exist_ok=True)
        
        try:
            subprocess.run(['git', 'init'], cwd=target_dir, check=True, capture_output=True)
            
            safe_url = self._sanitize_url_for_logging(repo_location)
            self.logger.debug(f"Adding remote origin: {safe_url}")
            subprocess.run(['git', 'remote', 'add', 'origin', repo_location], cwd=target_dir, check=True, capture_output=True)
            
            # Configure git to minimize memory usage
            subprocess.run(['git', 'config', 'core.compression', '0'], cwd=target_dir, check=True)
            subprocess.run(['git', 'config', 'http.postBuffer', '524288000'], cwd=target_dir, check=True)
            subprocess.run(['git', 'config', 'pack.windowMemory', '10m'], cwd=target_dir, check=True)
            subprocess.run(['git', 'config', 'pack.packSizeLimit', '100m'], cwd=target_dir, check=True)
            subprocess.run(['git', 'config', 'core.packedGitLimit', '128m'], cwd=target_dir, check=True)
            subprocess.run(['git', 'config', 'core.packedGitWindowSize', '128m'], cwd=target_dir, check=True)
            
            # Fetch with minimal data - using blob:none for lazy loading
            fetch_cmd = [
                'git', 'fetch',
                '--depth=1',
                '--no-tags',
                '--filter=blob:none',  # Lazy fetch blobs only when needed
                'origin', 'HEAD'
            ]
            
            result = subprocess.run(
                fetch_cmd,
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=600,
                check=True
            )
            
            # Checkout the fetched branch
            subprocess.run(['git', 'checkout', 'FETCH_HEAD'], cwd=target_dir, check=True)
            
            self.logger.info(f"Repository successfully cloned with minimal strategy to: {target_dir}")
            return target_dir
            
        except subprocess.CalledProcessError as e:
            error_msg = self._sanitize_error_message(str(e))
            raise Exception(f"Minimal clone failed: {error_msg}")
        except subprocess.TimeoutExpired:
            raise Exception("Minimal clone timed out after 10 minutes")
    
    def get_current_branch(self, repo_dir: str) -> str:
        """Get the current branch name of a git repository.

        Args:
            repo_dir: Directory containing the git repository

        Returns:
            The current branch name, or "main" as fallback if the command fails.
            Returns "HEAD" for detached HEAD state.
        """
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        # Fallback for detached HEAD or empty repo
        return "main"

    def push_with_authentication(self, repo_dir: str, branch: str = "main") -> dict:
        """
        Push changes to remote repository with proper authentication.

        Uses git credential helper — credentials are never embedded in URLs.
        """
        cred_path = None
        try:
            # Get current remote URL
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=repo_dir, capture_output=True, text=True
            )

            if result.returncode == 0:
                current_url = result.stdout.strip()
                safe_url = self._sanitize_url_for_logging(current_url)
                self.logger.info(f"Current remote URL: {safe_url}")

                # Set up credential helper for the push
                cred_path = self._write_credential_store(current_url)
                if cred_path:
                    self._configure_git_credential_helper(cred_path)
                    provider = self._detect_provider_name(current_url)
                    self.logger.info(f"Using {provider} authentication via credential helper for push")
            
            # Perform the push
            push_result = subprocess.run(
                ["git", "push", "origin", branch],
                cwd=repo_dir, capture_output=True, text=True
            )
            
            if push_result.returncode != 0:
                error_msg = self._sanitize_error_message(push_result.stderr)
                return {
                    "status": "failed",
                    "message": f"Failed to push changes: {error_msg}",
                    "stderr": error_msg
                }
            
            self.logger.info(f"Successfully pushed changes to {branch}")
            return {
                "status": "success",
                "message": f"Successfully pushed changes to {branch}",
                "stdout": push_result.stdout
            }
            
        except Exception as e:
            error_msg = self._sanitize_error_message(str(e))
            return {
                "status": "failed",
                "message": f"Push operation failed: {error_msg}",
                "error": error_msg
            }
        finally:
            if cred_path:
                self._cleanup_credential_store(cred_path)
    
    def validate_github_token(self) -> dict:
        """
        Validate the GitHub token and return user information.
        
        Returns:
            Dictionary with validation status and user info
        """
        if not self.github_token:
            return {
                "status": "no_token",
                "message": "No GitHub token found in environment"
            }
        
        try:
            import requests
            headers = {
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            response = requests.get('https://api.github.com/user', headers=headers, timeout=10)
            
            if response.status_code == 200:
                user_info = response.json()
                return {
                    "status": "valid",
                    "message": f"GitHub token authenticated as user: {user_info.get('login', 'unknown')}",
                    "user": user_info.get('login', 'unknown'),
                    "user_info": user_info
                }
            else:
                return {
                    "status": "invalid",
                    "message": f"GitHub token validation failed: HTTP {response.status_code}",
                    "status_code": response.status_code
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Could not validate GitHub token: {str(e)}",
                "error": str(e)
            }
    
    def configure_git_user(self, repo_dir: str, user_name: str, user_email: str) -> bool:
        """
        Configure git user for commits in the repository.
        
        Args:
            repo_dir: Directory containing the git repository
            user_name: Git user name
            user_email: Git user email
            
        Returns:
            True if configuration was successful, False otherwise
        """
        try:
            subprocess.run(
                ["git", "config", "user.name", user_name],
                cwd=repo_dir,
                check=True
            )
            subprocess.run(
                ["git", "config", "user.email", user_email],
                cwd=repo_dir,
                check=True
            )
            
            self.logger.info(f"Git configured with user: {user_name} <{user_email}>")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to configure git user: {str(e)}")
            return False
    
    def check_repository_permissions(self, repo_url: str) -> dict:
        """
        Check if the current GitHub token has push permissions to the repository.
        
        Args:
            repo_url: Repository URL to check permissions for
            
        Returns:
            Dictionary with permission check results
        """
        if not self.github_token:
            return {
                "status": "no_token",
                "message": "No GitHub token available to check permissions"
            }
        
        # Extract owner and repo from URL
        try:
            if 'github.com' not in repo_url:
                return {
                    "status": "not_github",
                    "message": "Repository is not hosted on GitHub"
                }
            
            # Parse GitHub URL to extract owner/repo
            # Handle both https://github.com/owner/repo and https://github.com/owner/repo.git
            url_path = repo_url.replace('https://github.com/', '').replace('.git', '')
            if '/' not in url_path:
                return {
                    "status": "invalid_url",
                    "message": "Could not parse repository owner/name from URL"
                }
            
            owner, repo = url_path.split('/', 1)
            
            import requests
            headers = {
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # Check repository permissions
            api_url = f'https://api.github.com/repos/{owner}/{repo}'
            response = requests.get(api_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                repo_data = response.json()
                permissions = repo_data.get('permissions', {})
                
                can_push = permissions.get('push', False)
                can_admin = permissions.get('admin', False)
                
                if can_push or can_admin:
                    return {
                        "status": "allowed",
                        "message": f"Token has push permissions to {owner}/{repo}",
                        "permissions": permissions,
                        "owner": owner,
                        "repo": repo
                    }
                else:
                    return {
                        "status": "denied",
                        "message": f"Token does not have push permissions to {owner}/{repo}",
                        "permissions": permissions,
                        "owner": owner,
                        "repo": repo
                    }
            elif response.status_code == 404:
                return {
                    "status": "not_found",
                    "message": f"Repository {owner}/{repo} not found or no access",
                    "owner": owner,
                    "repo": repo
                }
            else:
                return {
                    "status": "error",
                    "message": f"GitHub API returned {response.status_code}",
                    "status_code": response.status_code,
                    "owner": owner,
                    "repo": repo
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to check repository permissions: {str(e)}",
                "error": str(e)
            }
    
    def list_codecommit_repositories(self, region: str = None) -> dict:
        """
        List all CodeCommit repositories in the specified AWS region.

        Args:
            region: AWS region (defaults to AWS_DEFAULT_REGION env var or us-east-1)

        Returns:
            Dictionary with status and list of repositories
        """
        try:
            import boto3

            # Determine region
            aws_region = region or os.getenv('AWS_DEFAULT_REGION', 'us-east-1')

            self.logger.info(f"Listing CodeCommit repositories in region {aws_region}")

            # Create CodeCommit client
            codecommit = boto3.client('codecommit', region_name=aws_region)

            # List repositories
            response = codecommit.list_repositories()

            repositories = []
            for repo_metadata in response.get('repositories', []):
                repo_name = repo_metadata['repositoryName']

                # Get detailed repository info
                try:
                    repo_detail = codecommit.get_repository(repositoryName=repo_name)
                    repo_info = repo_detail['repositoryMetadata']

                    repositories.append({
                        'name': repo_name,
                        'clone_url_http': repo_info['cloneUrlHttp'],
                        'clone_url_ssh': repo_info.get('cloneUrlSsh', ''),
                        'arn': repo_info.get('Arn', ''),
                        'description': repo_info.get('repositoryDescription', ''),
                        'created_date': repo_info.get('creationDate', ''),
                        'last_modified_date': repo_info.get('lastModifiedDate', '')
                    })
                except Exception as e:
                    self.logger.warning(f"Could not get details for repository {repo_name}: {str(e)}")
                    # Add basic info even if details fail
                    repositories.append({
                        'name': repo_name,
                        'clone_url_http': f"https://git-codecommit.{aws_region}.amazonaws.com/v1/repos/{repo_name}",
                        'error': str(e)
                    })

            self.logger.info(f"Found {len(repositories)} CodeCommit repositories")

            return {
                "status": "success",
                "region": aws_region,
                "count": len(repositories),
                "repositories": repositories
            }

        except Exception as e:
            self.logger.error(f"Failed to list CodeCommit repositories: {str(e)}")
            return {
                "status": "error",
                "message": f"Failed to list CodeCommit repositories: {str(e)}",
                "error": str(e)
            }

    def list_gitlab_repositories(self, token: str = None, base_url: str = "https://gitlab.com") -> dict:
        """
        List all GitLab repositories accessible by the token.

        Args:
            token: GitLab personal access token (defaults to GITLAB_TOKEN env var)
            base_url: GitLab instance base URL (defaults to https://gitlab.com)

        Returns:
            Dictionary with status and list of repositories
        """
        try:
            import urllib.request
            import json as json_module

            gitlab_token = token or self.gitlab_token
            if not gitlab_token:
                return {
                    "status": "error",
                    "message": "No GitLab token available. Set GITLAB_TOKEN environment variable.",
                    "error": "No token"
                }

            self.logger.info(f"Listing GitLab repositories from {base_url}")

            repositories = []
            page = 1

            while True:
                api_url = f"{base_url}/api/v4/projects?membership=true&per_page=100&page={page}"
                req = urllib.request.Request(api_url)
                req.add_header('PRIVATE-TOKEN', gitlab_token)

                with urllib.request.urlopen(req) as response:
                    data = json_module.loads(response.read().decode('utf-8'))

                if not data:
                    break

                for project in data:
                    repositories.append({
                        'name': project.get('path_with_namespace', project.get('name', '')),
                        'clone_url_http': project.get('http_url_to_repo', ''),
                        'description': project.get('description', '') or ''
                    })

                page += 1

            self.logger.info(f"Found {len(repositories)} GitLab repositories")

            return {
                "status": "success",
                "count": len(repositories),
                "repositories": repositories
            }

        except Exception as e:
            self.logger.error(f"Failed to list GitLab repositories: {str(e)}")
            return {
                "status": "error",
                "message": f"Failed to list GitLab repositories: {str(e)}",
                "error": str(e)
            }

    def list_bitbucket_repositories(self, username: str = None, app_password: str = None, workspace: str = None) -> dict:
        """
        List all Bitbucket repositories in the specified workspace.

        Args:
            username: Bitbucket username (defaults to BITBUCKET_USERNAME env var)
            app_password: Bitbucket app password (defaults to BITBUCKET_APP_PASSWORD env var)
            workspace: Bitbucket workspace slug (defaults to BITBUCKET_WORKSPACE env var or username)

        Returns:
            Dictionary with status and list of repositories
        """
        try:
            import urllib.request
            import json as json_module
            import base64

            bb_username = username or self.bitbucket_username
            bb_app_password = app_password or self.bitbucket_app_password
            bb_workspace = workspace or os.getenv('BITBUCKET_WORKSPACE', bb_username)

            if not bb_username or not bb_app_password:
                return {
                    "status": "error",
                    "message": "No Bitbucket credentials available. Set BITBUCKET_USERNAME and BITBUCKET_APP_PASSWORD.",
                    "error": "No credentials"
                }

            if not bb_workspace:
                return {
                    "status": "error",
                    "message": "No Bitbucket workspace specified. Set BITBUCKET_WORKSPACE environment variable.",
                    "error": "No workspace"
                }

            self.logger.info(f"Listing Bitbucket repositories in workspace {bb_workspace}")

            repositories = []
            api_url = f"https://api.bitbucket.org/2.0/repositories/{bb_workspace}"

            # Create basic auth header
            credentials = base64.b64encode(f"{bb_username}:{bb_app_password}".encode()).decode()

            while api_url:
                req = urllib.request.Request(api_url)
                req.add_header('Authorization', f'Basic {credentials}')

                with urllib.request.urlopen(req) as response:
                    data = json_module.loads(response.read().decode('utf-8'))

                for repo in data.get('values', []):
                    clone_url = ''
                    for link in repo.get('links', {}).get('clone', []):
                        if link.get('name') == 'https':
                            clone_url = link.get('href', '')
                            break

                    repositories.append({
                        'name': repo.get('full_name', repo.get('name', '')),
                        'clone_url_http': clone_url,
                        'description': repo.get('description', '') or ''
                    })

                api_url = data.get('next')

            self.logger.info(f"Found {len(repositories)} Bitbucket repositories")

            return {
                "status": "success",
                "count": len(repositories),
                "repositories": repositories
            }

        except Exception as e:
            self.logger.error(f"Failed to list Bitbucket repositories: {str(e)}")
            return {
                "status": "error",
                "message": f"Failed to list Bitbucket repositories: {str(e)}",
                "error": str(e)
            }

    def list_azure_devops_repositories(self, pat: str = None, organization: str = None, project: str = None) -> dict:
        """
        List all Azure DevOps repositories in the specified organization and project.

        Args:
            pat: Azure DevOps personal access token (defaults to AZURE_DEVOPS_PAT env var)
            organization: Azure DevOps organization (defaults to AZURE_DEVOPS_ORG env var)
            project: Azure DevOps project (defaults to AZURE_DEVOPS_PROJECT env var)

        Returns:
            Dictionary with status and list of repositories
        """
        try:
            import urllib.request
            import json as json_module
            import base64

            azure_pat = pat or self.azure_devops_pat
            azure_org = organization or os.getenv('AZURE_DEVOPS_ORG')
            azure_project = project or os.getenv('AZURE_DEVOPS_PROJECT')

            if not azure_pat:
                return {
                    "status": "error",
                    "message": "No Azure DevOps PAT available. Set AZURE_DEVOPS_PAT environment variable.",
                    "error": "No PAT"
                }

            if not azure_org:
                return {
                    "status": "error",
                    "message": "No Azure DevOps organization specified. Set AZURE_DEVOPS_ORG environment variable.",
                    "error": "No organization"
                }

            if not azure_project:
                return {
                    "status": "error",
                    "message": "No Azure DevOps project specified. Set AZURE_DEVOPS_PROJECT environment variable.",
                    "error": "No project"
                }

            self.logger.info(f"Listing Azure DevOps repositories in {azure_org}/{azure_project}")

            api_url = f"https://dev.azure.com/{azure_org}/{azure_project}/_apis/git/repositories?api-version=7.1"

            # Create basic auth header (empty username, PAT as password)
            credentials = base64.b64encode(f":{azure_pat}".encode()).decode()

            req = urllib.request.Request(api_url)
            req.add_header('Authorization', f'Basic {credentials}')

            with urllib.request.urlopen(req) as response:
                data = json_module.loads(response.read().decode('utf-8'))

            repositories = []
            for repo in data.get('value', []):
                repositories.append({
                    'name': repo.get('name', ''),
                    'clone_url_http': repo.get('remoteUrl', ''),
                    'description': repo.get('project', {}).get('description', '') or ''
                })

            self.logger.info(f"Found {len(repositories)} Azure DevOps repositories")

            return {
                "status": "success",
                "count": len(repositories),
                "repositories": repositories
            }

        except Exception as e:
            self.logger.error(f"Failed to list Azure DevOps repositories: {str(e)}")
            return {
                "status": "error",
                "message": f"Failed to list Azure DevOps repositories: {str(e)}",
                "error": str(e)
            }

    def _ensure_clean_directory(self, directory: str):
        """Ensure a directory is clean and ready for use."""
        if os.path.exists(directory):
            self.logger.info(f"Cleaning up existing directory: {directory}")
            shutil.rmtree(directory)
        os.makedirs(directory, exist_ok=True) 