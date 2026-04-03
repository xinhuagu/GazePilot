"""Read Claude API credentials from Claude Code's storage.

Discovery priority (same as AceClaw):
  1. macOS Keychain: service "Claude Code-credentials"
  2. File: ~/.claude/.credentials.json
  3. Environment variable: ANTHROPIC_API_KEY

This reuses the same OAuth token that Claude Code already has,
so no separate API key setup is needed.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

KEYCHAIN_SERVICE = "Claude Code-credentials"
CREDENTIALS_FILE = Path.home() / ".claude" / ".credentials.json"


def get_api_key() -> str | None:
    """Get Anthropic API key, trying multiple sources.

    Returns:
        API key string, or None if not found.
    """
    # 1. Claude Code Keychain (OAuth token)
    token = _read_from_keychain()
    if token:
        logger.debug("Using Claude Code OAuth token from Keychain")
        return token

    # 2. Claude Code credentials file
    token = _read_from_file()
    if token:
        logger.debug("Using Claude Code OAuth token from credentials file")
        return token

    # 3. Environment variable (direct API key)
    import os

    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        logger.debug("Using ANTHROPIC_API_KEY from environment")
        return env_key

    return None


def _read_from_keychain() -> str | None:
    """Read OAuth access token from macOS Keychain."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        return _parse_oauth_json(result.stdout.strip())
    except Exception:
        return None


def _read_from_file() -> str | None:
    """Read OAuth access token from credentials file."""
    if not CREDENTIALS_FILE.is_file():
        return None
    try:
        text = CREDENTIALS_FILE.read_text()
        return _parse_oauth_json(text)
    except Exception:
        return None


def _parse_oauth_json(raw: str) -> str | None:
    """Extract accessToken from Claude Code OAuth JSON."""
    try:
        data = json.loads(raw)
        token = data.get("claudeAiOauth", {}).get("accessToken")
        if token and isinstance(token, str) and len(token) > 10:
            return token
    except (json.JSONDecodeError, AttributeError):
        pass
    return None
