"""
B1 Mode Tests - Block custom field validation and rendering
Tests del Modo B1 - Validacion y renderizado de campos custom de bloques

Test coverage:
1. Custom field update works correctly
2. Empty custom doesn't append
3. SUBMITTED state blocks custom field updates
4. Variable field updates rejected
5. Manager download includes base + custom
6. All three append_modes work correctly
7. HTML sanitization for richtext
8. Max length validation

Run with: pytest tests/test_block_mode.py -v
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.models.review import Review, ReviewStatus
from api.services.validation import SchemaValidator
from api.services.block_parser import (
    BlockParser, BlockDefinition, AppendMode,
    CustomFieldType, HtmlSanitizer
)
from api.services.storage import ReviewStorage


@pytest.fixture
def sample_data():
    """Sample review data with block custom fields"""
    return {
        "Nombre_Cliente": "ACME Corp",
        "Fecha_de_hoy": "2024-01-15",
        "Fecha_encargo": "2024-01-01",
        "Oficina_Seleccionada": "BARCELONA",
        "Direccion_Oficina": "C/ Diputacio, 260",
        "CP": "08007",
        "Ciudad_Oficina": "Barcelona",
        "organo": "consejo",
        "Nombre_Firma": "Juan Perez",
        "Cargo_Firma": "Director",
        # Block custom fields
        "scope_base_custom": "",
        "responsabilidades_custom": "",
        "manifestaciones_generales_custom": "",
        "hechos_posteriores_custom": ""
    }


@pytest.fixture
def validator():
    """Schema validator instance"""
    return SchemaValidator()


@pytest.fixture
def block_parser():
    """Block parser instance"""
    return BlockParser()


@pytest.fixture
def temp_storage(tmp_path):
    """Temporary storage for tests"""
    return ReviewStorage(base_dir=tmp_path / "reviews")


class TestBlockCustomFieldValidation:
    """Tests for block custom field validation"""

    def test_custom_field_update_works(self, validator, sample_data):
        """Test 1: Custom field update is accepted and stored correctly"""
        update_data = {
            "scope_base_custom": "Additional scope notes from employee"
        }

        result = validator.validate_update("carta_manifestacion", update_data)

        assert result.is_valid is True
        assert "scope_base_custom" in result.filtered_data
        assert result.filtered_data["scope_base_custom"] == "Additional scope notes from employee"
        assert len(result.unauthorized_fields) == 0

    def test_empty_custom_accepted(self, validator):
        """Test 2: Empty custom field value is accepted (not appended)"""
        update_data = {
            "scope_base_custom": ""
        }

        result = validator.validate_update("carta_manifestacion", update_data)

        assert result.is_valid is True
        assert result.filtered_data.get("scope_base_custom") == ""

    def test_submitted_blocks_custom_update(self, temp_storage, sample_data):
        """Test 3: SUBMITTED status prevents custom field updates"""
        # Create and submit review
        review = Review.create("carta_manifestacion", sample_data, "employee_1")
        review.submit("employee_1")
        temp_storage.save(review)

        # Verify cannot edit
        assert review.can_edit() is False
        assert review.status == ReviewStatus.SUBMITTED

        # Try to update
        success = review.update_field("scope_base_custom", "Hacked value", "employee_1")

        assert success is False
        assert review.data_json.get("scope_base_custom", "") == ""

    def test_variable_field_rejected(self, validator):
        """Test 4: Updates to template variable fields are rejected"""
        update_data = {
            "scope_base_custom": "Valid custom",  # Should be accepted
            "Nombre_Cliente": "HACKED NAME",       # Regular field - editable
            "Oficina_Seleccionada": "HACKED"       # NOT editable - rejected
        }

        result = validator.validate_update("carta_manifestacion", update_data)

        # Custom field accepted
        assert "scope_base_custom" in result.filtered_data

        # Editable field accepted
        assert "Nombre_Cliente" in result.filtered_data

        # Non-editable field rejected
        assert "Oficina_Seleccionada" not in result.filtered_data
        assert "Oficina_Seleccionada" in result.unauthorized_fields


class TestBlockAppendModes:
    """Tests for different append modes"""

    def test_newline_append_mode(self, block_parser):
        """Test 5a: Newline append mode works correctly"""
        base = "El alcance del trabajo incluye revision de estados financieros."
        custom = "Nota adicional del empleado."

        result = block_parser.combine_content(base, custom, AppendMode.NEWLINE)

        assert result == f"{base}\n{custom}"

    def test_inline_append_mode(self, block_parser):
        """Test 5b: Inline append mode works correctly"""
        base = "El alcance del trabajo incluye revision de estados financieros."
        custom = "Incluyendo subsidiarias."

        result = block_parser.combine_content(base, custom, AppendMode.INLINE)

        assert result == f"{base} {custom}"

    def test_labelled_append_mode(self, block_parser):
        """Test 5c: Labelled append mode works correctly"""
        base = "Las responsabilidades de la direccion son:"
        custom = "Ver anexo detallado."
        label = "Nota adicional:"

        result = block_parser.combine_content(base, custom, AppendMode.LABELLED, label)

        assert result == f"{base}\n{label} {custom}"

    def test_empty_custom_no_append(self, block_parser):
        """Test 6: Empty custom doesn't append anything"""
        base = "El alcance del trabajo incluye revision."

        result = block_parser.combine_content(base, "", AppendMode.NEWLINE)

        assert result == base

        result = block_parser.combine_content(base, None, AppendMode.INLINE)

        assert result == base


class TestBlockVariableRendering:
    """Tests for block variable rendering"""

    def test_render_block_inner_template(self, block_parser):
        """Test 7: Block inner template renders variables correctly"""
        inner_template = "El trabajo para {{ Nombre_Cliente }} incluye: {{ alcance }}"
        data = {
            "Nombre_Cliente": "ACME Corp",
            "alcance": "auditoria completa"
        }

        result = block_parser.render_block_inner(inner_template, data)

        assert result == "El trabajo para ACME Corp incluye: auditoria completa"

    def test_missing_variable_renders_empty(self, block_parser):
        """Test 8: Missing variables render as empty string"""
        inner_template = "Cliente: {{ Nombre_Cliente }}, Extra: {{ missing_var }}"
        data = {"Nombre_Cliente": "Test Corp"}

        result = block_parser.render_block_inner(inner_template, data)

        assert result == "Cliente: Test Corp, Extra: "


class TestHtmlSanitization:
    """Tests for HTML sanitization (richtext_limited)"""

    def test_allowed_tags_preserved(self):
        """Test 9: Allowed HTML tags are preserved"""
        html = "<p>Paragraph</p><b>Bold</b><i>Italic</i><ul><li>Item</li></ul>"

        result = HtmlSanitizer.sanitize(html)

        assert "<p>" in result
        assert "<b>" in result
        assert "<i>" in result
        assert "<ul>" in result
        assert "<li>" in result

    def test_script_tags_removed(self):
        """Test 10: Script tags are removed (XSS prevention)"""
        html = "<p>Normal</p><script>alert('xss')</script><b>Bold</b>"

        result = HtmlSanitizer.sanitize(html)

        assert "<script>" not in result
        assert "alert" not in result
        assert "<p>" in result
        assert "<b>" in result

    def test_attributes_stripped(self):
        """Test 11: Attributes are stripped from tags"""
        html = '<p onclick="alert()" style="color:red">Text</p>'

        result = HtmlSanitizer.sanitize(html)

        assert "onclick" not in result
        assert "style" not in result
        assert "<p>Text</p>" in result

    def test_convert_to_word_format(self):
        """Test 12: HTML converted to Word-compatible text"""
        html = "<p>First paragraph</p><p>Second</p><ul><li>Item 1</li><li>Item 2</li></ul>"

        result = HtmlSanitizer.convert_to_word_format(html)

        assert "First paragraph" in result
        assert "Second" in result
        assert "• Item 1" in result
        assert "• Item 2" in result


class TestBlockCustomFieldMaxLength:
    """Tests for max length validation"""

    def test_max_length_enforced(self, validator):
        """Test 13: Max length is enforced for custom fields"""
        # scope_base_custom has max_length of 2000
        long_text = "A" * 2500

        update_data = {"scope_base_custom": long_text}

        result = validator.validate_update("carta_manifestacion", update_data)

        # Should fail validation
        assert result.is_valid is False
        assert any("max" in str(e.message).lower() for e in result.errors)

    def test_within_max_length_accepted(self, validator):
        """Test 14: Content within max length is accepted"""
        valid_text = "A" * 1000  # Within 2000 limit

        update_data = {"scope_base_custom": valid_text}

        result = validator.validate_update("carta_manifestacion", update_data)

        assert result.is_valid is True
        assert "scope_base_custom" in result.filtered_data


class TestBlockDefinition:
    """Tests for BlockDefinition creation"""

    def test_block_definition_from_schema(self):
        """Test 15: BlockDefinition created correctly from schema config"""
        config = {
            "custom_field": "test_custom",
            "append_mode": "labelled",
            "label": "Note:",
            "custom_type": "text",
            "max_length": 1500,
            "required": False
        }

        block = BlockDefinition.from_schema("test_block", config)

        assert block.key == "test_block"
        assert block.custom_field == "test_custom"
        assert block.append_mode == AppendMode.LABELLED
        assert block.label == "Note:"
        assert block.custom_type == CustomFieldType.TEXT
        assert block.max_length == 1500

    def test_block_definition_defaults(self):
        """Test 16: BlockDefinition uses correct defaults"""
        config = {}

        block = BlockDefinition.from_schema("simple_block", config)

        assert block.key == "simple_block"
        assert block.custom_field == "simple_block_custom"
        assert block.append_mode == AppendMode.NEWLINE
        assert block.custom_type == CustomFieldType.TEXT
        assert block.max_length == 2000
        assert block.required is False


class TestValidatorBlockIntegration:
    """Integration tests for validator with blocks"""

    def test_get_block_custom_fields(self, validator):
        """Test 17: get_block_custom_fields returns all custom field names"""
        custom_fields = validator.get_block_custom_fields("carta_manifestacion")

        assert "scope_base_custom" in custom_fields
        assert "responsabilidades_custom" in custom_fields
        assert "manifestaciones_generales_custom" in custom_fields
        assert "hechos_posteriores_custom" in custom_fields

    def test_editable_fields_includes_block_custom(self, validator):
        """Test 18: get_editable_fields includes block custom fields"""
        editable = validator.get_editable_fields("carta_manifestacion")

        # Regular editable fields
        assert "Nombre_Cliente" in editable
        assert "Nombre_Firma" in editable

        # Block custom fields
        assert "scope_base_custom" in editable
        assert "responsabilidades_custom" in editable

    def test_get_blocks_config(self, validator):
        """Test 19: get_blocks_config returns all block configurations"""
        blocks = validator.get_blocks_config("carta_manifestacion")

        assert "scope_base" in blocks
        assert "responsabilidades" in blocks
        assert blocks["scope_base"]["append_mode"] == "newline"
        assert blocks["responsabilidades"]["append_mode"] == "labelled"
        assert blocks["responsabilidades"]["label"] == "Nota adicional:"


class TestAPIIntegration:
    """API integration tests for B1 mode"""

    @pytest.fixture
    def client(self):
        """FastAPI test client"""
        import os
        os.environ["MANAGER_PASSWORD"] = "test_password"

        from fastapi.testclient import TestClient
        from api.app import app
        return TestClient(app)

    def test_create_review_with_empty_custom(self, client, sample_data):
        """Test 20: Create review with empty custom fields"""
        response = client.post("/reviews", json={
            "doc_type": "carta_manifestacion",
            "initial_data": sample_data,
            "created_by": "test_employee"
        })

        assert response.status_code == 200
        data = response.json()
        assert "review_id" in data

    def test_patch_custom_field(self, client, sample_data):
        """Test 21: PATCH custom field updates correctly"""
        # Create review
        response = client.post("/reviews", json={
            "doc_type": "carta_manifestacion",
            "initial_data": sample_data
        })
        review_id = response.json()["review_id"]

        # Update custom field
        response = client.patch(f"/reviews/{review_id}/data", json={
            "data": {"scope_base_custom": "Employee's note here"}
        })

        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert "scope_base_custom" in result["updated_fields"]

    def test_patch_after_submit_fails(self, client, sample_data):
        """Test 22: PATCH custom field after submit returns 403"""
        # Create and submit
        response = client.post("/reviews", json={
            "doc_type": "carta_manifestacion",
            "initial_data": sample_data
        })
        review_id = response.json()["review_id"]
        client.post(f"/reviews/{review_id}/submit")

        # Try to patch
        response = client.patch(f"/reviews/{review_id}/data", json={
            "data": {"scope_base_custom": "Attempted update"}
        })

        assert response.status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
