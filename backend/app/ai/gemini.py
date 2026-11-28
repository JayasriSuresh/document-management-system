"""
Module 10 — Google Gemini Provider Adapter.

Migrates and centralizes the existing Google Gemini integration into the
unified AIProvider interface. Supports OCR, structured data extraction,
invoice generation, and connection testing.
"""

import io
import json
import logging
import re
import time
from typing import Dict, Any, Optional, List, Tuple
from PIL import Image

from app.ai.base import AIProvider, ExtractionResult, GenerationResult, AIProviderError

logger = logging.getLogger("dms.ai.gemini")


class GeminiProvider(AIProvider):
    """Google Gemini AI Provider."""

    def __init__(self, api_key: str, default_model: str = "gemini-3.6-flash"):
        self.api_key = api_key
        self.default_model = default_model

    @property
    def provider_key(self) -> str:
        return "gemini"

    def _get_client(self):
        try:
            from google import genai
            return genai.Client(api_key=self.api_key)
        except ImportError as e:
            raise AIProviderError("AI_SDK_MISSING", "google-genai SDK is not installed.", is_retryable=False, raw_error=e)
        except Exception as e:
            raise AIProviderError("AI_INVALID_CREDENTIALS", "Failed to initialize Gemini client with provided API key.", is_retryable=False, raw_error=e)

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
        timeout = cfg.get("timeout_seconds", 30)
        start_time = time.time()

        if not images:
            raise AIProviderError("AI_INVALID_INPUT", "No image bytes provided for extraction.", is_retryable=False)

        client = self._get_client()
        pil_images = []
        for img_bytes in images:
            try:
                pil_images.append(Image.open(io.BytesIO(img_bytes)))
            except Exception as e:
                raise AIProviderError("AI_INVALID_INPUT", f"Failed to parse image data: {e}", is_retryable=False, raw_error=e)

        extract_prompt = prompt or (
            "Extract all text and structured invoice fields from this document. "
            "Return valid JSON matching this structure: "
            "{\"seller\": {\"name\": \"\", \"gstin\": \"\", \"address\": \"\"}, "
            "\"buyer\": {\"name\": \"\", \"gstin\": \"\", \"address\": \"\"}, "
            "\"invoice\": {\"number\": \"\", \"date\": \"\"}, "
            "\"totals\": {\"grand_total\": null, \"taxable_value\": null}, "
            "\"items\": [{\"description\": \"\", \"amount\": null}]}"
        )

        try:
            from google.genai import types as genai_types
            gen_config = genai_types.GenerateContentConfig(
                response_mime_type="application/json"
            )
            contents = pil_images + [extract_prompt]
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=gen_config,
            )
            latency_ms = int((time.time() - start_time) * 1000)

            raw_text = response.text.strip() if response and response.text else ""
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

            # Extract token counts if reported
            tokens_in = 0
            tokens_out = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                tokens_in = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                tokens_out = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

            return ExtractionResult(
                structured_data=structured_data,
                raw_text=raw_text,
                provider=self.provider_key,
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
                validation_status="valid" if structured_data else "partial",
            )
        except Exception as exc:
            latency_ms = int((time.time() - start_time) * 1000)
            err_str = str(exc).lower()
            if "quota" in err_str or "429" in err_str or "resource_exhausted" in err_str:
                raise AIProviderError("AI_RATE_LIMITED", "Gemini rate limit or quota exceeded.", is_retryable=True, raw_error=exc)
            if "timeout" in err_str or "deadline" in err_str:
                raise AIProviderError("AI_PROVIDER_TIMEOUT", "Gemini request timed out.", is_retryable=True, raw_error=exc)
            if "api key" in err_str or "401" in err_str or "403" in err_str:
                raise AIProviderError("AI_INVALID_CREDENTIALS", "Gemini API key is invalid or unauthorized.", is_retryable=False, raw_error=exc)
            raise AIProviderError("AI_PROVIDER_UNAVAILABLE", f"Gemini extraction failed: {exc}", is_retryable=True, raw_error=exc)

    def generate(
        self,
        input_data: Any,
        schema: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> GenerationResult:
        cfg = config or {}
        model = cfg.get("model") or self.default_model
        start_time = time.time()
        client = self._get_client()

        user_content = json.dumps(input_data) if isinstance(input_data, (dict, list)) else str(input_data)
        prompt = f"{system_prompt}\n\nInput Data:\n{user_content}" if system_prompt else user_content

        try:
            from google.genai import types as genai_types
            gen_config = genai_types.GenerateContentConfig(
                response_mime_type="application/json" if schema else "text/plain"
            )
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=gen_config,
            )
            latency_ms = int((time.time() - start_time) * 1000)
            content = response.text.strip() if response and response.text else ""

            structured_data = None
            if schema or content.startswith("{") or content.startswith("["):
                try:
                    structured_data = json.loads(content)
                except Exception:
                    pass

            tokens_in = 0
            tokens_out = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                tokens_in = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                tokens_out = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

            return GenerationResult(
                content=content,
                structured_data=structured_data,
                provider=self.provider_key,
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            err_str = str(exc).lower()
            if "quota" in err_str or "429" in err_str:
                raise AIProviderError("AI_RATE_LIMITED", "Gemini rate limit exceeded.", is_retryable=True, raw_error=exc)
            if "timeout" in err_str:
                raise AIProviderError("AI_PROVIDER_TIMEOUT", "Gemini request timed out.", is_retryable=True, raw_error=exc)
            raise AIProviderError("AI_PROVIDER_UNAVAILABLE", f"Gemini generation failed: {exc}", is_retryable=True, raw_error=exc)

    def test_connection(self, api_key: str, model: str) -> Tuple[bool, str, int]:
        start = time.time()
        candidate_models = [model]
        for fallback in ("gemini-3.6-flash", "gemini-flash-latest", "gemini-1.5-flash"):
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        last_error = ""
        for target_model in candidate_models:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                resp = client.models.generate_content(model=target_model, contents="Hello. Respond with OK.")
                latency_ms = int((time.time() - start) * 1000)
                if resp and resp.text:
                    note = f" (via {target_model})" if target_model != model else ""
                    return True, f"Connection successful{note}.", latency_ms
            except Exception as e:
                err = str(e).lower()
                last_error = str(e)
                if "api key" in err or "401" in err or "403" in err or "api_key_invalid" in err:
                    latency_ms = int((time.time() - start) * 1000)
                    return False, "Invalid API key.", latency_ms
                if "404" in err or "not found" in err or "no longer available" in err or "not supported" in err:
                    continue
                if "503" in err or "high demand" in err or "temporar" in err:
                    continue

        latency_ms = int((time.time() - start) * 1000)
        err_lower = last_error.lower()
        if "503" in err_lower or "high demand" in err_lower or "temporar" in err_lower:
            return False, "Gemini API is temporarily experiencing high demand. Please try again shortly.", latency_ms
        if "no longer available" in err_lower or "not supported" in err_lower or "404" in err_lower:
            return False, f"Model '{model}' is not supported or not available.", latency_ms
        return False, f"Connection failed: {last_error[:120]}", latency_ms
