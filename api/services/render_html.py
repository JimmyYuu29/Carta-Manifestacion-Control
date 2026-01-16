"""
HTML Rendering Service - Renders preview HTML using same data as Word
Servicio de renderizado HTML - Renderiza HTML de previsualizacion usando los mismos datos que Word

KEY REQUIREMENT: HTML preview must use the same data_json as Word rendering
to ensure what employee sees matches what manager downloads.

B1 MODE: Supports [[BLOCK:key]]...[[/BLOCK]] anchor blocks with:
- System-generated read-only base content (rendered with variables)
- Employee-editable custom field for supplements
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import date, datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape, BaseLoader
import sys
import re
import json
import html as html_module

# Add parent modules to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.plugin_loader import load_plugin
from modules.context_builder import ContextBuilder
from .block_parser import (
    BlockParser, BlockDefinition, BlockSchemaLoader,
    RenderedBlock, AppendMode, CustomFieldType
)


class HtmlRenderer:
    """
    HTML renderer that uses same data source as Word renderer
    Renderizador HTML que usa la misma fuente de datos que el renderizador Word

    B1 Mode: Also renders [[BLOCK:key]]...[[/BLOCK]] sections with
    editable custom fields for employee supplements.
    """

    def __init__(self, templates_dir: Path = None, schemas_dir: Path = None):
        if templates_dir is None:
            templates_dir = Path(__file__).parent.parent.parent / "templates_html"
        if schemas_dir is None:
            schemas_dir = Path(__file__).parent.parent.parent / "schemas"

        self.templates_dir = Path(templates_dir)
        self.schemas_dir = Path(schemas_dir)
        self.block_parser = BlockParser()

        # Setup Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )

        # Register custom filters
        self.env.filters['date_es'] = self._format_date_spanish
        self.env.filters['currency_eur'] = self._format_currency_eur
        self.env.filters['bool_sn'] = self._format_bool_sn
        self.env.filters['render_block'] = self._render_block_html

    def _format_date_spanish(self, value) -> str:
        """Format date in Spanish format"""
        if value is None:
            return ""

        if isinstance(value, str):
            try:
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                try:
                    value = datetime.strptime(value, "%d/%m/%Y").date()
                except ValueError:
                    return value

        if isinstance(value, (date, datetime)):
            months = [
                "enero", "febrero", "marzo", "abril", "mayo", "junio",
                "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
            ]
            return f"{value.day} de {months[value.month - 1]} de {value.year}"

        return str(value)

    def _format_currency_eur(self, value) -> str:
        """Format currency in EUR format"""
        if value is None:
            return ""
        try:
            num = float(str(value).replace(",", "").replace(" ", ""))
            return f"{num:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")
        except (ValueError, TypeError):
            return str(value)

    def _format_bool_sn(self, value) -> str:
        """Format boolean as Si/No"""
        if value is None:
            return "No"
        if isinstance(value, bool):
            return "Si" if value else "No"
        if isinstance(value, str):
            return "Si" if value.lower() in ('true', 'si', 'yes', '1') else "No"
        return "Si" if value else "No"

    def _render_block_html(self, block: dict) -> str:
        """Jinja2 filter to render a block as HTML component"""
        return self.render_block_component(block)

    def load_blocks_config(self, doc_type: str) -> Dict[str, dict]:
        """Load blocks configuration from schema"""
        schema_file = self.schemas_dir / f"{doc_type}.json"
        if not schema_file.exists():
            return {}

        with open(schema_file, 'r', encoding='utf-8') as f:
            schema = json.load(f)

        return schema.get("blocks", {})

    def render_blocks(self, doc_type: str, data_json: Dict[str, Any],
                      can_edit: bool) -> List[dict]:
        """
        Render all blocks for a document type

        Returns list of block data for template rendering:
        [
            {
                "key": "scope_base",
                "base_html": "El alcance del trabajo para ACME...",
                "custom_field": "scope_base_custom",
                "custom_value": "Employee's note...",
                "custom_type": "text",
                "max_length": 2000,
                "can_edit": True,
                "description": "Alcance del trabajo"
            },
            ...
        ]
        """
        blocks_config = self.load_blocks_config(doc_type)
        rendered_blocks = []

        for block_key, config in blocks_config.items():
            # Create block definition
            block_def = BlockDefinition.from_schema(block_key, config)

            # Get inner template if defined in config (or empty)
            inner_template = config.get("inner_template", "")

            # Render base content with variables
            base_html = self.block_parser.render_block_inner(inner_template, data_json)

            # Get custom field value
            custom_field = config.get("custom_field", f"{block_key}_custom")
            custom_value = data_json.get(custom_field, "")

            rendered_blocks.append({
                "key": block_key,
                "base_html": base_html,
                "custom_field": custom_field,
                "custom_value": custom_value or "",
                "custom_type": config.get("custom_type", "text"),
                "max_length": config.get("max_length", 2000),
                "append_mode": config.get("append_mode", "newline"),
                "label": config.get("label", ""),
                "can_edit": can_edit,
                "description": config.get("description", "")
            })

        return rendered_blocks

    def render_block_component(self, block: dict) -> str:
        """
        Render a single block as HTML component

        Args:
            block: Block data dict from render_blocks()

        Returns:
            HTML string for the block component
        """
        can_edit = block.get("can_edit", False)
        custom_type = block.get("custom_type", "text")
        custom_value = block.get("custom_value", "")

        # Escape for HTML
        import html
        base_html = block.get("base_html", "")
        custom_value_escaped = html.escape(custom_value) if custom_value else ""
        description = html.escape(block.get("description", ""))

        # Determine input type
        if custom_type == "richtext_limited":
            input_html = f'''<div class="richtext-editor"
                data-field="{block['custom_field']}"
                data-max-length="{block['max_length']}"
                contenteditable="{str(can_edit).lower()}">{custom_value}</div>'''
        else:
            input_html = f'''<textarea
                name="{block['custom_field']}"
                data-field="{block['custom_field']}"
                maxlength="{block['max_length']}"
                placeholder="Agregar comentario adicional..."
                {'readonly' if not can_edit else ''}>{custom_value_escaped}</textarea>'''

        return f'''
        <section class="doc-block" data-block="{block['key']}">
            <div class="doc-block-header">
                <span class="block-label">{description}</span>
            </div>
            <div class="doc-block-base">
                <div class="base-content">{base_html if base_html else '<em>(Contenido del sistema)</em>'}</div>
            </div>
            <div class="doc-block-custom">
                <label for="{block['custom_field']}">Complemento (opcional)</label>
                {input_html}
                <span class="char-count">0 / {block['max_length']}</span>
            </div>
        </section>
        '''

    def render_preview(self, doc_type: str, data_json: Dict[str, Any],
                       editable_fields: list, review_id: str,
                       status: str, can_edit: bool) -> str:
        """
        Render HTML preview using the same data as Word rendering
        Renderizar HTML de previsualizacion usando los mismos datos que Word

        Args:
            doc_type: Document type
            data_json: Same data_json that will be used for Word rendering
            editable_fields: List of field names that are editable
            review_id: Review ID for form actions
            status: Current review status
            can_edit: Whether editing is allowed (DRAFT status)

        Returns:
            Rendered HTML string
        """
        # Load plugin to get context building logic
        plugin = load_plugin(doc_type)
        context_builder = ContextBuilder(plugin)

        # Build full context using same logic as Word renderer
        full_context = context_builder.build_context(data_json)

        # Get conditional values for template logic
        conditionals = context_builder.get_conditional_values(data_json)
        full_context.update(conditionals)

        # B1 MODE: Render blocks with custom fields
        blocks = self.render_blocks(doc_type, data_json, can_edit)
        blocks_config = self.load_blocks_config(doc_type)

        # Load template
        template_path = f"{doc_type}/preview.html"
        try:
            template = self.env.get_template(template_path)
        except Exception:
            # Fallback to generic template
            template = self.env.get_template("_base/preview.html")

        # Render with full context plus UI-specific variables
        html = template.render(
            # Document data (same as Word)
            **full_context,
            data=data_json,
            # UI-specific context
            review_id=review_id,
            status=status,
            can_edit=can_edit,
            editable_fields=editable_fields,
            doc_type=doc_type,
            # B1 MODE: Blocks
            blocks=blocks,
            blocks_config=blocks_config,
            render_block=self.render_block_component
        )

        return html

    def render_manager_page(self, review_id: str, doc_type: str, status: str,
                            client_name: str = "") -> str:
        """
        Render manager download entry page
        Renderizar pagina de entrada para descarga de manager
        """
        template = self.env.get_template("_base/manager.html")
        return template.render(
            review_id=review_id,
            doc_type=doc_type,
            status=status,
            client_name=client_name
        )

    def _process_block_markers(self, html_content: str, data_json: Dict[str, Any],
                                can_edit: bool) -> str:
        """
        Process [[BLOCK:key]]...[[/BLOCK]] markers in HTML content
        Replace them with editable HTML elements

        Args:
            html_content: HTML string with block markers
            data_json: Data containing block custom values
            can_edit: Whether editing is allowed

        Returns:
            HTML with blocks replaced by editable elements
        """
        import re

        def replace_block(match):
            block_key = match.group(1)
            block_content = match.group(2)
            custom_field = f"{block_key}_custom"
            custom_value = data_json.get(custom_field, "")

            # Escape for HTML attributes
            custom_value_escaped = html_module.escape(custom_value) if custom_value else ""

            if can_edit:
                # Editable block with textarea
                return f'''
                <section class="doc-block" data-block="{block_key}" data-block-key="{block_key}">
                  <div class="doc-block-base">
                    {block_content}
                  </div>
                  <div class="doc-block-custom">
                    <label>Complemento (opcional - se anadira al documento final)</label>
                    <textarea name="{custom_field}" data-field="{custom_field}" placeholder="Agregue texto adicional aqui...">{custom_value_escaped}</textarea>
                    <div class="hint">Este contenido se anadira al parrafo anterior en el documento Word final.</div>
                  </div>
                </section>
                '''
            else:
                # Read-only block display
                custom_display = f'<div class="block-custom-content"><strong>Complemento:</strong> {custom_value_escaped}</div>' if custom_value else ''
                return f'''
                <section class="doc-block doc-block-readonly" data-block="{block_key}">
                  <div class="doc-block-base">
                    {block_content}
                  </div>
                  {custom_display}
                </section>
                '''

        # Pattern to match [[BLOCK:key]]content[[/BLOCK]]
        pattern = r'\[\[BLOCK:(\w+)\]\](.*?)\[\[/BLOCK\]\]'
        return re.sub(pattern, replace_block, html_content, flags=re.DOTALL)

    def render_document_preview(self, doc_type: str, data_json: Dict[str, Any],
                                 review_id: str, status: str, can_edit: bool,
                                 editable_fields: list, mode: str = "employee",
                                 download_url: str = None, token: str = None) -> str:
        """
        Render document preview using the template.html from config/templates
        Renderizar previsualizacion del documento usando template.html de config/templates

        Args:
            doc_type: Document type (e.g., "carta_manifestacion")
            data_json: Data to fill the template
            review_id: Review ID
            status: Current review status
            can_edit: Whether editing is allowed
            editable_fields: List of editable field names
            mode: "employee" or "manager"
            download_url: URL for downloading Word (manager mode)
            token: Download token (manager mode)

        Returns:
            Rendered HTML string with document preview
        """
        # Load plugin for context building
        plugin = load_plugin(doc_type)
        context_builder = ContextBuilder(plugin)

        # Build full context using same logic as Word renderer
        full_context = context_builder.build_context(data_json)
        conditionals = context_builder.get_conditional_values(data_json)
        full_context.update(conditionals)

        # Also add raw data for access
        full_context.update(data_json)

        # Load template.html from config/templates
        config_templates_dir = Path(__file__).parent.parent.parent / "config" / "templates"
        template_file = config_templates_dir / doc_type / "template.html"

        if not template_file.exists():
            # Fallback to default preview if template doesn't exist
            return self.render_preview(doc_type, data_json, editable_fields,
                                        review_id, status, can_edit)

        # Create a separate Jinja2 environment for config templates
        config_env = Environment(
            loader=FileSystemLoader(str(config_templates_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )

        # Register same filters
        config_env.filters['date_es'] = self._format_date_spanish
        config_env.filters['currency_eur'] = self._format_currency_eur
        config_env.filters['bool_sn'] = self._format_bool_sn
        config_env.filters['default'] = lambda value, default_value='': value if value else default_value

        try:
            # Render the document template
            doc_template = config_env.get_template(f"{doc_type}/template.html")
            document_html = doc_template.render(**full_context)

            # Process [[BLOCK:key]]...[[/BLOCK]] markers if any remain
            document_html = self._process_block_markers(document_html, data_json, can_edit)
        except Exception as e:
            # If rendering fails, show error with more details
            import traceback
            error_detail = traceback.format_exc()
            document_html = f'''
            <div class="error" style="background: #fee2e2; border: 1px solid #fca5a5; padding: 20px; border-radius: 8px; margin: 20px;">
                <h3 style="color: #991b1b; margin-bottom: 10px;">Error rendering template</h3>
                <p style="color: #b91c1c;">{html_module.escape(str(e))}</p>
                <details style="margin-top: 10px;">
                    <summary style="cursor: pointer; color: #6b7280;">Ver detalles tecnicos</summary>
                    <pre style="background: #f9fafb; padding: 10px; margin-top: 10px; overflow: auto; font-size: 12px;">{html_module.escape(error_detail)}</pre>
                </details>
            </div>
            '''

        # Load the wrapper template for the preview
        wrapper_template = self.env.get_template("_base/document_preview.html")

        # B1 MODE: Render blocks for potential use in wrapper
        blocks = self.render_blocks(doc_type, data_json, can_edit)

        return wrapper_template.render(
            document_html=document_html,
            review_id=review_id,
            status=status,
            can_edit=can_edit,
            editable_fields=editable_fields,
            doc_type=doc_type,
            mode=mode,
            download_url=download_url,
            token=token,
            data=data_json,
            blocks=blocks,
            client_name=data_json.get("Nombre_Cliente", "")
        )
