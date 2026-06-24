import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from core.config import settings
from schemas.rag import RagIndexSourceResponse, RagUploadResponse, RagUrlIngestPreviewResponse
from services.rag.indexing.indexing_service import RagIndexingService
from services.rag.ingestion.exceptions import DuplicateSourceError
from services.rag.ingestion.chunker import RagChunker
from services.rag.ingestion.parsers.resolver import ParserResolver
from services.rag.ingestion.parsers.url_parser_factory import parse_url_document
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

        duplicate = self.source_repository.find_duplicate_by_hash(
            client_id=client_id,
            corpus_id=corpus_id,
            content_hash=content_hash,
        )

        if duplicate is not None:
            file_path.unlink(missing_ok=True)
            raise DuplicateSourceError(
                message="Ce fichier a déjà été importé dans ce corpus.",
                existing_source=duplicate,
            )

        source = self.source_repository.create_source(
            client_id=client_id,
            corpus_id=corpus_id,
            source_type=source_type,
            source_name=safe_filename,
            source_uri=str(file_path),
            metadata_json={
                "original_filename": upload_file.filename,
                "content_type": upload_file.content_type,
                "ingestion_mode": "sync_preview",
            },
            content_hash=content_hash,
        )

        parser = ParserResolver.get_parser(str(file_path), source_type=source_type)
        parsed_document = parser.parse(str(file_path))

        chunks = self.chunker.chunk_pages(parsed_document.pages)

        chunks_path = self._write_chunks_file(
            base_path=file_path,
            client_id=client_id,
            corpus_id=corpus_id,
            source_id=source.source_id,
            source_type=source.source_type,
            source_name=source.source_name,
            chunks=chunks,
        )

        metadata = source.metadata_json or {}
        metadata.update(
            {
                "chunks_path": str(chunks_path),
                "parser_metadata": parsed_document.metadata,
            }
        )
        source.metadata_json = metadata

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
            preview_chunks=self._preview_chunks(chunks),
            parser_metadata=parsed_document.metadata,
        )

    def ingest_url_preview(
        self,
        *,
        client_id: str,
        corpus_id: str,
        url: str,
        source_name: str | None = None,
        metadata: dict | None = None,
    ) -> RagUrlIngestPreviewResponse:
        storage_dir = self._build_storage_dir(client_id=client_id)
        storage_dir.mkdir(parents=True, exist_ok=True)

        normalized_url = self.source_repository.normalize_source_uri(str(url))

        duplicate = self.source_repository.find_duplicate_by_source_uri(
            client_id=client_id,
            corpus_id=corpus_id,
            source_uri=normalized_url,
            source_type="url",
        )

        if duplicate is not None:
            raise DuplicateSourceError(
                message="Cette URL a déjà été importée dans ce corpus.",
                existing_source=duplicate,
            )

        parsed_document = parse_url_document(normalized_url)

        final_source_name = source_name or parsed_document.metadata.get("title") or url
        safe_source_name = self._safe_filename(final_source_name)[:120] or "url_source"

        content_hash = self._hash_text(parsed_document.text)

        source = self.source_repository.create_source(
            client_id=client_id,
            corpus_id=corpus_id,
            source_type="url",
            source_name=final_source_name,
            source_uri=normalized_url,
            metadata_json={
                **(metadata or {}),
                **parsed_document.metadata,
                "ingestion_mode": "sync_preview",
            },
            content_hash=content_hash,
        )

        chunks = self.chunker.chunk_pages(parsed_document.pages)

        base_path = storage_dir / f"{uuid4().hex}_{safe_source_name}.url"
        chunks_path = self._write_chunks_file(
            base_path=base_path,
            client_id=client_id,
            corpus_id=corpus_id,
            source_id=source.source_id,
            source_type=source.source_type,
            source_name=source.source_name,
            chunks=chunks,
        )

        metadata_json = source.metadata_json or {}
        metadata_json.update(
            {
                "chunks_path": str(chunks_path),
                "parser_metadata": parsed_document.metadata,
            }
        )
        source.metadata_json = metadata_json

        self.source_repository.update_status(
            source_id=source.source_id,
            status="pending",
            qdrant_points_count=len(chunks),
        )

        return RagUrlIngestPreviewResponse(
            source_id=source.source_id,
            client_id=client_id,
            corpus_id=corpus_id,
            source_type=source.source_type,
            source_name=source.source_name,
            status="pending",
            source_uri=normalized_url,
            chunks_path=str(chunks_path),
            chunks_count=len(chunks),
            preview_chunks=self._preview_chunks(chunks),
            parser_metadata=parsed_document.metadata,
        )

    async def create_upload_source_for_async(
        self,
        *,
        client_id: str,
        corpus_id: str,
        upload_file: UploadFile,
    ):
        source_type = self._detect_source_type(upload_file.filename)

        storage_dir = self._build_storage_dir(client_id=client_id)
        storage_dir.mkdir(parents=True, exist_ok=True)

        file_id = uuid4().hex
        safe_filename = self._safe_filename(upload_file.filename or f"upload_{file_id}")
        file_path = storage_dir / f"{file_id}_{safe_filename}"

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)

        content_hash = self._hash_file(file_path)

        duplicate = self.source_repository.find_duplicate_by_hash(
            client_id=client_id,
            corpus_id=corpus_id,
            content_hash=content_hash,
        )

        if duplicate is not None:
            file_path.unlink(missing_ok=True)
            raise DuplicateSourceError(
                message="Ce fichier a déjà été importé dans ce corpus.",
                existing_source=duplicate,
            )

        return self.source_repository.create_source(
            client_id=client_id,
            corpus_id=corpus_id,
            source_type=source_type,
            source_name=safe_filename,
            source_uri=str(file_path),
            metadata_json={
                "original_filename": upload_file.filename,
                "content_type": upload_file.content_type,
                "ingestion_mode": "async",
                "file_path": str(file_path),
            },
            content_hash=content_hash,
        )

    def create_url_source_for_async(
        self,
        *,
        client_id: str,
        corpus_id: str,
        url: str,
        source_name: str | None = None,
        metadata: dict | None = None,
    ):
        normalized_url = self.source_repository.normalize_source_uri(str(url))
        final_source_name = source_name or normalized_url

        duplicate = self.source_repository.find_duplicate_by_source_uri(
            client_id=client_id,
            corpus_id=corpus_id,
            source_uri=normalized_url,
            source_type="url",
        )

        if duplicate is not None:
            raise DuplicateSourceError(
                message="Cette URL a déjà été importée dans ce corpus.",
                existing_source=duplicate,
            )

        return self.source_repository.create_source(
            client_id=client_id,
            corpus_id=corpus_id,
            source_type="url",
            source_name=final_source_name,
            source_uri=normalized_url,
            metadata_json={
                **(metadata or {}),
                "ingestion_mode": "async",
                "url": normalized_url,
                "source_name_provided": bool(source_name),
            },
            content_hash=None,
        )

    def ingest_source_and_index(
        self,
        source_id: str,
    ) -> RagIndexSourceResponse:
        source = self.source_repository.get_by_source_id(source_id)

        if source is None:
            raise ValueError("Source RAG introuvable")

        if source.status == "deleted":
            raise ValueError("Impossible d'ingérer une source supprimée")

        try:
            source.status = "indexing"
            source.error_message = None
            self.db.commit()
            self.db.refresh(source)

            if source.source_type == "url":
                chunks_path, chunks_count, parser_metadata, content_hash = self._parse_chunk_url_source(source)
            else:
                chunks_path, chunks_count, parser_metadata, content_hash = self._parse_chunk_file_source(source)

            metadata = source.metadata_json or {}
            metadata.update(
                {
                    "chunks_path": str(chunks_path),
                    "parser_metadata": parser_metadata,
                    "async_ingested_at": datetime.now(timezone.utc).isoformat(),
                }
            )

            source.metadata_json = metadata
            source.content_hash = content_hash
            source.qdrant_points_count = chunks_count
            source.status = "pending"
            self.db.commit()
            self.db.refresh(source)

            indexing_service = RagIndexingService(self.db)
            return indexing_service.index_source(source_id)

        except Exception as exc:
            source = self.source_repository.get_by_source_id(source_id)

            if source is not None:
                source.status = "error"
                source.error_message = str(exc)
                self.db.commit()

            raise

    def _parse_chunk_file_source(self, source) -> tuple[Path, int, dict, str]:
        if not source.source_uri:
            raise ValueError("Chemin fichier manquant pour la source")

        file_path = Path(source.source_uri)

        if not file_path.exists():
            raise ValueError(f"Fichier source introuvable: {file_path}")

        parser = ParserResolver.get_parser(str(file_path), source_type=source.source_type)
        parsed_document = parser.parse(str(file_path))

        chunks = self.chunker.chunk_pages(parsed_document.pages)

        if not chunks:
            raise ValueError("Aucun chunk généré pour cette source")

        chunks_path = self._write_chunks_file(
            base_path=file_path,
            client_id=source.client_id,
            corpus_id=source.corpus_id,
            source_id=source.source_id,
            source_type=source.source_type,
            source_name=source.source_name,
            chunks=chunks,
        )

        return chunks_path, len(chunks), parsed_document.metadata, self._hash_file(file_path)

    def _parse_chunk_url_source(self, source) -> tuple[Path, int, dict, str]:
        if not source.source_uri:
            raise ValueError("URL manquante pour la source")

        storage_dir = self._build_storage_dir(client_id=source.client_id)
        storage_dir.mkdir(parents=True, exist_ok=True)

        parsed_document = parse_url_document(source.source_uri)

        chunks = self.chunker.chunk_pages(parsed_document.pages)

        if not chunks:
            raise ValueError("Aucun chunk généré pour cette URL")

        metadata = source.metadata_json or {}

        if not metadata.get("source_name_provided"):
            title = parsed_document.metadata.get("title")
            if title:
                source.source_name = title

        safe_source_name = self._safe_filename(source.source_name or "url_source")[:120] or "url_source"
        base_path = storage_dir / f"{uuid4().hex}_{safe_source_name}.url"

        chunks_path = self._write_chunks_file(
            base_path=base_path,
            client_id=source.client_id,
            corpus_id=source.corpus_id,
            source_id=source.source_id,
            source_type=source.source_type,
            source_name=source.source_name,
            chunks=chunks,
        )

        parser_metadata = {
            **parsed_document.metadata,
            "chunks_base_path": str(base_path),
        }

        return chunks_path, len(chunks), parser_metadata, self._hash_text(parsed_document.text)

    def _write_chunks_file(
        self,
        *,
        base_path: Path,
        client_id: str,
        corpus_id: str,
        source_id: str,
        source_type: str,
        source_name: str,
        chunks,
    ) -> Path:
        chunks_payload = [
            {
                "client_id": client_id,
                "corpus_id": corpus_id,
                "source_id": source_id,
                "source_type": source_type,
                "source_name": source_name,
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "metadata": chunk.metadata,
            }
            for chunk in chunks
        ]

        chunks_path = base_path.with_suffix(base_path.suffix + ".chunks.json")

        with open(chunks_path, "w", encoding="utf-8") as file:
            json.dump(chunks_payload, file, ensure_ascii=False, indent=2)

        return chunks_path

    def _preview_chunks(self, chunks) -> list[dict]:
        return [
            {
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text[:500],
            }
            for chunk in chunks[:3]
        ]

    def _build_storage_dir(self, *, client_id: str) -> Path:
        return Path(settings.RAG_STORAGE_DIR) / client_id

    def _detect_source_type(self, filename: str | None) -> str:
        suffix = Path(filename or "").suffix.lower()

        if suffix == ".pdf":
            return "pdf"

        if suffix == ".txt":
            return "txt"

        if suffix == ".docx":
            return "docx"

        raise ValueError(
            "Type de fichier non supporté pour l'instant. "
            "Formats acceptés: .txt, .pdf, .docx"
        )

    def _hash_file(self, file_path: Path) -> str:
        hasher = hashlib.sha256()

        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                hasher.update(chunk)

        return hasher.hexdigest()

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _safe_filename(self, filename: str) -> str:
        filename = os.path.basename(filename)
        filename = filename.replace(" ", "_")
        allowed = []

        for char in filename:
            if char.isalnum() or char in {".", "_", "-"}:
                allowed.append(char)

        return "".join(allowed) or "uploaded_file"
