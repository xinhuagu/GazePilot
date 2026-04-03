"""GitHub Copilot LLM provider for Gazefy.

Uses the same authentication flow as AceClaw:
  1. Cached OAuth token from ~/.aceclaw/copilot-oauth-token
  2. gh auth token (GitHub CLI)
  3. GITHUB_TOKEN / GH_TOKEN env vars

Token exchange: GitHub token → Copilot session token via
  GET https://api.github.com/copilot_internal/v2/token

Then calls: POST https://api.githubcopilot.com/chat/completions
  (OpenAI-compatible Chat Completions API)

Supports: claude-sonnet-4.5, gpt-4o, o4-mini, codex models, etc.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

TOKEN_EXCHANGE_URL = "https://api.github.com/copilot_internal/v2/token"
DEFAULT_ENDPOINT = "https://api.githubcopilot.com"
CACHED_TOKEN_FILE = Path.home() / ".aceclaw" / "copilot-oauth-token"

# Headers matching what Copilot API expects
COPILOT_HEADERS = {
    "editor-version": "vscode/1.95.0",
    "editor-plugin-version": "copilot-chat/0.26.7",
    "Copilot-Integration-Id": "vscode-chat",
    "openai-intent": "conversation-panel",
}


class CopilotClient:
    """GitHub Copilot LLM client with token exchange and retry."""

    def __init__(self, model: str = "claude-sonnet-4.5"):
        self._model = model
        self._session_token: str | None = None
        self._endpoint: str = DEFAULT_ENDPOINT
        self._token_expires: float = 0

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        model: str | None = None,
    ) -> str:
        """Send a chat completion request. Returns the response text."""
        self._ensure_token()
        model = model or self._model

        url = f"{self._endpoint}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._session_token}",
            "Content-Type": "application/json",
            **COPILOT_HEADERS,
        }
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        for attempt in range(3):
            try:
                resp = httpx.post(url, headers=headers, json=payload, timeout=60)
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
                elif resp.status_code == 429:
                    delay = 2 ** (attempt + 1)
                    logger.warning("Copilot 429, retry in %ds", delay)
                    time.sleep(delay)
                    continue
                elif resp.status_code == 401:
                    logger.info("Token expired, refreshing")
                    self._session_token = None
                    self._ensure_token()
                    continue
                else:
                    logger.error(
                        "Copilot API error %d: %s",
                        resp.status_code,
                        resp.text[:200],
                    )
                    raise RuntimeError(f"Copilot API error {resp.status_code}: {resp.text[:200]}")
            except httpx.TimeoutException:
                if attempt < 2:
                    logger.warning("Copilot timeout, retrying")
                    continue
                raise

        raise RuntimeError("Copilot API: max retries exceeded")

    def chat_with_image(
        self,
        text: str,
        image_b64: str,
        media_type: str = "image/png",
        max_tokens: int = 4096,
        model: str | None = None,
    ) -> str:
        """Send a chat request with an image (vision). Returns response text."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
                    },
                ],
            }
        ]
        return self.chat(messages, max_tokens=max_tokens, model=model)

    def _ensure_token(self) -> None:
        """Ensure we have a valid Copilot session token."""
        if self._session_token and time.time() < self._token_expires - 300:
            return
        self._exchange_token()

    def _exchange_token(self) -> None:
        """Exchange a GitHub token for a Copilot session token."""
        github_token = _resolve_github_token()
        if not github_token:
            raise RuntimeError("No GitHub token. Run 'gh auth login' or set GITHUB_TOKEN.")

        # OAuth tokens use "token" prefix; PATs use "Bearer"
        is_pat = github_token.startswith(("github_pat_", "ghp_"))
        auth_prefix = "Bearer" if is_pat else "token"

        resp = httpx.get(
            TOKEN_EXCHANGE_URL,
            headers={
                "Authorization": f"{auth_prefix} {github_token}",
                "Accept": "application/json",
                "User-Agent": "GitHubCopilotChat/0.26.7",
                "editor-version": "vscode/1.95.0",
                "editor-plugin-version": "copilot-chat/0.26.7",
            },
            timeout=30,
        )

        if resp.status_code != 200:
            # Fallback: use token directly (for PATs with copilot scope)
            logger.info("Token exchange failed (%d), using direct token", resp.status_code)
            self._session_token = github_token
            self._endpoint = DEFAULT_ENDPOINT
            self._token_expires = time.time() + 3600
            return

        data = resp.json()
        self._session_token = data.get("token")
        expires_at = data.get("expires_at", 0)
        self._token_expires = float(expires_at) if expires_at else time.time() + 1800

        endpoints = data.get("endpoints", {})
        api_ep = endpoints.get("api", DEFAULT_ENDPOINT)
        self._endpoint = api_ep.rstrip("/")

        logger.info(
            "Copilot token exchanged: endpoint=%s, model=%s",
            self._endpoint,
            self._model,
        )


def _resolve_github_token() -> str | None:
    """Try multiple sources for a GitHub token."""
    # 1. AceClaw cached OAuth token
    if CACHED_TOKEN_FILE.exists():
        token = CACHED_TOKEN_FILE.read_text().strip()
        if token:
            return token

    # 2. Environment variables
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        val = os.environ.get(var)
        if val:
            return val

    # 3. gh CLI
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass

    return None
