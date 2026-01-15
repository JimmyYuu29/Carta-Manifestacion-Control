"""
Review Models - Data models for controlled editing review system
Modelos de datos para sistema de revision con edicion controlada

This module defines:
- Review: Main review entity with status management
- ReviewStatus: State machine enum (DRAFT -> SUBMITTED -> DOWNLOADED)
- AuditLogEntry: Individual audit log record
- DownloadToken: Short-lived token for manager downloads
"""

from enum import Enum
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
import json
import uuid
import hashlib
import secrets
from pathlib import Path


class ReviewStatus(str, Enum):
    """
    Review status state machine
    Maquina de estados para status de revision

    State transitions:
    - DRAFT: Initial state, employee can edit
    - SUBMITTED: Frozen, awaiting manager download
    - DOWNLOADED: Final state, manager has downloaded
    """
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    DOWNLOADED = "DOWNLOADED"


@dataclass
class AuditLogEntry:
    """
    Individual audit log record
    Registro individual de log de auditoria
    """
    timestamp: str
    action: str  # "field_update", "submit", "download", "unauthorized_field_attempt"
    actor: str  # employee_id or "manager"
    field_name: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "AuditLogEntry":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DownloadToken:
    """
    Short-lived token for manager download authorization
    Token de corta duracion para autorizacion de descarga de manager
    """
    token: str
    review_id: str
    created_at: datetime
    expires_at: datetime
    used: bool = False
    used_at: Optional[datetime] = None

    @classmethod
    def generate(cls, review_id: str, ttl_seconds: int = 300) -> "DownloadToken":
        """Generate a new download token with specified TTL (default 5 minutes)"""
        now = datetime.utcnow()
        token = secrets.token_urlsafe(32)
        return cls(
            token=token,
            review_id=review_id,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            used=False
        )

    def is_valid(self) -> bool:
        """Check if token is valid (not expired and not used)"""
        return not self.used and datetime.utcnow() < self.expires_at

    def mark_used(self) -> None:
        """Mark token as used"""
        self.used = True
        self.used_at = datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "token": self.token,
            "review_id": self.review_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "used": self.used,
            "used_at": self.used_at.isoformat() if self.used_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DownloadToken":
        return cls(
            token=data["token"],
            review_id=data["review_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            used=data.get("used", False),
            used_at=datetime.fromisoformat(data["used_at"]) if data.get("used_at") else None
        )


@dataclass
class Review:
    """
    Main review entity with full lifecycle management
    Entidad principal de revision con gestion completa del ciclo de vida
    """
    review_id: str
    doc_type: str
    status: ReviewStatus
    data_json: Dict[str, Any]
    created_by: str
    created_at: datetime
    audit_log: List[AuditLogEntry] = field(default_factory=list)
    submitted_at: Optional[datetime] = None
    downloaded_at: Optional[datetime] = None
    downloaded_by: Optional[str] = None

    @classmethod
    def create(cls, doc_type: str, initial_data: Dict[str, Any], created_by: str) -> "Review":
        """
        Factory method to create a new review in DRAFT status
        Metodo factory para crear una nueva revision en estado DRAFT
        """
        review_id = str(uuid.uuid4())
        now = datetime.utcnow()

        review = cls(
            review_id=review_id,
            doc_type=doc_type,
            status=ReviewStatus.DRAFT,
            data_json=initial_data,
            created_by=created_by,
            created_at=now,
            audit_log=[]
        )

        # Log creation
        review.add_audit_log(AuditLogEntry(
            timestamp=now.isoformat(),
            action="create",
            actor=created_by,
            details=f"Review created for doc_type={doc_type}"
        ))

        return review

    def can_edit(self) -> bool:
        """Check if review can be edited (only in DRAFT status)"""
        return self.status == ReviewStatus.DRAFT

    def can_submit(self) -> bool:
        """Check if review can be submitted (only in DRAFT status)"""
        return self.status == ReviewStatus.DRAFT

    def can_download(self) -> bool:
        """Check if review can be downloaded (only in SUBMITTED status)"""
        return self.status == ReviewStatus.SUBMITTED

    def update_field(self, field_name: str, new_value: Any, actor: str,
                     ip_address: Optional[str] = None) -> bool:
        """
        Update a single field value with audit logging
        Returns False if review is not editable
        """
        if not self.can_edit():
            return False

        old_value = self.data_json.get(field_name)
        self.data_json[field_name] = new_value

        self.add_audit_log(AuditLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            action="field_update",
            actor=actor,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address
        ))

        return True

    def log_unauthorized_attempt(self, field_name: str, attempted_value: Any,
                                  actor: str, ip_address: Optional[str] = None) -> None:
        """Log an attempted update to a non-editable field"""
        self.add_audit_log(AuditLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            action="unauthorized_field_attempt",
            actor=actor,
            field_name=field_name,
            new_value=attempted_value,
            ip_address=ip_address,
            details="Attempted to update non-editable field"
        ))

    def submit(self, actor: str, ip_address: Optional[str] = None) -> bool:
        """
        Submit review for manager approval, transitioning to SUBMITTED status
        Returns False if review cannot be submitted
        """
        if not self.can_submit():
            return False

        self.status = ReviewStatus.SUBMITTED
        self.submitted_at = datetime.utcnow()

        self.add_audit_log(AuditLogEntry(
            timestamp=self.submitted_at.isoformat(),
            action="submit",
            actor=actor,
            ip_address=ip_address,
            details="Review submitted and frozen"
        ))

        return True

    def mark_downloaded(self, actor: str = "manager",
                        ip_address: Optional[str] = None,
                        user_agent: Optional[str] = None) -> bool:
        """
        Mark review as downloaded, transitioning to DOWNLOADED status
        Returns False if review cannot be downloaded
        """
        if not self.can_download():
            return False

        self.status = ReviewStatus.DOWNLOADED
        self.downloaded_at = datetime.utcnow()
        self.downloaded_by = actor

        self.add_audit_log(AuditLogEntry(
            timestamp=self.downloaded_at.isoformat(),
            action="download",
            actor=actor,
            ip_address=ip_address,
            user_agent=user_agent,
            details="Document downloaded by manager"
        ))

        return True

    def add_audit_log(self, entry: AuditLogEntry) -> None:
        """Add an audit log entry"""
        self.audit_log.append(entry)

    def get_editable_data(self, schema_editable_fields: List[str]) -> Dict[str, Any]:
        """Return only editable fields from data_json"""
        return {k: v for k, v in self.data_json.items() if k in schema_editable_fields}

    def to_dict(self) -> dict:
        """Serialize review to dictionary for storage"""
        return {
            "review_id": self.review_id,
            "doc_type": self.doc_type,
            "status": self.status.value,
            "data_json": self.data_json,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "audit_log": [entry.to_dict() for entry in self.audit_log],
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "downloaded_at": self.downloaded_at.isoformat() if self.downloaded_at else None,
            "downloaded_by": self.downloaded_by
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Review":
        """Deserialize review from dictionary"""
        return cls(
            review_id=data["review_id"],
            doc_type=data["doc_type"],
            status=ReviewStatus(data["status"]),
            data_json=data["data_json"],
            created_by=data["created_by"],
            created_at=datetime.fromisoformat(data["created_at"]),
            audit_log=[AuditLogEntry.from_dict(e) for e in data.get("audit_log", [])],
            submitted_at=datetime.fromisoformat(data["submitted_at"]) if data.get("submitted_at") else None,
            downloaded_at=datetime.fromisoformat(data["downloaded_at"]) if data.get("downloaded_at") else None,
            downloaded_by=data.get("downloaded_by")
        )

    def get_manager_link(self, base_url: str) -> str:
        """Generate the manager download entry link"""
        return f"{base_url}/manager/reviews/{self.review_id}"
