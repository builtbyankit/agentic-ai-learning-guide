"""Small, local RAG ingestion and retrieval lab using only the Python standard library.

The hashing embedder exists to make the storage/query path runnable offline. It is a
deterministic lexical feature hash, not a semantic embedding model and not suitable
for production relevance claims.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol, Sequence


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_WORD = re.compile(r"[\w'-]+", re.UNICODE)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_LIKE = re.compile(r"(?<!\w)(?:\+?1[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]?\d{3}[ .-]?\d{4}(?!\w)")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CLASSIFICATIONS = {"public", "internal", "confidential", "restricted"}
_STATUSES = {"active", "superseded", "draft"}
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "can", "do", "for", "from", "how", "i", "in",
    "is", "it", "me", "of", "on", "or", "the", "to", "was", "what", "when", "where", "who", "with",
}


@dataclass(frozen=True)
class Document:
    source_id: str
    tenant_id: str
    version: str
    effective_date: str
    status: str
    classification: str
    text: str
    redact_basic_pii: bool = False


@dataclass(frozen=True)
class Section:
    path: str
    text: str


@dataclass(frozen=True)
class PreparedChunk:
    chunk_id: str
    source_id: str
    tenant_id: str
    version: str
    effective_date: str
    status: str
    classification: str
    source_hash: str
    section_path: str
    text: str


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    source_id: str
    version: str
    effective_date: str
    section_path: str
    classification: str
    text: str
    score: float


class Embedder(Protocol):
    model_id: str

    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Offline feature hashing for plumbing demos; it does not understand meaning."""

    def __init__(self, dimensions: int = 512) -> None:
        if dimensions < 32:
            raise ValueError("Use at least 32 dimensions for this demo embedder.")
        self.dimensions = dimensions
        self.model_id = f"demo-feature-hash-v1-{dimensions}d"

    def embed(self, text: str) -> list[float]:
        words = [word.lower() for word in _WORD.findall(text)]
        features = [(word, 1.0) for word in words]
        features.extend((f"{left} {right}", 0.5) for left, right in zip(words, words[1:]))
        vector = [0.0] * self.dimensions
        for feature, weight in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimensions
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += weight * sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector


def normalize_text(text: str, *, redact_basic_pii: bool = False) -> str:
    """Normalize common text noise while preserving paragraph and line boundaries."""
    value = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    value = _CONTROL.sub("", value)
    if redact_basic_pii:
        value = _EMAIL.sub("[REDACTED_EMAIL]", value)
        value = _PHONE_LIKE.sub("[REDACTED_PHONE]", value)
    lines = [re.sub(r"[\t \u00a0]+", " ", line).strip() for line in value.split("\n")]
    value = "\n".join(lines)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def parse_markdown_sections(text: str) -> list[Section]:
    """Keep heading hierarchy attached to the body that follows each heading."""
    headings: list[tuple[int, str]] = []
    sections: list[Section] = []
    body: list[str] = []

    def flush() -> None:
        content = "\n".join(body).strip()
        if content:
            path = " > ".join(title for _, title in headings) or "Document"
            sections.append(Section(path=path, text=content))
        body.clear()

    for line in text.splitlines():
        match = _HEADING.match(line)
        if not match:
            body.append(line)
            continue
        flush()
        level = len(match.group(1))
        title = match.group(2).strip()
        headings[:] = [(depth, heading) for depth, heading in headings if depth < level]
        headings.append((level, title))
    flush()
    return sections


def chunk_sections(
    sections: Sequence[Section],
    *,
    max_words: int = 90,
    overlap_words: int = 18,
) -> list[tuple[str, str]]:
    """Split by whitespace-word units, retaining heading paths and a bounded overlap.

    Word units keep this standard-library exercise deterministic. Replace this
    counter with the production model's tokenizer when enforcing token budgets.
    """
    if max_words < 1 or overlap_words < 0 or overlap_words >= max_words:
        raise ValueError("Require max_words > overlap_words >= 0.")
    chunks: list[tuple[str, str]] = []
    for section in sections:
        words = section.text.split()
        if not words:
            continue
        start = 0
        while start < len(words):
            end = min(len(words), start + max_words)
            chunks.append((section.path, " ".join(words[start:end])))
            if end == len(words):
                break
            start = end - overlap_words
    return chunks


def prepare_document(
    document: Document,
    *,
    max_words: int = 90,
    overlap_words: int = 18,
) -> list[PreparedChunk]:
    if not document.source_id.strip() or not document.tenant_id.strip():
        raise ValueError("source_id and tenant_id are required trusted metadata.")
    if document.status not in _STATUSES:
        raise ValueError("Unsupported document status.")
    if document.classification not in _CLASSIFICATIONS:
        raise ValueError("Unsupported document classification.")
    clean = normalize_text(document.text, redact_basic_pii=document.redact_basic_pii)
    if not clean:
        return []
    source_hash = hashlib.sha256(clean.encode("utf-8")).hexdigest()
    chunks = chunk_sections(
        parse_markdown_sections(clean),
        max_words=max_words,
        overlap_words=overlap_words,
    )
    prepared: list[PreparedChunk] = []
    for index, (section_path, body) in enumerate(chunks):
        rendered = f"{section_path}\n\n{body}"
        identity = "\x1f".join(
            (
                document.tenant_id,
                document.source_id,
                document.version,
                document.status,
                section_path,
                str(index),
                rendered,
            )
        )
        chunk_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        prepared.append(
            PreparedChunk(
                chunk_id=chunk_id,
                source_id=document.source_id,
                tenant_id=document.tenant_id,
                version=document.version,
                effective_date=document.effective_date,
                status=document.status,
                classification=document.classification,
                source_hash=source_hash,
                section_path=section_path,
                text=rendered,
            )
        )
    return prepared


class SQLiteVectorStore:
    """Persistent exact-cosine vector search for small local learning datasets.

    This stores vectors and filter metadata in SQLite and scans authorized rows
    exactly. It is not an approximate-nearest-neighbor service for large corpora.
    """

    def __init__(self, path: str | Path, embedder: Embedder) -> None:
        self.embedder = embedder
        self.connection = sqlite3.connect(str(path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                version TEXT NOT NULL,
                effective_date TEXT NOT NULL,
                status TEXT NOT NULL,
                classification TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                section_path TEXT NOT NULL,
                text TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                embedding_json TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS chunks_scope ON chunks(tenant_id, status, classification, embedding_model)"
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS chunks_source ON chunks(tenant_id, source_id, status)"
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def ingest(self, document: Document, *, max_words: int = 90, overlap_words: int = 18) -> int:
        chunks = prepare_document(document, max_words=max_words, overlap_words=overlap_words)
        current = self.connection.execute(
            """SELECT chunk_id, source_hash, version, effective_date, status,
                      classification, embedding_model
               FROM chunks
               WHERE tenant_id = ? AND source_id = ? AND status = 'active'""",
            (document.tenant_id, document.source_id),
        ).fetchall()
        expected_ids = {chunk.chunk_id for chunk in chunks}
        unchanged = len(current) == len(chunks) and {row["chunk_id"] for row in current} == expected_ids
        if unchanged:
            unchanged = all(
                row["source_hash"] == chunks[0].source_hash
                and row["version"] == document.version
                and row["effective_date"] == document.effective_date
                and row["status"] == document.status
                and row["classification"] == document.classification
                and row["embedding_model"] == self.embedder.model_id
                for row in current
            ) if current else True
        if unchanged:
            return 0
        with self.connection:
            if document.status == "active":
                self.connection.execute(
                    "UPDATE chunks SET status = 'superseded' WHERE tenant_id = ? AND source_id = ? AND status = 'active'",
                    (document.tenant_id, document.source_id),
                )
            for chunk in chunks:
                vector = self.embedder.embed(chunk.text)
                self.connection.execute(
                    """
                    INSERT OR REPLACE INTO chunks (
                        chunk_id, source_id, tenant_id, version, effective_date, status,
                        classification, source_hash, section_path, text,
                        embedding_model, embedding_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        chunk.source_id,
                        chunk.tenant_id,
                        chunk.version,
                        chunk.effective_date,
                        chunk.status,
                        chunk.classification,
                        chunk.source_hash,
                        chunk.section_path,
                        chunk.text,
                        self.embedder.model_id,
                        json.dumps(vector, separators=(",", ":")),
                    ),
                )
        return len(chunks)

    def supersede_source(self, *, tenant_id: str, source_id: str) -> int:
        """Remove a source from active retrieval while retaining its indexed history."""
        if not tenant_id or not source_id:
            raise ValueError("tenant_id and source_id are required for superseding a source.")
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE chunks SET status = 'superseded' WHERE tenant_id = ? AND source_id = ? AND status = 'active'",
                (tenant_id, source_id),
            )
        return cursor.rowcount

    def delete_source(self, *, tenant_id: str, source_id: str) -> int:
        if not tenant_id or not source_id:
            raise ValueError("tenant_id and source_id are required for deletion.")
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM chunks WHERE tenant_id = ? AND source_id = ?",
                (tenant_id, source_id),
            )
        return cursor.rowcount

    def search(
        self,
        *,
        tenant_id: str,
        query: str,
        allowed_classifications: Sequence[str],
        top_k: int = 4,
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        if not tenant_id:
            raise ValueError("A trusted tenant_id is required; it cannot come from model text.")
        if not allowed_classifications or any(value not in _CLASSIFICATIONS for value in allowed_classifications):
            raise ValueError("Pass an explicit, valid classification allowlist.")
        if top_k < 1 or top_k > 50:
            raise ValueError("top_k must be between 1 and 50.")
        if not query.strip():
            return []

        classes = tuple(sorted(set(allowed_classifications)))
        placeholders = ",".join("?" for _ in classes)
        rows = self.connection.execute(
            f"""SELECT chunk_id, source_id, version, effective_date, section_path,
                       classification, text, embedding_json
                FROM chunks
                WHERE tenant_id = ? AND status = 'active' AND classification IN ({placeholders})
                  AND embedding_model = ?""",
            (tenant_id, *classes, self.embedder.model_id),
        ).fetchall()
        query_vector = self.embedder.embed(query)
        if not any(query_vector):
            return []
        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            candidate = json.loads(row["embedding_json"])
            if len(candidate) != len(query_vector):
                raise RuntimeError("Stored vector dimensions do not match the configured embedder.")
            score = sum(left * right for left, right in zip(query_vector, candidate))
            if score >= min_score:
                scored.append((score, row))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["chunk_id"]))
        return [
            SearchHit(
                chunk_id=row["chunk_id"],
                source_id=row["source_id"],
                version=row["version"],
                effective_date=row["effective_date"],
                section_path=row["section_path"],
                classification=row["classification"],
                text=row["text"],
                score=round(score, 6),
            )
            for score, row in scored[:top_k]
        ]

    def search_lexical(
        self,
        *,
        tenant_id: str,
        query: str,
        allowed_classifications: Sequence[str],
        top_k: int = 4,
        relative_score_floor: float = 0.0,
    ) -> list[SearchHit]:
        """BM25-style lexical ranking over the same authorization-filtered corpus."""
        if not tenant_id:
            raise ValueError("A trusted tenant_id is required; it cannot come from model text.")
        if not allowed_classifications or any(value not in _CLASSIFICATIONS for value in allowed_classifications):
            raise ValueError("Pass an explicit, valid classification allowlist.")
        if top_k < 1 or top_k > 50:
            raise ValueError("top_k must be between 1 and 50.")
        if relative_score_floor < 0 or relative_score_floor > 1:
            raise ValueError("relative_score_floor must be between 0 and 1.")
        query_terms = [
            token.lower() for token in _WORD.findall(query) if token.lower() not in _STOP_WORDS
        ]
        if not query_terms:
            return []

        classes = tuple(sorted(set(allowed_classifications)))
        placeholders = ",".join("?" for _ in classes)
        rows = self.connection.execute(
            f"""SELECT chunk_id, source_id, version, effective_date, section_path,
                       classification, text
                FROM chunks
                WHERE tenant_id = ? AND status = 'active' AND classification IN ({placeholders})""",
            (tenant_id, *classes),
        ).fetchall()
        if not rows:
            return []

        tokenized = [[token.lower() for token in _WORD.findall(row["text"])] for row in rows]
        lengths = [len(tokens) for tokens in tokenized]
        average_length = sum(lengths) / len(lengths) if lengths else 0.0
        query_frequency = Counter(query_terms)
        document_frequency = {
            term: sum(1 for tokens in tokenized if term in set(tokens))
            for term in query_frequency
        }
        k1, b = 1.5, 0.75
        scored: list[tuple[float, sqlite3.Row]] = []
        for row, tokens, length in zip(rows, tokenized, lengths):
            frequencies = Counter(tokens)
            score = 0.0
            for term, query_count in query_frequency.items():
                term_frequency = frequencies[term]
                if not term_frequency:
                    continue
                df = document_frequency[term]
                inverse_frequency = math.log(1 + (len(rows) - df + 0.5) / (df + 0.5))
                length_norm = term_frequency + k1 * (1 - b + b * length / max(average_length, 1.0))
                score += query_count * inverse_frequency * term_frequency * (k1 + 1) / length_norm
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["chunk_id"]))
        if scored and relative_score_floor:
            score_floor = scored[0][0] * relative_score_floor
            scored = [pair for pair in scored if pair[0] >= score_floor]
        return [
            SearchHit(
                chunk_id=row["chunk_id"],
                source_id=row["source_id"],
                version=row["version"],
                effective_date=row["effective_date"],
                section_path=row["section_path"],
                classification=row["classification"],
                text=row["text"],
                score=round(score, 6),
            )
            for score, row in scored[:top_k]
        ]

    def search_hybrid(
        self,
        *,
        tenant_id: str,
        query: str,
        allowed_classifications: Sequence[str],
        top_k: int = 4,
        min_dense_score: float = 0.0,
        lexical_relative_score_floor: float = 0.0,
        rank_constant: int = 60,
    ) -> list[SearchHit]:
        """Fuse dense and BM25 ranks with reciprocal-rank fusion."""
        if rank_constant < 1:
            raise ValueError("rank_constant must be positive.")
        if top_k < 1 or top_k > 50:
            raise ValueError("top_k must be between 1 and 50.")
        candidate_k = min(50, max(top_k * 5, top_k))
        dense = self.search(
            tenant_id=tenant_id,
            query=query,
            allowed_classifications=allowed_classifications,
            top_k=candidate_k,
            min_score=min_dense_score,
        )
        lexical = self.search_lexical(
            tenant_id=tenant_id,
            query=query,
            allowed_classifications=allowed_classifications,
            top_k=candidate_k,
            relative_score_floor=lexical_relative_score_floor,
        )
        fused: dict[str, tuple[float, SearchHit]] = {}
        for ranked in (dense, lexical):
            for rank, hit in enumerate(ranked, start=1):
                prior, _ = fused.get(hit.chunk_id, (0.0, hit))
                fused[hit.chunk_id] = (prior + 1.0 / (rank_constant + rank), hit)
        ordered = sorted(fused.values(), key=lambda item: (-item[0], item[1].chunk_id))
        return [replace(hit, score=round(score, 6)) for score, hit in ordered[:top_k]]


def load_manifest_documents(manifest_path: str | Path) -> list[Document]:
    manifest_path = Path(manifest_path).resolve()
    root = manifest_path.parent.resolve()
    records = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents: list[Document] = []
    for record in records:
        source_path = (root / record["path"]).resolve()
        if root not in source_path.parents:
            raise ValueError("Knowledge source path escapes the manifest directory.")
        documents.append(
            Document(
                source_id=record["source_id"],
                tenant_id=record["tenant_id"],
                version=record["version"],
                effective_date=record["effective_date"],
                status=record["status"],
                classification=record["classification"],
                text=source_path.read_text(encoding="utf-8"),
                redact_basic_pii=record.get("redact_basic_pii", False),
            )
        )
    return documents
