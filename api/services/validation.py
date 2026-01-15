"""
Validation Service - Schema-based whitelist validation and filtering
Servicio de validacion basado en schema con filtrado de lista blanca

CRITICAL: This service is the security core that ensures:
1. Only editable=true fields can be updated
2. All values are validated against schema rules
3. Unauthorized field attempts are logged
4. Block custom fields are validated and sanitized (B1 mode)
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, date

from .block_parser import BlockSchemaLoader, HtmlSanitizer, CustomFieldType


@dataclass
class ValidationError:
    """Validation error with field info"""
    field: str
    message: str
    code: str  # "not_editable", "required", "type_error", "validation_error"


@dataclass
class ValidationResult:
    """Result of validation operation"""
    is_valid: bool
    errors: List[ValidationError]
    filtered_data: Dict[str, Any]  # Only editable fields that passed validation
    unauthorized_fields: List[str]  # Fields attempted but not editable


class SchemaValidator:
    """
    Schema-based validator with strict whitelist enforcement
    Validador basado en schema con aplicacion estricta de lista blanca

    Security guarantees:
    - Only fields with editable=true are accepted for updates
    - Non-editable field updates are rejected AND logged
    - All values are type-checked and validated
    """

    def __init__(self, schemas_dir: Path = None):
        if schemas_dir is None:
            schemas_dir = Path(__file__).parent.parent.parent / "schemas"
        self.schemas_dir = Path(schemas_dir)
        self._schema_cache: Dict[str, dict] = {}

    def load_schema(self, doc_type: str) -> dict:
        """
        Load and cache schema for doc_type
        Cargar y cachear schema para doc_type
        """
        if doc_type in self._schema_cache:
            return self._schema_cache[doc_type]

        schema_file = self.schemas_dir / f"{doc_type}.json"
        if not schema_file.exists():
            raise FileNotFoundError(f"Schema not found for doc_type: {doc_type}")

        with open(schema_file, 'r', encoding='utf-8') as f:
            schema = json.load(f)

        self._schema_cache[doc_type] = schema
        return schema

    def get_editable_fields(self, doc_type: str) -> List[str]:
        """
        Get list of editable field names for doc_type
        Obtener lista de nombres de campos editables para doc_type

        Includes both regular editable fields AND block custom fields (B1 mode)
        """
        schema = self.load_schema(doc_type)

        # Regular editable fields
        editable = [
            field_name
            for field_name, field_spec in schema.get("fields", {}).items()
            if field_spec.get("editable", False)
        ]

        # Block custom fields (B1 mode)
        block_custom_fields = self.get_block_custom_fields(doc_type)
        editable.extend(block_custom_fields)

        return editable

    def get_block_custom_fields(self, doc_type: str) -> List[str]:
        """
        Get list of block custom field names for doc_type
        These are auto-generated from block definitions in schema
        """
        schema = self.load_schema(doc_type)
        blocks = schema.get("blocks", {})

        return [
            block_config.get("custom_field", f"{block_key}_custom")
            for block_key, block_config in blocks.items()
        ]

    def get_block_config(self, doc_type: str, custom_field: str) -> Optional[dict]:
        """
        Get block configuration for a custom field
        Returns None if not a block custom field
        """
        schema = self.load_schema(doc_type)
        blocks = schema.get("blocks", {})

        for block_key, block_config in blocks.items():
            if block_config.get("custom_field", f"{block_key}_custom") == custom_field:
                return {
                    "block_key": block_key,
                    **block_config
                }
        return None

    def get_blocks_config(self, doc_type: str) -> Dict[str, dict]:
        """Get all blocks configuration from schema"""
        schema = self.load_schema(doc_type)
        return schema.get("blocks", {})

    def get_field_spec(self, doc_type: str, field_name: str) -> Optional[dict]:
        """Get field specification from schema"""
        schema = self.load_schema(doc_type)
        return schema.get("fields", {}).get(field_name)

    def is_field_editable(self, doc_type: str, field_name: str) -> bool:
        """
        Check if a specific field is editable
        SECURITY: This is the core whitelist check
        """
        field_spec = self.get_field_spec(doc_type, field_name)
        if not field_spec:
            return False
        return field_spec.get("editable", False)

    def validate_field_value(self, doc_type: str, field_name: str, value: Any) -> Tuple[bool, Optional[str], Any]:
        """
        Validate a single field value against schema rules
        Returns (is_valid, error_message, sanitized_value)

        For block custom fields with richtext_limited, sanitizes HTML
        """
        # Check if this is a block custom field
        block_config = self.get_block_config(doc_type, field_name)
        if block_config:
            return self._validate_block_custom_field(field_name, value, block_config)

        # Regular field validation
        field_spec = self.get_field_spec(doc_type, field_name)
        if not field_spec:
            return False, f"Unknown field: {field_name}", value

        field_type = field_spec.get("type", "string")
        required = field_spec.get("required", False)
        validation = field_spec.get("validation", {})

        # Check required
        if required and (value is None or value == ""):
            return False, f"Field '{field_name}' is required", value

        # Allow None/empty for non-required fields
        if value is None or value == "":
            return True, None, value

        # Type validation
        valid, error = self._validate_type(field_name, value, field_type, field_spec)
        if not valid:
            return False, error, value

        # Additional validation rules
        if validation:
            valid, error = self._validate_rules(field_name, value, validation)
            if not valid:
                return False, error, value

        return True, None, value

    def _validate_block_custom_field(self, field_name: str, value: Any,
                                      block_config: dict) -> Tuple[bool, Optional[str], Any]:
        """
        Validate and sanitize a block custom field value

        For richtext_limited: sanitizes HTML, removing disallowed tags
        For text: strips any HTML tags

        SECURITY: This ensures XSS prevention for user-submitted content
        """
        if value is None or value == "":
            if block_config.get("required", False):
                return False, f"Field '{field_name}' is required", value
            return True, None, value

        if not isinstance(value, str):
            return False, f"Field '{field_name}' must be a string", value

        # Get max_length from config
        max_length = block_config.get("max_length", 2000)
        custom_type = block_config.get("custom_type", "text")

        # Sanitize based on type
        if custom_type == "richtext_limited":
            # Sanitize HTML - only allow safe tags
            sanitized = HtmlSanitizer.sanitize(value)
        else:
            # Plain text - strip all HTML tags
            sanitized = HtmlSanitizer.strip_all_tags(value)

        # Check length after sanitization
        if len(sanitized) > max_length:
            return False, f"Field '{field_name}' must be at most {max_length} characters", sanitized

        return True, None, sanitized

    def _validate_type(self, field_name: str, value: Any, field_type: str, field_spec: dict) -> Tuple[bool, Optional[str]]:
        """Validate value against expected type"""
        if field_type == "string":
            if not isinstance(value, str):
                return False, f"Field '{field_name}' must be a string"

        elif field_type == "boolean":
            if not isinstance(value, bool):
                return False, f"Field '{field_name}' must be a boolean"

        elif field_type == "date":
            if isinstance(value, str):
                # Validate date format
                try:
                    datetime.strptime(value, "%Y-%m-%d")
                except ValueError:
                    try:
                        datetime.strptime(value, "%d/%m/%Y")
                    except ValueError:
                        return False, f"Field '{field_name}' must be a valid date (YYYY-MM-DD or DD/MM/YYYY)"
            elif not isinstance(value, (date, datetime)):
                return False, f"Field '{field_name}' must be a date"

        elif field_type == "enum":
            enum_values = field_spec.get("enum_values", [])
            if value not in enum_values:
                return False, f"Field '{field_name}' must be one of: {enum_values}"

        elif field_type == "list":
            if not isinstance(value, list):
                return False, f"Field '{field_name}' must be a list"
            # Validate list items
            item_schema = field_spec.get("item_schema", {})
            if item_schema:
                for i, item in enumerate(value):
                    if not isinstance(item, dict):
                        return False, f"Field '{field_name}' item {i} must be an object"
                    for item_field, item_spec in item_schema.items():
                        if item_spec.get("required", False) and item_field not in item:
                            return False, f"Field '{field_name}' item {i} missing required field '{item_field}'"

        return True, None

    def _validate_rules(self, field_name: str, value: Any, validation: dict) -> Tuple[bool, Optional[str]]:
        """Validate value against additional validation rules"""
        if not isinstance(value, str):
            value = str(value)

        # Pattern validation
        if "pattern" in validation:
            pattern = validation["pattern"]
            if not re.match(pattern, value):
                return False, f"Field '{field_name}' does not match required pattern"

        # Length validation
        if "min_length" in validation:
            if len(value) < validation["min_length"]:
                return False, f"Field '{field_name}' must be at least {validation['min_length']} characters"

        if "max_length" in validation:
            if len(value) > validation["max_length"]:
                return False, f"Field '{field_name}' must be at most {validation['max_length']} characters"

        # Numeric validation
        if "min" in validation:
            try:
                if float(value) < validation["min"]:
                    return False, f"Field '{field_name}' must be at least {validation['min']}"
            except ValueError:
                pass

        if "max" in validation:
            try:
                if float(value) > validation["max"]:
                    return False, f"Field '{field_name}' must be at most {validation['max']}"
            except ValueError:
                pass

        return True, None

    def validate_update(self, doc_type: str, update_data: Dict[str, Any]) -> ValidationResult:
        """
        Validate an update request with strict whitelist enforcement
        SECURITY: This is the main entry point for validating employee updates

        1. Filters out non-editable fields (logs them as unauthorized)
        2. Validates each editable field against schema
        3. Sanitizes block custom fields (HTML cleaning for richtext)
        4. Returns only the valid, editable fields with sanitized values

        Args:
            doc_type: Document type (e.g., "carta_manifestacion")
            update_data: Data submitted by employee

        Returns:
            ValidationResult with filtered_data containing only valid editable fields
        """
        errors = []
        filtered_data = {}
        unauthorized_fields = []

        editable_fields = self.get_editable_fields(doc_type)

        for field_name, value in update_data.items():
            # SECURITY CHECK: Is field editable?
            if field_name not in editable_fields:
                unauthorized_fields.append(field_name)
                # Don't add to filtered_data - silently reject
                continue

            # Validate the field value (returns sanitized value for block custom fields)
            is_valid, error_msg, sanitized_value = self.validate_field_value(doc_type, field_name, value)

            if not is_valid:
                errors.append(ValidationError(
                    field=field_name,
                    message=error_msg or "Validation failed",
                    code="validation_error"
                ))
            else:
                # Use sanitized value (important for richtext fields)
                filtered_data[field_name] = sanitized_value

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            filtered_data=filtered_data,
            unauthorized_fields=unauthorized_fields
        )

    def validate_complete_data(self, doc_type: str, data: Dict[str, Any]) -> ValidationResult:
        """
        Validate complete data (for initial creation)
        This validates all fields, not just editable ones
        """
        errors = []
        schema = self.load_schema(doc_type)

        for field_name, field_spec in schema.get("fields", {}).items():
            value = data.get(field_name)

            # Check required
            if field_spec.get("required", False) and (value is None or value == ""):
                errors.append(ValidationError(
                    field=field_name,
                    message=f"Field '{field_name}' is required",
                    code="required"
                ))
                continue

            # Validate if value present
            if value is not None and value != "":
                is_valid, error_msg, _ = self.validate_field_value(doc_type, field_name, value)
                if not is_valid:
                    errors.append(ValidationError(
                        field=field_name,
                        message=error_msg or "Validation failed",
                        code="validation_error"
                    ))

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            filtered_data=data,
            unauthorized_fields=[]
        )

    def get_schema_for_ui(self, doc_type: str) -> dict:
        """
        Get schema formatted for UI consumption
        Returns field definitions with editability info and blocks config
        """
        schema = self.load_schema(doc_type)
        fields = schema.get("fields", {})
        sections = schema.get("sections", [])
        blocks = schema.get("blocks", {})

        return {
            "doc_type": doc_type,
            "fields": fields,
            "sections": sections,
            "editable_fields": self.get_editable_fields(doc_type),
            "blocks": blocks,
            "block_custom_fields": self.get_block_custom_fields(doc_type)
        }
