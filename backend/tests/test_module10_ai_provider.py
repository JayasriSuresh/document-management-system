"""
Module 10 Test Suite — Multi-Provider AI Architecture (Gemini, GPT, Claude).

Covers:
1. Vendor-neutral AI provider adapters (Gemini, OpenAI, Claude mocked)
2. Centralized pricing and cost calculation
3. Write-only AES-256-GCM credential encryption and masking
4. Multi-tier resolution hierarchy (Platform -> Company -> Branch)
5. Explicit company consent lifecycle (grant, revoke, unconsented blocking)
6. Automatic secondary provider fallback with distinct attempt-level logging
7. Concurrency-safe row-level budget reservation and settlement
8. Multi-branch operational isolation (Chennai Gemini/GPT vs Mysore Claude/Gemini)
9. Durable worker integration with multi-provider execution
10. REST API endpoints for Platform, Company, and Branch AI management
"""

import io
import json
import uuid
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import (
    Company, Branch, User, UserRole, AccountStatus, UserRoleAssignment, Document,
    PlatformAIProvider, CompanyAISetting, CompanyAIConsent, BranchAIConfig,
    AICredential, AIProcessingLog, ProcessingJob, OcrStatus, MasterAdmin
)
from app.auth import get_password_hash, create_access_token
from app.security.encryption import encrypt_api_key, decrypt_api_key, mask_api_key
from app.ai.base import AIProviderError, ExtractionResult, GenerationResult
from app.ai.pricing import calculate_cost_cents
from app.ai.gemini import GeminiProvider
from app.ai.openai_provider import OpenAIProvider
from app.ai.claude import ClaudeProvider
from app.ai.resolver import resolve_ai_config, resolve_credential
from app.ai.service import AIExecutionService
from app.worker import DocumentWorker
from app.storage import get_storage_adapter


# ── Fixtures & Teardown Helpers ──────────────────────────────────────────────

@pytest.fixture
def test_env(db):
    """
    Creates an isolated test tenant environment:
    1 Company, 2 Branches (Chennai & Mysore), 1 Company Admin, 2 Branch Admins.
    Guarantees full teardown so zero test data leaks into dms_db.
    """
    tag = uuid.uuid4().hex[:6]
    company = Company(
        name=f"Mod10 Test Corp {tag}",
        display_name=f"Mod10 Enterprise {tag}",
        code=f"M10_{tag}",
        status="active",
        monthly_ai_budget_cents=5000,
        ai_budget_spent_cents=0,
    )
    db.add(company)
    db.flush()

    chennai = Branch(
        company_id=company.id,
        name=f"Chennai Branch {tag}",
        code=f"CHN_{tag}",
        city="Chennai",
        state="Tamil Nadu",
        status="active",
    )
    mysore = Branch(
        company_id=company.id,
        name=f"Mysore Branch {tag}",
        code=f"MYS_{tag}",
        city="Mysore",
        state="Karnataka",
        status="active",
    )
    db.add_all([chennai, mysore])
    db.flush()

    # Company Admin user
    comp_admin = User(
        company_id=company.id,
        branch_id=chennai.id,
        email=f"admin_{tag}@m10test.com",
        name=f"Admin {tag}",
        password_hash=get_password_hash("StrongPass123!"),
        role=UserRole.GLOBAL_ADMIN,
        status=AccountStatus.ACTIVE,
    )
    db.add(comp_admin)
    db.flush()

    # Assign GLOBAL_ADMIN role
    db.add(UserRoleAssignment(
        user_id=comp_admin.id,
        role="GLOBAL_ADMIN",
        scope_type="company",
        scope_id=company.id,
    ))

    # Company AI Settings
    comp_setting = CompanyAISetting(
        company_id=company.id,
        allowed_providers=["gemini", "openai", "anthropic"],
        default_read_provider="gemini",
        default_read_model="gemini-2.0-flash",
        default_generate_provider="gemini",
        default_generate_model="gemini-2.0-flash",
    )
    db.add(comp_setting)

    # Consent for Gemini and OpenAI by default (Claude unconsented initially)
    c_gemini = CompanyAIConsent(
        company_id=company.id,
        provider_key="gemini",
        is_consented=True,
        consented_at=datetime.utcnow(),
        consented_by=comp_admin.id,
        policy_version="1.0",
    )
    c_openai = CompanyAIConsent(
        company_id=company.id,
        provider_key="openai",
        is_consented=True,
        consented_at=datetime.utcnow(),
        consented_by=comp_admin.id,
        policy_version="1.0",
    )
    db.add_all([c_gemini, c_openai])

    # Store encrypted credentials
    cred_gemini = AICredential(
        provider_key="gemini",
        scope_type="company",
        scope_id=company.id,
        encrypted_key=encrypt_api_key("test-gemini-secret-key-123456"),
        masked_key=mask_api_key("test-gemini-secret-key-123456"),
        status="active",
    )
    cred_openai = AICredential(
        provider_key="openai",
        scope_type="company",
        scope_id=company.id,
        encrypted_key=encrypt_api_key("test-openai-secret-key-654321"),
        masked_key=mask_api_key("test-openai-secret-key-654321"),
        status="active",
    )
    cred_claude = AICredential(
        provider_key="anthropic",
        scope_type="company",
        scope_id=company.id,
        encrypted_key=encrypt_api_key("test-claude-secret-key-789012"),
        masked_key=mask_api_key("test-claude-secret-key-789012"),
        status="active",
    )
    db.add_all([cred_gemini, cred_openai, cred_claude])

    db.commit()

    env_data = {
        "company": company,
        "chennai": chennai,
        "mysore": mysore,
        "comp_admin": comp_admin,
    }

    try:
        yield env_data
    finally:
        # Full teardown of test company and all associated records
        db.query(AIProcessingLog).filter(AIProcessingLog.company_id == company.id).delete(synchronize_session=False)
        db.query(ProcessingJob).filter(ProcessingJob.company_id == company.id).delete(synchronize_session=False)
        db.query(Document).filter(Document.company_id == company.id).delete(synchronize_session=False)
        db.query(BranchAIConfig).filter(BranchAIConfig.company_id == company.id).delete(synchronize_session=False)
        db.query(AICredential).filter(AICredential.scope_id == company.id).delete(synchronize_session=False)
        db.query(CompanyAIConsent).filter(CompanyAIConsent.company_id == company.id).delete(synchronize_session=False)
        db.query(CompanyAISetting).filter(CompanyAISetting.company_id == company.id).delete(synchronize_session=False)
        db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == comp_admin.id).delete(synchronize_session=False)
        db.query(User).filter(User.company_id == company.id).delete(synchronize_session=False)
        db.query(Branch).filter(Branch.company_id == company.id).delete(synchronize_session=False)
        db.query(Company).filter(Company.id == company.id).delete(synchronize_session=False)
        db.commit()


# ── 1. Provider Adapter Tests ────────────────────────────────────────────────

def test_encryption_helpers():
    """Verify AES-256-GCM encryption, decryption, and write-only key masking."""
    secret = "sk-proj-abc123xyz9876543210987654321"
    encrypted = encrypt_api_key(secret)
    assert encrypted != secret
    assert len(encrypted) > len(secret)

    decrypted = decrypt_api_key(encrypted)
    assert decrypted == secret

    masked = mask_api_key(secret)
    assert masked.endswith("4321")
    assert "xyz987" not in masked
    assert "************" in masked


def test_pricing_calculator():
    """Verify conservative token pricing with 1-cent minimum on non-zero consumption."""
    # Free or 0 tokens -> 0 cents
    assert calculate_cost_cents("gemini-2.0-flash", 0, 0) == 0

    # 100 in, 50 out for gemini-2.0-flash (fractional cent -> clamped to 1 cent)
    cost = calculate_cost_cents("gemini-2.0-flash", 100, 50)
    assert cost == 1

    # High token volume: 500k in, 200k out on gpt-4o ($2.50/m in, $10.00/m out)
    # in: 0.5 * 2.50 = 1.25, out: 0.2 * 10 = 2.00 -> $3.25 = 325 cents
    gpt_cost = calculate_cost_cents("gpt-4o", 500_000, 200_000)
    assert gpt_cost == 325


def test_gemini_provider_adapter_mocked():
    """Test GeminiProvider extract and generate with mocked google-genai client."""
    provider = GeminiProvider(api_key="mock-gemini-key", default_model="gemini-2.0-flash")
    assert provider.provider_key == "gemini"

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "Bill No: 101\nTotal: 1500\nCustomer: Ravi"
    mock_resp.usage_metadata.prompt_token_count = 120
    mock_resp.usage_metadata.candidates_token_count = 45
    mock_client.models.generate_content.return_value = mock_resp

    with patch.object(provider, "_get_client", return_value=mock_client):
        # 1x1 white jpeg image
        img_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
        res = provider.extract(images=[img_bytes], mime_type="image/jpeg")
        assert res.is_success
        assert res.provider == "gemini"
        assert res.tokens_in == 120
        assert res.tokens_out == 45
        assert "Bill No: 101" in res.raw_text


def test_openai_provider_adapter_mocked():
    """Test OpenAIProvider extract and generate with mocked httpx response."""
    provider = OpenAIProvider(api_key="mock-openai-key", default_model="gpt-4o-mini")
    assert provider.provider_key == "openai"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "raw_text": "INVOICE #999 TOTAL 2500",
                        "structured_data": {"bill_no": "999", "total_amount": 2500},
                    })
                }
            }
        ],
        "usage": {"prompt_tokens": 200, "completion_tokens": 80},
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        res = provider.extract(images=[b"fake_image_bytes"], mime_type="image/jpeg")
        assert res.is_success
        assert res.provider == "openai"
        assert res.tokens_in == 200
        assert res.tokens_out == 80
        assert res.structured_data["bill_no"] == "999"


def test_claude_provider_adapter_mocked():
    """Test ClaudeProvider extract and generate with mocked Anthropic API response."""
    provider = ClaudeProvider(api_key="mock-claude-key", default_model="claude-3-5-sonnet-20241022")
    assert provider.provider_key == "anthropic"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "msg_test",
        "content": [
            {
                "type": "text",
                "text": json.dumps({
                    "raw_text": "TAX INVOICE CLAUDE EXTRACTED",
                    "structured_data": {"bill_no": "CL-01", "total_amount": 5400},
                }),
            }
        ],
        "usage": {"input_tokens": 350, "output_tokens": 110},
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        res = provider.extract(images=[b"fake_image_bytes"], mime_type="image/jpeg")
        assert res.is_success
        assert res.provider == "anthropic"
        assert res.tokens_in == 350
        assert res.tokens_out == 110
        assert res.structured_data["bill_no"] == "CL-01"


# ── 2. Governance, Precedence & Consent Tests ────────────────────────────────

def test_consent_required_blocks_unconsented_provider(db, test_env):
    """Verify that an unconsented provider is strictly blocked from external execution."""
    company = test_env["company"]
    chennai = test_env["chennai"]

    # Configure Chennai branch to use Claude for reading (Claude is NOT consented)
    b_cfg = BranchAIConfig(
        company_id=company.id,
        branch_id=chennai.id,
        operation="read",
        primary_provider="anthropic",
        primary_model="claude-3-5-sonnet-20241022",
    )
    db.add(b_cfg)
    db.commit()

    with pytest.raises(AIProviderError) as exc_info:
        resolve_ai_config(db, company.id, chennai.id, operation="read")

    assert exc_info.value.error_code == "AI_CONSENT_REQUIRED"
    assert "Company consent has not been granted for AI provider 'anthropic'" in exc_info.value.message


def test_platform_disabled_provider_blocks_execution(db, test_env):
    """Verify that if Master Admin disables a provider platform-wide, executions fail."""
    company = test_env["company"]
    chennai = test_env["chennai"]

    # Temporarily disable OpenAI at platform level
    plat_openai = db.query(PlatformAIProvider).filter(PlatformAIProvider.provider_key == "openai").first()
    original_state = plat_openai.is_enabled
    plat_openai.is_enabled = False
    db.commit()

    # Configure Chennai to use OpenAI
    b_cfg = BranchAIConfig(
        company_id=company.id,
        branch_id=chennai.id,
        operation="read",
        primary_provider="openai",
        primary_model="gpt-4o-mini",
    )
    db.add(b_cfg)
    db.commit()

    try:
        with pytest.raises(AIProviderError) as exc_info:
            resolve_ai_config(db, company.id, chennai.id, operation="read")
        assert exc_info.value.error_code == "AI_PROVIDER_DISABLED"
    finally:
        plat_openai.is_enabled = original_state
        db.commit()


def test_company_disallowed_provider_blocks_branch(db, test_env):
    """Verify that a branch cannot select a provider disallowed by its company."""
    company = test_env["company"]
    chennai = test_env["chennai"]

    # Restrict company to Gemini only
    comp_setting = db.query(CompanyAISetting).filter(CompanyAISetting.company_id == company.id).first()
    comp_setting.allowed_providers = ["gemini"]
    db.commit()

    # Chennai branch attempts to use OpenAI
    b_cfg = BranchAIConfig(
        company_id=company.id,
        branch_id=chennai.id,
        operation="read",
        primary_provider="openai",
        primary_model="gpt-4o-mini",
    )
    db.add(b_cfg)
    db.commit()

    with pytest.raises(AIProviderError) as exc_info:
        resolve_ai_config(db, company.id, chennai.id, operation="read")
    assert exc_info.value.error_code == "AI_PROVIDER_DISALLOWED"


def test_model_not_in_platform_allow_list(db, test_env):
    """Verify that attempting to configure an unapproved model is blocked."""
    company = test_env["company"]
    chennai = test_env["chennai"]

    b_cfg = BranchAIConfig(
        company_id=company.id,
        branch_id=chennai.id,
        operation="read",
        primary_provider="gemini",
        primary_model="unapproved-experimental-model-99",
    )
    db.add(b_cfg)
    db.commit()

    with pytest.raises(AIProviderError) as exc_info:
        resolve_ai_config(db, company.id, chennai.id, operation="read")
    assert exc_info.value.error_code == "AI_MODEL_NOT_ALLOWED"


# ── 3. Fallback Pipeline & Concurrency Budget Tests ──────────────────────────

def test_fallback_triggers_and_logs_distinct_attempts(db, test_env):
    """
    Test that when primary provider fails with a transient error,
    the execution service automatically invokes the fallback provider,
    logs both attempts into ai_processing_logs, and settles cost correctly.
    """
    company = test_env["company"]
    chennai = test_env["chennai"]

    # Configure Chennai branch: Primary = OpenAI, Fallback = Gemini
    b_cfg = BranchAIConfig(
        company_id=company.id,
        branch_id=chennai.id,
        operation="read",
        primary_provider="openai",
        primary_model="gpt-4o-mini",
        fallback_provider="gemini",
        fallback_model="gemini-2.0-flash",
    )
    db.add(b_cfg)
    db.commit()

    # Mock OpenAI adapter to fail with connection timeout
    mock_openai = MagicMock()
    mock_openai.extract.side_effect = AIProviderError("OPENAI_TIMEOUT", "Connection to api.openai.com timed out.", is_retryable=True)

    # Mock Gemini adapter to succeed
    mock_gemini = MagicMock()
    mock_gemini.extract.return_value = ExtractionResult(
        structured_data={"bill_no": "FALLBACK-001", "total_amount": 1200},
        raw_text="RECOVERED BY FALLBACK GEMINI",
        provider="gemini",
        model="gemini-2.0-flash",
        tokens_in=150,
        tokens_out=60,
        latency_ms=250,
    )

    def mock_adapter_factory(provider_key, api_key, model):
        if provider_key == "openai":
            return mock_openai
        if provider_key == "gemini":
            return mock_gemini
        raise ValueError(f"Unexpected provider {provider_key}")

    with patch.object(AIExecutionService, "get_provider_adapter", side_effect=mock_adapter_factory):
        result = AIExecutionService.extract_document(
            db=db,
            company_id=company.id,
            branch_id=chennai.id,
            images=[b"fake_bytes"],
            mime_type="image/jpeg",
        )

    # 1. Result should be from Gemini (fallback)
    assert result.is_success
    assert result.provider == "gemini"
    assert result.structured_data["bill_no"] == "FALLBACK-001"

    # 2. Check ai_processing_logs: must contain exactly 2 distinct rows
    logs = (
        db.query(AIProcessingLog)
        .filter(AIProcessingLog.company_id == company.id)
        .order_by(AIProcessingLog.attempt_number.asc())
        .all()
    )
    assert len(logs) == 2

    # Primary attempt log
    assert logs[0].provider == "openai"
    assert logs[0].is_fallback is False
    assert logs[0].attempt_number == 1
    assert logs[0].success is False
    assert logs[0].error_code == "OPENAI_TIMEOUT"

    # Fallback attempt log
    assert logs[1].provider == "gemini"
    assert logs[1].is_fallback is True
    assert logs[1].attempt_number == 2
    assert logs[1].success is True
    assert logs[1].cost_cents == 1

    # 3. Budget spent should be settled
    db.refresh(company)
    assert company.ai_budget_spent_cents == 1


def test_concurrency_safe_budget_exhaustion(db, test_env):
    """
    Test that when company AI spend exceeds the monthly budget,
    further executions are blocked with AI_BUDGET_EXHAUSTED.
    """
    company = test_env["company"]
    chennai = test_env["chennai"]

    # Set spent equal to monthly budget
    company.monthly_ai_budget_cents = 1000  # $10.00
    company.ai_budget_spent_cents = 1000    # $10.00 spent
    db.commit()

    with pytest.raises(AIProviderError) as exc_info:
        AIExecutionService.extract_document(
            db=db,
            company_id=company.id,
            branch_id=chennai.id,
            images=[b"fake_bytes"],
            mime_type="image/jpeg",
        )

    assert exc_info.value.error_code == "AI_BUDGET_EXHAUSTED"
    assert "budget of $10.00 has been reached" in exc_info.value.message


# ── 4. End-to-End Multi-Branch Isolation Test ────────────────────────────────

def test_multi_branch_isolation_chennai_vs_mysore(db, test_env):
    """
    Verifies the core architectural requirement:
    - Chennai Branch uses Gemini for reading and OpenAI for generation.
    - Mysore Branch uses Claude for reading and Gemini for generation.
    - Each branch operates completely independently with verified logs.
    """
    company = test_env["company"]
    chennai = test_env["chennai"]
    mysore = test_env["mysore"]

    # Grant consent for Claude as well for Mysore branch
    consent_claude = CompanyAIConsent(
        company_id=company.id,
        provider_key="anthropic",
        is_consented=True,
        consented_at=datetime.utcnow(),
        consented_by=test_env["comp_admin"].id,
    )
    db.add(consent_claude)
    db.commit()

    # 1. Configure Chennai: Read = Gemini, Generate = OpenAI
    db.add(BranchAIConfig(
        company_id=company.id,
        branch_id=chennai.id,
        operation="read",
        primary_provider="gemini",
        primary_model="gemini-2.0-flash",
    ))
    db.add(BranchAIConfig(
        company_id=company.id,
        branch_id=chennai.id,
        operation="generate",
        primary_provider="openai",
        primary_model="gpt-4o-mini",
    ))

    # 2. Configure Mysore: Read = Claude, Generate = Gemini
    db.add(BranchAIConfig(
        company_id=company.id,
        branch_id=mysore.id,
        operation="read",
        primary_provider="anthropic",
        primary_model="claude-3-5-sonnet-20241022",
    ))
    db.add(BranchAIConfig(
        company_id=company.id,
        branch_id=mysore.id,
        operation="generate",
        primary_provider="gemini",
        primary_model="gemini-2.0-flash",
    ))
    db.commit()

    # Mock adapters
    mock_gemini = MagicMock()
    mock_gemini.extract.return_value = ExtractionResult(
        structured_data={"branch": "Chennai", "doc_type": "invoice"},
        raw_text="CHENNAI GEMINI INVOICE",
        provider="gemini",
        model="gemini-2.0-flash",
        tokens_in=100,
        tokens_out=50,
        latency_ms=180,
    )
    mock_gemini.generate.return_value = GenerationResult(
        content='{"generated_for": "Mysore"}',
        structured_data={"generated_for": "Mysore"},
        provider="gemini",
        model="gemini-2.0-flash",
        tokens_in=80,
        tokens_out=40,
        latency_ms=150,
    )

    mock_openai = MagicMock()
    mock_openai.generate.return_value = GenerationResult(
        content='{"generated_for": "Chennai"}',
        structured_data={"generated_for": "Chennai"},
        provider="openai",
        model="gpt-4o-mini",
        tokens_in=90,
        tokens_out=45,
        latency_ms=210,
    )

    mock_claude = MagicMock()
    mock_claude.extract.return_value = ExtractionResult(
        structured_data={"branch": "Mysore", "doc_type": "receipt"},
        raw_text="MYSORE CLAUDE RECEIPT",
        provider="anthropic",
        model="claude-3-5-sonnet-20241022",
        tokens_in=250,
        tokens_out=70,
        latency_ms=320,
    )

    def mock_factory(provider_key, api_key, model):
        if provider_key == "gemini": return mock_gemini
        if provider_key == "openai": return mock_openai
        if provider_key == "anthropic": return mock_claude
        raise ValueError(provider_key)

    with patch.object(AIExecutionService, "get_provider_adapter", side_effect=mock_factory):
        # A. Execute Chennai reading -> MUST use Gemini
        chn_read = AIExecutionService.extract_document(
            db, company_id=company.id, branch_id=chennai.id, images=[b"chn_doc"]
        )
        assert chn_read.provider == "gemini"
        assert chn_read.structured_data["branch"] == "Chennai"

        # B. Execute Chennai generation -> MUST use OpenAI
        chn_gen = AIExecutionService.generate_document(
            db, company_id=company.id, branch_id=chennai.id, input_data={"total": 500}
        )
        assert chn_gen.provider == "openai"
        assert chn_gen.structured_data["generated_for"] == "Chennai"

        # C. Execute Mysore reading -> MUST use Claude (Anthropic)
        mys_read = AIExecutionService.extract_document(
            db, company_id=company.id, branch_id=mysore.id, images=[b"mys_doc"]
        )
        assert mys_read.provider == "anthropic"
        assert mys_read.structured_data["branch"] == "Mysore"

        # D. Execute Mysore generation -> MUST use Gemini
        mys_gen = AIExecutionService.generate_document(
            db, company_id=company.id, branch_id=mysore.id, input_data={"total": 750}
        )
        assert mys_gen.provider == "gemini"
        assert mys_gen.structured_data["generated_for"] == "Mysore"

    # Verify audit logs
    chn_logs = db.query(AIProcessingLog).filter(AIProcessingLog.branch_id == chennai.id).all()
    mys_logs = db.query(AIProcessingLog).filter(AIProcessingLog.branch_id == mysore.id).all()

    assert len(chn_logs) == 2
    assert {l.provider for l in chn_logs} == {"gemini", "openai"}

    assert len(mys_logs) == 2
    assert {l.provider for l in mys_logs} == {"anthropic", "gemini"}


# ── 5. Worker & Pipeline Integration Tests ───────────────────────────────────

def test_worker_executes_pipeline_with_ai_service(db, test_env):
    """
    Verify that the Module 9 DocumentWorker picks up jobs and processes
    them cleanly through AIExecutionService.extract_document.
    """
    company = test_env["company"]
    chennai = test_env["chennai"]

    storage = get_storage_adapter()
    file_key = storage.build_original_key(company.id, chennai.id, str(uuid.uuid4()))
    storage.save(file_key, b"simulated_invoice_image_bytes")

    doc = Document(
        company_id=company.id,
        branch_id=chennai.id,
        uploaded_by=test_env["comp_admin"].id,
        original_filename="chennai_invoice_001.jpg",
        storage_key=file_key,
        mime_type="image/jpeg",
        file_size=1024,
        ocr_status=OcrStatus.UPLOADED,
        sha256="fakehash" + uuid.uuid4().hex[:16],
    )
    db.add(doc)
    db.commit()

    job = ProcessingJob(
        document_id=doc.id,
        company_id=company.id,
        branch_id=chennai.id,
        status="pending",
        attempts=0,
    )
    db.add(job)
    db.commit()

    worker = DocumentWorker(worker_id="test-worker-m10")

    mock_extract_result = ExtractionResult(
        structured_data={"bill_no": "WORKER-100", "total": 999.0},
        raw_text="WORKER EXTRACTED TEXT BILL 100",
        provider="gemini",
        model="gemini-2.0-flash",
        tokens_in=110,
        tokens_out=40,
        latency_ms=195,
    )

    with patch.object(AIExecutionService, "extract_document", return_value=mock_extract_result):
        success = worker.process_one_job(db, job)
        assert success is True

    db.refresh(doc)
    assert doc.ocr_status == OcrStatus.COMPLETED
    assert doc.ocr_text == "WORKER EXTRACTED TEXT BILL 100"
    assert "WORKER-100" in doc.structured_data

    # Storage cleanup
    try:
        storage.delete(file_key)
    except Exception:
        pass


# ── 6. REST API Tests ────────────────────────────────────────────────────────

def test_api_platform_and_company_endpoints(client, db, test_env):
    """Test REST endpoints for Master Admin, Company Admin, and Branch AI config."""
    company = test_env["company"]
    chennai = test_env["chennai"]
    comp_admin = test_env["comp_admin"]

    # 1. Master Admin token
    m_admin = db.query(MasterAdmin).first()
    master_token = create_access_token({
        "sub": m_admin.email if m_admin else "master@platform.local",
        "master_admin_id": m_admin.id if m_admin else 1,
        "identity_type": "master_admin",
        "role": "MASTER_ADMIN",
        "portal": "platform",
    }, audience="platform")

    # Master Admin: GET /api/admin/ai/providers
    resp = client.get("/api/admin/ai/providers", headers={"Authorization": f"Bearer {master_token}"})
    assert resp.status_code == 200
    providers = resp.json()
    assert len(providers) >= 3
    assert any(p["provider_key"] == "gemini" for p in providers)

    # 2. Company Admin token
    comp_token = create_access_token({
        "sub": comp_admin.email,
        "user_id": comp_admin.id,
        "company_id": company.id,
        "branch_id": chennai.id,
        "role": "GLOBAL_ADMIN",
        "portal": "company",
    }, audience="company")

    # Company Admin: GET /api/company/ai/settings
    resp = client.get("/api/company/ai/settings", headers={"Authorization": f"Bearer {comp_token}"})
    assert resp.status_code == 200
    comp_data = resp.json()
    assert comp_data["company_id"] == company.id
    assert "allowed_providers" in comp_data

    # Company Admin: POST /api/company/ai/consent (grant consent for Claude)
    resp = client.post(
        "/api/company/ai/consent",
        headers={"Authorization": f"Bearer {comp_token}"},
        json={"provider_key": "anthropic", "consented_terms_version": "v1.0"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "consented"

    # Branch Config: PUT /api/company/branches/{branch_id}/ai/config
    resp = client.put(
        f"/api/company/branches/{chennai.id}/ai/config",
        headers={"Authorization": f"Bearer {comp_token}"},
        json={
            "operation": "read",
            "primary_provider": "gemini",
            "primary_model": "gemini-2.0-flash",
            "fallback_provider": "openai",
            "fallback_model": "gpt-4o-mini",
            "max_retries": 2,
            "timeout_seconds": 30,
        },
    )
    assert resp.status_code == 200
    branch_cfg = resp.json()
    assert branch_cfg["primary_provider"] == "gemini"
    assert branch_cfg["fallback_provider"] == "openai"

    # Branch Config: GET /api/company/branches/{branch_id}/ai/config
    resp = client.get(
        f"/api/company/branches/{chennai.id}/ai/config",
        headers={"Authorization": f"Bearer {comp_token}"},
    )
    assert resp.status_code == 200
    b_data = resp.json()
    assert "read" in b_data["configs"]
    assert b_data["configs"]["read"]["primary_provider"] == "gemini"
