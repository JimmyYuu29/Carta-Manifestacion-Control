"""
Storage Service - File-based storage for reviews with concurrency control
Servicio de almacenamiento basado en archivos para revisiones con control de concurrencia
"""

import json
import os
import fcntl
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import threading

from ..models.review import Review, DownloadToken


class ReviewStorage:
    """
    File-based storage for reviews with file locking for concurrency
    Almacenamiento basado en archivos para revisiones con bloqueo de archivos
    """

    def __init__(self, base_dir: Path = None):
        if base_dir is None:
            base_dir = Path(__file__).parent.parent.parent / "storage" / "reviews"
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Token storage (in-memory with persistence)
        self._tokens: Dict[str, DownloadToken] = {}
        self._tokens_file = self.base_dir / "_tokens.json"
        self._load_tokens()

        # Thread lock for token operations
        self._token_lock = threading.Lock()

    def _get_review_dir(self, review_id: str) -> Path:
        """Get directory for a specific review"""
        return self.base_dir / review_id

    def _get_review_file(self, review_id: str) -> Path:
        """Get review.json path for a specific review"""
        return self._get_review_dir(review_id) / "review.json"

    def save(self, review: Review) -> None:
        """
        Save review to storage with file locking
        Guardar revision en almacenamiento con bloqueo de archivo
        """
        review_dir = self._get_review_dir(review.review_id)
        review_dir.mkdir(parents=True, exist_ok=True)

        review_file = self._get_review_file(review.review_id)

        # Use file locking for concurrent access
        with open(review_file, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(review.to_dict(), f, indent=2, ensure_ascii=False)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def load(self, review_id: str) -> Optional[Review]:
        """
        Load review from storage
        Cargar revision desde almacenamiento
        """
        review_file = self._get_review_file(review_id)

        if not review_file.exists():
            return None

        with open(review_file, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                data = json.load(f)
                return Review.from_dict(data)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def exists(self, review_id: str) -> bool:
        """Check if review exists"""
        return self._get_review_file(review_id).exists()

    def list_reviews(self, status: Optional[str] = None, created_by: Optional[str] = None) -> List[Review]:
        """
        List all reviews, optionally filtered by status or creator
        Listar todas las revisiones, opcionalmente filtradas por estado o creador
        """
        reviews = []

        for review_dir in self.base_dir.iterdir():
            if not review_dir.is_dir() or review_dir.name.startswith("_"):
                continue

            review = self.load(review_dir.name)
            if review:
                if status and review.status.value != status:
                    continue
                if created_by and review.created_by != created_by:
                    continue
                reviews.append(review)

        # Sort by creation date, newest first
        reviews.sort(key=lambda r: r.created_at, reverse=True)
        return reviews

    def delete(self, review_id: str) -> bool:
        """Delete a review and its directory"""
        review_dir = self._get_review_dir(review_id)
        if not review_dir.exists():
            return False

        import shutil
        shutil.rmtree(review_dir)
        return True

    # Token management
    def _load_tokens(self) -> None:
        """Load tokens from persistent storage"""
        if self._tokens_file.exists():
            try:
                with open(self._tokens_file, 'r') as f:
                    data = json.load(f)
                    self._tokens = {
                        k: DownloadToken.from_dict(v)
                        for k, v in data.items()
                    }
            except (json.JSONDecodeError, KeyError):
                self._tokens = {}

    def _save_tokens(self) -> None:
        """Save tokens to persistent storage"""
        with open(self._tokens_file, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(
                    {k: v.to_dict() for k, v in self._tokens.items()},
                    f, indent=2
                )
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def create_download_token(self, review_id: str, ttl_seconds: int = 300) -> DownloadToken:
        """
        Create a new download token for a review
        Crear un nuevo token de descarga para una revision
        """
        with self._token_lock:
            token = DownloadToken.generate(review_id, ttl_seconds)
            self._tokens[token.token] = token
            self._save_tokens()
            return token

    def validate_and_consume_token(self, token_str: str, review_id: str) -> bool:
        """
        Validate a download token and mark it as used if valid
        Returns True if token is valid and was consumed
        """
        with self._token_lock:
            token = self._tokens.get(token_str)

            if not token:
                return False

            if token.review_id != review_id:
                return False

            if not token.is_valid():
                return False

            # Mark as used
            token.mark_used()
            self._save_tokens()
            return True

    def get_token(self, token_str: str) -> Optional[DownloadToken]:
        """Get token by string (for inspection, doesn't consume)"""
        return self._tokens.get(token_str)

    def cleanup_expired_tokens(self) -> int:
        """Remove expired tokens, returns count of removed tokens"""
        with self._token_lock:
            now = datetime.utcnow()
            expired = [k for k, v in self._tokens.items()
                       if v.expires_at < now or v.used]
            for k in expired:
                del self._tokens[k]

            if expired:
                self._save_tokens()

            return len(expired)
