"""
Unit tests for Bedrock adapter in ClaudeAnalyzer.
Tests the Bedrock provider selection and model mapping functionality.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
import sys

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'src'))

from investigator.core.claude_analyzer import ClaudeAnalyzer


class TestBedrockAdapter:
    """Tests for Bedrock adapter functionality in ClaudeAnalyzer."""

    def test_standard_anthropic_client_when_bedrock_not_set(self):
        """Test that standard Anthropic client is used when CLAUDE_PROVIDER is not set to 'bedrock'."""
        with patch.dict(os.environ, {}, clear=True):
            with patch('anthropic.Anthropic') as mock_anthropic:
                mock_client = Mock()
                mock_anthropic.return_value = mock_client
                mock_logger = Mock()

                analyzer = ClaudeAnalyzer("test-api-key", mock_logger)

                assert analyzer.use_bedrock is False
                assert analyzer.client == mock_client
                mock_anthropic.assert_called_once_with(api_key="test-api-key")
                mock_logger.info.assert_called_with("Using standard Anthropic API")

    def test_bedrock_client_when_provider_set(self):
        """Test that Bedrock client is used when CLAUDE_PROVIDER is set to 'bedrock'."""
        with patch.dict(os.environ, {'CLAUDE_PROVIDER': 'bedrock', 'AWS_DEFAULT_REGION': 'us-east-1'}):
            with patch('anthropic.AnthropicBedrock') as mock_bedrock:
                mock_client = Mock()
                mock_bedrock.return_value = mock_client
                mock_logger = Mock()

                analyzer = ClaudeAnalyzer("test-api-key", mock_logger)

                assert analyzer.use_bedrock is True
                assert analyzer.client == mock_client
                mock_bedrock.assert_called_once_with(aws_region='us-east-1')
                mock_logger.info.assert_called_with("Using Bedrock provider in region us-east-1")

    def test_bedrock_uses_default_region_when_not_set(self):
        """Test that Bedrock uses default region when AWS_DEFAULT_REGION is not set."""
        with patch.dict(os.environ, {'CLAUDE_PROVIDER': 'bedrock'}, clear=True):
            with patch('anthropic.AnthropicBedrock') as mock_bedrock:
                mock_client = Mock()
                mock_bedrock.return_value = mock_client
                mock_logger = Mock()

                analyzer = ClaudeAnalyzer("test-api-key", mock_logger)

                assert analyzer.use_bedrock is True
                mock_bedrock.assert_called_once_with(aws_region='us-east-1')

    def test_bedrock_model_mapping_opus(self):
        """Test that Bedrock model mapping works correctly for Opus models."""
        with patch.dict(os.environ, {'CLAUDE_PROVIDER': 'bedrock'}):
            with patch('anthropic.AnthropicBedrock'):
                mock_logger = Mock()
                analyzer = ClaudeAnalyzer("test-api-key", mock_logger)

                model_id = analyzer._get_model_id("claude-opus-4-5-20251101")

                assert model_id == "us.anthropic.claude-opus-4-5-20251101-v1:0"
                mock_logger.debug.assert_called_with(
                    "Mapped claude-opus-4-5-20251101 to Bedrock model us.anthropic.claude-opus-4-5-20251101-v1:0"
                )

    def test_bedrock_model_mapping_sonnet(self):
        """Test that Bedrock model mapping works correctly for Sonnet models."""
        with patch.dict(os.environ, {'CLAUDE_PROVIDER': 'bedrock'}):
            with patch('anthropic.AnthropicBedrock'):
                mock_logger = Mock()
                analyzer = ClaudeAnalyzer("test-api-key", mock_logger)

                model_id = analyzer._get_model_id("claude-sonnet-4-5-20250929")

                assert model_id == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    def test_bedrock_model_mapping_haiku(self):
        """Test that Bedrock model mapping works correctly for Haiku models."""
        with patch.dict(os.environ, {'CLAUDE_PROVIDER': 'bedrock'}):
            with patch('anthropic.AnthropicBedrock'):
                mock_logger = Mock()
                analyzer = ClaudeAnalyzer("test-api-key", mock_logger)

                model_id = analyzer._get_model_id("claude-haiku-4-5-20251001")

                assert model_id == "us.anthropic.claude-haiku-4-5-20251001-v1:0"

    def test_bedrock_model_mapping_unmapped_model(self):
        """Test that unmapped models are returned as-is with a warning."""
        with patch.dict(os.environ, {'CLAUDE_PROVIDER': 'bedrock'}):
            with patch('anthropic.AnthropicBedrock'):
                mock_logger = Mock()
                analyzer = ClaudeAnalyzer("test-api-key", mock_logger)

                model_id = analyzer._get_model_id("claude-unknown-model")

                assert model_id == "claude-unknown-model"
                mock_logger.warning.assert_called_with(
                    "No Bedrock mapping for claude-unknown-model, using as-is"
                )

    def test_standard_api_model_id_passthrough(self):
        """Test that standard API returns model names as-is."""
        with patch.dict(os.environ, {}, clear=True):
            with patch('anthropic.Anthropic'):
                mock_logger = Mock()
                analyzer = ClaudeAnalyzer("test-api-key", mock_logger)

                model_id = analyzer._get_model_id("claude-opus-4-5-20251101")

                assert model_id == "claude-opus-4-5-20251101"
                # Should not call debug for mapping in standard mode
                assert not any(
                    'Mapped' in str(call) for call in mock_logger.debug.call_args_list
                )

    @patch('anthropic.AnthropicBedrock')
    def test_analyze_with_context_uses_bedrock_model_mapping(self, mock_bedrock):
        """Test that analyze_with_context uses Bedrock model mapping when in Bedrock mode."""
        with patch.dict(os.environ, {'CLAUDE_PROVIDER': 'bedrock', 'AWS_DEFAULT_REGION': 'us-east-1'}):
            mock_client = Mock()
            mock_response = Mock()
            mock_response.content = [Mock(text="Test analysis result")]
            mock_client.messages.create.return_value = mock_response
            mock_bedrock.return_value = mock_client

            mock_logger = Mock()
            analyzer = ClaudeAnalyzer("test-api-key", mock_logger)

            result = analyzer.analyze_with_context(
                prompt_template="Test prompt: {repo_structure}",
                repo_structure="Test structure",
                config_overrides={"claude_model": "claude-opus-4-5-20251101"}
            )

            # Verify the Bedrock model ID was used in the API call
            mock_client.messages.create.assert_called_once()
            call_kwargs = mock_client.messages.create.call_args[1]
            assert call_kwargs['model'] == "us.anthropic.claude-opus-4-5-20251101-v1:0"
            assert result == "Test analysis result"

    @patch('anthropic.Anthropic')
    def test_analyze_with_context_uses_standard_model_name(self, mock_anthropic):
        """Test that analyze_with_context uses standard model name when not in Bedrock mode."""
        with patch.dict(os.environ, {}, clear=True):
            mock_client = Mock()
            mock_response = Mock()
            mock_response.content = [Mock(text="Test analysis result")]
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            mock_logger = Mock()
            analyzer = ClaudeAnalyzer("test-api-key", mock_logger)

            result = analyzer.analyze_with_context(
                prompt_template="Test prompt: {repo_structure}",
                repo_structure="Test structure",
                config_overrides={"claude_model": "claude-opus-4-5-20251101"}
            )

            # Verify the standard model name was used
            mock_client.messages.create.assert_called_once()
            call_kwargs = mock_client.messages.create.call_args[1]
            assert call_kwargs['model'] == "claude-opus-4-5-20251101"
            assert result == "Test analysis result"

    def test_all_bedrock_model_mappings_present(self):
        """Test that all valid Claude models have Bedrock mappings."""
        with patch.dict(os.environ, {'CLAUDE_PROVIDER': 'bedrock'}):
            with patch('anthropic.AnthropicBedrock'):
                from investigator.core.config import Config

                mock_logger = Mock()
                analyzer = ClaudeAnalyzer("test-api-key", mock_logger)

                # Check that all valid models have mappings
                for model in Config.VALID_CLAUDE_MODELS:
                    model_id = analyzer._get_model_id(model)
                    assert model_id.startswith("us.anthropic.")
                    assert "-v1" in model_id  # some models use -v1, others -v1:0
                    # Verify the model family is in the Bedrock ID (strip date suffix)
                    model_family = model.rsplit("-", 1)[0]  # e.g. claude-opus-4-6
                    assert model_family in model_id, f"{model_family} not in {model_id}"
