from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.entities import (
    Extraction,
    Invoice,
    ReviewEvent,
    SourceFile,
    User,
    ValidationIssue,
)
from app.services.push import compute_idempotency_key, push_invoice


@pytest.mark.asyncio
async def test_r2_cannot_reach_approved_without_authenticated_reviewer(
    client: AsyncClient, db_session: AsyncSession
):
    """R2: Unauthenticated client cannot approve an invoice."""
    inv = Invoice(
        id=uuid.uuid4(),
        source_file_id=uuid.uuid4(),
        status="NEEDS_REVIEW",
        row_version=1,
    )
    db_session.add(inv)
    await db_session.flush()

    resp = await client.post(
        f"/api/v1/invoices/{inv.id}/approve",
        json={"row_version": 1},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_r2_approving_with_error_requires_override_reason(
    reviewer_client: AsyncClient, db_session: AsyncSession
):
    """R2: Approving with remaining error issues requires a valid override reason >= 10 chars."""
    inv = Invoice(
        id=uuid.uuid4(),
        source_file_id=uuid.uuid4(),
        status="NEEDS_REVIEW",
        row_version=1,
    )
    ext = Extraction(
        id=uuid.uuid4(),
        invoice_id=inv.id,
        version=1,
        kind="model",
        data={"invoice_number": "INV-1"},
    )
    inv.current_extraction_id = ext.id

    issue = ValidationIssue(
        id=uuid.uuid4(),
        invoice_id=inv.id,
        extraction_id=ext.id,
        code="total_mismatch",
        severity="error",
        message="Total amount does not match line sums",
        resolved_by_override=False,
    )
    db_session.add_all([inv, ext, issue])
    await db_session.flush()

    # Attempt 1: No override reason -> 422
    resp1 = await reviewer_client.post(
        f"/api/v1/invoices/{inv.id}/approve",
        json={"row_version": 1},
    )
    assert resp1.status_code == 422

    # Attempt 2: Too short override reason -> 422
    resp2 = await reviewer_client.post(
        f"/api/v1/invoices/{inv.id}/approve",
        json={"row_version": 1, "override_reason": "short"},
    )
    assert resp2.status_code == 422

    # Attempt 3: Valid override reason >= 10 chars -> 200
    with patch("app.services.push.push_invoice", AsyncMock()):
        resp3 = await reviewer_client.post(
            f"/api/v1/invoices/{inv.id}/approve",
            json={
                "row_version": 1,
                "override_reason": "Verified difference with supplier credit memo",
            },
        )
        assert resp3.status_code == 200
        data = resp3.json()
        assert data["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_r2_editing_approved_invoice_reverts_to_needs_review(
    reviewer_client: AsyncClient, reviewer_user: User, db_session: AsyncSession
):
    """R2: Editing an approved but unpushed invoice invalidates the approval and reverts to NEEDS_REVIEW."""
    now = datetime.now(UTC)
    ext1 = Extraction(
        id=uuid.uuid4(),
        version=1,
        kind="model",
        data={"invoice_number": "INV-100", "total": "100.00", "line_items": []},
    )
    inv = Invoice(
        id=uuid.uuid4(),
        source_file_id=uuid.uuid4(),
        status="APPROVED",
        current_extraction_id=ext1.id,
        approved_extraction_id=ext1.id,
        approved_by=reviewer_user.id,
        approved_at=now,
        row_version=2,
    )
    ext1.invoice_id = inv.id
    db_session.add_all([ext1, inv])
    await db_session.flush()

    # Edit the invoice
    edit_payload = {
        "extraction": {
            "invoice_number": "INV-100-EDITED",
            "invoice_date": "2026-03-15",
            "supplier_name": "Acme Corp",
            "supplier_gstin": "27AAPFU0939F1ZV",
            "taxable_value": "100.00",
            "cgst": "9.00",
            "sgst": "9.00",
            "igst": "0.00",
            "total": "118.00",
            "line_items": [
                {"description": "Item A", "quantity": 1, "rate": 100, "amount": "100.00"}
            ],
            "field_confidence": {},
            "unreadable_fields": [],
        },
        "row_version": 2,
    }

    resp = await reviewer_client.patch(
        f"/api/v1/invoices/{inv.id}/fields",
        json=edit_payload,
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "NEEDS_REVIEW"
    assert res_data["row_version"] == 3


@pytest.mark.asyncio
async def test_r2_push_uses_approved_extraction_not_latest(
    db_session: AsyncSession, reviewer_user: User
):
    """R2: Push uses approved_extraction_id, even if a newer extraction exists."""
    ext_approved = Extraction(
        id=uuid.uuid4(),
        version=1,
        kind="model",
        data={"invoice_number": "INV-ORIGINAL", "total": "100.00"},
    )
    ext_later = Extraction(
        id=uuid.uuid4(),
        version=2,
        kind="human_edit",
        data={"invoice_number": "INV-LATER-TAMPERED", "total": "999.00"},
    )
    inv = Invoice(
        id=uuid.uuid4(),
        source_file_id=uuid.uuid4(),
        status="APPROVED",
        current_extraction_id=ext_later.id,  # Points to later
        approved_extraction_id=ext_approved.id,  # Points to approved
        approved_by=reviewer_user.id,
        approved_at=datetime.now(UTC),
        supplier_gstin="27AAPFU0939F1ZV",
        normalized_invoice_number="INVORIGINAL",
        financial_year="2025-26",
    )
    ext_approved.invoice_id = inv.id
    ext_later.invoice_id = inv.id
    db_session.add_all([ext_approved, ext_later, inv])
    await db_session.flush()

    captured_payload = None

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        import json

        captured_payload = json.loads(request.content)
        return httpx.Response(201, json={"accounting_id": "ACC-TEST-123"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as test_client:
        res = await push_invoice(db_session, inv.id, client=test_client)
        assert res is not None
        assert res.status == "PUSHED"
        assert res.accounting_id == "ACC-TEST-123"

    assert captured_payload is not None
    assert captured_payload["invoice_number"] == "INV-ORIGINAL"
    assert captured_payload["total"] == "100.00"


@pytest.mark.asyncio
async def test_r3_override_duplicate_produces_distinct_idempotency_key():
    """R3: Overridden duplicate produces distinct idempotency key with invoice UUID appended."""
    u1 = uuid.uuid4()
    u2 = uuid.uuid4()
    k_standard = compute_idempotency_key(
        "27AAPFU0939F1ZV", "INV42", "2025-26", invoice_id=u1, dup_overridden=False
    )
    k_overridden = compute_idempotency_key(
        "27AAPFU0939F1ZV", "INV42", "2025-26", invoice_id=u2, dup_overridden=True
    )
    assert k_standard != k_overridden
    assert str(u2) in k_overridden


@pytest.mark.asyncio
async def test_auth_login_inactive_user_and_rate_limiting(
    client: AsyncClient, db_session: AsyncSession
):
    """Auth: Inactive users cannot log in; rate limiting blocks excessive failures."""
    inactive_user = User(
        id=uuid.uuid4(),
        email="inactive@test.com",
        password_hash=hash_password("Pass123!"),
        role="reviewer",
        is_active=False,
    )
    db_session.add(inactive_user)
    await db_session.flush()

    # Inactive login
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@test.com", "password": "Pass123!"},
    )
    assert resp.status_code == 401
    assert "deactivated" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_endpoints_role_enforcement(
    reviewer_client: AsyncClient, admin_client: AsyncClient, db_session: AsyncSession
):
    """Admin: Non-admin users cannot access admin CRUD."""
    # Reviewer attempts to list users -> 403
    r_resp = await reviewer_client.get("/api/v1/admin/users")
    assert r_resp.status_code == 403

    # Admin lists users -> 200
    a_resp = await admin_client.get("/api/v1/admin/users")
    assert a_resp.status_code == 200
    assert isinstance(a_resp.json(), list)


@pytest.mark.asyncio
async def test_metrics_summary_endpoint(reviewer_client: AsyncClient, db_session: AsyncSession):
    """Metrics: Summary endpoint returns counts, age, and durations."""
    resp = await reviewer_client.get("/api/v1/metrics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "status_counts" in data
    assert "oldest_waiting_age_minutes" in data
    assert "median_time_to_approve_minutes" in data
    assert "p95_time_to_approve_minutes" in data


@pytest.mark.asyncio
async def test_admin_supplier_crud_and_csv_import(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """Admin: CRUD and CSV import with row-level validation."""
    # Create supplier
    create_resp = await admin_client.post(
        "/api/v1/admin/suppliers",
        json={"gstin": "27AAPFU0939F1ZV", "name": "Standard Supplies Ltd"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["gstin"] == "27AAPFU0939F1ZV"

    # CSV Import
    csv_content = "gstin,name\n27AAPFU0939F1ZV,Updated Supplies Ltd\nINVALID_GSTIN,Bad Supplier\n"
    files = {"file": ("suppliers.csv", csv_content.encode("utf-8"), "text/csv")}
    import_resp = await admin_client.post(
        "/api/v1/admin/suppliers/import-csv",
        files=files,
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert import_resp.status_code == 200
    res_data = import_resp.json()
    assert res_data["imported"] == 1
    assert len(res_data["errors"]) == 1
    assert res_data["errors"][0]["row"] == 3


@pytest.mark.asyncio
async def test_invoices_list_and_detail_endpoints(
    reviewer_client: AsyncClient, db_session: AsyncSession
):
    """Test GET /api/v1/invoices and GET /api/v1/invoices/{id}."""
    sf = SourceFile(
        id=uuid.uuid4(),
        sha256="detail_hash",
        original_filename="sample_detail.pdf",
        content_type="application/pdf",
        size_bytes=1000,
        storage_key="test/sample_detail.pdf",
        source="upload",
    )
    inv = Invoice(
        id=uuid.uuid4(),
        source_file_id=sf.id,
        status="NEEDS_REVIEW",
        supplier_gstin="27AAPFU0939F1ZV",
        normalized_invoice_number="INV999",
        financial_year="2025-26",
        page_count=2,
    )
    db_session.add_all([sf, inv])
    await db_session.flush()

    # List
    list_resp = await reviewer_client.get("/api/v1/invoices?status=NEEDS_REVIEW&q=INV999")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert any(i["id"] == str(inv.id) for i in list_data["items"])

    # Detail
    detail_resp = await reviewer_client.get(f"/api/v1/invoices/{inv.id}")
    assert detail_resp.status_code == 200
    d_data = detail_resp.json()
    assert d_data["id"] == str(inv.id)
    assert len(d_data["pages"]) == 2


@pytest.mark.asyncio
async def test_invoice_rejections_and_resend(
    reviewer_client: AsyncClient, db_session: AsyncSession
):
    """Test POST /api/v1/invoices/{id}/reject and /request-resend."""
    inv1 = Invoice(id=uuid.uuid4(), source_file_id=uuid.uuid4(), status="NEEDS_REVIEW")
    inv2 = Invoice(id=uuid.uuid4(), source_file_id=uuid.uuid4(), status="NEEDS_REVIEW")
    db_session.add_all([inv1, inv2])
    await db_session.flush()

    # Reject
    r_resp = await reviewer_client.post(
        f"/api/v1/invoices/{inv1.id}/reject",
        json={"reason": "Incorrect buyer entity name"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r_resp.status_code == 200
    await db_session.refresh(inv1)
    assert inv1.status == "REJECTED"

    # Resend
    s_resp = await reviewer_client.post(
        f"/api/v1/invoices/{inv2.id}/request-resend",
        json={"reason": "Page 2 is completely black"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert s_resp.status_code == 200
    await db_session.refresh(inv2)
    assert inv2.status == "RESEND_REQUESTED"


@pytest.mark.asyncio
async def test_invoice_duplicate_confirm_and_override(
    reviewer_client: AsyncClient, reviewer_user: User, db_session: AsyncSession
):
    """Test POST /api/v1/invoices/{id}/confirm-duplicate and /override-duplicate."""
    orig = Invoice(
        id=uuid.uuid4(),
        source_file_id=uuid.uuid4(),
        status="PUSHED",
        approved_by=reviewer_user.id,
        approved_extraction_id=uuid.uuid4(),
    )
    dup = Invoice(
        id=uuid.uuid4(),
        source_file_id=uuid.uuid4(),
        status="NEEDS_REVIEW",
        dup_of_id=orig.id,
    )
    db_session.add_all([orig, dup])
    await db_session.flush()

    # Confirm duplicate
    c_resp = await reviewer_client.post(
        f"/api/v1/invoices/{dup.id}/confirm-duplicate",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert c_resp.status_code == 200
    await db_session.refresh(dup)
    assert dup.status == "REJECTED_DUPLICATE"

    # Override duplicate on another invoice
    dup2 = Invoice(
        id=uuid.uuid4(),
        source_file_id=uuid.uuid4(),
        status="NEEDS_REVIEW",
        dup_of_id=orig.id,
    )
    db_session.add(dup2)
    await db_session.flush()

    o_resp = await reviewer_client.post(
        f"/api/v1/invoices/{dup2.id}/override-duplicate",
        json={"reason": "Valid supplementary invoice under same number"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert o_resp.status_code == 200
    await db_session.refresh(dup2)
    assert dup2.dup_overridden is True


@pytest.mark.asyncio
async def test_invoice_audit_trail_endpoint(reviewer_client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/v1/invoices/{id}/audit."""
    inv = Invoice(id=uuid.uuid4(), source_file_id=uuid.uuid4(), status="NEEDS_REVIEW")
    rev = ReviewEvent(
        id=uuid.uuid4(),
        invoice_id=inv.id,
        action="status_change",
        payload={"from": "RECEIVED", "to": "NEEDS_REVIEW"},
    )
    db_session.add_all([inv, rev])
    await db_session.flush()

    resp = await reviewer_client.get(f"/api/v1/invoices/{inv.id}/audit")
    assert resp.status_code == 200
    trail = resp.json()
    assert len(trail) >= 1
    assert trail[0]["action"] == "status_change"


@pytest.mark.asyncio
async def test_admin_user_crud_and_retry_endpoints(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """Test admin user create, update, and invoice retry."""
    # Create user
    create_resp = await admin_client.post(
        "/api/v1/admin/users",
        json={"email": "newbie@test.com", "password": "Password123!", "role": "reviewer"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert create_resp.status_code == 200
    user_id = create_resp.json()["id"]

    # Patch user
    patch_resp = await admin_client.patch(
        f"/api/v1/admin/users/{user_id}",
        json={"is_active": False, "role": "admin"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False

    # Retry FAILED invoice
    sf = SourceFile(
        id=uuid.uuid4(),
        sha256="retry_hash",
        original_filename="retry.pdf",
        content_type="application/pdf",
        size_bytes=100,
        storage_key="test/retry.pdf",
        source="upload",
    )
    failed_inv = Invoice(
        id=uuid.uuid4(),
        source_file_id=sf.id,
        status="FAILED",
        status_reason="Network error",
    )
    db_session.add_all([sf, failed_inv])
    await db_session.flush()

    with patch("app.services.pipeline.process_invoice_pipeline", AsyncMock()):
        retry_resp = await admin_client.post(
            f"/api/v1/admin/invoices/{failed_inv.id}/retry",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert retry_resp.status_code == 200
        assert "re-triggered" in retry_resp.json()["message"]


@pytest.mark.asyncio
async def test_auth_me_and_logout(reviewer_client: AsyncClient, reviewer_user: User):
    """Test GET /api/v1/auth/me and POST /api/v1/auth/logout."""
    me_resp = await reviewer_client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == reviewer_user.email

    logout_resp = await reviewer_client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200
    assert "Logged out" in logout_resp.json()["message"]


@pytest.mark.asyncio
async def test_push_invoice_client_error_and_retries(db_session: AsyncSession, reviewer_user: User):
    """Test push_invoice client error (400) transitions directly to PUSH_FAILED."""
    ext = Extraction(
        id=uuid.uuid4(),
        version=1,
        kind="model",
        data={"invoice_number": "INV-FAIL", "total": "50.00"},
    )
    inv = Invoice(
        id=uuid.uuid4(),
        source_file_id=uuid.uuid4(),
        status="APPROVED",
        current_extraction_id=ext.id,
        approved_extraction_id=ext.id,
        approved_by=reviewer_user.id,
        approved_at=datetime.now(UTC),
        supplier_gstin="27AAPFU0939F1ZV",
        normalized_invoice_number="INVFAIL",
        financial_year="2025-26",
    )
    ext.invoice_id = inv.id
    db_session.add_all([ext, inv])
    await db_session.flush()

    # 400 Bad Request handler
    async def bad_request_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "Bad Request format"})

    transport = httpx.MockTransport(bad_request_handler)
    async with httpx.AsyncClient(transport=transport) as mock_c:
        res = await push_invoice(db_session, inv.id, client=mock_c)
        assert res is not None
        assert res.status == "PUSH_FAILED"
        assert "400" in (res.status_reason or "")
