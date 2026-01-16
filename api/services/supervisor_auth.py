"""
Supervisor Authentication Service - Multi-supervisor authentication and approval code management
Servicio de Autenticacion de Supervisores - Autenticacion multi-supervisor y gestion de codigos de aprobacion

This module handles:
1. Multi-supervisor authentication (password verification)
2. Approval code generation and validation
3. Supervisor management (list, verify, etc.)
"""

import json
import hashlib
import secrets
import string
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, asdict
import threading

# Path to supervisors configuration
SUPERVISORS_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "supervisors.json"
APPROVAL_CODES_PATH = Path(__file__).parent.parent.parent / "storage" / "approval_codes.json"


@dataclass
class Supervisor:
    """Supervisor data model"""
    id: str
    name: str
    email: str
    active: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ApprovalCode:
    """Approval code data model"""
    code: str
    review_id: str
    supervisor_id: str
    created_at: str
    expires_at: str
    used: bool = False
    used_at: Optional[str] = None

    def is_expired(self) -> bool:
        """Check if code has expired"""
        expires = datetime.fromisoformat(self.expires_at)
        return datetime.utcnow() > expires

    def is_valid(self) -> bool:
        """Check if code is valid (not used and not expired)"""
        return not self.used and not self.is_expired()

    def to_dict(self) -> dict:
        return asdict(self)


class SupervisorAuthService:
    """
    Service for managing supervisor authentication and approval codes
    """

    def __init__(self):
        self._config: Optional[dict] = None
        self._approval_codes: Dict[str, ApprovalCode] = {}
        self._lock = threading.Lock()
        self._load_config()
        self._load_approval_codes()

    def _load_config(self) -> None:
        """Load supervisors configuration from JSON file"""
        if SUPERVISORS_CONFIG_PATH.exists():
            with open(SUPERVISORS_CONFIG_PATH, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
        else:
            # Default configuration
            self._config = {
                "supervisors": {
                    "admin": {
                        "name": "Administrador",
                        "email": "admin@forvismazars.com",
                        "password": "Forvis30",
                        "active": True
                    },
                    "maria_jose": {
                        "name": "Maria Jose",
                        "email": "maria.jose@forvismazars.com",
                        "password": "maria_jose123",
                        "active": True
                    }
                },
                "settings": {
                    "approval_code_ttl_hours": 72,
                    "download_token_ttl_seconds": 300,
                    "max_failed_attempts": 5,
                    "lockout_duration_minutes": 30
                }
            }
            # Save default config
            SUPERVISORS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(SUPERVISORS_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)

    def _load_approval_codes(self) -> None:
        """Load approval codes from storage"""
        if APPROVAL_CODES_PATH.exists():
            try:
                with open(APPROVAL_CODES_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for code, code_data in data.items():
                        self._approval_codes[code] = ApprovalCode(**code_data)
            except (json.JSONDecodeError, TypeError):
                self._approval_codes = {}
        else:
            self._approval_codes = {}

    def _save_approval_codes(self) -> None:
        """Save approval codes to storage"""
        APPROVAL_CODES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(APPROVAL_CODES_PATH, 'w', encoding='utf-8') as f:
            data = {code: ac.to_dict() for code, ac in self._approval_codes.items()}
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _hash_password(self, password: str) -> str:
        """Generate SHA-256 hash of password"""
        return hashlib.sha256(password.encode()).hexdigest()

    def _generate_approval_code(self) -> str:
        """Generate a unique 8-character approval code"""
        chars = string.ascii_uppercase + string.digits
        while True:
            code = ''.join(secrets.choice(chars) for _ in range(8))
            if code not in self._approval_codes:
                return code

    def get_supervisors_list(self) -> List[Supervisor]:
        """
        Get list of active supervisors (without passwords)
        Returns list safe for display in UI
        """
        supervisors = []
        for sup_id, sup_data in self._config.get("supervisors", {}).items():
            if sup_data.get("active", True):
                supervisors.append(Supervisor(
                    id=sup_id,
                    name=sup_data.get("name", sup_id),
                    email=sup_data.get("email", ""),
                    active=True
                ))
        return supervisors

    def get_supervisor(self, supervisor_id: str) -> Optional[Supervisor]:
        """Get supervisor by ID"""
        sup_data = self._config.get("supervisors", {}).get(supervisor_id)
        if sup_data and sup_data.get("active", True):
            return Supervisor(
                id=supervisor_id,
                name=sup_data.get("name", supervisor_id),
                email=sup_data.get("email", ""),
                active=True
            )
        return None

    def verify_password(self, supervisor_id: str, password: str) -> bool:
        """
        Verify supervisor password
        Checks both plain password and hash for flexibility
        """
        sup_data = self._config.get("supervisors", {}).get(supervisor_id)
        if not sup_data:
            return False

        if not sup_data.get("active", True):
            return False

        # Check password hash first (more secure)
        stored_hash = sup_data.get("password_hash")
        if stored_hash:
            if self._hash_password(password) == stored_hash:
                return True

        # Fall back to plain password (for development/initial setup)
        stored_password = sup_data.get("password")
        if stored_password and password == stored_password:
            return True

        return False

    def create_approval_code(self, review_id: str, supervisor_id: str) -> Tuple[str, ApprovalCode]:
        """
        Create a new approval code for a review

        Args:
            review_id: The review ID this code is for
            supervisor_id: The supervisor who will use this code

        Returns:
            Tuple of (code_string, ApprovalCode object)
        """
        with self._lock:
            # Check supervisor exists
            if not self.get_supervisor(supervisor_id):
                raise ValueError(f"Unknown supervisor: {supervisor_id}")

            # Generate code
            code = self._generate_approval_code()

            # Calculate expiration
            ttl_hours = self._config.get("settings", {}).get("approval_code_ttl_hours", 72)
            now = datetime.utcnow()
            expires_at = now + timedelta(hours=ttl_hours)

            # Create approval code object
            approval_code = ApprovalCode(
                code=code,
                review_id=review_id,
                supervisor_id=supervisor_id,
                created_at=now.isoformat(),
                expires_at=expires_at.isoformat(),
                used=False
            )

            # Store
            self._approval_codes[code] = approval_code
            self._save_approval_codes()

            return code, approval_code

    def validate_approval_code(self, code: str) -> Tuple[bool, Optional[ApprovalCode], str]:
        """
        Validate an approval code

        Args:
            code: The approval code to validate

        Returns:
            Tuple of (is_valid, ApprovalCode if valid, error_message)
        """
        code = code.upper().strip()

        if code not in self._approval_codes:
            return False, None, "Codigo de aprobacion no encontrado"

        approval_code = self._approval_codes[code]

        if approval_code.used:
            return False, None, "Este codigo ya ha sido utilizado"

        if approval_code.is_expired():
            return False, None, "El codigo de aprobacion ha expirado"

        return True, approval_code, ""

    def use_approval_code(self, code: str) -> bool:
        """
        Mark an approval code as used

        Args:
            code: The approval code to mark as used

        Returns:
            True if successfully marked, False otherwise
        """
        with self._lock:
            code = code.upper().strip()

            if code not in self._approval_codes:
                return False

            approval_code = self._approval_codes[code]
            if approval_code.used:
                return False

            approval_code.used = True
            approval_code.used_at = datetime.utcnow().isoformat()
            self._save_approval_codes()

            return True

    def get_approval_code_info(self, code: str) -> Optional[Dict[str, Any]]:
        """Get information about an approval code (for display)"""
        code = code.upper().strip()

        if code not in self._approval_codes:
            return None

        ac = self._approval_codes[code]
        supervisor = self.get_supervisor(ac.supervisor_id)

        return {
            "code": ac.code,
            "review_id": ac.review_id,
            "supervisor_id": ac.supervisor_id,
            "supervisor_name": supervisor.name if supervisor else "Unknown",
            "created_at": ac.created_at,
            "expires_at": ac.expires_at,
            "used": ac.used,
            "used_at": ac.used_at,
            "is_valid": ac.is_valid()
        }

    def cleanup_expired_codes(self) -> int:
        """
        Remove expired approval codes from storage

        Returns:
            Number of codes removed
        """
        with self._lock:
            initial_count = len(self._approval_codes)
            self._approval_codes = {
                code: ac for code, ac in self._approval_codes.items()
                if not ac.is_expired() or ac.used  # Keep used codes for audit trail
            }
            removed = initial_count - len(self._approval_codes)
            if removed > 0:
                self._save_approval_codes()
            return removed

    def get_codes_for_review(self, review_id: str) -> List[Dict[str, Any]]:
        """Get all approval codes generated for a specific review"""
        codes = []
        for ac in self._approval_codes.values():
            if ac.review_id == review_id:
                supervisor = self.get_supervisor(ac.supervisor_id)
                codes.append({
                    "code": ac.code,
                    "supervisor_name": supervisor.name if supervisor else "Unknown",
                    "created_at": ac.created_at,
                    "expires_at": ac.expires_at,
                    "used": ac.used,
                    "is_valid": ac.is_valid()
                })
        return codes


# Singleton instance
_supervisor_auth_service: Optional[SupervisorAuthService] = None


def get_supervisor_auth_service() -> SupervisorAuthService:
    """Get singleton instance of SupervisorAuthService"""
    global _supervisor_auth_service
    if _supervisor_auth_service is None:
        _supervisor_auth_service = SupervisorAuthService()
    return _supervisor_auth_service
