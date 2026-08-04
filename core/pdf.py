"""Local PDF text extraction.

Used by the Ollama provider (which cannot read documents natively) and by blind
screening on any provider, since anonymization needs the resume as editable text.
"""

import io

from .providers.base import LLMError


def pdf_to_text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not text.strip():
        raise LLMError(
            "This PDF has no extractable text (is it a scan/image?). "
            "Blind screening and the Ollama engine both need selectable text; "
            "use the Claude engine with blind screening off to read it natively."
        )
    return text
