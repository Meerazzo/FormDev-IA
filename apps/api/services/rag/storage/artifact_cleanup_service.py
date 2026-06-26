from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from core.config import settings


class RagArtifactCleanupService:
    """
    Supprime prudemment les artefacts locaux créés pendant l'ingestion RAG.

    Politique par défaut :
    - après indexation réussie, supprimer le fichier original uploadé ;
    - conserver le fichier .chunks.json pour permettre reindex/resync ;
    - lors d'une suppression de source, supprimer fichier original + chunks.
    """

    def __init__(self, db) -> None:
        self.db = db
        self.storage_root = Path(settings.RAG_STORAGE_DIR)

    def cleanup_after_successful_index(self, source) -> dict[str, Any]:
        if not settings.RAG_CLEANUP_LOCAL_FILES_AFTER_INDEX:
            return {"enabled": False, "reason": "RAG_CLEANUP_LOCAL_FILES_AFTER_INDEX=false"}

        deleted: list[str] = []
        skipped: list[dict[str, str]] = []

        if source.source_type != "url":
            source_path = self._safe_local_path(source.source_uri)
            if source_path is None:
                skipped.append({"artifact": "source_file", "reason": "missing_or_unsafe_path"})
            else:
                if self._delete_file(source_path):
                    deleted.append(str(source_path))
                else:
                    skipped.append({"artifact": "source_file", "reason": "not_found"})
        else:
            skipped.append({"artifact": "source_file", "reason": "url_source_has_no_local_original"})

        if not settings.RAG_CLEANUP_KEEP_CHUNKS_AFTER_INDEX:
            chunks_path = self._chunks_path(source)
            if chunks_path is not None and self._delete_file(chunks_path):
                deleted.append(str(chunks_path))

        cleanup_report = {
            "policy": "delete_original_keep_chunks" if settings.RAG_CLEANUP_KEEP_CHUNKS_AFTER_INDEX else "delete_original_and_chunks",
            "trigger": "index_success",
            "deleted_paths": deleted,
            "skipped": skipped,
            "source_file_deleted": bool(deleted),
            "chunks_file_kept": settings.RAG_CLEANUP_KEEP_CHUNKS_AFTER_INDEX,
            "reindex_available": settings.RAG_CLEANUP_KEEP_CHUNKS_AFTER_INDEX,
            "cleaned_at": datetime.now(timezone.utc).isoformat(),
        }

        self._append_cleanup_metadata(source, cleanup_report)
        self.db.commit()
        self.db.refresh(source)
        return cleanup_report

    def cleanup_on_source_delete(self, source) -> dict[str, Any]:
        if not settings.RAG_CLEANUP_ARTIFACTS_ON_SOURCE_DELETE:
            return {"enabled": False, "reason": "RAG_CLEANUP_ARTIFACTS_ON_SOURCE_DELETE=false"}

        deleted: list[str] = []
        skipped: list[dict[str, str]] = []

        if source.source_type != "url":
            source_path = self._safe_local_path(source.source_uri)
            if source_path is not None and self._delete_file(source_path):
                deleted.append(str(source_path))
            else:
                skipped.append({"artifact": "source_file", "reason": "not_found_or_unsafe_path"})

        chunks_path = self._chunks_path(source)
        if chunks_path is not None and self._delete_file(chunks_path):
            deleted.append(str(chunks_path))
        else:
            skipped.append({"artifact": "chunks_file", "reason": "not_found_or_unsafe_path"})

        cleanup_report = {
            "policy": "delete_all_local_artifacts_on_source_delete",
            "trigger": "source_delete",
            "deleted_paths": deleted,
            "skipped": skipped,
            "reindex_available": False,
            "cleaned_at": datetime.now(timezone.utc).isoformat(),
        }

        self._append_cleanup_metadata(source, cleanup_report)
        self.db.commit()
        self.db.refresh(source)
        return cleanup_report

    def _chunks_path(self, source) -> Path | None:
        metadata = source.metadata_json or {}
        chunks_path = metadata.get("chunks_path")
        if not chunks_path:
            return None
        return self._safe_local_path(chunks_path)

    def _safe_local_path(self, raw_path: str | None) -> Path | None:
        if not raw_path:
            return None

        path = Path(raw_path)
        if not path.is_absolute():
            return None

        try:
            resolved_path = path.resolve(strict=False)
            resolved_root = self.storage_root.resolve(strict=False)
            if resolved_path == resolved_root or resolved_root not in resolved_path.parents:
                return None
            return resolved_path
        except Exception:
            return None

    @staticmethod
    def _delete_file(path: Path) -> bool:
        if not path.exists() or not path.is_file():
            return False
        path.unlink()
        return True

    @staticmethod
    def _append_cleanup_metadata(source, cleanup_report: dict[str, Any]) -> None:
        metadata = dict(source.metadata_json or {})
        history = list(metadata.get("storage_cleanup_history") or [])
        history.append(cleanup_report)
        metadata["storage_cleanup_history"] = history
        metadata["storage_cleanup"] = cleanup_report
        source.metadata_json = metadata
        flag_modified(source, "metadata_json")
