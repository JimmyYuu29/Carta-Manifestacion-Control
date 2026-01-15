"""
DOCX Rendering Service - Wrapper around existing renderer for API use
Servicio de renderizado DOCX - Wrapper alrededor del renderizador existente para uso de API

This service wraps the existing DocxRenderer to:
1. Generate Word documents from review data
2. Store output in secure, non-public directory
3. Return file paths for authorized download only
"""

from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
import uuid
import sys

# Add parent modules to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.plugin_loader import load_plugin
from modules.renderer_docx import DocxRenderer
from modules.generate import preprocess_input


class DocxRenderService:
    """
    DOCX rendering service that generates documents in secure location
    Servicio de renderizado DOCX que genera documentos en ubicacion segura

    SECURITY: Output directory is NOT in static/public path
    """

    def __init__(self, output_dir: Path = None):
        if output_dir is None:
            # SECURITY: Store in non-public directory
            output_dir = Path(__file__).parent.parent.parent / "storage" / "generated"
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

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
        """
        # Load plugin
        plugin = load_plugin(doc_type)

        # Preprocess data (type conversions)
        processed_data = preprocess_input(data_json, plugin)

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
