from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from core.config import settings


class RagLocalArtifactCleanup:
    """
    Nettoyage prudent des fichiers locaux RAG.

    Mode sûr par défaut :
    - après indexation : supprimer le fichier original uploadé ;
    - conserver le .chunks.json pour garder reindex/resync possibles ;
    - à la suppression d'une source : supprimer original + .chunks.json.
    """

    def __init__(self, db) -> None:
        self.db = db
        self.storage_root = Path(settings.RAG_STORAGE_DIR)

    def after_index_success(self, source) -> dict[str, Any]:
        deleted_paths: list[str] = []
        skipped: list[dict[str, str]] = []

        if source.source_type == "url":
            skipped.append({"artifact": "source_file", "reason": "url_source"})
        else:
            source_file = self._safe_path(source.source_uri)
            if source_file is None:
                skipped.append({"artifact": "source_file", "reason": "missing_or_unsafe_path"})
            elif self._remove_file(source_file):
                deleted_paths.append(str(source_file))
            else:
                skipped.append({"artifact": "source_file", "reason": "already_absent"})

        report = {
            "trigger": "index_success",
            "policy": "delete_original_keep_chunks",
            "deleted_paths": deleted_paths,
            "skipped": skipped,
            "chunks_file_kept": True,
            "reindex_available": True,
            "cleaned_at": datetime.now(timezone.utc).isoformat(),
        }
        self._store_report(source, report)
        self.db.commit()
        self.db.refresh(source)
        return report

    def on_source_delete(self, source) -> dict[str, Any]:
        deleted_paths: list[str] = []
        skipped: list[dict[str, str]] = []

        if source.source_type != "url":
            source_file = self._safe_path(source.source_uri)
            if source_file is not None and self._remove_file(source_file):
                deleted_paths.append(str(source_file))
            else:
                skipped.append({"artifact": "source_file", "reason": "absent_or_unsafe"})

        chunks_file = self._chunks_path(source)
        if chunks_file is not None and self._remove_file(chunks_file):
            deleted_paths.append(str(chunks_file))
        else:
            skipped.append({"artifact": "chunks_file", "reason": "absent_or_unsafe"})

        report = {
            "trigger": "source_delete",
            "policy": "delete_all_local_artifacts_on_source_delete",
            "deleted_paths": deleted_paths,
            "skipped": skipped,
            "reindex_available": False,
            "cleaned_at": datetime.now(timezone.utc).isoformat(),
        }
        self._store_report(source, report)
        self.db.commit()
        self.db.refresh(source)
        return report

    def _chunks_path(self, source) -> Path | None:
        metadata = source.metadata_json or {}
        return self._safe_path(metadata.get("chunks_path"))

    def _safe_path(self, raw_path: str | None) -> Path | None:
        if not raw_path:
            return None
        path = Path(raw_path)
        if not path.is_absolute():
            return None
        try:
            resolved_root = self.storage_root.resolve(strict=False)
            resolved_path = path.resolve(strict=False)
        except Exception:
            return None
        if resolved_path == resolved_root:
            return None
        if resolved_root not in resolved_path.parents:
            return None
        return resolved_path

    @staticmethod
    def _remove_file(path: Path) -> bool:
        if not path.exists() or not path.is_file():
            return False
        path.unlink()
        return True

    @staticmethod
    def _store_report(source, report: dict[str, Any]) -> None:
        metadata = dict(source.metadata_json or {})
        history = list(metadata.get("storage_cleanup_history") or [])
        history.append(report)
        metadata["storage_cleanup_history"] = history
        metadata["storage_cleanup"] = report
        source.metadata_json = metadata
        flag_modified(source, "metadata_json")
