"""Test settings: tasks run inline and uploaded files go to a throwaway directory."""

import tempfile

from .settings import *  # noqa: F403

TASKS = {"default": {"BACKEND": "django.tasks.backends.immediate.ImmediateBackend"}}
MEDIA_ROOT = tempfile.mkdtemp(prefix="aether-test-media-")
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher", *PASSWORD_HASHERS]  # noqa: F405

# Unit tests must never call real AI APIs. Real keys are kept aside for the opt-in live tests only.
LIVE_API_KEYS = {"gemini": GEMINI_API_KEY, "anthropic": ANTHROPIC_API_KEY, "tavily": TAVILY_API_KEY}  # noqa: F405
GEMINI_API_KEY = ""
ANTHROPIC_API_KEY = ""
EMBEDDING_PROVIDER = "none"
TAVILY_API_KEY = ""
