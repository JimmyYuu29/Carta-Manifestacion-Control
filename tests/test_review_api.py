"""
Review API Tests - Security and Functionality Validation
Tests de API de Revision - Validacion de Seguridad y Funcionalidad

Test coverage:
1. Whitelist field validation
2. Status machine transitions
3. Token authorization and expiration
4. Audit logging
5. Download permissions

Run with: pytest tests/test_review_api.py -v
"""

import pytest
import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.models.review import Review, ReviewStatus, AuditLogEntry, DownloadToken
from api.services.validation import SchemaValidator, ValidationResult
from api.services.storage import ReviewStorage


# Test fixtures
@pytest.fixture
def sample_data():
    """Sample review data"""
    return {
        "Nombre_Cliente": "Test Client S.A.",
        "Fecha_de_hoy": "2024-01-15",
        "Fecha_encargo": "2024-01-01",
        "FF_Ejecicio": "2024-12-31",
        "Fecha_cierre": "2024-12-31",
        "Oficina_Seleccionada": "BARCELONA",
        "Direccion_Oficina": "C/ Diputacio, 260",
        "CP": "08007",
        "Ciudad_Oficina": "Barcelona",
        "organo": "consejo",
        "Nombre_Firma": "Juan Perez",
        "Cargo_Firma": "Director"
    }


@pytest.fixture
def validator():
    """Schema validator instance"""
    return SchemaValidator()


@pytest.fixture
def temp_storage(tmp_path):
    """Temporary storage for tests"""
    return ReviewStorage(base_dir=tmp_path / "reviews")


class TestReviewModel:
    """Tests for Review model and state machine"""

    def test_create_review_draft_status(self, sample_data):
        """Test 1: Review created in DRAFT status"""
        review = Review.create(
            doc_type="carta_manifestacion",
            initial_data=sample_data,
            created_by="employee_1"
        )

        assert review.status == ReviewStatus.DRAFT
        assert review.can_edit() is True
        assert review.can_submit() is True
        assert review.can_download() is False

    def test_submit_transitions_to_submitted(self, sample_data):
        """Test 2: Submit transitions status to SUBMITTED"""
        review = Review.create("carta_manifestacion", sample_data, "employee_1")

        success = review.submit("employee_1", "192.168.1.1")

        assert success is True
        assert review.status == ReviewStatus.SUBMITTED
        assert review.can_edit() is False
        assert review.can_submit() is False
        assert review.can_download() is True
        assert review.submitted_at is not None

    def test_cannot_edit_after_submit(self, sample_data):
        """Test 3: Cannot edit after submit (frozen state)"""
        review = Review.create("carta_manifestacion", sample_data, "employee_1")
        review.submit("employee_1")

        # Attempt to update field
        success = review.update_field("Nombre_Cliente", "New Name", "employee_1")

        assert success is False
        assert review.data_json["Nombre_Cliente"] == sample_data["Nombre_Cliente"]

    def test_audit_log_records_updates(self, sample_data):
        """Test 4: Audit log records all field updates"""
        review = Review.create("carta_manifestacion", sample_data, "employee_1")

        review.update_field("Nombre_Cliente", "Updated Name", "employee_1", "192.168.1.1")
        review.update_field("Nombre_Firma", "Updated Signer", "employee_1", "192.168.1.1")

        # Check audit log
        update_logs = [e for e in review.audit_log if e.action == "field_update"]
        assert len(update_logs) == 2
        assert update_logs[0].field_name == "Nombre_Cliente"
        assert update_logs[0].old_value == sample_data["Nombre_Cliente"]
        assert update_logs[0].new_value == "Updated Name"


class TestSchemaValidation:
    """Tests for schema-based whitelist validation"""

    def test_editable_fields_whitelist(self, validator):
        """Test 5: Only editable fields are in whitelist"""
        editable = validator.get_editable_fields("carta_manifestacion")

        # These should be editable
        assert "Nombre_Cliente" in editable
        assert "Nombre_Firma" in editable
        assert "Cargo_Firma" in editable
        assert "Fecha_encargo" in editable

        # These should NOT be editable
        assert "Fecha_de_hoy" not in editable
        assert "Oficina_Seleccionada" not in editable
        assert "organo" not in editable

    def test_reject_non_editable_fields(self, validator):
        """Test 6: Updates to non-editable fields are rejected"""
        update_data = {
            "Nombre_Cliente": "Valid Update",  # Editable
            "Oficina_Seleccionada": "MALAGA",  # Not editable - should be rejected
            "organo": "administrador_unico"     # Not editable - should be rejected
        }

        result = validator.validate_update("carta_manifestacion", update_data)

        assert "Nombre_Cliente" in result.filtered_data
        assert "Oficina_Seleccionada" not in result.filtered_data
        assert "organo" not in result.filtered_data
        assert "Oficina_Seleccionada" in result.unauthorized_fields
        assert "organo" in result.unauthorized_fields

    def test_validation_rules_enforced(self, validator):
        """Test 7: Field validation rules are enforced"""
        # Test max_length validation
        update_data = {
            "Nombre_Cliente": "A" * 300  # Exceeds max_length of 200
        }

        result = validator.validate_update("carta_manifestacion", update_data)

        assert result.is_valid is False
        assert any(e.field == "Nombre_Cliente" for e in result.errors)


class TestDownloadToken:
    """Tests for download token security"""

    def test_token_generation_and_validation(self):
        """Test 8: Token generation with TTL and single-use"""
        token = DownloadToken.generate("review_123", ttl_seconds=60)

        assert token.is_valid() is True
        assert token.used is False
        assert token.review_id == "review_123"

    def test_token_expires(self):
        """Test 9: Token expires after TTL"""
        token = DownloadToken.generate("review_123", ttl_seconds=1)

        assert token.is_valid() is True

        # Wait for expiration
        time.sleep(1.5)

        assert token.is_valid() is False

    def test_token_single_use(self):
        """Test 10: Token becomes invalid after use"""
        token = DownloadToken.generate("review_123", ttl_seconds=300)

        assert token.is_valid() is True

        token.mark_used()

        assert token.is_valid() is False
        assert token.used is True
        assert token.used_at is not None


class TestStorage:
    """Tests for review storage"""

    def test_save_and_load_review(self, temp_storage, sample_data):
        """Test 11: Review persists correctly"""
        review = Review.create("carta_manifestacion", sample_data, "employee_1")
        temp_storage.save(review)

        loaded = temp_storage.load(review.review_id)

        assert loaded is not None
        assert loaded.review_id == review.review_id
        assert loaded.status == ReviewStatus.DRAFT
        assert loaded.data_json == sample_data

    def test_token_storage_and_consumption(self, temp_storage):
        """Test 12: Token storage with consumption"""
        token = temp_storage.create_download_token("review_123", ttl_seconds=300)

        # Valid token
        assert temp_storage.validate_and_consume_token(token.token, "review_123") is True

        # Token already consumed
        assert temp_storage.validate_and_consume_token(token.token, "review_123") is False

    def test_token_wrong_review_id(self, temp_storage):
        """Test 13: Token invalid for different review_id"""
        token = temp_storage.create_download_token("review_123", ttl_seconds=300)

        # Wrong review_id
        assert temp_storage.validate_and_consume_token(token.token, "review_456") is False


class TestSecurityRequirements:
    """Critical security requirement tests"""

    def test_no_docx_exposed_in_draft(self, sample_data, temp_storage):
        """Test 14: No DOCX download possible in DRAFT status"""
        review = Review.create("carta_manifestacion", sample_data, "employee_1")
        temp_storage.save(review)

        assert review.can_download() is False

    def test_unauthorized_field_logged(self, sample_data):
        """Test 15: Unauthorized field attempts are logged"""
        review = Review.create("carta_manifestacion", sample_data, "employee_1")

        review.log_unauthorized_attempt(
            field_name="Oficina_Seleccionada",
            attempted_value="HACKED",
            actor="employee_1",
            ip_address="192.168.1.100"
        )

        audit_entries = [e for e in review.audit_log if e.action == "unauthorized_field_attempt"]
        assert len(audit_entries) == 1
        assert audit_entries[0].field_name == "Oficina_Seleccionada"
        assert audit_entries[0].new_value == "HACKED"

    def test_download_only_with_valid_token(self, temp_storage, sample_data):
        """Test 16: Download requires valid token"""
        review = Review.create("carta_manifestacion", sample_data, "employee_1")
        review.submit("employee_1")
        temp_storage.save(review)

        # Create token
        token = temp_storage.create_download_token(review.review_id, ttl_seconds=300)

        # Valid token for correct review
        assert temp_storage.validate_and_consume_token(token.token, review.review_id) is True

        # Invalid random token
        assert temp_storage.validate_and_consume_token("invalid_token", review.review_id) is False


class TestAPIIntegration:
    """Integration tests for API endpoints"""

    @pytest.fixture
    def client(self):
        """FastAPI test client"""
        # Set test password
        os.environ["MANAGER_PASSWORD"] = "test_password"

        from fastapi.testclient import TestClient
        from api.app import app
        return TestClient(app)

    def test_create_and_get_preview(self, client, sample_data):
        """Test 17: Create review and get HTML preview"""
        # Create review
        response = client.post("/reviews", json={
            "doc_type": "carta_manifestacion",
            "initial_data": sample_data,
            "created_by": "test_employee"
        })

        assert response.status_code == 200
        data = response.json()
        assert "review_id" in data
        assert data["status"] == "DRAFT"

        # Get preview
        review_id = data["review_id"]
        response = client.get(f"/reviews/{review_id}/preview")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert sample_data["Nombre_Cliente"] in response.text

    def test_patch_blocked_after_submit(self, client, sample_data):
        """Test 18: PATCH returns 403 after submit"""
        # Create review
        response = client.post("/reviews", json={
            "doc_type": "carta_manifestacion",
            "initial_data": sample_data,
            "created_by": "test_employee"
        })
        review_id = response.json()["review_id"]

        # Submit
        response = client.post(f"/reviews/{review_id}/submit")
        assert response.status_code == 200

        # Try to patch - should fail
        response = client.patch(f"/reviews/{review_id}/data", json={
            "data": {"Nombre_Cliente": "Hacked Name"}
        })

        assert response.status_code == 403

    def test_manager_wrong_password(self, client, sample_data):
        """Test 19: Manager authorization fails with wrong password"""
        # Create and submit review
        response = client.post("/reviews", json={
            "doc_type": "carta_manifestacion",
            "initial_data": sample_data
        })
        review_id = response.json()["review_id"]
        client.post(f"/reviews/{review_id}/submit")

        # Try wrong password
        response = client.post(f"/manager/reviews/{review_id}/authorize", json={
            "password": "wrong_password"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Invalid password" in data["error"]

    def test_manager_correct_password_gets_token(self, client, sample_data):
        """Test 20: Manager gets download token with correct password"""
        # Create and submit review
        response = client.post("/reviews", json={
            "doc_type": "carta_manifestacion",
            "initial_data": sample_data
        })
        review_id = response.json()["review_id"]
        client.post(f"/reviews/{review_id}/submit")

        # Correct password
        response = client.post(f"/manager/reviews/{review_id}/authorize", json={
            "password": "test_password"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "token" in data
        assert "download_url" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
