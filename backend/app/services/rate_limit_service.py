"""
Rate limiting and brute-force account lockout service.

Enforces:
  1. Progressive account lockout after consecutive failed login attempts (DB-backed).
  2. In-memory sliding window IP rate limiting for sensitive authentication endpoints.
  3. Safe proxy header handling.
"""

import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional, Union

from fastapi import HTTPException, Request, status

from app.config import settings
from app.models import AccountStatus, MasterAdmin, User

logger = logging.getLogger("dms.security")


class RateLimitService:
    def __init__(self):
        # Sliding window log: ip -> list of timestamps
        self._ip_windows = defaultdict(list)
        self._lock = threading.Lock()

    def check_ip_rate_limit(
        self,
        request: Request,
        action: str,
        max_requests: int = 20,
        window_seconds: int = 60,
    ) -> None:
        """
        Sliding-window rate limiter per client IP and action.
        """
        client_ip = request.client.host if request.client else "unknown"
        if settings.is_test or client_ip == "testclient":
            return
        key = f"{action}:{client_ip}"
        now = time.time()

        with self._lock:
            # Prune timestamps older than window
            cutoff = now - window_seconds
            timestamps = [ts for ts in self._ip_windows[key] if ts > cutoff]
            self._ip_windows[key] = timestamps

            if len(timestamps) >= max_requests:
                logger.warning("Rate limit exceeded for IP %s on action %s", client_ip, action)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please slow down and try again later.",
                )

            self._ip_windows[key].append(now)

    @staticmethod
    def check_lockout(identity: Union[User, MasterAdmin]) -> None:
        """
        Check if account is currently locked due to failed attempts.
        If lockout duration has expired, clears lockout automatically.
        """
        if identity.locked_until:
            if identity.locked_until > datetime.utcnow():
                logger.warning(
                    "Attempted login on locked account: %s (locked until %s)",
                    identity.email,
                    identity.locked_until,
                )
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail="Account is temporarily locked due to multiple failed login attempts. Please try again later.",
                )
            else:
                # Lockout expired — clear
                identity.locked_until = None
                identity.failed_attempts = 0

    @staticmethod
    def record_failed_attempt(db, identity: Union[User, MasterAdmin]) -> None:
        """
        Increment failed attempt count. Lock account if threshold exceeded.
        """
        identity.failed_attempts = (identity.failed_attempts or 0) + 1
        if identity.failed_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
            identity.locked_until = datetime.utcnow() + timedelta(
                minutes=settings.LOCKOUT_DURATION_MINUTES
            )
            logger.warning(
                "Account locked: %s reached %d failed attempts. Locked for %d minutes.",
                identity.email,
                identity.failed_attempts,
                settings.LOCKOUT_DURATION_MINUTES,
            )
            from app.audit import audit, AUTH_ACCOUNT_LOCKOUT, ActorType
            is_master = hasattr(identity, "role") and identity.role == "MASTER_ADMIN"
            audit.record(
                db=db,
                action=AUTH_ACCOUNT_LOCKOUT,
                actor_type=ActorType.MASTER_ADMIN if is_master else ActorType.COMPANY_USER,
                actor_id=identity.id,
                company_id=getattr(identity, "company_id", None),
                branch_id=getattr(identity, "branch_id", None),
                object_type="user" if not is_master else "master_admin",
                object_id=identity.id,
                metadata={"email": identity.email, "failed_attempts": identity.failed_attempts, "lockout_minutes": settings.LOCKOUT_DURATION_MINUTES},
            )
        db.commit()

    @staticmethod
    def record_successful_login(db, identity: Union[User, MasterAdmin]) -> None:
        """
        Reset failed attempts and update last login timestamp.
        """
        identity.failed_attempts = 0
        identity.locked_until = None
        if hasattr(identity, "last_login_at"):
            identity.last_login_at = datetime.utcnow()
        db.commit()


rate_limit_service = RateLimitService()
