"""Check preprocessing, re-ingestion, provenance, and vector-store boundaries offline."""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

from rag_pipeline import (
    Document,
    HashingEmbedder,
    SQLiteVectorStore,
    chunk_sections,
    docx_to_markdown,
    load_manifest_documents,
    normalize_text,
    parse_markdown_sections,
    prepare_document,
)


def main() -> int:
    normalized = normalize_text("A\r\nB\t C\x00", redact_basic_pii=False)
    assert normalized == "A\nB C"
    redacted = normalize_text(
        "Contact me at ada@example.test or 415-555-1212; policy date 2026-01-01.",
        redact_basic_pii=True,
    )
    assert "ada@example.test" not in redacted and "415-555-1212" not in redacted
    assert "2026-01-01" in redacted
    print("PASS  normalization preserves line structure; basic redaction leaves policy dates intact")

    sections = parse_markdown_sections("# Policy\nIntro text\n## Reporting\nReport damage in seven days.")
    assert [section.path for section in sections] == ["Policy", "Policy > Reporting"]
    doc = Document(
        source_id="chunk-check",
        tenant_id="tenant-a",
        version="v1",
        effective_date="2026-01-01",
        status="active",
        classification="internal",
        text="# Terms\n" + "one two three four five six seven eight nine ten " * 4,
    )
    chunks = prepare_document(doc, max_words=10, overlap_words=2)
    assert len(chunks) > 1
    assert all(len(chunk.text.split()) <= 12 for chunk in chunks)
    assert all(chunk.section_path == "Terms" for chunk in chunks)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    print("PASS  heading paths, bounded overlapping chunks, and stable per-chunk identities")

    with tempfile.TemporaryDirectory() as temporary:
        html_path = Path(temporary) / "policy.html"
        html_path.write_text(
            """<!doctype html><html><head><script>ignore_script_marker</script></head><body>
            <nav>ignore_navigation_marker</nav><main><h1>Returns</h1><h2>Eligibility</h2>
            <p>Unused items may be returned within 30 days.</p>
            <table><thead><tr><th>Item</th><th>Window</th></tr></thead>
            <tbody><tr><td>Unopened</td><td>30 days</td></tr></tbody></table>
            <footer>ignore_footer_marker</footer></main></body></html>""",
            encoding="utf-8",
        )
        html_manifest = Path(temporary) / "html-manifest.json"
        html_manifest.write_text(
            json.dumps(
                [
                    {
                        "source_id": "html-policy",
                        "path": "policy.html",
                        "tenant_id": "tenant-a",
                        "version": "v1",
                        "effective_date": "2026-01-01",
                        "status": "active",
                        "classification": "internal",
                    }
                ]
            ),
            encoding="utf-8",
        )
        html_document = load_manifest_documents(html_manifest)[0]
        assert "# Returns" in html_document.text and "## Eligibility" in html_document.text
        html_sections = parse_markdown_sections(html_document.text)
        assert html_sections[0].path == "Returns > Eligibility"
        assert "| Item | Window |" in html_document.text
        assert "| Unopened | 30 days |" in html_document.text
        assert all(
            marker not in html_document.text
            for marker in ("ignore_script_marker", "ignore_navigation_marker", "ignore_footer_marker")
        )
        table_chunks = chunk_sections(html_sections, max_words=16, overlap_words=2)
        table_chunk = next(chunk for _, chunk in table_chunks if "| Unopened" in chunk)
        assert "| Item | Window |" in table_chunk and "| --- | --- |" in table_chunk
        assert len(table_chunk.split()) <= 16
        oversized_table = parse_markdown_sections(
            "# Data\n| Field | Value |\n| --- | --- |\n| This row is too long for the configured chunk budget |"
        )
        try:
            chunk_sections(oversized_table, max_words=10, overlap_words=1)
            raise AssertionError("oversized table rows must not be split silently")
        except ValueError as error:
            assert "table row exceeds" in str(error)
        print("PASS  static HTML ingestion keeps heading/table structure and removes known boilerplate")

        docx_path = Path(temporary) / "returns.docx"
        docx_xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Returns policy</w:t></w:r></w:p>
            <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Eligibility</w:t></w:r></w:p>
            <w:p><w:r><w:t>Contact ada@example.test for help with an unopened item.</w:t></w:r></w:p>
            <w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>Report damage within seven days.</w:t></w:r></w:p>
            <w:tbl>
              <w:tr><w:trPr><w:tblHeader/></w:trPr>
                <w:tc><w:p><w:r><w:t>Item</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>Window</w:t></w:r></w:p></w:tc>
              </w:tr>
              <w:tr>
                <w:tc><w:p><w:r><w:t>Unopened</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>30 days</w:t></w:r></w:p></w:tc>
              </w:tr>
            </w:tbl>
            <w:p><w:r><w:br w:type="page"/><w:t>Keep the original receipt.</w:t></w:r></w:p>
            <w:sectPr/>
          </w:body>
        </w:document>'''
        with zipfile.ZipFile(docx_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", docx_xml)
        docx_manifest = Path(temporary) / "docx-manifest.json"
        docx_manifest.write_text(
            json.dumps([{
                "source_id": "docx-policy",
                "path": "returns.docx",
                "tenant_id": "tenant-a",
                "version": "v1",
                "effective_date": "2026-01-01",
                "status": "active",
                "classification": "internal",
                "redact_basic_pii": True,
            }]),
            encoding="utf-8",
        )
        docx_document = load_manifest_documents(docx_manifest)[0]
        assert "# Returns policy" in docx_document.text
        assert "## Eligibility" in docx_document.text
        assert "- Report damage within seven days." in docx_document.text
        assert "| Item | Window |" in docx_document.text
        assert "| --- | --- |" in docx_document.text
        assert "[Page break]" in docx_document.text
        docx_sections = parse_markdown_sections(docx_document.text)
        assert docx_sections[0].path == "Returns policy > Eligibility"
        docx_table_chunk = next(
            chunk for _, chunk in chunk_sections(docx_sections, max_words=20, overlap_words=2)
            if "| Unopened" in chunk
        )
        assert "| Item | Window |" in docx_table_chunk and "| --- | --- |" in docx_table_chunk
        prepared_docx = prepare_document(docx_document, max_words=60, overlap_words=5)
        assert any("[REDACTED_EMAIL]" in chunk.text for chunk in prepared_docx)
        assert all("ada@example.test" not in chunk.text for chunk in prepared_docx)
        docx_store = SQLiteVectorStore(Path(temporary) / "docx-rag.sqlite", HashingEmbedder())
        assert docx_store.ingest(docx_document) > 0
        docx_hits = docx_store.search(
            tenant_id="tenant-a",
            query="unopened return window 30 days",
            allowed_classifications=["internal"],
            top_k=2,
        )
        assert docx_hits and any("Unopened" in hit.text for hit in docx_hits)
        assert all("ada@example.test" not in hit.text for hit in docx_hits)
        docx_store.close()

        unsafe_docx = Path(temporary) / "unsafe.docx"
        with zipfile.ZipFile(unsafe_docx, "w") as archive:
            archive.writestr(
                "word/document.xml",
                '<!DOCTYPE w:document [<!ENTITY x "expanded">]><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>',
            )
        try:
            docx_to_markdown(unsafe_docx)
            raise AssertionError("DOCX parser must reject DTD/entity declarations")
        except ValueError as error:
            assert "xml declarations" in str(error).lower()
        unsupported_docx = Path(temporary) / "unsupported.docx"
        with zipfile.ZipFile(unsupported_docx, "w") as archive:
            archive.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:sdt><w:sdtContent><w:p><w:r><w:t>content control text</w:t></w:r></w:p></w:sdtContent></w:sdt></w:body></w:document>',
            )
        try:
            docx_to_markdown(unsupported_docx)
            raise AssertionError("DOCX parser must reject body text it cannot preserve")
        except ValueError as error:
            assert "unsupported body structure" in str(error).lower()
        oversized_docx = Path(temporary) / "oversized.docx"
        with zipfile.ZipFile(oversized_docx, "w") as archive:
            archive.writestr("word/document.xml", b"x" * (8 * 1024 * 1024 + 1))
        try:
            docx_to_markdown(oversized_docx)
            raise AssertionError("DOCX parser must enforce expanded package-member limits")
        except ValueError as error:
            assert "oversized package member" in str(error).lower()
        print("PASS  DOCX extraction preserves supported structure, redacts PII, and rejects unsafe, partial, or oversized input")

        db_path = Path(temporary) / "rag-checks.sqlite"
        embedder = HashingEmbedder()
        store = SQLiteVectorStore(db_path, embedder)
        docs = load_manifest_documents(Path(__file__).with_name("knowledge") / "manifest.json")
        first_count = sum(store.ingest(item) for item in docs)
        second_count = sum(store.ingest(item) for item in docs)
        assert first_count == 4 and second_count == 0
        hit = store.search(
            tenant_id="demo-tenant",
            query="item arrived damaged report time",
            allowed_classifications=["internal"],
            top_k=1,
        )
        assert hit and hit[0].source_id == "returns-policy"
        assert hit[0].version == "2026.1" and hit[0].section_path.endswith("Reporting a problem")
        lexical_hit = store.search_lexical(
            tenant_id="demo-tenant",
            query="item arrived damaged report time",
            allowed_classifications=["internal"],
            top_k=1,
        )
        hybrid_hit = store.search_hybrid(
            tenant_id="demo-tenant",
            query="item arrived damaged report time",
            allowed_classifications=["internal"],
            top_k=1,
            min_dense_score=0.22,
            lexical_relative_score_floor=0.3,
        )
        assert lexical_hit and lexical_hit[0].source_id == "returns-policy"
        assert hybrid_hit and hybrid_hit[0].source_id == "returns-policy"
        assert store.search(
            tenant_id="other-tenant",
            query="item arrived damaged",
            allowed_classifications=["internal"],
        ) == []
        assert store.search_lexical(
            tenant_id="other-tenant",
            query="item arrived damaged",
            allowed_classifications=["internal"],
        ) == []
        assert store.search_hybrid(
            tenant_id="demo-tenant",
            query="item arrived damaged",
            allowed_classifications=["public"],
        ) == []
        assert store.search(
            tenant_id="demo-tenant",
            query="item arrived damaged",
            allowed_classifications=["public"],
        ) == []
        print("PASS  persistent ingestion is idempotent and carries source/version/section provenance")
        print("PASS  dense, lexical, and hybrid paths preserve tenant and classification filters")

        newer = Document(
            source_id="returns-policy",
            tenant_id="demo-tenant",
            version="2026.2",
            effective_date="2026-06-01",
            status="active",
            classification="internal",
            text="# Returns\n## Window\nEligible items may be returned within 45 days of delivery.",
        )
        store.ingest(newer)
        draft = Document(
            source_id="returns-policy",
            tenant_id="demo-tenant",
            version="draft-2027",
            effective_date="2027-01-01",
            status="draft",
            classification="internal",
            text=newer.text,
        )
        store.ingest(draft)
        current = store.search(
            tenant_id="demo-tenant",
            query="return window delivery",
            allowed_classifications=["internal"],
            top_k=4,
        )
        return_hits = [item for item in current if item.source_id == "returns-policy"]
        assert return_hits and {item.version for item in return_hits} == {"2026.2"}
        store.close()

        reopened = SQLiteVectorStore(db_path, embedder)
        assert reopened.search(
            tenant_id="demo-tenant",
            query="return window delivery",
            allowed_classifications=["internal"],
            top_k=4,
        )
        assert reopened.supersede_source(tenant_id="demo-tenant", source_id="returns-policy") > 0
        assert all(
            item.source_id != "returns-policy"
            for item in reopened.search(
                tenant_id="demo-tenant",
                query="return window delivery",
                allowed_classifications=["internal"],
                top_k=4,
            )
        )
        assert reopened.delete_source(tenant_id="demo-tenant", source_id="delivery-policy") > 0
        assert all(
            item.source_id != "delivery-policy"
            for item in reopened.search(
                tenant_id="demo-tenant",
                query="delivery tracking",
                allowed_classifications=["internal"],
                top_k=4,
            )
        )
        reopened.close()
        print("PASS  active version replaces prior retrieval; draft does not replace active; persistence, supersede, and deletion work")

    print("\nRAG contract checks passed (offline; synthetic corpus; feature-hashing embedder).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
