"""
DOCX Rendering Service - Wrapper around existing renderer for API use
Servicio de renderizado DOCX - Wrapper alrededor del renderizador existente para uso de API

This service wraps the existing DocxRenderer to:
1. Generate Word documents from review data
2. Store output in secure, non-public directory
3. Return file paths for authorized download only

B1 MODE: Supports [[BLOCK:key]]...[[/BLOCK]] anchor blocks by:
1. Pre-computing __block_*__ variables with base + custom content
2. Injecting these variables into the data before rendering
"""

from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from datetime import datetime
import uuid
import sys
import json

# Add parent modules to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.plugin_loader import load_plugin
from modules.renderer_docx import DocxRenderer
from modules.generate import preprocess_input
from .block_parser import (
    BlockParser, BlockDefinition, BlockSchemaLoader,
    AppendMode, HtmlSanitizer
)


class DocxRenderService:
    """
    DOCX rendering service that generates documents in secure location
    Servicio de renderizado DOCX que genera documentos en ubicacion segura

    SECURITY: Output directory is NOT in static/public path

    B1 MODE: Handles [[BLOCK:key]]...[[/BLOCK]] by pre-computing
    __block_*__ variables that combine base content + custom content
    """

    def __init__(self, output_dir: Path = None, schemas_dir: Path = None):
        if output_dir is None:
            # SECURITY: Store in non-public directory
            output_dir = Path(__file__).parent.parent.parent / "storage" / "generated"
        if schemas_dir is None:
            schemas_dir = Path(__file__).parent.parent.parent / "schemas"

        self.output_dir = Path(output_dir)
        self.schemas_dir = Path(schemas_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.block_parser = BlockParser()

    def load_blocks_config(self, doc_type: str) -> Dict[str, dict]:
        """Load blocks configuration from schema"""
        schema_file = self.schemas_dir / f"{doc_type}.json"
        if not schema_file.exists():
            return {}

        with open(schema_file, 'r', encoding='utf-8') as f:
            schema = json.load(f)

        return schema.get("blocks", {})

    def compute_block_variables(self, doc_type: str, data_json: dict) -> Dict[str, str]:
        """
        B1 MODE: Compute __block_*__ variables for Word rendering

        For each block defined in schema:
        1. Render base content with data variables
        2. Get custom field value from data
        3. Combine according to append_mode
        4. Return as __block_{key}__ variable

        Args:
            doc_type: Document type
            data_json: Full data including custom fields

        Returns:
            Dictionary of __block_key__: final_content
        """
        blocks_config = self.load_blocks_config(doc_type)
        block_vars = {}

        for block_key, config in blocks_config.items():
            # Get block configuration
            custom_field = config.get("custom_field", f"{block_key}_custom")
            append_mode = AppendMode(config.get("append_mode", "newline"))
            label = config.get("label", "")
            inner_template = config.get("inner_template", "")
            custom_type = config.get("custom_type", "text")

            # Render base content with variables
            base_rendered = self.block_parser.render_block_inner(inner_template, data_json)

            # Get custom content
            custom_content = data_json.get(custom_field, "") or ""

            # For richtext, convert to Word-compatible format
            if custom_type == "richtext_limited" and custom_content:
                custom_content = HtmlSanitizer.convert_to_word_format(custom_content)

            # Combine base + custom according to append_mode
            final_content = self.block_parser.combine_content(
                base_rendered,
                custom_content,
                append_mode,
                label
            )

            # Store as __block_key__ variable
            var_name = f"__block_{block_key}__"
            block_vars[var_name] = final_content

        return block_vars

    def render(self, doc_type: str, data_json: dict, review_id: str) -> Tuple[Path, str]:
        """
        Render Word document from review data

        Args:
            doc_type: Document type (e.g., "carta_manifestacion")
            data_json: Data to render (from review)
            review_id: Review ID for filename

        Returns:
            Tuple of (output_path, filename)

        SECURITY: Returns path in secure directory, not accessible via HTTP

        B1 MODE: Injects __block_*__ variables before rendering
        """
        # Load plugin
        plugin = load_plugin(doc_type)

        # B1 MODE: Compute block variables
        block_vars = self.compute_block_variables(doc_type, data_json)

        # Merge block variables into data
        data_with_blocks = {**data_json, **block_vars}

        # Preprocess data (type conversions)
        processed_data = preprocess_input(data_with_blocks, plugin)

        # Ensure block vars are preserved after preprocessing
        processed_data.update(block_vars)

        # Create renderer
        renderer = DocxRenderer(plugin)

        # Generate filename
        client_name = data_json.get("Nombre_Cliente", "documento")
        client_name = "".join(c for c in client_name if c.isalnum() or c in "_ -")[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Carta_Manifestacion_{client_name}_{timestamp}.docx"

        # Create review-specific output directory
        review_output_dir = self.output_dir / review_id
        review_output_dir.mkdir(parents=True, exist_ok=True)

        output_path = review_output_dir / filename

        # Render document
        output_path, traces = renderer.render(processed_data, output_path)

        return output_path, filename

    def get_existing_document(self, review_id: str) -> Optional[Tuple[Path, str]]:
        """
        Get existing rendered document for review if exists

        Returns:
            Tuple of (path, filename) or None if not exists
        """
        review_output_dir = self.output_dir / review_id

        if not review_output_dir.exists():
            return None

        # Find most recent .docx file
        docx_files = list(review_output_dir.glob("*.docx"))
        if not docx_files:
            return None

        # Return most recent
        latest = max(docx_files, key=lambda p: p.stat().st_mtime)
        return latest, latest.name

    def cleanup_review_documents(self, review_id: str) -> bool:
        """Delete all generated documents for a review"""
        review_output_dir = self.output_dir / review_id

        if not review_output_dir.exists():
            return False

        import shutil
        shutil.rmtree(review_output_dir)
        return True
