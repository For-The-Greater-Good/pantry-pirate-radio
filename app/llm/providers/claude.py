"""Claude provider implementation using the Claude CLI."""

import asyncio
import json
import os
import subprocess  # nosec B404
import tempfile
import time
from typing import Any, cast

from app.core.logging import get_logger
from app.llm.config import LLMConfig
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.types import GenerateConfig, LLMInput, LLMResponse

logger = get_logger().bind(module="claude_provider")


class ClaudeQuotaExceededException(Exception):  # noqa: N818
    """Exception raised when Claude quota is exceeded."""

    def __init__(self, message: str, retry_after: int = 3600):
        super().__init__(message)
        self.retry_after = retry_after  # Seconds to wait before retrying


class ClaudeNotAuthenticatedException(Exception):  # noqa: N818
    """Exception raised when Claude is not properly authenticated."""

    def __init__(self, message: str, retry_after: int = 300):
        super().__init__(message)
        self.retry_after = retry_after  # Seconds to wait before retrying


class ClaudeConfig(LLMConfig):
    """Configuration for Claude provider."""

    def __init__(
        self,
        model_name: str = "claude-sonnet-4-20250514",
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> None:
        """Initialize Claude config.

        Args:
            model_name: Name of the model to use
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum number of tokens to generate
        """
        super().__init__(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            supports_structured=True,
        )


class ClaudeProvider(BaseLLMProvider[None, ClaudeConfig]):
    """Claude provider implementation using the Claude CLI."""

    def __init__(
        self,
        config: ClaudeConfig,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the Claude provider.

        Args:
            config: Provider configuration
            api_key: Anthropic API key
            **kwargs: Additional configuration
        """
        self.config = config
        super().__init__(
            model_name=config.model_name,
            api_key=api_key,
            **kwargs,
        )

    def _init_config(self, **kwargs: Any) -> ClaudeConfig:
        """Initialize provider configuration.

        Args:
            **kwargs: Configuration parameters

        Returns:
            ClaudeConfig: Provider configuration
        """
        # Get model_name from kwargs or self
        model_name = kwargs.get("model_name", self.model_name)
        if not model_name:
            raise ValueError("model_name is required")

        # Get temperature from kwargs or default
        temperature = kwargs.get("temperature", 0.7)

        # Get max_tokens from kwargs
        max_tokens = kwargs.get("max_tokens")

        return ClaudeConfig(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @property
    def environment_key(self) -> str:
        """Get the environment variable name for the API key."""
        return "ANTHROPIC_API_KEY"

    @property
    def model(self) -> None:
        """Get the model instance (not applicable for CLI)."""
        return None

    async def health_check(self) -> dict[str, Any]:
        """Check the health of the Claude provider.

        Returns:
            dict: Health status information
        """
        try:
            is_authenticated = await self._check_authentication()

            return {
                "provider": "claude",
                "status": "healthy" if is_authenticated else "unhealthy",
                "authenticated": is_authenticated,
                "model": self.config.model_name,
                "message": (
                    "Ready"
                    if is_authenticated
                    else "Authentication required. Run: docker compose exec worker claude"
                ),
            }
        except Exception as e:
            return {
                "provider": "claude",
                "status": "unhealthy",
                "authenticated": False,
                "error": str(e),
                "message": "Health check failed",
            }

    def _format_prompt(
        self,
        prompt: LLMInput,
        format: dict[str, Any] | None = None,
    ) -> str:
        """Format input prompt for Claude CLI.

        Args:
            prompt: The prompt to format
            format: Optional JSON schema for structured output

        Returns:
            str: Formatted prompt
        """
        if isinstance(prompt, str):
            if format:
                # Add structured output instructions
                json_schema = json.dumps(format, indent=2)
                return f"""You are a helpful assistant that always responds with valid JSON.
Your response must be a complete, properly formatted JSON object that matches this schema:

{json_schema}

IMPORTANT: Only return the JSON object, no additional text or explanation.

{prompt}"""
            return prompt

        # Handle list of messages (chat format)
        if isinstance(prompt, list):
            # Convert to a single string for CLI
            formatted_parts = []
            for msg in prompt:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    formatted_parts.append(f"System: {content}")
                elif role == "user":
                    formatted_parts.append(f"User: {content}")
                elif role == "assistant":
                    formatted_parts.append(f"Assistant: {content}")
                else:
                    formatted_parts.append(f"{role}: {content}")

            base_prompt = "\n\n".join(formatted_parts)

            if format:
                json_schema = json.dumps(format, indent=2)
                return f"""You are a helpful assistant that always responds with valid JSON.
Your response must be a complete, properly formatted JSON object that matches this schema:

{json_schema}

IMPORTANT: Only return the JSON object, no additional text or explanation.

{base_prompt}"""
            return base_prompt

        return str(prompt)

    def _build_cli_args(
        self,
        prompt: str,
        config: GenerateConfig | None = None,
        format: dict[str, Any] | None = None,
    ) -> list[str]:
        """Build CLI arguments for Claude Code.

        Args:
            prompt: Formatted prompt
            config: Generation configuration
            format: Optional JSON schema for structured output

        Returns:
            list[str]: CLI arguments
        """
        args = ["claude", "-p"]  # Print mode for non-interactive execution

        # Add output format
        if format:
            args.extend(["--output-format", "json"])
        else:
            args.extend(["--output-format", "text"])

        # Add model if specified
        if self.config.model_name:
            args.extend(["--model", self.config.model_name])

        # Add the prompt as the last argument
        args.append(prompt)

        return args

    async def _check_authentication(self) -> bool:
        """Check if Claude CLI is properly authenticated.

        Returns:
            bool: True if authenticated, False otherwise
        """
        try:
            # Test authentication with a simple command
            test_args = ["claude", "-p", "--output-format", "json", "Hello"]

            # Set up environment
            env = {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "HOME": os.environ.get("HOME", "/root"),
            }

            # Add API key if available
            if self.api_key and self.api_key != "your_anthropic_api_key_here":
                env["ANTHROPIC_API_KEY"] = self.api_key

            # Execute test command with short timeout
            process = await asyncio.create_subprocess_exec(
                *test_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)

            if process.returncode == 0:
                # Check if response indicates successful authentication
                output = stdout.decode("utf-8")
                try:
                    data = json.loads(output)
                    if isinstance(data, dict):
                        # Check for authentication-related errors
                        result = data.get("result", "")
                        auth_errors = [
                            "invalid api key",
                            "fix external api key",
                            "authentication",
                            "login required",
                            "not authenticated",
                            "please log in",
                        ]
                        if any(error in str(result).lower() for error in auth_errors):
                            return False
                        # If we get a normal response, we're authenticated
                        return not data.get("is_error", False)
                except json.JSONDecodeError:
                    # If it's not JSON but return code 0, probably authenticated
                    return True

            return False

        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Authentication check failed: {e}")
            return False

    def _is_quota_exceeded(self, output: str) -> bool:
        """Check if the output indicates quota exceeded.

        Args:
            output: CLI output to check

        Returns:
            bool: True if quota is exceeded
        """
        try:
            data = json.loads(output)
            if isinstance(data, dict):
                result = data.get("result", "")
                # Check for various quota-related error messages
                quota_indicators = [
                    "usage limit",
                    "quota",
                    "rate limit",
                    "too many requests",
                    "exceeded",
                    "throttle",
                    "usage cap",
                ]
                return any(
                    indicator in str(result).lower() for indicator in quota_indicators
                )
        except (json.JSONDecodeError, KeyError):
            pass
        return False

    def _parse_cli_output(
        self,
        output: str,
        format: dict[str, Any] | None = None,
    ) -> tuple[str, Any | None, dict[str, int]]:
        """Parse CLI output.

        Args:
            output: Raw CLI output
            format: Optional JSON schema for structured output

        Returns:
            tuple[str, Any | None, dict[str, int]]: (text, parsed_data, usage)
        """
        if not format:
            # Text output
            return (
                output.strip(),
                None,
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

        try:
            # Parse JSON output
            data = json.loads(output)

            # Extract relevant fields from Claude CLI JSON response
            if isinstance(data, dict) and "result" in data:
                text = data["result"]
                usage = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                }

                # Try to parse structured output
                parsed = None
                if format and text:
                    try:
                        # Try to parse the result as JSON
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        # If it's not valid JSON, keep as text
                        pass

                return text, parsed, usage
            else:
                # Direct JSON response
                return (
                    json.dumps(data),
                    data,
                    {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                )

        except json.JSONDecodeError:
            # Fallback to text parsing
            return (
                output.strip(),
                None,
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

    async def generate(
        self,
        prompt: LLMInput,
        config: GenerateConfig | None = None,
        format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate text using Claude CLI.

        Args:
            prompt: The input prompt or chat messages
            config: Optional generation configuration
            format: Optional JSON schema for structured output
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse: Generated response

        Raises:
            ValueError: If there is an error in generation
        """
        try:
            # Check if format is embedded in config when format parameter is None
            if format is None and config is not None and hasattr(config, 'format') and config.format:
                format = config.format
            # Check authentication first
            if not await self._check_authentication():
                logger.error(
                    "Claude is not properly authenticated. Please run 'docker compose exec worker claude' to set up authentication."
                )
                raise ClaudeNotAuthenticatedException(
                    "Claude authentication required. Please run: docker compose exec worker claude"
                )

            # Format prompt
            formatted_prompt = self._format_prompt(prompt, format)

            # Build CLI arguments
            cli_args = self._build_cli_args(formatted_prompt, config, format)

            # Log the request
            logger.info(
                f"Making Claude CLI request with args: {cli_args[:-1]}"
            )  # Don't log the prompt
            logger.debug(f"Full prompt: {formatted_prompt[:200]}...")

            # Set up environment
            env = {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "HOME": os.environ.get("HOME", "/root"),  # Needed for Claude config
            }

            # Check if we have a valid API key, otherwise use CLI authentication
            if self.api_key and self.api_key != "your_anthropic_api_key_here":
                env["ANTHROPIC_API_KEY"] = self.api_key
                logger.info("Using ANTHROPIC_API_KEY for authentication")
            else:
                logger.info("Using Claude CLI authentication (logged in account)")

            # Execute Claude CLI
            process = await asyncio.create_subprocess_exec(
                *cli_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8") if stderr else "Unknown error"
                stdout_msg = stdout.decode("utf-8") if stdout else "No output"

                # Check if this is a quota exceeded error
                if self._is_quota_exceeded(stdout_msg):
                    from app.core.config import settings

                    retry_delay = getattr(settings, "CLAUDE_QUOTA_RETRY_DELAY", 3600)
                    logger.warning(
                        f"Claude quota exceeded, will retry after {retry_delay} seconds"
                    )
                    raise ClaudeQuotaExceededException(
                        f"Claude quota exceeded: {stdout_msg}", retry_after=retry_delay
                    )

                logger.error(f"Claude CLI failed with return code {process.returncode}")
                logger.error(f"stderr: {error_msg}")
                logger.error(f"stdout: {stdout_msg}")
                logger.error(f"Command args: {cli_args}")
                raise ValueError(
                    f"Claude CLI error (code {process.returncode}): {error_msg}. stdout: {stdout_msg}"
                )

            # Parse output
            output = stdout.decode("utf-8")
            text, parsed, usage = self._parse_cli_output(output, format)

            # Log response
            logger.info(f"Received Claude CLI response: {len(text)} characters")
            logger.debug(f"Response text: {text[:200]}...")

            # Build response
            response_data: dict[str, Any] = {
                "text": text,
                "model": self.config.model_name,
                "usage": usage,
                "raw": {"output": output},
            }

            if parsed is not None:
                response_data["parsed"] = parsed

            return LLMResponse(**response_data)

        except Exception as e:
            logger.error(f"Error in Claude CLI generation: {e}")
            if isinstance(
                e,
                ValueError
                | ClaudeNotAuthenticatedException
                | ClaudeQuotaExceededException,
            ):
                raise
            raise ValueError(f"Error generating with Claude CLI: {e}")
