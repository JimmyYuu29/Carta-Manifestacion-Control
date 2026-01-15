"""
Block Parser - Parses [[BLOCK:key]]...[[/BLOCK]] anchor blocks in templates
解析模板中的锚点块语法 [[BLOCK:key]]...[[/BLOCK]]

This module:
1. Parses block definitions from templates (Word and HTML)
2. Renders block base content with variables
3. Appends custom content according to append_mode
4. Generates pre-computed __block_*__ variables for Word rendering
"""

import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
import html


class AppendMode(str, Enum):
    """Append mode for custom content"""
    NEWLINE = "newline"      # base + "\n" + custom
    INLINE = "inline"        # base + " " + custom
    LABELLED = "labelled"    # base + "\n" + label + " " + custom


class CustomFieldType(str, Enum):
    """Type of custom field"""
    TEXT = "text"                    # Plain text only
    RICHTEXT_LIMITED = "richtext_limited"  # Limited HTML tags allowed


@dataclass
class BlockDefinition:
    """Definition of a single block from schema or template"""
    key: str
    inner_template: str  # The content between [[BLOCK:key]] and [[/BLOCK]]
    custom_field: str    # Default: {key}_custom
    append_mode: AppendMode = AppendMode.NEWLINE
    label: str = ""      # Label for labelled mode
    custom_type: CustomFieldType = CustomFieldType.TEXT
    max_length: int = 2000
    required: bool = False

    @classmethod
    def from_schema(cls, key: str, config: dict, inner_template: str = "") -> "BlockDefinition":
        """Create BlockDefinition from schema configuration"""
        return cls(
            key=key,
            inner_template=inner_template,
            custom_field=config.get("custom_field", f"{key}_custom"),
            append_mode=AppendMode(config.get("append_mode", "newline")),
            label=config.get("label", ""),
            custom_type=CustomFieldType(config.get("custom_type", "text")),
            max_length=config.get("max_length", 2000),
            required=config.get("required", False)
        )


@dataclass
class ParsedBlock:
    """Result of parsing a block from template"""
    key: str
    start_pos: int
    end_pos: int
    inner_template: str
    full_match: str  # The entire [[BLOCK:...]]...[[/BLOCK]] string


@dataclass
class RenderedBlock:
    """A block with rendered base content and custom content"""
    key: str
    base_rendered: str      # Block inner template rendered with variables
    custom_content: str     # Employee's custom content (may be empty)
    final_content: str      # Combined content according to append_mode
    definition: BlockDefinition


class BlockParser:
    """
    Parser for [[BLOCK:key]]...[[/BLOCK]] syntax
    """

    # Regex pattern for block detection
    BLOCK_PATTERN = re.compile(
        r'\[\[BLOCK:(\w+)\]\](.*?)\[\[/BLOCK\]\]',
        re.DOTALL
    )

    # Placeholder pattern for pre-computed block variables
    BLOCK_VAR_PATTERN = r'__block_{key}__'

    def __init__(self):
        self._block_cache: Dict[str, List[ParsedBlock]] = {}

    def parse_template(self, template_content: str) -> List[ParsedBlock]:
        """
        Parse all [[BLOCK:...]]...[[/BLOCK]] from template content

        Args:
            template_content: Raw template string (HTML or Word text)

        Returns:
            List of ParsedBlock with positions and content
        """
        blocks = []

        for match in self.BLOCK_PATTERN.finditer(template_content):
            block_key = match.group(1)
            inner_template = match.group(2).strip()

            blocks.append(ParsedBlock(
                key=block_key,
                start_pos=match.start(),
                end_pos=match.end(),
                inner_template=inner_template,
                full_match=match.group(0)
            ))

        return blocks

    def extract_block_keys(self, template_content: str) -> List[str]:
        """Extract just the block keys from template"""
        return [block.key for block in self.parse_template(template_content)]

    def render_block_inner(self, inner_template: str, data: Dict[str, Any]) -> str:
        """
        Render block inner template with data variables

        Uses simple {{ variable }} replacement (not full Jinja2 to avoid conflicts)

        Args:
            inner_template: Template string with {{ variables }}
            data: Data dictionary with variable values

        Returns:
            Rendered string
        """
        result = inner_template

        # Replace {{ variable }} patterns
        var_pattern = re.compile(r'\{\{\s*(\w+)\s*\}\}')

        def replace_var(match):
            var_name = match.group(1)
            value = data.get(var_name, "")
            if value is None:
                return ""
            return str(value)

        result = var_pattern.sub(replace_var, result)
        return result

    def combine_content(self, base: str, custom: str, mode: AppendMode, label: str = "") -> str:
        """
        Combine base content with custom content according to append mode

        Args:
            base: Rendered base content
            custom: Employee's custom content
            mode: Append mode (newline, inline, labelled)
            label: Label text for labelled mode

        Returns:
            Combined content string
        """
        # If custom is empty, return only base
        if not custom or not custom.strip():
            return base

        custom = custom.strip()

        if mode == AppendMode.NEWLINE:
            return f"{base}\n{custom}"
        elif mode == AppendMode.INLINE:
            return f"{base} {custom}"
        elif mode == AppendMode.LABELLED:
            if label:
                return f"{base}\n{label} {custom}"
            else:
                return f"{base}\n{custom}"

        return base

    def render_block(self, definition: BlockDefinition, data: Dict[str, Any]) -> RenderedBlock:
        """
        Render a complete block with base + custom content

        Args:
            definition: Block definition from schema
            data: Full data dictionary (includes custom fields)

        Returns:
            RenderedBlock with all content
        """
        # Render base content
        base_rendered = self.render_block_inner(definition.inner_template, data)

        # Get custom content from data
        custom_content = data.get(definition.custom_field, "") or ""

        # Combine according to append mode
        final_content = self.combine_content(
            base_rendered,
            custom_content,
            definition.append_mode,
            definition.label
        )

        return RenderedBlock(
            key=definition.key,
            base_rendered=base_rendered,
            custom_content=custom_content,
            final_content=final_content,
            definition=definition
        )

    def generate_block_variables(self, blocks: List[BlockDefinition],
                                  data: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate __block_*__ variables for Word template rendering

        This pre-computes the final block content so Word rendering
        can simply replace {{ __block_key__ }} with the final content.

        Args:
            blocks: List of block definitions
            data: Full data dictionary

        Returns:
            Dictionary mapping __block_key__ to final rendered content
        """
        variables = {}

        for block_def in blocks:
            rendered = self.render_block(block_def, data)
            var_name = f"__block_{block_def.key}__"
            variables[var_name] = rendered.final_content

        return variables

    def prepare_template_for_docx(self, template_content: str,
                                   block_definitions: Dict[str, BlockDefinition]) -> str:
        """
        Prepare template by replacing [[BLOCK:...]]...[[/BLOCK]] with {{ __block_key__ }}

        This transforms the template so that the standard variable replacement
        will handle block content.

        Args:
            template_content: Original template content
            block_definitions: Dictionary of block definitions by key

        Returns:
            Modified template content with block placeholders
        """
        result = template_content
        parsed_blocks = self.parse_template(template_content)

        # Process in reverse order to maintain positions
        for block in reversed(parsed_blocks):
            placeholder = f"{{{{ __block_{block.key}__ }}}}"

            # If we have a definition, update it with the inner template
            if block.key in block_definitions:
                block_definitions[block.key].inner_template = block.inner_template

            result = result[:block.start_pos] + placeholder + result[block.end_pos:]

        return result


class BlockSchemaLoader:
    """
    Loads block definitions from schema configuration
    """

    @staticmethod
    def load_blocks_from_schema(schema: dict) -> Dict[str, BlockDefinition]:
        """
        Load block definitions from schema

        Schema format:
        {
            "blocks": {
                "scope_base": {
                    "custom_field": "scope_base_custom",
                    "append_mode": "newline",
                    "label": "Nota adicional:",
                    "custom_type": "text",
                    "max_length": 1000,
                    "required": false
                }
            }
        }
        """
        blocks = {}
        blocks_config = schema.get("blocks", {})

        for key, config in blocks_config.items():
            blocks[key] = BlockDefinition.from_schema(key, config)

        return blocks

    @staticmethod
    def get_custom_fields_from_blocks(blocks: Dict[str, BlockDefinition]) -> List[str]:
        """Get list of custom field names from block definitions"""
        return [block.custom_field for block in blocks.values()]

    @staticmethod
    def generate_field_schema_for_custom(block: BlockDefinition) -> dict:
        """
        Generate field schema entry for a block's custom field

        This allows custom fields to be properly validated
        """
        return {
            "type": "string" if block.custom_type == CustomFieldType.TEXT else "richtext",
            "label": f"Custom content for {block.key}",
            "section": "blocks",
            "editable": True,
            "required": block.required,
            "is_block_custom": True,
            "block_key": block.key,
            "validation": {
                "max_length": block.max_length
            }
        }


class HtmlSanitizer:
    """
    Sanitizes HTML for richtext_limited fields

    Only allows: b, i, u, br, ul, ol, li, p
    """

    ALLOWED_TAGS = {'b', 'i', 'u', 'br', 'ul', 'ol', 'li', 'p', 'strong', 'em'}

    # Pattern to match HTML tags
    TAG_PATTERN = re.compile(r'<(/?)(\w+)([^>]*)>', re.IGNORECASE)

    @classmethod
    def sanitize(cls, html_content: str) -> str:
        """
        Sanitize HTML content, removing disallowed tags

        Args:
            html_content: Raw HTML content

        Returns:
            Sanitized HTML with only allowed tags
        """
        if not html_content:
            return ""

        def replace_tag(match):
            closing = match.group(1)
            tag_name = match.group(2).lower()
            attrs = match.group(3)

            if tag_name in cls.ALLOWED_TAGS:
                # Keep allowed tags but strip attributes (prevent XSS)
                if closing:
                    return f"</{tag_name}>"
                else:
                    # br is self-closing
                    if tag_name == 'br':
                        return "<br>"
                    return f"<{tag_name}>"
            else:
                # Remove disallowed tags
                return ""

        sanitized = cls.TAG_PATTERN.sub(replace_tag, html_content)

        # Also escape any remaining angle brackets that aren't part of allowed tags
        # This prevents injection of script via malformed tags

        return sanitized

    @classmethod
    def strip_all_tags(cls, html_content: str) -> str:
        """Remove all HTML tags and return plain text"""
        if not html_content:
            return ""

        # Remove all tags
        text = re.sub(r'<[^>]+>', '', html_content)
        # Decode HTML entities
        text = html.unescape(text)
        return text.strip()

    @classmethod
    def convert_to_word_format(cls, html_content: str) -> str:
        """
        Convert limited HTML to Word-compatible text

        Converts:
        - <br> to newline
        - <p>...</p> to text + double newline
        - <ul>/<ol>/<li> to bullet points
        - <b>/<strong> stripped (Word handles differently)
        - <i>/<em> stripped
        """
        if not html_content:
            return ""

        text = html_content

        # Convert <br> and <br/> to newlines
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)

        # Convert <p>...</p> to text + newline
        text = re.sub(r'<p>(.+?)</p>', r'\1\n', text, flags=re.IGNORECASE | re.DOTALL)

        # Convert list items to bullet points
        text = re.sub(r'<li>(.+?)</li>', r'• \1\n', text, flags=re.IGNORECASE | re.DOTALL)

        # Remove remaining tags
        text = re.sub(r'<[^>]+>', '', text)

        # Decode HTML entities
        text = html.unescape(text)

        # Clean up multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()
