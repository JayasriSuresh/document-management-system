"""
Module 10 — Multi-Provider AI Architecture Package.
"""

from app.ai.base import (
    AIProvider,
    ExtractionResult,
    GenerationResult,
    AIProviderError,
)
from app.ai.pricing import calculate_cost_cents, MODEL_PRICING
from app.ai.gemini import GeminiProvider
from app.ai.openai_provider import OpenAIProvider
from app.ai.claude import ClaudeProvider
from app.ai.resolver import (
    resolve_ai_config,
    resolve_credential,
    ResolvedAIConfig,
    ResolvedProviderDetails,
)
from app.ai.service import AIExecutionService

__all__ = [
    "AIProvider",
    "ExtractionResult",
    "GenerationResult",
    "AIProviderError",
    "calculate_cost_cents",
    "MODEL_PRICING",
    "GeminiProvider",
    "OpenAIProvider",
    "ClaudeProvider",
    "resolve_ai_config",
    "resolve_credential",
    "ResolvedAIConfig",
    "ResolvedProviderDetails",
    "AIExecutionService",
]
