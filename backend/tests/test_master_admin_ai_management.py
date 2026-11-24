"""
Centralized AI Provider and Model Management — Master Admin Control Tests.

Validates:
1. Master Admin Exclusive Authority:
   - AI Providers & Credentials management (encrypted at rest, masked in API)
   - AI Model Catalogue management (CRUD, active toggles, capabilities)
   - Company-Specific AI Model Assignments & Budgets
   - AI Usage & Cost Overview
2. Company Admin Restrictions:
   - 403 Forbidden on Master Admin endpoints
   - 403 Forbidden on API key creation/update or settings overrides
3. Company AI Information & Model Request Workflow:
   - Read-only Company AI Information
   - Model request submission, listing, and cancellation
   - Master Admin approval (with auto-assignment to target task)
   - Master Admin rejection (with recorded reason)
4. Multi-Tenant Isolation:
   - Companies cannot view or modify other companies' requests or assignments
5. AI Execution Enforcement:
   - Resolver enforces company assignment
   - Resolver blocks execution when is_ai_enabled=False
"""

import json
import uuid
from datetime import datetime
import pytest
from fastapi.testclient import TestClient

from app.models import (
    Company, Branch, User, UserRole, AccountStatus, UserRoleAssignment,
    PlatformAIProvider, CompanyAISetting, CompanyAIConsent, AICredential,
    AIModelCatalogue, CompanyAIModelAssignment, CompanyAIModelRequest, MasterAdmin
)
from app.auth import get_password_hash, create_access_token
from app.security.encryption import encrypt_api_key, mask_api_key
from app.ai.resolver import resolve_ai_config
from app.ai.base import AIProviderError


@pytest.fixture
def ai_mgmt_env(db):
    """Set up two isolated companies with branches, admins, and master admin."""
    tag = uuid.uuid4().hex[:6]

    # Ensure MasterAdmin exists
    m_admin = db.query(MasterAdmin).first()
    if not m_admin:
        m_admin = MasterAdmin(
            email=f"master_{tag}@platform.local",
            name="Platform Root Admin",
            password_hash=get_password_hash("MasterAdmin123!"),
            is_active=True,
        )
        db.add(m_admin)
        db.flush()

    master_token = create_access_token({
        "sub": m_admin.email,
        "master_admin_id": m_admin.id,
        "identity_type": "master_admin",
        "role": "MASTER_ADMIN",
        "portal": "platform",
    }, audience="platform")

    # Company A
    comp_a = Company(
        name=f"Enterprise Alpha {tag}",
        display_name=f"Alpha Corp {tag}",
        code=f"ALP_{tag}",
        status="active",
        monthly_ai_budget_cents=5000,
        ai_budget_spent_cents=0,
    )
    # Company B
    comp_b = Company(
        name=f"Enterprise Beta {tag}",
        display_name=f"Beta Corp {tag}",
        code=f"BET_{tag}",
        status="active",
        monthly_ai_budget_cents=2500,
        ai_budget_spent_cents=0,
    )
    db.add_all([comp_a, comp_b])
    db.flush()

    # Branches
    branch_a = Branch(company_id=comp_a.id, name=f"Branch A {tag}", code=f"BA_{tag}", city="Chennai", state="TN", status="active")
    branch_b = Branch(company_id=comp_b.id, name=f"Branch B {tag}", code=f"BB_{tag}", city="Bengaluru", state="KA", status="active")
    db.add_all([branch_a, branch_b])
    db.flush()

    # Company Admins
    admin_a = User(
        company_id=comp_a.id,
        branch_id=branch_a.id,
        email=f"admin_a_{tag}@alpha.com",
        name=f"Admin A {tag}",
        password_hash=get_password_hash("Pass123!"),
        role=UserRole.GLOBAL_ADMIN,
        status=AccountStatus.ACTIVE,
    )
    admin_b = User(
        company_id=comp_b.id,
        branch_id=branch_b.id,
        email=f"admin_b_{tag}@beta.com",
        name=f"Admin B {tag}",
        password_hash=get_password_hash("Pass123!"),
        role=UserRole.GLOBAL_ADMIN,
        status=AccountStatus.ACTIVE,
    )
    db.add_all([admin_a, admin_b])
    db.flush()

    db.add(UserRoleAssignment(user_id=admin_a.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=comp_a.id))
    db.add(UserRoleAssignment(user_id=admin_b.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=comp_b.id))

    # Company Settings & Consents
    setting_a = CompanyAISetting(company_id=comp_a.id, is_ai_enabled=True, allowed_providers=["gemini", "openai", "anthropic"])
    setting_b = CompanyAISetting(company_id=comp_b.id, is_ai_enabled=True, allowed_providers=["gemini"])
    db.add_all([setting_a, setting_b])

    consent_a = CompanyAIConsent(company_id=comp_a.id, provider_key="gemini", is_consented=True, consented_at=datetime.utcnow(), consented_by=admin_a.id, policy_version="1.0")
    consent_b = CompanyAIConsent(company_id=comp_b.id, provider_key="gemini", is_consented=True, consented_at=datetime.utcnow(), consented_by=admin_b.id, policy_version="1.0")
    db.add_all([consent_a, consent_b])

    # Initial model assignment for Company A
    db.add(CompanyAIModelAssignment(company_id=comp_a.id, task_type="ocr", provider_key="gemini", model_id="gemini-2.0-flash", is_enabled=True))
    db.add(CompanyAIModelAssignment(company_id=comp_a.id, task_type="extraction", provider_key="gemini", model_id="gemini-2.0-flash", is_enabled=True))
    db.add(CompanyAIModelAssignment(company_id=comp_a.id, task_type="generation", provider_key="gemini", model_id="gemini-2.0-flash", is_enabled=True))

    db.commit()

    token_a = create_access_token({
        "sub": admin_a.email,
        "user_id": admin_a.id,
        "company_id": comp_a.id,
        "branch_id": branch_a.id,
        "role": "GLOBAL_ADMIN",
        "portal": "company",
    }, audience="company")

    token_b = create_access_token({
        "sub": admin_b.email,
        "user_id": admin_b.id,
        "company_id": comp_b.id,
        "branch_id": branch_b.id,
        "role": "GLOBAL_ADMIN",
        "portal": "company",
    }, audience="company")

    env_data = {
        "master_token": master_token,
        "comp_a": comp_a,
        "comp_b": comp_b,
        "branch_a": branch_a,
        "branch_b": branch_b,
        "admin_a": admin_a,
        "admin_b": admin_b,
        "token_a": token_a,
        "token_b": token_b,
        "m_admin": m_admin,
    }

    try:
        yield env_data
    finally:
        # Teardown
        db.query(CompanyAIModelRequest).filter(CompanyAIModelRequest.company_id.in_([comp_a.id, comp_b.id])).delete(synchronize_session=False)
        db.query(CompanyAIModelAssignment).filter(CompanyAIModelAssignment.company_id.in_([comp_a.id, comp_b.id])).delete(synchronize_session=False)
        db.query(CompanyAIConsent).filter(CompanyAIConsent.company_id.in_([comp_a.id, comp_b.id])).delete(synchronize_session=False)
        db.query(CompanyAISetting).filter(CompanyAISetting.company_id.in_([comp_a.id, comp_b.id])).delete(synchronize_session=False)
        db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id.in_([admin_a.id, admin_b.id])).delete(synchronize_session=False)
        db.query(User).filter(User.company_id.in_([comp_a.id, comp_b.id])).delete(synchronize_session=False)
        db.query(Branch).filter(Branch.company_id.in_([comp_a.id, comp_b.id])).delete(synchronize_session=False)
        db.query(Company).filter(Company.id.in_([comp_a.id, comp_b.id])).delete(synchronize_session=False)
        db.commit()


# ── 1. Master Admin Exclusive Authority ────────────────────────────────────────

def test_master_admin_ai_providers_and_credentials(client: TestClient, ai_mgmt_env, db):
    master_token = ai_mgmt_env["master_token"]
    headers = {"Authorization": f"Bearer {master_token}"}

    # 1. List providers
    res = client.get("/api/admin/ai/providers", headers=headers)
    assert res.status_code == 200
    providers = res.json()
    assert len(providers) >= 3
    assert any(p["provider_key"] == "gemini" for p in providers)

    # 2. Toggle provider status
    res = client.put("/api/admin/ai/providers/gemini", json={"is_enabled": True}, headers=headers)
    assert res.status_code == 200
    assert res.json()["is_enabled"] is True

    # 3. Create or rotate platform encrypted credential
    secret_key = "sk-test-super-secret-master-key-xyz"
    res = client.post("/api/admin/ai/credentials", json={"provider_key": "openai", "api_key": secret_key}, headers=headers)
    assert res.status_code == 200
    cred_data = res.json()
    assert cred_data["provider_key"] == "openai"
    assert cred_data["masked_key"] != secret_key
    assert "xyz" in cred_data["masked_key"]
    assert secret_key not in json.dumps(cred_data)

    # 4. List credentials
    res = client.get("/api/admin/ai/credentials", headers=headers)
    assert res.status_code == 200
    creds = res.json()
    assert any(c["provider_key"] == "openai" for c in creds)

    # Clean up test credential
    cred_id = cred_data["id"]
    res = client.delete(f"/api/admin/ai/credentials/{cred_id}", headers=headers)
    assert res.status_code == 200


def test_master_admin_ai_model_catalogue_crud(client: TestClient, ai_mgmt_env, db):
    master_token = ai_mgmt_env["master_token"]
    headers = {"Authorization": f"Bearer {master_token}"}

    # 1. List catalogue
    res = client.get("/api/admin/ai/models", headers=headers)
    assert res.status_code == 200
    models = res.json()
    assert len(models) >= 8

    # 2. Create new model in catalogue
    model_tag = uuid.uuid4().hex[:6]
    test_model_id = f"gemini-test-exp-{model_tag}"
    new_model_payload = {
        "provider_key": "gemini",
        "model_id": test_model_id,
        "display_name": f"Gemini Exp {model_tag}",
        "capabilities": ["ocr", "extraction"],
        "is_active": True,
        "context_window": 1000000,
        "cost_per_1k_input": 0.0001,
        "cost_per_1k_output": 0.0004,
    }
    res = client.post("/api/admin/ai/models", json=new_model_payload, headers=headers)
    assert res.status_code in (200, 201)
    created = res.json()
    model_pk = created["id"]
    assert created["model_id"] == test_model_id
    assert created["display_name"] == f"Gemini Exp {model_tag}"

    # 3. Update model
    res = client.put(f"/api/admin/ai/models/{model_pk}", json={"display_name": "Gemini Exp Updated", "is_active": False}, headers=headers)
    assert res.status_code == 200
    assert res.json()["display_name"] == "Gemini Exp Updated"
    assert res.json()["is_active"] is False

    # 4. Delete model
    res = client.delete(f"/api/admin/ai/models/{model_pk}", headers=headers)
    assert res.status_code == 200


def test_master_admin_company_assignments_and_budgets(client: TestClient, ai_mgmt_env, db):
    master_token = ai_mgmt_env["master_token"]
    comp_a = ai_mgmt_env["comp_a"]
    headers = {"Authorization": f"Bearer {master_token}"}

    # 1. View all company assignments summary
    res = client.get("/api/admin/ai/company-assignments", headers=headers)
    assert res.status_code == 200
    summaries = res.json()
    assert any(s["company_id"] == comp_a.id for s in summaries)

    # 2. View specific company assignments detail
    res = client.get(f"/api/admin/ai/companies/{comp_a.id}/assignments", headers=headers)
    assert res.status_code == 200
    detail = res.json()
    assert detail["company_id"] == comp_a.id
    assert detail["is_ai_enabled"] is True

    # 3. Update company assignments, budget, and toggle is_ai_enabled
    update_payload = {
        "is_ai_enabled": True,
        "monthly_ai_budget_dollars": 100.0,
        "assignments": [
            {"task_type": "ocr", "provider_key": "gemini", "model_id": "gemini-2.0-flash"},
            {"task_type": "extraction", "provider_key": "openai", "model_id": "gpt-4o"},
            {"task_type": "generation", "provider_key": "anthropic", "model_id": "claude-3-5-sonnet-20241022"},
        ]
    }
    res = client.put(f"/api/admin/ai/companies/{comp_a.id}/assignments", json=update_payload, headers=headers)
    assert res.status_code == 200

    # Verify updated values via GET
    res = client.get(f"/api/admin/ai/companies/{comp_a.id}/assignments", headers=headers)
    assert res.status_code == 200
    updated = res.json()
    assert updated["monthly_ai_budget_dollars"] == 100.0
    task_map = {a["task_type"]: (a["provider_key"], a["model_id"]) for a in updated["assignments"]}
    assert task_map["extraction"] == ("openai", "gpt-4o")
    assert task_map["generation"] == ("anthropic", "claude-3-5-sonnet-20241022")

    # 4. Delete a task assignment
    res = client.delete(f"/api/admin/ai/companies/{comp_a.id}/assignments/generation", headers=headers)
    assert res.status_code == 200


def test_master_admin_usage_overview(client: TestClient, ai_mgmt_env):
    master_token = ai_mgmt_env["master_token"]
    headers = {"Authorization": f"Bearer {master_token}"}

    res = client.get("/api/admin/ai/usage-overview", headers=headers)
    assert res.status_code == 200
    overview = res.json()
    assert "platform_totals" in overview
    assert "providers" in overview
    assert "companies" in overview


# ── 2. Company Admin Restrictions (403 Forbidden) ─────────────────────────────

def test_company_admin_forbidden_from_master_admin_ai_endpoints(client: TestClient, ai_mgmt_env):
    token_a = ai_mgmt_env["token_a"]
    headers = {"Authorization": f"Bearer {token_a}"}

    # Company admin cannot manage platform providers
    res = client.get("/api/admin/ai/providers", headers=headers)
    assert res.status_code in (401, 403)

    # Company admin cannot manage platform credentials
    res = client.get("/api/admin/ai/credentials", headers=headers)
    assert res.status_code in (401, 403)

    # Company admin cannot manage model catalogue
    res = client.post("/api/admin/ai/models", json={}, headers=headers)
    assert res.status_code in (401, 403)

    # Company admin cannot manage company assignments endpoint
    res = client.get("/api/admin/ai/company-assignments", headers=headers)
    assert res.status_code in (401, 403)


def test_company_admin_forbidden_from_saving_keys_or_overriding_settings(client: TestClient, ai_mgmt_env):
    token_a = ai_mgmt_env["token_a"]
    headers = {"Authorization": f"Bearer {token_a}"}

    # POST /api/company/ai/credentials -> 403 Forbidden
    res = client.post("/api/company/ai/credentials", json={"provider_key": "gemini", "api_key": "some-key"}, headers=headers)
    assert res.status_code == 403
    assert "Master Admin" in res.json().get("detail", "")

    # PUT /api/company/ai/settings -> 403 Forbidden
    res = client.put("/api/company/ai/settings", json={"allowed_providers": ["openai"]}, headers=headers)
    assert res.status_code == 403
    assert "Master Admin" in res.json().get("detail", "")


# ── 3. Company AI Information & Model Request Lifecycle ────────────────────────

def test_company_ai_info_read_only(client: TestClient, ai_mgmt_env):
    token_a = ai_mgmt_env["token_a"]
    headers = {"Authorization": f"Bearer {token_a}"}

    res = client.get("/api/company/ai/info", headers=headers)
    assert res.status_code == 200
    info = res.json()
    assert info["is_ai_enabled"] is True
    assert "assignments" in info
    assert "budget" in info
    assert "available_catalogue_models" in info
    assert len(info["available_catalogue_models"]) >= 8


def test_company_ai_model_request_lifecycle(client: TestClient, ai_mgmt_env, db):
    token_a = ai_mgmt_env["token_a"]
    master_token = ai_mgmt_env["master_token"]
    comp_a = ai_mgmt_env["comp_a"]

    company_headers = {"Authorization": f"Bearer {token_a}"}
    master_headers = {"Authorization": f"Bearer {master_token}"}

    # 1. Company submits request for Claude 3.5 Sonnet on extraction
    req_payload = {
        "provider_key": "anthropic",
        "model_id": "claude-3-5-sonnet-20241022",
        "task_type": "extraction",
        "reason": "Need superior extraction accuracy for multi-line healthcare invoices.",
    }
    res = client.post("/api/company/ai/requests", json=req_payload, headers=company_headers)
    assert res.status_code in (200, 201)
    created_req = res.json()
    req_id = created_req["id"]
    assert created_req["status"] == "pending"
    assert created_req["model_id"] == "claude-3-5-sonnet-20241022"

    # 2. Company lists their requests
    res = client.get("/api/company/ai/requests", headers=company_headers)
    assert res.status_code == 200
    my_reqs = res.json()
    assert any(r["id"] == req_id for r in my_reqs)

    # 3. Master Admin lists requests
    res = client.get("/api/admin/ai/requests", headers=master_headers)
    assert res.status_code == 200
    admin_reqs = res.json()
    assert any(r["id"] == req_id for r in admin_reqs)

    # 4. Master Admin approves request with auto_assign=True
    res = client.post(
        f"/api/admin/ai/requests/{req_id}/approve",
        json={"reason": "Approved for enterprise contract tier.", "auto_assign": True},
        headers=master_headers,
    )
    assert res.status_code == 200
    approved_res = res.json()
    assert approved_res["status"] == "approved"
    assert approved_res["decision_notes"] == "Approved for enterprise contract tier."

    # 5. Verify company assignment was automatically updated
    res = client.get(f"/api/admin/ai/companies/{comp_a.id}/assignments", headers=master_headers)
    assert res.status_code == 200
    detail = res.json()
    ext_assignment = next((a for a in detail["assignments"] if a["task_type"] == "extraction"), None)
    assert ext_assignment is not None
    assert ext_assignment["provider_key"] == "anthropic"
    assert ext_assignment["model_id"] == "claude-3-5-sonnet-20241022"


def test_company_ai_model_request_rejection(client: TestClient, ai_mgmt_env, db):
    token_a = ai_mgmt_env["token_a"]
    master_token = ai_mgmt_env["master_token"]
    comp_a = ai_mgmt_env["comp_a"]

    company_headers = {"Authorization": f"Bearer {token_a}"}
    master_headers = {"Authorization": f"Bearer {master_token}"}

    # 1. Submit request
    req_payload = {
        "provider_key": "openai",
        "model_id": "gpt-4-turbo",
        "task_type": "generation",
        "reason": "Test request to be rejected.",
    }
    res = client.post("/api/company/ai/requests", json=req_payload, headers=company_headers)
    assert res.status_code in (200, 201)
    req_id = res.json()["id"]

    # 2. Master Admin rejects request with reason
    reject_reason = "Model is not supported for current company billing tier."
    res = client.post(
        f"/api/admin/ai/requests/{req_id}/reject",
        json={"reason": reject_reason},
        headers=master_headers,
    )
    assert res.status_code == 200
    rejected = res.json()
    assert rejected["status"] == "rejected"
    assert rejected["decision_reason"] == reject_reason

    # 3. Company Admin views rejection in their requests
    res = client.get("/api/company/ai/requests", headers=company_headers)
    assert res.status_code == 200
    found = next((r for r in res.json() if r["id"] == req_id), None)
    assert found is not None
    assert found["status"] == "rejected"
    assert found["decision_reason"] == reject_reason


def test_company_ai_model_request_cancellation(client: TestClient, ai_mgmt_env):
    token_a = ai_mgmt_env["token_a"]
    company_headers = {"Authorization": f"Bearer {token_a}"}

    # Submit request
    res = client.post("/api/company/ai/requests", json={
        "provider_key": "gemini",
        "model_id": "gemini-1.5-pro",
        "task_type": "ocr",
        "reason": "Will cancel soon",
    }, headers=company_headers)
    assert res.status_code in (200, 201)
    req_id = res.json()["id"]

    # Cancel request
    res = client.post(f"/api/company/ai/requests/{req_id}/cancel", headers=company_headers)
    assert res.status_code == 200


# ── 4. Multi-Tenant Isolation ──────────────────────────────────────────────────

def test_company_isolation_on_ai_requests(client: TestClient, ai_mgmt_env):
    token_a = ai_mgmt_env["token_a"]
    token_b = ai_mgmt_env["token_b"]

    # Company A creates a request
    res = client.post("/api/company/ai/requests", json={
        "provider_key": "openai",
        "model_id": "gpt-4o",
        "task_type": "ocr",
        "reason": "Alpha secret reason",
    }, headers={"Authorization": f"Bearer {token_a}"})
    assert res.status_code in (200, 201)
    req_id_a = res.json()["id"]

    # Company B cannot see Company A's request
    res = client.get("/api/company/ai/requests", headers={"Authorization": f"Bearer {token_b}"})
    assert res.status_code == 200
    reqs_b = res.json()
    assert not any(r["id"] == req_id_a for r in reqs_b)

    # Company B cannot cancel Company A's request
    res = client.post(f"/api/company/ai/requests/{req_id_a}/cancel", headers={"Authorization": f"Bearer {token_b}"})
    assert res.status_code == 404


# ── 5. AI Execution Enforcement ───────────────────────────────────────────────

def test_resolve_ai_config_respects_master_admin_assignment(db, ai_mgmt_env):
    comp_a = ai_mgmt_env["comp_a"]
    branch_a = ai_mgmt_env["branch_a"]

    # In ai_mgmt_env, Company A's OCR task is assigned to gemini / gemini-2.0-flash
    config = resolve_ai_config(db, company_id=comp_a.id, branch_id=branch_a.id, operation="ocr")
    assert config.primary.provider_key == "gemini"
    assert config.primary.model == "gemini-2.0-flash"


def test_resolve_ai_config_blocks_when_ai_disabled_by_master_admin(db, ai_mgmt_env):
    comp_a = ai_mgmt_env["comp_a"]
    branch_a = ai_mgmt_env["branch_a"]

    # Master Admin disables AI for Company A
    setting = db.query(CompanyAISetting).filter(CompanyAISetting.company_id == comp_a.id).first()
    setting.is_ai_enabled = False
    db.commit()

    with pytest.raises(AIProviderError) as exc_info:
        resolve_ai_config(db, company_id=comp_a.id, branch_id=branch_a.id, operation="ocr")
    assert "disabled for Company" in str(exc_info.value)
