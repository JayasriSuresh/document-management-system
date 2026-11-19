"""
Module 4 – Route-Level Permission Declarations & FastAPI Dependencies.

Provides:
  - require_permission(permission: str) -> FastAPI Dependency
  - @requires(permission: str)          -> Endpoint Decorator
"""

import functools
import inspect
from typing import Any, Callable, Optional, Union

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.authorization import can
from app.auth.permissions import is_valid_permission
from app.config import settings
from app.context import (
    AuthContext,
    MasterAdminContext,
    _build_auth_context,
    _build_master_admin_context,
)
from app.database import get_db


class PermissionChecker:
    """FastAPI dependency callable enforcing a declared permission."""

    def __init__(self, permission: str):
        if not is_valid_permission(permission):
            raise ValueError(f"Unknown permission identifier: '{permission}'")
        self.permission = permission
        self.__required_permission__ = permission

    def __call__(
        self,
        request: Request,
        db: Session = Depends(get_db),
    ) -> Union[AuthContext, MasterAdminContext]:
        # Accept token from Authorization: Bearer <token> or ?token=<token>
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        else:
            token = request.query_params.get("token")

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        ctx: Optional[Union[AuthContext, MasterAdminContext]] = None

        # Inspect unverified token payload to route to the appropriate context builder
        try:
            unverified = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        is_platform = (
            unverified.get("aud") == settings.JWT_AUDIENCE_PLATFORM
            or unverified.get("identity_type") == "master_admin"
            or bool(unverified.get("master_admin_id"))
        )

        if is_platform:
            # Allow Master Admins to access security, platform management, and MFA setup
            allow_unenrolled = self.permission in (
                "platform.manage",
                "mfa.manage_platform",
                "security.manage",
            )
            ctx = _build_master_admin_context(token, db, allow_unenrolled_mfa=allow_unenrolled)
        else:
            ctx = _build_auth_context(token, db)

        if not can(ctx, self.permission):
            role_hint = "Staff cannot delete documents. " if (getattr(ctx, "is_staff", False) and self.permission == "document.delete") else ""
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"{role_hint}Permission denied: Missing required permission '{self.permission}'",
            )

        return ctx


def require_permission(permission: str) -> PermissionChecker:
    """FastAPI dependency factory enforcing that the caller possesses the specified permission."""
    return PermissionChecker(permission)


def requires(permission: str) -> Callable:
    """
    Decorator for FastAPI route handlers that declares the required permission on the function.
    Can be used alongside or in addition to require_permission dependency.
    """
    if not is_valid_permission(permission):
        raise ValueError(f"Unknown permission identifier: '{permission}'")

    def decorator(func: Callable) -> Callable:
        setattr(func, "__required_permission__", permission)
        return func

    return decorator
