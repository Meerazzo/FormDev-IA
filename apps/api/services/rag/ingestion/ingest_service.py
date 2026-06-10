import hashlib
import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from core.config import settings
from schemas.rag import RagUploadResponse
from services.rag.ingestion.chunker import RagChunker
from services.rag.ingestion.parsers.resolver import ParserResolver
from services.rag.sources.source_repository import RagSourceRepository


class RagIngestService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.source_repository = RagSourceRepository(db)
        self.chunker = RagChunker()

    async def ingest_upload_preview(
        self,
        *,
        client_id: str,
        corpus_id: str,
        upload_file: UploadFile,
    ) -> RagUploadResponse:
        source_type = self._detect_source_type(upload_file.filename)

        storage_dir = self._build_storage_dir(client_id=client_id)
        storage_dir.mkdir(parents=True, exist_ok=True)

        file_id = uuid4().hex
        safe_filename = self._safe_filename(upload_file.filename or f"upload_{file_id}")
        file_path = storage_dir / f"{file_id}_{safe_filename}"

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)

        content_hash = self._hash_file(file_path)

        source = self.source_repository.create_source(
            client_id=client_id,
            corpus_id=corpus_id,
            source_type=source_type,
            source_name=safe_filename,
            source_uri=str(file_path),
            metadata_json={
                "original_filename": upload_file.filename,
                "content_type": upload_file.content_type,
            },
            content_hash=content_hash,
        )

        parser = ParserResolver.get_parser(str(file_path), source_type=source_type)
        parsed_document = parser.parse(str(file_path))

        chunks = self.chunker.chunk_pages(parsed_document.pages)

        chunks_payload = [
            {
                "client_id": client_id,
                "corpus_id": corpus_id,
                "source_id": source.source_id,
                "source_type": source.source_type,
                "source_name": source.source_name,
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "metadata": chunk.metadata,
            }
            for chunk in chunks
        ]

        chunks_path = file_path.with_suffix(file_path.suffix + ".chunks.json")
        with open(chunks_path, "w", encoding="utf-8") as file:
            json.dump(chunks_payload, file, ensure_ascii=False, indent=2)

        self.source_repository.update_status(
            source_id=source.source_id,
            status="pending",
            qdrant_points_count=len(chunks),
        )

        return RagUploadResponse(
            source_id=source.source_id,
            client_id=client_id,
            corpus_id=corpus_id,
            source_type=source.source_type,
            source_name=source.source_name,
            status="pending",
            file_path=str(file_path),
            chunks_path=str(chunks_path),
            chunks_count=len(chunks),
            preview_chunks=[
                {
                    "page": chunk.page,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text[:500],
                }
                for chunk in chunks[:3]
            ],
            parser_metadata=parsed_document.metadata,
        )

    def _build_storage_dir(self, *, client_id: str) -> Path:
        return Path(settings.RAG_STORAGE_DIR) / client_id

    def _detect_source_type(self, filename: str | None) -> str:
        suffix = Path(filename or "").suffix.lower()

        if suffix == ".pdf":
            return "pdf"

        if suffix == ".txt":
            return "txt"

        raise ValueError("Type de fichier non supporté pour l'instant. Formats acceptés: .txt, .pdf")

    def _hash_file(self, file_path: Path) -> str:
        hasher = hashlib.sha256()

        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                hasher.update(chunk)

        return hasher.hexdigest()

    def _safe_filename(self, filename: str) -> str:
        filename = os.path.basename(filename)
        filename = filename.replace(" ", "_")
        allowed = []
        for char in filename:
            if char.isalnum() or char in {".", "_", "-"}:
                allowed.append(char)
        return "".join(allowed) or "uploaded_file"
