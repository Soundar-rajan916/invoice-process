"""Coverage test suite targeting uncovered branches across Phase 3 APIs and services.
Ensures app coverage exceeds 85% requirement.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.invoices import get_diff
from app.core.security import hash_password
from app.core.storage import StorageService
from app.models.entities import (
    Extraction,
    Invoice,
    ReviewEvent,
    SourceFile,
    Supplier,
    User,
    ValidationIssue,
)
from app.services.push import push_invoice


@pytest.mark.asyncio
async def test_invoices_list_filters_and_pagination(
    reviewer_client: AsyncClient, db_session: AsyncSession
):
    """Test invoice listing filters (status, flagged, q), sorting and pagination."""
    sf1 = SourceFile(
        id=uuid.uuid4(),
        sha256="cov_hash_1",
        original_filename="inv1.pdf",
        content_type="application/pdf",
        size_bytes=1000,
        storage_key="cov/1.pdf",
        source="upload",
    )
    sf2 = SourceFile(
        id=uuid.uuid4(),
        sha256="cov_hash_2",
        original_filename="inv2.pdf",
        content_type="application/pdf",
        size_bytes=1000,
        storage_key="cov/2.pdf",
        source="upload",
    )
    db_session.add_all([sf1, sf2])
    await db_session.flush()

    inv1 = Invoice(
        id=uuid.uuid4(),
        source_file_id=sf1.id,
        status="NEEDS_REVIEW",
        normalized_invoice_number="INV101",
        supplier_gstin="27AAPFU0939F1ZV",
        page_count=2,
    )
    inv2 = Invoice(
        id=uuid.uuid4(),
        source_file_id=sf2.id,
        status="REJECTED",
        normalized_invoice_number="INV202",
        supplier_gstin="29ABCDE1234F1Z5",
        page_count=1,
    )
    db_session.add_all([inv1, inv2])
    await db_session.flush()

    # Add a validation error to inv1
    issue = ValidationIssue(
        id=uuid.uuid4(),
        invoice_id=inv1.id,
        code="total_mismatch",
        severity="error",
        message="Total differs",
    )
    db_session.add(issue)
    await db_session.flush()

    # 1. Filter by status
    resp = await reviewer_client.get("/api/v1/invoices?status=NEEDS_REVIEW")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == str(inv1.id)
    assert data["counts"]["NEEDS_REVIEW"] >= 1

    # 2. Filter flagged=true
    resp_flagged = await reviewer_client.get("/api/v1/invoices?flagged=true")
    assert resp_flagged.status_code == 200
    flagged_ids = [item["id"] for item in resp_flagged.json()["items"]]
    assert str(inv1.id) in flagged_ids

    # 3. Filter query q
    resp_q = await reviewer_client.get("/api/v1/invoices?q=INV101")
    assert resp_q.status_code == 200
    assert len(resp_q.json()["items"]) == 1

    # 4. Sorting asc / desc
    resp_sort = await reviewer_client.get("/api/v1/invoices?sort=newest&page=1&page_size=5")
    assert resp_sort.status_code == 200


@pytest.mark.asyncio
async def test_invoice_detail_and_404(reviewer_client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/v1/invoices/{id} and 404 behavior."""
    non_existent = uuid.uuid4()
    resp = await reviewer_client.get(f"/api/v1/invoices/{non_existent}")
    assert resp.status_code == 404

    # Detail with presigned urls mocked
    sf = SourceFile(
        id=uuid.uuid4(),
        sha256="det_hash",
        original_filename="det.pdf",
        content_type="application/pdf",
        size_bytes=1000,
        storage_key="cov/det.pdf",
        source="upload",
    )
    inv = Invoice(
        id=uuid.uuid4(),
        source_file_id=sf.id,
        status="NEEDS_REVIEW",
        page_count=2,
    )
    db_session.add_all([sf, inv])
    await db_session.flush()

    with patch(
        "app.api.invoices.storage_service.generate_presigned_url",
        return_value="https://s3.example.com/p1",
    ):
        detail_resp = await reviewer_client.get(f"/api/v1/invoices/{inv.id}")
        assert detail_resp.status_code == 200
        res_json = detail_resp.json()
        assert len(res_json["pages"]) == 2
        assert res_json["pages"][0]["url"] == "https://s3.example.com/p1"


@pytest.mark.asyncio
async def test_invoice_fields_optimistic_locking_conflict(
    reviewer_client: AsyncClient, db_session: AsyncSession
):
    """Test PATCH /api/v1/invoices/{id}/fields returns 409 on stale row_version."""
    inv = Invoice(
        id=uuid.uuid4(),
        source_file_id=uuid.uuid4(),
        status="NEEDS_REVIEW",
        row_version=5,
    )
    db_session.add(inv)
    await db_session.flush()

    payload = {
        "extraction": {
            "invoice_number": "INV-CONFLICT",
            "invoice_date": "2026-03-15",
            "supplier_name": "Test",
            "supplier_gstin": "27AAPFU0939F1ZV",
            "total": "100.00",
            "line_items": [],
            "field_confidence": {},
            "unreadable_fields": [],
        },
        "row_version": 4,  # Stale row version!
    }
    resp = await reviewer_client.patch(
        f"/api/v1/invoices/{inv.id}/fields",
        json=payload,
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 409
    assert "modified" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_invoice_reject_and_request_resend(
    reviewer_client: AsyncClient, db_session: AsyncSession
):
    """Test POST /api/v1/invoices/{id}/reject and /request-resend."""
    sf1 = SourceFile(
        id=uuid.uuid4(),
        sha256="s1_hash",
        original_filename="f1.pdf",
        content_type="application/pdf",
        size_bytes=10,
        storage_key="k1",
        source="upload",
    )
    sf2 = SourceFile(
        id=uuid.uuid4(),
        sha256="s2_hash",
        original_filename="f2.pdf",
        content_type="application/pdf",
        size_bytes=10,
        storage_key="k2",
        source="upload",
    )
    inv1 = Invoice(id=uuid.uuid4(), source_file_id=sf1.id, status="NEEDS_REVIEW")
    inv2 = Invoice(id=uuid.uuid4(), source_file_id=sf2.id, status="NEEDS_REVIEW")
    db_session.add_all([sf1, sf2, inv1, inv2])
    await db_session.flush()

    # Reject without reason -> 422/400
    r_empty = await reviewer_client.post(
        f"/api/v1/invoices/{inv1.id}/reject",
        json={"reason": ""},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r_empty.status_code in (400, 422)

    # Reject with valid reason
    r_ok = await reviewer_client.post(
        f"/api/v1/invoices/{inv1.id}/reject",
        json={"reason": "Unreadable damaged copy"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r_ok.status_code == 200
    inv1_db = await db_session.get(Invoice, inv1.id)
    assert inv1_db.status == "REJECTED"

    # Request resend
    resend_ok = await reviewer_client.post(
        f"/api/v1/invoices/{inv2.id}/request-resend",
        json={"reason": "Please resend higher resolution photo"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resend_ok.status_code == 200
    inv2_db = await db_session.get(Invoice, inv2.id)
    assert inv2_db.status == "RESEND_REQUESTED"

    # Test Cancel Resend
    cancel_resp = await reviewer_client.post(
        f"/api/v1/invoices/{inv2.id}/cancel-resend",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert cancel_resp.status_code == 200
    inv2_db = await db_session.get(Invoice, inv2.id)
    assert inv2_db.status == "NEEDS_REVIEW"

    # Cancel resend again -> 400
    cancel_fail = await reviewer_client.post(
        f"/api/v1/invoices/{inv2.id}/cancel-resend",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert cancel_fail.status_code == 400

    # Put back in RESEND_REQUESTED
    await reviewer_client.post(
        f"/api/v1/invoices/{inv2.id}/request-resend",
        json={"reason": "Blurry lines"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    inv2_db = await db_session.get(Invoice, inv2.id)
    assert inv2_db.status == "RESEND_REQUESTED"

    inv2_id = inv2.id
    # Test Upload Replacement
    with patch("app.core.storage.storage_service.upload_bytes"):
        fake_pdf = b"%PDF-1.4 header and mock content for replacement"
        files = {"file": ("replacement.pdf", fake_pdf, "application/pdf")}
        upload_resp = await reviewer_client.post(
            f"/api/v1/invoices/{inv2_id}/upload-replacement",
            files=files,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert upload_resp.status_code == 200
        db_session.expire_all()
        inv2_db = await db_session.get(Invoice, inv2_id)
        assert inv2_db.status in ("RECEIVED", "NEEDS_REVIEW", "PROCESSING")

    # Verify audit trail logs the resend lifecycle actions
    audit_resp = await reviewer_client.get(f"/api/v1/invoices/{inv2_id}/audit")
    assert audit_resp.status_code == 200
    actions = [e["action"] for e in audit_resp.json()]
    assert "request_resend" in actions
    assert "cancel_resend" in actions
    assert "resend_fulfilled" in actions


@pytest.mark.asyncio
async def test_invoice_confirm_duplicate_and_override_edge_cases(
    reviewer_client: AsyncClient, reviewer_user: User, db_session: AsyncSession
):
    """Test edge cases in duplicate confirmation and override."""
    # Confirm duplicate on non-existent invoice -> 404
    non_existent = uuid.uuid4()
    c_bad = await reviewer_client.post(
        f"/api/v1/invoices/{non_existent}/confirm-duplicate",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert c_bad.status_code == 404

    # Override duplicate with short reason (< 3 chars) -> 422
    orig = Invoice(
        id=uuid.uuid4(),
        source_file_id=uuid.uuid4(),
        status="APPROVED",
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

    o_short = await reviewer_client.post(
        f"/api/v1/invoices/{dup.id}/override-duplicate",
        json={"reason": "no"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert o_short.status_code in (400, 422)


@pytest.mark.asyncio
async def test_admin_supplier_and_user_extra_endpoints(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """Test GET suppliers and user update in admin router."""
    # Create a supplier
    sup = Supplier(
        id=uuid.uuid4(),
        gstin="29ABCDE1234F1Z5",
        name="Karnataka Supplier",
        state_code="29",
        is_active=True,
    )
    db_session.add(sup)
    await db_session.flush()

    # GET suppliers list
    list_s = await admin_client.get("/api/v1/admin/suppliers")
    assert list_s.status_code == 200
    assert len(list_s.json()) >= 1

    # Update user (deactivate)
    user = User(
        id=uuid.uuid4(),
        email="temporary@test.com",
        password_hash=hash_password("Temp123!"),
        role="reviewer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    patch_u = await admin_client.patch(
        f"/api/v1/admin/users/{user.id}",
        json={"is_active": False},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert patch_u.status_code == 200
    await db_session.refresh(user)
    assert user.is_active is False


@pytest.mark.asyncio
async def test_admin_retry_invalid_state(admin_client: AsyncClient, db_session: AsyncSession):
    """Test admin retry returns 400 when invoice is not in FAILED or PUSH_FAILED."""
    inv = Invoice(id=uuid.uuid4(), source_file_id=uuid.uuid4(), status="NEEDS_REVIEW")
    db_session.add(inv)
    await db_session.flush()

    resp = await admin_client.post(
        f"/api/v1/admin/invoices/{inv.id}/retry",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 400
    assert "failed" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_auth_login_invalid_credentials(reviewer_client: AsyncClient):
    """Test auth login with invalid password and nonexistent user."""
    r_bad_pass = await reviewer_client.post(
        "/api/v1/auth/login",
        json={"email": "reviewer@test.com", "password": "WrongPassword123!"},
    )
    assert r_bad_pass.status_code == 401

    r_no_user = await reviewer_client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@test.com", "password": "WrongPassword123!"},
    )
    assert r_no_user.status_code == 401


@pytest.mark.asyncio
async def test_metrics_calculation_with_approved_and_edited_invoices(
    reviewer_client: AsyncClient, reviewer_user: User, db_session: AsyncSession
):
    """Test metrics endpoint calculating median, p95, and 7-day edit rates."""
    now = datetime.now(UTC)
    inv = Invoice(
        id=uuid.uuid4(),
        source_file_id=uuid.uuid4(),
        status="APPROVED",
        approved_by=reviewer_user.id,
        approved_extraction_id=uuid.uuid4(),
        created_at=now - timedelta(hours=2),
        approved_at=now,
    )
    # Add human edit event
    rev = ReviewEvent(
        id=uuid.uuid4(),
        invoice_id=inv.id,
        actor_id=reviewer_user.id,
        action="edit",
        payload={"diff": {"total": {"old": "100.00", "new": "110.00"}}},
        created_at=now - timedelta(days=1),
    )
    db_session.add_all([inv, rev])
    await db_session.flush()

    resp = await reviewer_client.get("/api/v1/metrics/summary")
    assert resp.status_code == 200
    metrics = resp.json()
    assert metrics["median_time_to_approve_minutes"] is not None
    assert metrics["median_time_to_approve_minutes"] >= 119
    assert metrics["field_edit_rates_7d"].get("total", 0) >= 1


@pytest.mark.asyncio
async def test_push_invoice_5xx_retry_and_exhaustion(db_session: AsyncSession, reviewer_user: User):
    """Test push_invoice retries on 500 error up to max attempts."""
    ext = Extraction(
        id=uuid.uuid4(),
        version=1,
        kind="model",
        data={"invoice_number": "INV-SERVER-ERR", "total": "50.00"},
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
        normalized_invoice_number="INVSERVERERR",
        financial_year="2025-26",
    )
    ext.invoice_id = inv.id
    db_session.add_all([ext, inv])
    await db_session.flush()

    # Always 500 Internal Server Error
    async def server_error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "Accounting system down"})

    transport = httpx.MockTransport(server_error_handler)
    async with httpx.AsyncClient(transport=transport) as mock_c:
        # Patch sleep so test runs instantly
        with patch("asyncio.sleep", AsyncMock()):
            res = await push_invoice(db_session, inv.id, client=mock_c)
            assert res is not None
            assert res.status == "PUSH_FAILED"
            assert "attempts" in (res.status_reason or "").lower()


@pytest.mark.asyncio
async def test_direct_invoice_router_functions(db_session: AsyncSession, reviewer_user: User):
    """Directly call invoice router endpoints to guarantee 100% path coverage."""
    from app.api.invoices import (
        ApproveRequest,
        EditFieldsRequest,
        ReasonRequest,
        approve_invoice,
        confirm_duplicate_invoice,
        get_invoice_audit_trail,
        get_invoice_detail,
        list_invoices,
        override_duplicate_invoice,
        reject_invoice,
        request_resend_invoice,
        update_invoice_fields,
    )
    from app.schemas.extraction import InvoiceExtraction

    sf = SourceFile(
        id=uuid.uuid4(),
        sha256="direct_cov_hash",
        original_filename="direct.pdf",
        content_type="application/pdf",
        size_bytes=100,
        storage_key="cov/direct.pdf",
        source="upload",
    )
    db_session.add(sf)
    await db_session.flush()

    ext1 = Extraction(
        id=uuid.uuid4(),
        version=1,
        kind="model",
        data={"invoice_number": "DIR-1", "total": "100.00"},
    )
    inv = Invoice(
        id=uuid.uuid4(),
        source_file_id=sf.id,
        status="APPROVED",
        current_extraction_id=ext1.id,
        approved_extraction_id=ext1.id,
        approved_by=reviewer_user.id,
        approved_at=datetime.now(UTC),
        row_version=1,
        page_count=2,
    )
    ext1.invoice_id = inv.id
    db_session.add_all([ext1, inv])
    await db_session.flush()

    # 1. list_invoices with all sort options
    for sort_opt in ("oldest", "newest", "total_asc", "total_desc"):
        res = await list_invoices(
            status_filter="APPROVED",
            flagged=False,
            q="DIR",
            sort=sort_opt,
            page=1,
            page_size=10,
            user=reviewer_user,
            db=db_session,
        )
        assert res["total"] >= 1

    # 2. get_invoice_detail
    with patch(
        "app.api.invoices.storage_service.generate_presigned_url", return_value="http://s3/test"
    ):
        det = await get_invoice_detail(inv.id, user=reviewer_user, db=db_session)
        assert det["id"] == str(inv.id)
        assert len(det["pages"]) == 2

    # 3. update_invoice_fields (reverts APPROVED -> NEEDS_REVIEW)
    edit_req = EditFieldsRequest(
        extraction=InvoiceExtraction(
            invoice_number="DIR-2",
            invoice_date=datetime.now(UTC).date(),
            supplier_name="Acme",
            supplier_gstin="27AAPFU0939F1ZV",
            taxable_value=Decimal("100.00"),
            cgst=Decimal("9.00"),
            sgst=Decimal("9.00"),
            igst=Decimal("0.00"),
            total=Decimal("118.00"),
            line_items=[],
            field_confidence={},
            unreadable_fields=[],
        ),
        row_version=1,
    )
    upd = await update_invoice_fields(inv.id, edit_req, user=reviewer_user, db=db_session, _=None)
    assert upd["status"] == "NEEDS_REVIEW"
    assert upd["row_version"] == 2

    # 4. approve_invoice (server-side validation and push)
    with patch("app.services.push.push_invoice", AsyncMock()):
        appr = await approve_invoice(
            inv.id,
            ApproveRequest(row_version=2, override_reason="Reason valid over 10 chars"),
            user=reviewer_user,
            db=db_session,
            _=None,
        )
        assert appr["status"] == "APPROVED"

    # 5. reject_invoice (requires NEEDS_REVIEW)
    inv.status = "NEEDS_REVIEW"
    await db_session.flush()
    rej = await reject_invoice(
        inv.id, ReasonRequest(reason="Damaged copy"), user=reviewer_user, db=db_session, _=None
    )
    assert rej["message"] == "Invoice rejected"

    # 6. request_resend_invoice (requires NEEDS_REVIEW)
    inv.status = "NEEDS_REVIEW"
    await db_session.flush()
    resend = await request_resend_invoice(
        inv.id,
        ReasonRequest(reason="Please resend clean image"),
        user=reviewer_user,
        db=db_session,
        _=None,
    )
    assert resend["message"] == "Resend requested"

    # 7. confirm_duplicate_invoice
    c_dup = await confirm_duplicate_invoice(inv.id, user=reviewer_user, db=db_session, _=None)
    assert c_dup["message"] == "Duplicate confirmed"

    # 8. override_duplicate_invoice
    o_dup = await override_duplicate_invoice(
        inv.id,
        ReasonRequest(reason="Not a duplicate legitimate invoice"),
        user=reviewer_user,
        db=db_session,
        _=None,
    )
    assert o_dup["dup_overridden"] is True

    # 9. get_invoice_audit_trail
    trail = await get_invoice_audit_trail(inv.id, user=reviewer_user, db=db_session)
    assert len(trail) >= 4


def test_parse_edit_diff_helper():
    """Unit test the get_diff helper."""
    old_data = {"invoice_number": "INV1", "total": "100.00", "supplier_name": "Acme"}
    new_data = {"invoice_number": "INV2", "total": "100.00", "supplier_name": "Acme Corp"}
    diff = get_diff(old_data, new_data)
    assert "invoice_number" in diff
    assert diff["invoice_number"]["before"] == "INV1"
    assert diff["invoice_number"]["after"] == "INV2"
    assert "total" not in diff
    assert "supplier_name" in diff


def test_minio_storage_operations():
    """Test StorageService upload_bytes, download_bytes, and generate_presigned_url."""
    storage = StorageService()
    mock_s3 = MagicMock()
    storage._client = mock_s3
    storage._s3_available = True

    # download_bytes
    mock_body = MagicMock()
    mock_body.read.return_value = b"test bytes"
    mock_s3.get_object.return_value = {"Body": mock_body}
    assert storage.download_bytes("test/key.pdf") == b"test bytes"
    mock_s3.get_object.assert_called_with(Bucket=storage.bucket, Key="test/key.pdf")

    # upload_bytes
    storage.upload_bytes(b"data", "test/key.pdf")
    mock_s3.put_object.assert_called_once()

    # presigned url
    mock_s3.generate_presigned_url.return_value = "https://minio.test/presigned"
    url = storage.generate_presigned_url("test/key.pdf", expires_in=300)
    assert url == "https://minio.test/presigned"


@pytest.mark.asyncio
async def test_direct_admin_and_auth_router_functions(db_session: AsyncSession, admin_user: User):
    """Directly test admin and auth router functions."""
    from fastapi import Response, UploadFile

    from app.api.admin import (
        SupplierCreateRequest,
        UserCreateRequest,
        UserUpdateRequest,
        create_supplier,
        create_user,
        import_suppliers_csv,
        list_suppliers,
        list_users,
        retry_invoice,
        update_user,
    )
    from app.api.auth import LoginRequest, get_me, login, logout

    # 1. Admin suppliers
    s_req = SupplierCreateRequest(gstin="27AAPFU0939F1ZV", name="Direct Supplier")
    s_res = await create_supplier(s_req, user=admin_user, db=db_session, _=None)
    assert s_res["gstin"] == "27AAPFU0939F1ZV"

    sups = await list_suppliers(user=admin_user, db=db_session)
    assert len(sups) >= 1

    # CSV import
    csv_bytes = b"gstin,name\n27AAPFU0939F1ZV,Updated Direct Supplier\n"
    csv_file = UploadFile(file=io.BytesIO(csv_bytes), filename="sups.csv")
    csv_res = await import_suppliers_csv(file=csv_file, user=admin_user, db=db_session, _=None)
    assert csv_res["imported"] == 1

    # 2. Admin users
    u_req = UserCreateRequest(
        email="direct_user@test.com", password="Password123!", role="reviewer"
    )
    u_res = await create_user(u_req, user=admin_user, db=db_session, _=None)
    assert u_res["email"] == "direct_user@test.com"

    users = await list_users(user=admin_user, db=db_session)
    assert len(users) >= 1

    upd_res = await update_user(
        uuid.UUID(u_res["id"]),
        UserUpdateRequest(is_active=False),
        user=admin_user,
        db=db_session,
        _=None,
    )
    assert upd_res["is_active"] is False

    # 3. Retry invoice
    sf = SourceFile(
        id=uuid.uuid4(),
        sha256="retry_cov_hash",
        original_filename="ret.pdf",
        content_type="application/pdf",
        size_bytes=100,
        storage_key="cov/ret.pdf",
        source="upload",
    )
    inv_failed = Invoice(
        id=uuid.uuid4(),
        source_file_id=sf.id,
        status="FAILED",
    )
    db_session.add_all([sf, inv_failed])
    await db_session.flush()

    with patch("app.services.pipeline.process_invoice_pipeline", AsyncMock()):
        retry_res = await retry_invoice(inv_failed.id, user=admin_user, db=db_session, _=None)
        assert "re-triggered" in retry_res["message"]

    # 4. Auth endpoints
    resp = Response()
    mock_req = MagicMock(client=MagicMock(host="127.0.0.1"))
    login_res = await login(
        LoginRequest(email="admin@test.com", password="AdminPass123"),
        response=resp,
        request=mock_req,
        db=db_session,
    )
    assert login_res.email == "admin@test.com"

    me_res = await get_me(user=admin_user)
    assert me_res.email == admin_user.email

    logout_res = await logout(response=resp)
    assert "Logged out" in logout_res["message"]
