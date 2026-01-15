"""
HTML Rendering Service - Renders preview HTML using same data as Word
Servicio de renderizado HTML - Renderiza HTML de previsualizacion usando los mismos datos que Word

KEY REQUIREMENT: HTML preview must use the same data_json as Word rendering
to ensure what employee sees matches what manager downloads.
"""

from pathlib import Path
from typing import Dict, Any, Optional
from datetime import date, datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape
import sys

# Add parent modules to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.plugin_loader import load_plugin
from modules.context_builder import ContextBuilder


class HtmlRenderer:
    """
    HTML renderer that uses same data source as Word renderer
    Renderizador HTML que usa la misma fuente de datos que el renderizador Word
    """

    def __init__(self, templates_dir: Path = None):
        if templates_dir is None:
            templates_dir = Path(__file__).parent.parent.parent / "templates_html"
        self.templates_dir = Path(templates_dir)

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
            doc_type=doc_type
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
