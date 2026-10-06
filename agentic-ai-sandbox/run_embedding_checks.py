"""Exercise Voyage request mechanics and ingestion safety without network calls."""

from __future__ import annotations

import json
import tempfile
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

from rag_pipeline import Document, SQLiteVectorStore
from run_rag_evals import evaluate_dataset
from voyage_embedder import VoyageEmbedder


class FakeTransport:
    def __init__(self, responder):
        self.responder = responder
        self.requests: list[tuple[Request, float]] = []

    def __call__(self, request: Request, *, timeout: float):
        self.requests.append((request, timeout))
        return self.responder(request, len(self.requests))


def response_for(
    request: Request,
    _call_index: int = 1,
    *,
    reverse: bool = True,
    dimensions: int = 2,
) -> BytesIO:
    payload = json.loads(request.data.decode("utf-8"))
    indexed = [
        {
            "index": index,
            "embedding": [float(len(text)), *([float(index + 1)] * (dimensions - 1))],
        }
        for index, text in enumerate(payload["input"])
    ]
    if reverse:
        indexed.reverse()
    result = {
        "data": indexed,
        "usage": {"total_tokens": sum(len(text.split()) for text in payload["input"])},
    }
    return BytesIO(json.dumps(result).encode("utf-8"))


def run() -> int:
    checks = 0

    calls = 0

    def should_not_call(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("transport must not be called without credentials")

    try:
        VoyageEmbedder(api_key="", opener=should_not_call)
        raise AssertionError("empty credentials should be rejected")
    except ValueError as error:
        assert "VOYAGE_API_KEY" in str(error)
    assert calls == 0
    checks += 1
    print("PASS  missing credentials fail before transport")

    transport = FakeTransport(response_for)
    embedder = VoyageEmbedder(
        api_key="local-fake-token",
        model="voyage-4",
        batch_size=2,
        timeout_seconds=7,
        opener=transport,
    )
    document_vectors = embedder.embed_documents(["red fox", "blue whale", "green owl"])
    assert document_vectors == [[7.0, 1.0], [10.0, 2.0], [9.0, 1.0]]
    assert len(transport.requests) == 2
    assert [json.loads(request.data)["input_type"] for request, _ in transport.requests] == [
        "document",
        "document",
    ]
    assert all(request.get_header("Authorization") == "Bearer local-fake-token" for request, _ in transport.requests)
    assert all(timeout == 7 for _, timeout in transport.requests)
    assert embedder.request_count == 2 and embedder.input_tokens == 6
    assert embedder.document_request_count == 2 and embedder.document_input_tokens == 6
    checks += 1
    print("PASS  document requests batch, preserve provider indices, and count usage")

    query_vector = embedder.embed_query("find red fox")
    query_request = transport.requests[-1][0]
    assert query_vector == [12.0, 1.0]
    assert json.loads(query_request.data)["input_type"] == "query"
    assert embedder.request_count == 3
    assert embedder.query_request_count == 1 and embedder.query_input_tokens == 3
    checks += 1
    print("PASS  query embedding uses retrieval query mode")

    malformed_transport = FakeTransport(
        lambda _request, _index: BytesIO(
            json.dumps(
                {"data": [{"index": 0, "embedding": [1.0]}, {"index": 0, "embedding": [2.0]}]}
            ).encode("utf-8")
        )
    )
    malformed = VoyageEmbedder(api_key="local-fake-token", opener=malformed_transport)
    try:
        malformed.embed_queries(["first query", "second query"])
        raise AssertionError("duplicate response indices should be rejected")
    except RuntimeError as error:
        assert "malformed vectors" in str(error)
    checks += 1
    print("PASS  duplicate response indices fail closed")

    error_transport = FakeTransport(
        lambda _request, _index: (_ for _ in ()).throw(
            HTTPError("https://example.invalid", 401, "unauthorized", None, BytesIO(b"secret-response"))
        )
    )
    failing = VoyageEmbedder(api_key="local-fake-token", opener=error_transport)
    try:
        failing.embed_query("one query")
        raise AssertionError("HTTP errors should surface")
    except RuntimeError as error:
        assert "HTTP 401" in str(error)
        assert "secret-response" not in str(error)
        assert "local-fake-token" not in str(error)
    checks += 1
    print("PASS  provider errors do not expose response bodies or credentials")

    dimension_transport = FakeTransport(
        lambda request, index: response_for(request, dimensions=2 if index == 1 else 3)
    )
    changing_dimensions = VoyageEmbedder(api_key="local-fake-token", batch_size=1, opener=dimension_transport)
    try:
        changing_dimensions.embed_documents(["first", "second"])
        raise AssertionError("dimension changes should be rejected")
    except RuntimeError as error:
        assert "dimensions changed" in str(error)
    checks += 1
    print("PASS  vector dimensions remain stable across batches")

    atomic_transport = FakeTransport(
        lambda request, index: (
            response_for(request)
            if index == 1
            else (_ for _ in ()).throw(
                HTTPError("https://example.invalid", 503, "unavailable", None, BytesIO(b"private"))
            )
        )
    )
    atomic_embedder = VoyageEmbedder(api_key="local-fake-token", batch_size=1, opener=atomic_transport)
    document = Document(
        source_id="atomic-source",
        tenant_id="test-tenant",
        version="1",
        effective_date="2026-01-01",
        status="active",
        classification="internal",
        text=" ".join(f"word{index}" for index in range(50)),
    )
    with tempfile.TemporaryDirectory() as temporary:
        store = SQLiteVectorStore(Path(temporary) / "atomic.sqlite", atomic_embedder)
        try:
            store.ingest_many([document], max_words=20, overlap_words=4)
            raise AssertionError("simulated later-batch failure should abort ingestion")
        except RuntimeError:
            stored = store.connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            assert stored == 0
        finally:
            store.close()
    checks += 1
    print("PASS  failed embedding batch writes no partial document chunks")

    eval_transport = FakeTransport(response_for)
    eval_embedder = VoyageEmbedder(api_key="local-fake-token", opener=eval_transport)
    with tempfile.TemporaryDirectory() as temporary:
        data_root = Path(temporary)
        (data_root / "policy.md").write_text(
            "# Returns\nEligible items may be returned within 30 days.", encoding="utf-8"
        )
        eval_manifest = data_root / "manifest.json"
        eval_manifest.write_text(
            json.dumps(
                [
                    {
                        "source_id": "returns-policy",
                        "path": "policy.md",
                        "tenant_id": "test-tenant",
                        "version": "v1",
                        "effective_date": "2026-01-01",
                        "status": "active",
                        "classification": "internal",
                    }
                ]
            ),
            encoding="utf-8",
        )
        report = evaluate_dataset(
            {
                "dataset_version": "embedding-mock-v1",
                "split": "development",
                "top_k": 1,
                "scenarios": [
                    {
                        "id": "returns-query",
                        "query": "return window",
                        "expected_source_ids": ["returns-policy"],
                        "tenant_id": "test-tenant",
                        "allowed_classifications": ["internal"],
                    }
                ],
            },
            retriever="dense",
            manifest_path=eval_manifest,
            embedder=eval_embedder,
        )
    assert report["scenario_pass_rate"] == 1.0
    assert report["embedding_provider"] == "voyage" and report["embedding_dimensions"] == 2
    assert report["document_embedding_requests"] == 1 and report["query_embedding_requests"] == 1
    assert report["document_embedding_input_tokens"] > 0 and report["query_embedding_input_tokens"] == 2
    checks += 1
    print("PASS  RAG evaluation reports provider, dimension, and document/query usage separately")

    print(f"\nEmbedding adapter checks passed ({checks}/8; fake transport only; no network/API usage).")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
