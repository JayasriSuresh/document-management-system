"""
Module 10 — Common AI Provider Interface and Normalized Result Types.

Defines the vendor-neutral contract for all supported AI models:
- Google Gemini
- OpenAI GPT
- Anthropic Claude
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple


@dataclass
class ExtractionResult:
    """Normalized output from document/invoice extraction across all providers."""
    structured_data: Dict[str, Any]
    raw_text: str
    provider: str
    model: str
    tokens_in: Optional[int] = 0
    tokens_out: Optional[int] = 0
    latency_ms: int = 0
    request_id: Optional[str] = None
    validation_status: str = "valid"  # "valid", "partial", "invalid"
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.error_code is None and bool(self.structured_data or self.raw_text)


@dataclass
class GenerationResult:
    """Normalized output from invoice/document generation across all providers."""
    content: str
    structured_data: Optional[Dict[str, Any]] = None
    provider: str = ""
    model: str = ""
    tokens_in: Optional[int] = 0
    tokens_out: Optional[int] = 0
    latency_ms: int = 0
    request_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.error_code is None and bool(self.content or self.structured_data)


class AIProviderError(Exception):
    """Normalized AI provider error with sanitized message and machine-readable error code."""
    def __init__(self, error_code: str, message: str, is_retryable: bool = False, raw_error: Optional[Exception] = None):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.is_retryable = is_retryable
        self.raw_error = raw_error


class AIProvider(ABC):
    """Abstract common interface implemented by all AI provider adapters."""

    @property
    @abstractmethod
    def provider_key(self) -> str:
        """Unique identifier (e.g., 'gemini', 'openai', 'anthropic')."""
        pass

    @abstractmethod
    def extract(
        self,
        images: List[bytes],
        mime_type: str = "image/jpeg",
        schema: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """
        Extract structured invoice/receipt data and raw OCR text from document images.
        """
        pass

    @abstractmethod
    def generate(
        self,
        input_data: Any,
        schema: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> GenerationResult:
        """
        Generate structured document or text from input data.
        """
        pass

    @abstractmethod
    def test_connection(self, api_key: str, model: str) -> Tuple[bool, str, int]:
        """
        Perform a safe, minimal connection test without submitting customer data.
        Returns (success: bool, sanitized_reason: str, latency_ms: int).
        """
        pass
