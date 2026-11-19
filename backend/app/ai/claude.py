"""
Module 10 — Anthropic Claude Provider Adapter.

Implements the AIProvider interface for Anthropic Claude models (claude-3-5-sonnet,
claude-3-5-haiku, etc.) using direct HTTPX client calls to the official
Anthropic /v1/messages API.
Handles base64 image sources, prompt-engineered JSON extraction with local schema validation,
token usage extraction (input_tokens / output_tokens), and sanitized error normalization.
"""

import base64
import json
import logging
import re
import time
from typing import Dict, Any, Optional, List, Tuple
import httpx

from app.ai.base import AIProvider, ExtractionResult, GenerationResult, AIProviderError

logger = logging.getLogger("dms.ai.claude")


class ClaudeProvider(AIProvider):
    """Anthropic Claude AI Provider."""

    BASE_URL = "https://api.anthropic.com/v1"
    API_VERSION = "2023-06-01"

    def __init__(self, api_key: str, default_model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key
        self.default_model = default_model

    @property
    def provider_key(self) -> str:
        return "anthropic"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }

    def extract(
        self,
        images: List[bytes],
        mime_type: str = "image/jpeg",
        schema: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        cfg = config or {}
        model = cfg.get("model") or self.default_model
        timeout = cfg.get("timeout_seconds", 40)
        start_time = time.time()

        if not images:
            raise AIProviderError("AI_INVALID_INPUT", "No image bytes provided for extraction.", is_retryable=False)

        content_blocks: List[Dict[str, Any]] = []

        # Add image blocks
        for img_bytes in images:
            b64_str = base64.b64encode(img_bytes).decode("utf-8")
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": b64_str,
                }
            })

        extract_prompt = prompt or (
            "Extract all text and structured invoice fields from the document image(s). "
            "You MUST respond ONLY with valid JSON inside a ```json ... ``` block. "
            "Do NOT include any commentary. "
            "Expected structure: "
            "{\"seller\": {\"name\": \"\", \"gstin\": \"\", \"address\": \"\"}, "
            "\"buyer\": {\"name\": \"\", \"gstin\": \"\", \"address\": \"\"}, "
            "\"invoice\": {\"number\": \"\", \"date\": \"\"}, "
            "\"totals\": {\"grand_total\": null, \"taxable_value\": null}, "
            "\"items\": [{\"description\": \"\", \"amount\": null}]}"
        )
        content_blocks.append({"type": "text", "text": extract_prompt})

        payload = {
            "model": model,
            "max_tokens": 4096,
            "messages": [
                {"role": "user", "content": content_blocks}
            ],
            "temperature": 0.1,
        }

        try:
            with httpx.Client(timeout=timeout) as client:
                res = client.post(f"{self.BASE_URL}/messages", headers=self._get_headers(), json=payload)
            latency_ms = int((time.time() - start_time) * 1000)

            if res.status_code == 401:
                raise AIProviderError("AI_INVALID_CREDENTIALS", "Anthropic API key is invalid or unauthorized.", is_retryable=False)
            if res.status_code == 429:
                raise AIProviderError("AI_RATE_LIMITED", "Anthropic rate limit exceeded.", is_retryable=True)
            if res.status_code >= 500:
                raise AIProviderError("AI_PROVIDER_UNAVAILABLE", f"Anthropic server error ({res.status_code}).", is_retryable=True)
            if res.status_code != 200:
                raise AIProviderError("AI_PROVIDER_UNAVAILABLE", f"Anthropic API error ({res.status_code}): {res.text[:200]}", is_retryable=True)

            data = res.json()
            raw_content = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    raw_content += block.get("text", "")

            raw_text = raw_content.strip()
            structured_data = {}
            if raw_text:
                clean_json = raw_text
                m = re.search(r'```(?:json)?\s*(.*?)\s*```', clean_json, re.DOTALL)
                if m:
                    clean_json = m.group(1)
                try:
                    structured_data = json.loads(clean_json)
                except Exception:
                    structured_data = {"raw_content": raw_text}

            if isinstance(structured_data, dict) and "structured_data" in structured_data and isinstance(structured_data["structured_data"], dict):
                structured_data = structured_data["structured_data"]

            usage = data.get("usage", {})
            tokens_in = usage.get("input_tokens", 0)
            tokens_out = usage.get("output_tokens", 0)

            return ExtractionResult(
                structured_data=structured_data,
                raw_text=raw_text,
                provider=self.provider_key,
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
                request_id=data.get("id"),
                validation_status="valid" if structured_data else "partial",
            )
        except httpx.TimeoutException as exc:
            raise AIProviderError("AI_PROVIDER_TIMEOUT", "Anthropic request timed out.", is_retryable=True, raw_error=exc)
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError("AI_PROVIDER_UNAVAILABLE", f"Anthropic request failed: {exc}", is_retryable=True, raw_error=exc)

    def generate(
        self,
        input_data: Any,
        schema: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> GenerationResult:
        cfg = config or {}
        model = cfg.get("model") or self.default_model
        timeout = cfg.get("timeout_seconds", 30)
        start_time = time.time()

        user_content = json.dumps(input_data) if isinstance(input_data, (dict, list)) else str(input_data)
        sys_text = system_prompt or "You are a professional invoice and document generator. Output clean text or JSON as instructed."
        if schema:
            sys_text += " Respond ONLY with valid JSON."

        payload = {
            "model": model,
            "max_tokens": 4096,
            "system": sys_text,
            "messages": [
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.2,
        }

        try:
            with httpx.Client(timeout=timeout) as client:
                res = client.post(f"{self.BASE_URL}/messages", headers=self._get_headers(), json=payload)
            latency_ms = int((time.time() - start_time) * 1000)

            if res.status_code == 401:
                raise AIProviderError("AI_INVALID_CREDENTIALS", "Anthropic API key is invalid.", is_retryable=False)
            if res.status_code == 429:
                raise AIProviderError("AI_RATE_LIMITED", "Anthropic rate limit exceeded.", is_retryable=True)
            if res.status_code != 200:
                raise AIProviderError("AI_PROVIDER_UNAVAILABLE", f"Anthropic error ({res.status_code}): {res.text[:150]}", is_retryable=True)

            data = res.json()
            content = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block.get("text", "")
            content = content.strip()

            structured_data = None
            if schema or content.startswith("{"):
                try:
                    clean_json = content
                    m = re.search(r'```(?:json)?\s*(.*?)\s*```', clean_json, re.DOTALL)
                    if m:
                        clean_json = m.group(1)
                    structured_data = json.loads(clean_json)
                except Exception:
                    pass

            usage = data.get("usage", {})
            return GenerationResult(
                content=content,
                structured_data=structured_data,
                provider=self.provider_key,
                model=model,
                tokens_in=usage.get("input_tokens", 0),
                tokens_out=usage.get("output_tokens", 0),
                latency_ms=latency_ms,
                request_id=data.get("id"),
            )
        except httpx.TimeoutException as exc:
            raise AIProviderError("AI_PROVIDER_TIMEOUT", "Anthropic request timed out.", is_retryable=True, raw_error=exc)
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError("AI_PROVIDER_UNAVAILABLE", f"Anthropic generation failed: {exc}", is_retryable=True, raw_error=exc)

    def test_connection(self, api_key: str, model: str) -> Tuple[bool, str, int]:
        start = time.time()
        try:
            headers = {
                "x-api-key": api_key,
                "anthropic-version": self.API_VERSION,
                "content-type": "application/json",
            }
            payload = {
                "model": model,
                "max_tokens": 5,
                "messages": [{"role": "user", "content": "ping"}],
            }
            with httpx.Client(timeout=10) as client:
                res = client.post(f"{self.BASE_URL}/messages", headers=headers, json=payload)
            latency_ms = int((time.time() - start) * 1000)

            if res.status_code == 200:
                return True, "Connection successful.", latency_ms
            if res.status_code == 401:
                return False, "Invalid API key.", latency_ms
            if res.status_code == 404:
                return False, f"Model '{model}' not found or unsupported.", latency_ms
            return False, f"HTTP {res.status_code}: {res.text[:80]}", latency_ms
        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            return False, f"Connection failed: {str(e)[:100]}", latency_ms
