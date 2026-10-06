"""Exercise the optional PDF parser and its end-to-end RAG path offline."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

try:
    import pypdf  # noqa: F401
except ImportError as exc:
    raise SystemExit("Install optional PDF support with: python3 -m pip install -r requirements-pdf.txt") from exc

from rag_pipeline import (
    HashingEmbedder,
    OCRPageResult,
    SQLiteVectorStore,
    load_manifest_documents,
    pdf_to_markdown,
)


def make_minimal_pdf(page_texts: list[str]) -> bytes:
    """Build a tiny standards-shaped PDF fixture without a PDF authoring library."""
    page_count = len(page_texts)
    font_id = 3 + 2 * page_count
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            b"<< /Type /Pages /Kids ["
            + b" ".join(f"{3 + 2 * index} 0 R".encode("ascii") for index in range(page_count))
            + f"] /Count {page_count} >>".encode("ascii")
        ),
        font_id: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for index, text in enumerate(page_texts):
        page_id = 3 + 2 * index
        stream_id = page_id + 1
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 50 720 Td ({escaped}) Tj ET".encode("ascii")
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {stream_id} 0 R >>"
        ).encode("ascii")
        objects[stream_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
        )

    last_id = max(objects)
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for object_id in range(1, last_id + 1):
        offsets[object_id] = len(output)
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(objects[object_id])
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {last_id + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for object_id in range(1, last_id + 1):
        output.extend(f"{offsets[object_id]:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {last_id + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agentic-pdf-checks-") as temporary:
        root = Path(temporary)
        source_path = root / "policy.pdf"
        source_path.write_bytes(
            make_minimal_pdf([
                "Returns policy: unused items may be returned within 30 days.",
                "Contact ada@example.test for damaged-item support within seven days.",
            ])
        )
        manifest_path = root / "manifest.json"
        manifest_path.write_text(
            json.dumps([{
                "source_id": "pdf-policy",
                "path": "policy.pdf",
                "tenant_id": "tenant-pdf",
                "version": "v1",
                "effective_date": "2026-01-01",
                "status": "active",
                "classification": "internal",
                "redact_basic_pii": True,
            }]),
            encoding="utf-8",
        )

        document = load_manifest_documents(manifest_path)[0]
        assert "## Page 1" in document.text and "## Page 2" in document.text
        assert "30 days" in document.text and "ada@example.test" in document.text
        database_path = root / "pdf-rag.sqlite"
        store = SQLiteVectorStore(database_path, HashingEmbedder())
        assert store.ingest(document) > 0
        hits = store.search(
            tenant_id="tenant-pdf",
            query="returns 30 days",
            allowed_classifications=["internal"],
            top_k=2,
        )
        assert hits and any("Page 1" in hit.section_path and "30 days" in hit.text for hit in hits)
        assert all("ada@example.test" not in hit.text for hit in hits)
        store.close()
        print("PASS  selectable PDF pages retain page provenance and flow through redaction, chunking, and filtered retrieval")

        blank_path = root / "blank-page.pdf"
        blank_path.write_bytes(make_minimal_pdf([""]))
        try:
            pdf_to_markdown(blank_path)
            raise AssertionError("Textless PDF pages must be routed for OCR or blank-page review")
        except ValueError as exc:
            assert "no selectable text" in str(exc).lower()

        class FakeOCRAdapter:
            def __init__(self, confidence: float):
                self.confidence = confidence
                self.calls: list[tuple[Path, int]] = []

            def extract_page(self, pdf_path: Path, page_number: int) -> OCRPageResult:
                self.calls.append((pdf_path, page_number))
                return OCRPageResult(
                    "Scanned policy: notify support within seven days. Contact ada@example.test.",
                    self.confidence,
                )

        ocr_manifest = root / "ocr-manifest.json"
        ocr_manifest.write_text(
            json.dumps([{
                "source_id": "scanned-policy",
                "path": "blank-page.pdf",
                "tenant_id": "tenant-pdf",
                "version": "scan-v1",
                "effective_date": "2026-01-01",
                "status": "active",
                "classification": "internal",
                "redact_basic_pii": True,
            }]),
            encoding="utf-8",
        )
        fake_ocr = FakeOCRAdapter(confidence=0.94)
        scanned_document = load_manifest_documents(
            ocr_manifest,
            pdf_ocr_adapter=fake_ocr,
            min_ocr_confidence=0.75,
        )[0]
        assert len(fake_ocr.calls) == 1
        assert fake_ocr.calls[0][0].resolve() == blank_path.resolve() and fake_ocr.calls[0][1] == 1
        assert "Page 1 [OCR confidence 0.940]" in scanned_document.text
        assert "notify support within seven days" in scanned_document.text
        ocr_store = SQLiteVectorStore(root / "ocr-rag.sqlite", HashingEmbedder())
        assert ocr_store.ingest(scanned_document) > 0
        ocr_hits = ocr_store.search(
            tenant_id="tenant-pdf",
            query="notify support seven days",
            allowed_classifications=["internal"],
            top_k=2,
        )
        assert ocr_hits and any("Page 1" in hit.section_path for hit in ocr_hits)
        assert all("ada@example.test" not in hit.text for hit in ocr_hits)
        assert any("[REDACTED_EMAIL]" in hit.text for hit in ocr_hits)
        ocr_store.close()

        try:
            load_manifest_documents(
                ocr_manifest,
                pdf_ocr_adapter=FakeOCRAdapter(confidence=0.42),
                min_ocr_confidence=0.75,
            )
            raise AssertionError("Low-confidence OCR must require review")
        except ValueError as exc:
            assert "confidence is below" in str(exc).lower()
        print("PASS  synthetic OCR output retains provenance, meets confidence policy, and flows through redaction and retrieval")

        malformed_path = root / "malformed.pdf"
        malformed_path.write_bytes(b"not a PDF")
        try:
            pdf_to_markdown(malformed_path)
            raise AssertionError("Malformed PDFs must fail closed")
        except ValueError:
            pass

        too_many_pages = root / "too-many-pages.pdf"
        too_many_pages.write_bytes(make_minimal_pdf(["Page content"] * 501))
        try:
            pdf_to_markdown(too_many_pages)
            raise AssertionError("PDF page-count limit must be enforced")
        except ValueError as exc:
            assert "page-count limit" in str(exc).lower()
        print("PASS  textless, malformed, and over-limit PDFs are rejected instead of partially indexed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
