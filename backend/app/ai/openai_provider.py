"""
Module 10 — OpenAI GPT Provider Adapter.

Implements the AIProvider interface for OpenAI models (gpt-4o, gpt-4o-mini, etc.)
using direct HTTPX client calls adhering to the official OpenAI /v1/chat/completions API.
Handles vision image inputs via base64 data URLs, JSON schema responses, token usage,
and normalized error mappings.
"""

import base64
import json
import logging
import re
import time
from typing import Dict, Any, Optional, List, Tuple
import httpx

from app.ai.base import AIProvider, ExtractionResult, GenerationResult, AIProviderError

logger = logging.getLogger("dms.ai.openai")


class OpenAIProvider(AIProvider):
    """OpenAI GPT AI Provider."""

    BASE_URL = "https://api.openai.com/v1"

    def __init__(self, api_key: str, default_model: str = "gpt-4o"):
        self.api_key = api_key
        self.default_model = default_model

    @property
    def provider_key(self) -> str:
        return "openai"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
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

        # Build vision content blocks
        user_content: List[Dict[str, Any]] = []
        extract_prompt = prompt or (
            "Extract all text and structured invoice fields from the document image(s). "
            "You MUST respond with strictly valid JSON only. "
            "Expected structure: "
            "{\"seller\": {\"name\": \"\", \"gstin\": \"\", \"address\": \"\"}, "
            "\"buyer\": {\"name\": \"\", \"gstin\": \"\", \"address\": \"\"}, "
            "\"invoice\": {\"number\": \"\", \"date\": \"\"}, "
            "\"totals\": {\"grand_total\": null, \"taxable_value\": null}, "
            "\"items\": [{\"description\": \"\", \"amount\": null}]}"
        )
        user_content.append({"type": "text", "text": extract_prompt})

        for img_bytes in images:
            b64_str = base64.b64encode(img_bytes).decode("utf-8")
            data_url = f"data:{mime_type};base64,{b64_str}"
            user_content.append({
                "type": "image_url",
                "image_url": {"url": data_url}
            })

        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are an automated document and invoice extraction engine. Return valid JSON only."},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        try:
            with httpx.Client(timeout=timeout) as client:
                res = client.post(f"{self.BASE_URL}/chat/completions", headers=self._get_headers(), json=payload)
            latency_ms = int((time.time() - start_time) * 1000)

            if res.status_code == 401:
                raise AIProviderError("AI_INVALID_CREDENTIALS", "OpenAI API key is invalid or unauthorized.", is_retryable=False)
            if res.status_code == 429:
                raise AIProviderError("AI_RATE_LIMITED", "OpenAI rate limit or quota exceeded.", is_retryable=True)
            if res.status_code >= 500:
                raise AIProviderError("AI_PROVIDER_UNAVAILABLE", f"OpenAI server error ({res.status_code}).", is_retryable=True)
            if res.status_code != 200:
                raise AIProviderError("AI_PROVIDER_UNAVAILABLE", f"OpenAI API error ({res.status_code}): {res.text[:200]}", is_retryable=True)

            data = res.json()
            choice = data.get("choices", [{}])[0]
            raw_text = choice.get("message", {}).get("content", "").strip()

            structured_data = {}
            if raw_text:
                try:
                    structured_data = json.loads(raw_text)
                except Exception:
                    m = re.search(r'```(?:json)?\s*(.*?)\s*```', raw_text, re.DOTALL)
                    if m:
                        try:
                            structured_data = json.loads(m.group(1))
                        except Exception:
                            structured_data = {"raw_content": raw_text}

            if isinstance(structured_data, dict) and "structured_data" in structured_data and isinstance(structured_data["structured_data"], dict):
                structured_data = structured_data["structured_data"]

            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens", 0)
            tokens_out = usage.get("completion_tokens", 0)

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
            raise AIProviderError("AI_PROVIDER_TIMEOUT", "OpenAI request timed out.", is_retryable=True, raw_error=exc)
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError("AI_PROVIDER_UNAVAILABLE", f"OpenAI request failed: {exc}", is_retryable=True, raw_error=exc)

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
        messages = [
            {"role": "system", "content": system_prompt or "You are a professional invoice and document generator."},
            {"role": "user", "content": user_content},
        ]
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
        }
        if schema:
            payload["response_format"] = {"type": "json_object"}

        try:
            with httpx.Client(timeout=timeout) as client:
                res = client.post(f"{self.BASE_URL}/chat/completions", headers=self._get_headers(), json=payload)
            latency_ms = int((time.time() - start_time) * 1000)

            if res.status_code == 401:
                raise AIProviderError("AI_INVALID_CREDENTIALS", "OpenAI API key is invalid.", is_retryable=False)
            if res.status_code == 429:
                raise AIProviderError("AI_RATE_LIMITED", "OpenAI rate limit exceeded.", is_retryable=True)
            if res.status_code != 200:
                raise AIProviderError("AI_PROVIDER_UNAVAILABLE", f"OpenAI error ({res.status_code}): {res.text[:150]}", is_retryable=True)

            data = res.json()
            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "").strip()

            structured_data = None
            if schema or content.startswith("{"):
                try:
                    structured_data = json.loads(content)
                except Exception:
                    pass

            usage = data.get("usage", {})
            return GenerationResult(
                content=content,
                structured_data=structured_data,
                provider=self.provider_key,
                model=model,
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
                latency_ms=latency_ms,
                request_id=data.get("id"),
            )
        except httpx.TimeoutException as exc:
            raise AIProviderError("AI_PROVIDER_TIMEOUT", "OpenAI request timed out.", is_retryable=True, raw_error=exc)
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError("AI_PROVIDER_UNAVAILABLE", f"OpenAI generation failed: {exc}", is_retryable=True, raw_error=exc)

    def test_connection(self, api_key: str, model: str) -> Tuple[bool, str, int]:
        start = time.time()
        try:
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            }
            with httpx.Client(timeout=10) as client:
                res = client.post(f"{self.BASE_URL}/chat/completions", headers=headers, json=payload)
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
