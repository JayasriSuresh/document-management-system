"""
Module 10 — Centralized AI Execution Service.

Coordinates:
1. Multi-tier resolution (Platform -> Company -> Branch).
2. Explicit provider consent verification.
3. Concurrency-safe company AI budget reservation and settlement.
4. Provider execution (Gemini, OpenAI GPT, Anthropic Claude).
5. Automatic fallback to secondary provider on primary failure.
6. Attempt-level persistent logging in `ai_processing_logs`.
7. Tamper-resistant audit events for budget and connection tests.
"""

import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple, Union
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models import (
    Company, Branch, AIProcessingLog, ProcessingJob, Document, AIUsageLedger
)
from app.services.currency_service import get_usd_to_inr_rate, convert_usd_cents_to_inr
from app.ai.base import (
    AIProvider, ExtractionResult, GenerationResult, AIProviderError
)
from app.ai.pricing import calculate_cost_cents
from app.ai.gemini import GeminiProvider
from app.ai.openai_provider import OpenAIProvider
from app.ai.claude import ClaudeProvider
from app.ai.resolver import (
    resolve_ai_config, resolve_credential, ResolvedAIConfig, ResolvedProviderDetails
)
from app.audit import audit, AI_BUDGET_EXHAUSTED, AI_CONNECTION_TEST

logger = logging.getLogger("dms.ai.service")


class AIExecutionService:
    """Centralized service for multi-provider AI document extraction and generation."""

    @staticmethod
    def get_provider_adapter(provider_key: str, api_key: str, model: str) -> AIProvider:
        """Factory method returning initialized AIProvider adapter."""
        key = provider_key.lower().strip()
        if key == "gemini":
            return GeminiProvider(api_key=api_key, default_model=model)
        elif key == "openai":
            return OpenAIProvider(api_key=api_key, default_model=model)
        elif key == "anthropic":
            return ClaudeProvider(api_key=api_key, default_model=model)
        else:
            raise AIProviderError(
                "UNSUPPORTED_PROVIDER",
                f"Provider '{provider_key}' is not supported by the platform.",
                is_retryable=False,
            )

    @classmethod
    def _check_and_reserve_budget(
        cls,
        db: Session,
        company_id: int,
        estimated_cents: int = 5,
    ) -> Company:
        """
        Concurrency-safe budget check using row-level locking (SELECT ... FOR UPDATE).
        Prevents race conditions from exceeding company monthly AI budget.
        """
        company = (
            db.query(Company)
            .filter(Company.id == company_id)
            .with_for_update()
            .first()
        )
        if not company:
            raise AIProviderError("COMPANY_NOT_FOUND", f"Company #{company_id} not found.", is_retryable=False)

        monthly_limit = company.monthly_ai_budget_cents
        current_spent = company.ai_budget_spent_cents or 0

        if monthly_limit is not None and monthly_limit > 0:
            if current_spent + estimated_cents > monthly_limit:
                # Log audit event for exhausted budget
                try:
                    audit.record(
                        db=db,
                        action=AI_BUDGET_EXHAUSTED,
                        actor_type="system",
                        company_id=company_id,
                        object_type="company",
                        object_id=company_id,
                        metadata={"description": f"Monthly AI budget exhausted ({current_spent}/{monthly_limit} cents). Execution blocked."},
                    )
                except Exception as audit_err:
                    logger.warning("Failed to record AI_BUDGET_EXHAUSTED audit log: %s", audit_err)

                raise AIProviderError(
                    "AI_BUDGET_EXHAUSTED",
                    f"Company monthly AI budget of ${monthly_limit / 100:.2f} has been reached or exceeded.",
                    is_retryable=False,
                )

        db.commit()
        return company

    @classmethod
    def _settle_budget(
        cls,
        db: Session,
        company_id: int,
        cost_cents: int,
    ) -> None:
        """Settle and commit incurred cost to company monthly spend in USD and reporting INR."""
        if cost_cents <= 0:
            return
        company = (
            db.query(Company)
            .filter(Company.id == company_id)
            .with_for_update()
            .first()
        )
        if company:
            company.ai_budget_spent_cents = (company.ai_budget_spent_cents or 0) + cost_cents
            rate = get_usd_to_inr_rate(db)
            inr_cost = convert_usd_cents_to_inr(cost_cents, rate)
            company.ai_budget_spent_inr = round(float(company.ai_budget_spent_inr or 0.0) + inr_cost, 4)
            db.commit()

    @classmethod
    def _log_attempt(
        cls,
        db: Session,
        company_id: int,
        branch_id: Optional[int],
        document_id: Optional[int],
        job_id: Optional[int],
        operation: str,
        provider: str,
        model: str,
        is_fallback: bool,
        attempt_number: int,
        tokens_in: int,
        tokens_out: int,
        cost_cents: int,
        latency_ms: int,
        success: bool,
        error_code: Optional[str] = None,
    ) -> AIProcessingLog:
        """
        Persist attempt log row into ai_processing_logs with dual currency INR conversion snapshot,
        and synchronize with ai_usage_ledger.
        """
        rate = get_usd_to_inr_rate(db)
        cost_inr = convert_usd_cents_to_inr(cost_cents or 0, rate)
        now = datetime.utcnow()

        log_entry = AIProcessingLog(
            company_id=company_id,
            branch_id=branch_id,
            document_id=document_id,
            job_id=job_id,
            operation=operation,
            provider=provider,
            model=model,
            is_fallback=is_fallback,
            attempt_number=attempt_number,
            tokens_in=tokens_in or 0,
            tokens_out=tokens_out or 0,
            cost_cents=cost_cents or 0,
            cost_inr=cost_inr,
            exchange_rate=rate,
            converted_at=now,
            currency="INR",
            latency_ms=latency_ms or 0,
            success=success,
            error_code=error_code,
        )
        try:
            db.add(log_entry)
            if success:
                ledger_entry = AIUsageLedger(
                    company_id=company_id,
                    branch_id=branch_id or 1,
                    provider=provider,
                    model=model,
                    operation=operation,
                    tokens_in=tokens_in or 0,
                    tokens_out=tokens_out or 0,
                    cost_cents=cost_cents or 0,
                    cost_inr=cost_inr,
                    exchange_rate=rate,
                    converted_at=now,
                    currency="INR",
                    status="success" if success else "failed",
                )
                db.add(ledger_entry)
            db.commit()
            db.refresh(log_entry)
        except Exception as e:
            logger.error("Failed to persist AI processing log: %s", e)
            db.rollback()
        return log_entry

    @classmethod
    def extract_document(
        cls,
        db: Session,
        company_id: int,
        branch_id: int,
        images: List[bytes],
        mime_type: str = "image/jpeg",
        schema: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None,
        document_id: Optional[int] = None,
        job_id: Optional[int] = None,
        operation: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Execute document extraction through the configured provider hierarchy.
        Supports automatic fallback, token tracking, budget settlement, and logging.
        """
        op = operation or ("extraction" if schema else "ocr")
        # 1. Resolve configuration & credentials
        config = resolve_ai_config(db, company_id=company_id, branch_id=branch_id, operation=op)

        # 2. Check budget reservation
        cls._check_and_reserve_budget(db, company_id=company_id, estimated_cents=5)

        primary_details = config.primary
        fallback_details = config.fallback

        # 3. Attempt Primary Provider
        primary_adapter = cls.get_provider_adapter(
            provider_key=primary_details.provider_key,
            api_key=primary_details.api_key,
            model=primary_details.model,
        )

        primary_error: Optional[Exception] = None
        result: Optional[ExtractionResult] = None

        try:
            result = primary_adapter.extract(
                images=images,
                mime_type=mime_type,
                schema=schema,
                prompt=prompt,
                config={"timeout": primary_details.timeout_seconds},
            )
        except Exception as exc:
            primary_error = exc

        # Check if primary succeeded
        if result and result.is_success:
            cost = calculate_cost_cents(result.model, result.tokens_in or 0, result.tokens_out or 0)
            cls._log_attempt(
                db=db,
                company_id=company_id,
                branch_id=branch_id,
                document_id=document_id,
                job_id=job_id,
                operation=op,
                provider=result.provider,
                model=result.model,
                is_fallback=False,
                attempt_number=1,
                tokens_in=result.tokens_in or 0,
                tokens_out=result.tokens_out or 0,
                cost_cents=cost,
                latency_ms=result.latency_ms,
                success=True,
                error_code=None,
            )
            cls._settle_budget(db, company_id=company_id, cost_cents=cost)
            return result

        # Primary failed: record failure attempt
        err_code = "PRIMARY_EXTRACTION_FAILED"
        err_msg = str(primary_error) if primary_error else (result.error_message if result else "Unknown primary error")
        if isinstance(primary_error, AIProviderError):
            err_code = primary_error.error_code

        cls._log_attempt(
            db=db,
            company_id=company_id,
            branch_id=branch_id,
            document_id=document_id,
            job_id=job_id,
            operation=op,
            provider=primary_details.provider_key,
            model=primary_details.model,
            is_fallback=False,
            attempt_number=1,
            tokens_in=result.tokens_in if result else 0,
            tokens_out=result.tokens_out if result else 0,
            cost_cents=0,
            latency_ms=result.latency_ms if result else 0,
            success=False,
            error_code=err_code,
        )

        logger.warning(
            "Primary AI provider '%s' failed for Company #%s, Branch #%s: %s (%s). Checking fallback.",
            primary_details.provider_key, company_id, branch_id, err_msg, err_code
        )

        # 4. Attempt Fallback Provider if configured
        if fallback_details and fallback_details.provider_key != primary_details.provider_key:
            try:
                fallback_adapter = cls.get_provider_adapter(
                    provider_key=fallback_details.provider_key,
                    api_key=fallback_details.api_key,
                    model=fallback_details.model,
                )
                fb_result = fallback_adapter.extract(
                    images=images,
                    mime_type=mime_type,
                    schema=schema,
                    prompt=prompt,
                    config={"timeout": fallback_details.timeout_seconds},
                )
                if fb_result and fb_result.is_success:
                    fb_cost = calculate_cost_cents(fb_result.model, fb_result.tokens_in or 0, fb_result.tokens_out or 0)
                    cls._log_attempt(
                        db=db,
                        company_id=company_id,
                        branch_id=branch_id,
                        document_id=document_id,
                        job_id=job_id,
                        operation=op,
                        provider=fb_result.provider,
                        model=fb_result.model,
                        is_fallback=True,
                        attempt_number=2,
                        tokens_in=fb_result.tokens_in or 0,
                        tokens_out=fb_result.tokens_out or 0,
                        cost_cents=fb_cost,
                        latency_ms=fb_result.latency_ms,
                        success=True,
                        error_code=None,
                    )
                    cls._settle_budget(db, company_id=company_id, cost_cents=fb_cost)
                    return fb_result
                else:
                    fb_err_code = fb_result.error_code if fb_result else "FALLBACK_FAILED"
                    cls._log_attempt(
                        db=db,
                        company_id=company_id,
                        branch_id=branch_id,
                        document_id=document_id,
                        job_id=job_id,
                        operation=op,
                        provider=fallback_details.provider_key,
                        model=fallback_details.model,
                        is_fallback=True,
                        attempt_number=2,
                        tokens_in=0,
                        tokens_out=0,
                        cost_cents=0,
                        latency_ms=fb_result.latency_ms if fb_result else 0,
                        success=False,
                        error_code=fb_err_code,
                    )
            except Exception as fb_exc:
                logger.error("Fallback AI provider '%s' failed: %s", fallback_details.provider_key, fb_exc)
                fb_code = fb_exc.error_code if isinstance(fb_exc, AIProviderError) else "FALLBACK_EXCEPTION"
                cls._log_attempt(
                    db=db,
                    company_id=company_id,
                    branch_id=branch_id,
                    document_id=document_id,
                    job_id=job_id,
                    operation=op,
                    provider=fallback_details.provider_key,
                    model=fallback_details.model,
                    is_fallback=True,
                    attempt_number=2,
                    tokens_in=0,
                    tokens_out=0,
                    cost_cents=0,
                    latency_ms=0,
                    success=False,
                    error_code=fb_code,
                )

        # Neither succeeded: raise normalized AIProviderError
        if primary_error:
            if isinstance(primary_error, AIProviderError):
                raise primary_error
            raise AIProviderError("AI_EXTRACTION_FAILED", f"Document extraction failed: {err_msg}", is_retryable=True, raw_error=primary_error)
        raise AIProviderError(err_code, f"Document extraction failed: {err_msg}", is_retryable=True)

    @classmethod
    def generate_document(
        cls,
        db: Session,
        company_id: int,
        branch_id: int,
        input_data: Any,
        schema: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        job_id: Optional[int] = None,
    ) -> GenerationResult:
        """
        Execute document/invoice generation through the configured provider hierarchy.
        Supports automatic fallback, token tracking, budget settlement, and logging.
        """
        # 1. Resolve configuration & credentials
        config = resolve_ai_config(db, company_id=company_id, branch_id=branch_id, operation="generate")

        # 2. Check budget reservation
        cls._check_and_reserve_budget(db, company_id=company_id, estimated_cents=5)

        primary_details = config.primary
        fallback_details = config.fallback

        # 3. Attempt Primary Provider
        primary_adapter = cls.get_provider_adapter(
            provider_key=primary_details.provider_key,
            api_key=primary_details.api_key,
            model=primary_details.model,
        )

        primary_error: Optional[Exception] = None
        result: Optional[GenerationResult] = None

        try:
            result = primary_adapter.generate(
                input_data=input_data,
                schema=schema,
                system_prompt=system_prompt,
                config={"timeout": primary_details.timeout_seconds},
            )
        except Exception as exc:
            primary_error = exc

        if result and result.is_success:
            cost = calculate_cost_cents(result.model, result.tokens_in or 0, result.tokens_out or 0)
            cls._log_attempt(
                db=db,
                company_id=company_id,
                branch_id=branch_id,
                document_id=None,
                job_id=job_id,
                operation="generate",
                provider=result.provider,
                model=result.model,
                is_fallback=False,
                attempt_number=1,
                tokens_in=result.tokens_in or 0,
                tokens_out=result.tokens_out or 0,
                cost_cents=cost,
                latency_ms=result.latency_ms,
                success=True,
                error_code=None,
            )
            cls._settle_budget(db, company_id=company_id, cost_cents=cost)
            return result

        err_code = "PRIMARY_GENERATION_FAILED"
        err_msg = str(primary_error) if primary_error else (result.error_message if result else "Unknown generation error")
        if isinstance(primary_error, AIProviderError):
            err_code = primary_error.error_code

        cls._log_attempt(
            db=db,
            company_id=company_id,
            branch_id=branch_id,
            document_id=None,
            job_id=job_id,
            operation="generate",
            provider=primary_details.provider_key,
            model=primary_details.model,
            is_fallback=False,
            attempt_number=1,
            tokens_in=result.tokens_in if result else 0,
            tokens_out=result.tokens_out if result else 0,
            cost_cents=0,
            latency_ms=result.latency_ms if result else 0,
            success=False,
            error_code=err_code,
        )

        logger.warning(
            "Primary generation provider '%s' failed for Company #%s, Branch #%s: %s (%s). Checking fallback.",
            primary_details.provider_key, company_id, branch_id, err_msg, err_code
        )

        # 4. Attempt Fallback Provider if configured
        if fallback_details and fallback_details.provider_key != primary_details.provider_key:
            try:
                fallback_adapter = cls.get_provider_adapter(
                    provider_key=fallback_details.provider_key,
                    api_key=fallback_details.api_key,
                    model=fallback_details.model,
                )
                fb_result = fallback_adapter.generate(
                    input_data=input_data,
                    schema=schema,
                    system_prompt=system_prompt,
                    config={"timeout": fallback_details.timeout_seconds},
                )
                if fb_result and fb_result.is_success:
                    fb_cost = calculate_cost_cents(fb_result.model, fb_result.tokens_in or 0, fb_result.tokens_out or 0)
                    cls._log_attempt(
                        db=db,
                        company_id=company_id,
                        branch_id=branch_id,
                        document_id=None,
                        job_id=job_id,
                        operation="generate",
                        provider=fb_result.provider,
                        model=fb_result.model,
                        is_fallback=True,
                        attempt_number=2,
                        tokens_in=fb_result.tokens_in or 0,
                        tokens_out=fb_result.tokens_out or 0,
                        cost_cents=fb_cost,
                        latency_ms=fb_result.latency_ms,
                        success=True,
                        error_code=None,
                    )
                    cls._settle_budget(db, company_id=company_id, cost_cents=fb_cost)
                    return fb_result
                else:
                    fb_err_code = fb_result.error_code if fb_result else "FALLBACK_FAILED"
                    cls._log_attempt(
                        db=db,
                        company_id=company_id,
                        branch_id=branch_id,
                        document_id=None,
                        job_id=job_id,
                        operation="generate",
                        provider=fallback_details.provider_key,
                        model=fallback_details.model,
                        is_fallback=True,
                        attempt_number=2,
                        tokens_in=0,
                        tokens_out=0,
                        cost_cents=0,
                        latency_ms=fb_result.latency_ms if fb_result else 0,
                        success=False,
                        error_code=fb_err_code,
                    )
            except Exception as fb_exc:
                logger.error("Fallback AI provider '%s' failed for generation: %s", fallback_details.provider_key, fb_exc)
                fb_code = fb_exc.error_code if isinstance(fb_exc, AIProviderError) else "FALLBACK_EXCEPTION"
                cls._log_attempt(
                    db=db,
                    company_id=company_id,
                    branch_id=branch_id,
                    document_id=None,
                    job_id=job_id,
                    operation="generate",
                    provider=fallback_details.provider_key,
                    model=fallback_details.model,
                    is_fallback=True,
                    attempt_number=2,
                    tokens_in=0,
                    tokens_out=0,
                    cost_cents=0,
                    latency_ms=0,
                    success=False,
                    error_code=fb_code,
                )

        if primary_error:
            if isinstance(primary_error, AIProviderError):
                raise primary_error
            raise AIProviderError("AI_GENERATION_FAILED", f"Document generation failed: {err_msg}", is_retryable=True, raw_error=primary_error)
        raise AIProviderError(err_code, f"Document generation failed: {err_msg}", is_retryable=True)

    @classmethod
    def test_provider_connection(
        cls,
        db: Session,
        provider_key: str,
        model: str,
        company_id: Optional[int] = None,
        branch_id: Optional[int] = None,
        api_key: Optional[str] = None,
        actor_user_id: Optional[int] = None,
    ) -> Tuple[bool, str, int]:
        """
        Perform a safe, live connection test without submitting user documents.
        Logs an audit event on execution.
        Returns (success: bool, sanitized_message: str, latency_ms: int).
        """
        # Resolve API key if not supplied
        if not api_key:
            api_key, _ = resolve_credential(db, provider_key, company_id or 0, branch_id or 0)

        if not api_key:
            return False, f"No active credential configured for AI provider '{provider_key}'.", 0

        try:
            adapter = cls.get_provider_adapter(provider_key=provider_key, api_key=api_key, model=model)
            success, message, latency = adapter.test_connection(api_key=api_key, model=model)
        except Exception as exc:
            success = False
            message = str(exc)
            latency = 0

        # Record audit event
        try:
            audit.record(
                db=db,
                action=AI_CONNECTION_TEST,
                actor_type="company_admin" if company_id else "master_admin",
                actor_id=actor_user_id,
                company_id=company_id,
                object_type="ai_provider",
                object_id=0,
                metadata={"description": f"AI connection test for '{provider_key}' model '{model}': {'SUCCESS' if success else 'FAILED'} ({latency}ms)."},
            )
        except Exception as audit_err:
            logger.warning("Failed to record AI_CONNECTION_TEST audit log: %s", audit_err)

        return success, message, latency
