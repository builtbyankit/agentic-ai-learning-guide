"""Small Voyage text-embedding adapter using only the Python standard library.

This keeps provider calls outside the vector-store transaction and supports
bounded batches. Configure ``VOYAGE_API_KEY`` before constructing the adapter;
the key is never included in errors or evaluation reports.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class VoyageEmbedder:
    """Voyage embeddings adapter with explicit query/document input types.

    ``voyage-4`` is the default general-purpose model. Endpoint and model can
    be overridden for regional gateways or compatible deployments. Requests
    are deliberately not retried here: callers need an explicit retry budget,
    backoff policy, and idempotent ingestion policy at the job boundary.
    """

    DEFAULT_ENDPOINT = "https://api.voyageai.com/v1/embeddings"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "voyage-4",
        endpoint: str | None = None,
        timeout_seconds: float = 30.0,
        batch_size: int = 64,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("VOYAGE_API_KEY", "")
        if not self.api_key.strip():
            raise ValueError("VOYAGE_API_KEY is required for the Voyage embedding provider.")
        if not model.strip():
            raise ValueError("An embedding model name is required.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if batch_size < 1 or batch_size > 1000:
            raise ValueError("batch_size must be between 1 and 1000.")
        self.model_id = model
        self.endpoint = (endpoint or os.environ.get("VOYAGE_API_URL") or self.DEFAULT_ENDPOINT).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size
        self._opener = opener or urlopen
        self.request_count = 0
        self.input_tokens = 0
        self.document_request_count = 0
        self.query_request_count = 0
        self.document_input_tokens = 0
        self.query_input_tokens = 0
        self.embedding_dimensions: int | None = None

    def embed(self, text: str) -> list[float]:
        """Compatibility method; standalone text is treated as a query."""
        return self.embed_query(text)

    def embed_query(self, text: str) -> list[float]:
        return self.embed_queries([text])[0]

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed_many(texts, input_type="query")

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed_many(texts, input_type="document")

    def _embed_many(self, texts: Sequence[str], *, input_type: str) -> list[list[float]]:
        if input_type not in {"query", "document"}:
            raise ValueError("input_type must be query or document.")
        if not texts:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Embedding inputs must be non-empty strings.")

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start : start + self.batch_size])
            result = self._post_batch(batch, input_type=input_type)
            vectors.extend(result)
        return vectors

    def _post_batch(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        payload = json.dumps(
            {"input": texts, "model": self.model_id, "input_type": input_type},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            self.endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            response = self._opener(request, timeout=self.timeout_seconds)
            with response:
                body = response.read()
        except HTTPError as error:
            # Do not include provider response bodies: gateways may echo inputs.
            raise RuntimeError(f"Voyage embedding request failed with HTTP {error.code}.") from None
        except (URLError, TimeoutError, OSError) as error:
            raise RuntimeError(f"Voyage embedding request failed ({type(error).__name__}).") from None

        try:
            decoded = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RuntimeError("Voyage embedding response was not valid JSON.") from None
        if not isinstance(decoded, dict) or not isinstance(decoded.get("data"), list):
            raise RuntimeError("Voyage embedding response is missing its data array.")
        if len(decoded["data"]) != len(texts):
            raise RuntimeError("Voyage embedding response count did not match the request.")

        indexed: dict[int, list[float]] = {}
        for item in decoded["data"]:
            if not isinstance(item, dict) or type(item.get("index")) is not int:
                raise RuntimeError("Voyage embedding response contains an invalid item index.")
            index = item["index"]
            embedding = item.get("embedding")
            if index < 0 or index >= len(texts) or index in indexed or not isinstance(embedding, list):
                raise RuntimeError("Voyage embedding response contains malformed vectors.")
            if any(type(value) not in (int, float) for value in embedding):
                raise RuntimeError("Voyage embedding response contains a non-numeric vector.")
            try:
                vector = [float(value) for value in embedding]
            except (TypeError, ValueError, OverflowError):
                raise RuntimeError("Voyage embedding response contains a non-numeric vector.") from None
            if not vector or any(not math.isfinite(value) for value in vector):
                raise RuntimeError("Voyage embedding response contains an empty or non-finite vector.")
            if self.embedding_dimensions is not None and len(vector) != self.embedding_dimensions:
                raise RuntimeError("Voyage embedding dimensions changed during this adapter session.")
            self.embedding_dimensions = len(vector)
            indexed[index] = vector
        if set(indexed) != set(range(len(texts))):
            raise RuntimeError("Voyage embedding response omitted one or more input indices.")

        usage = decoded.get("usage", {})
        if isinstance(usage, dict):
            token_count = usage.get("total_tokens", usage.get("input_tokens", 0))
            if type(token_count) is int and token_count >= 0:
                self.input_tokens += token_count
                if input_type == "document":
                    self.document_input_tokens += token_count
                else:
                    self.query_input_tokens += token_count
        self.request_count += 1
        if input_type == "document":
            self.document_request_count += 1
        else:
            self.query_request_count += 1
        return [indexed[index] for index in range(len(texts))]
