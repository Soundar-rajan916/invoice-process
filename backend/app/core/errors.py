from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import settings


class ProblemDetail(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str | None = None
    extra: dict[str, Any] | None = None


class DomainError(Exception):
    def __init__(
        self,
        title: str,
        detail: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_type: str = "about:blank",
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.title = title
        self.detail = detail
        self.status_code = status_code
        self.error_type = error_type
        self.extra = extra or {}


class InvalidStateTransitionError(DomainError):
    def __init__(self, current_status: str, target_status: str, reason: str = "") -> None:
        detail = f"Cannot transition invoice from '{current_status}' to '{target_status}'. {reason}".strip()
        super().__init__(
            title="Invalid State Transition",
            detail=detail,
            status_code=status.HTTP_409_CONFLICT,
            error_type="https://invoiceflow.local/errors/invalid-state-transition",
            extra={"current_status": current_status, "target_status": target_status},
        )


class OptimisticLockError(DomainError):
    def __init__(self, current_version: int, client_version: int) -> None:
        detail = (
            f"This invoice has been modified by another process. "
            f"Your version: {client_version}, current version: {current_version}. Please reload."
        )
        super().__init__(
            title="Optimistic Lock Conflict",
            detail=detail,
            status_code=status.HTTP_409_CONFLICT,
            error_type="https://invoiceflow.local/errors/conflict",
            extra={"current_version": current_version, "client_version": client_version},
        )


class UnresolvedErrorsApprovalError(DomainError):
    def __init__(self, issue_count: int) -> None:
        detail = (
            f"Invoice has {issue_count} unresolved error-level validation issues. "
            f"An override reason of at least 10 characters is required for approval."
        )
        super().__init__(
            title="Approval Rejected Due To Validation Errors",
            detail=detail,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_type="https://invoiceflow.local/errors/unresolved-validation-errors",
            extra={"issue_count": issue_count},
        )


class DuplicateInvoiceError(DomainError):
    def __init__(self, invoice_number: str, supplier_gstin: str, existing_invoice_id: str) -> None:
        detail = (
            f"Invoice '{invoice_number}' for supplier '{supplier_gstin}' already exists "
            f"(ID: {existing_invoice_id}). Duplicate invoices require human confirmation or override."
        )
        super().__init__(
            title="Duplicate Invoice Detected",
            detail=detail,
            status_code=status.HTTP_409_CONFLICT,
            error_type="https://invoiceflow.local/errors/duplicate-invoice",
            extra={"existing_invoice_id": existing_invoice_id},
        )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        problem = ProblemDetail(
            type=exc.error_type,
            title=exc.title,
            status=exc.status_code,
            detail=exc.detail,
            instance=str(request.url.path),
            extra=exc.extra or None,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=problem.model_dump(exclude_none=True),
            media_type="application/problem+json",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = jsonable_encoder(exc.errors())
        problem = ProblemDetail(
            type="https://invoiceflow.local/errors/validation-error",
            title="Request Validation Error",
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="One or more fields in the request body or query parameters failed validation.",
            instance=str(request.url.path),
            extra={"errors": errors},
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=problem.model_dump(exclude_none=True),
            media_type="application/problem+json",
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        problem = ProblemDetail(
            type="https://invoiceflow.local/errors/internal-server-error",
            title="Internal Server Error",
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc)
            if settings.ENVIRONMENT != "production"
            else "An unexpected error occurred.",
            instance=str(request.url.path),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=problem.model_dump(exclude_none=True),
            media_type="application/problem+json",
        )
