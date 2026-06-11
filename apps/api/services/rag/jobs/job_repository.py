from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from db.models.rag_ingestion_job import RagIngestionJob
from schemas.rag import RagJobStatusResponse


class RagJobRepository:
    """
    Repository des jobs RAG persistés en PostgreSQL.

    RQ exécute techniquement les jobs, mais PostgreSQL conserve
    l'état métier durable : pending/running/succeeded/failed.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_job(
        self,
        *,
        client_id: str,
        corpus_id: str,
        job_type: str,
        source_id: str | None = None,
        total_sources: int = 1,
        metadata: dict | None = None,
    ) -> RagIngestionJob:
        job = RagIngestionJob(
            job_id=f"rag_job_{uuid4().hex}",
            client_id=client_id,
            corpus_id=corpus_id,
            source_id=source_id,
            job_type=job_type,
            status="pending",
            total_sources=total_sources,
            processed_sources=0,
            failed_sources=0,
            metadata_json=metadata or {},
        )

        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        return job

    def get_by_job_id(self, job_id: str) -> RagIngestionJob | None:
        return (
            self.db.query(RagIngestionJob)
            .filter(RagIngestionJob.job_id == job_id)
            .first()
        )

    def attach_rq_job_id(self, *, job_id: str, rq_job_id: str) -> RagIngestionJob:
        job = self._require_job(job_id)
        metadata = dict(job.metadata_json or {})
        metadata["rq_job_id"] = rq_job_id
        job.metadata_json = metadata

        self.db.commit()
        self.db.refresh(job)

        return job

    def mark_running(self, job_id: str) -> RagIngestionJob:
        job = self._require_job(job_id)
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(job)

        return job

    def mark_succeeded(
        self,
        job_id: str,
        *,
        processed_sources: int | None = None,
        failed_sources: int | None = None,
        metadata: dict | None = None,
    ) -> RagIngestionJob:
        job = self._require_job(job_id)
        job.status = "succeeded"
        job.finished_at = datetime.now(timezone.utc)
        job.error_message = None

        if processed_sources is not None:
            job.processed_sources = processed_sources

        if failed_sources is not None:
            job.failed_sources = failed_sources

        if metadata is not None:
            current_metadata = dict(job.metadata_json or {})
            current_metadata.update(metadata)
            job.metadata_json = current_metadata

        self.db.commit()
        self.db.refresh(job)

        return job

    def mark_failed(
        self,
        job_id: str,
        *,
        error_message: str,
        processed_sources: int | None = None,
        failed_sources: int | None = None,
        metadata: dict | None = None,
    ) -> RagIngestionJob:
        job = self._require_job(job_id)
        job.status = "failed"
        job.finished_at = datetime.now(timezone.utc)
        job.error_message = error_message

        if processed_sources is not None:
            job.processed_sources = processed_sources

        if failed_sources is not None:
            job.failed_sources = failed_sources

        if metadata is not None:
            current_metadata = dict(job.metadata_json or {})
            current_metadata.update(metadata)
            job.metadata_json = current_metadata

        self.db.commit()
        self.db.refresh(job)

        return job

    def to_response(self, job: RagIngestionJob) -> RagJobStatusResponse:
        metadata = dict(job.metadata_json or {})

        return RagJobStatusResponse(
            job_id=job.job_id,
            rq_job_id=metadata.get("rq_job_id"),
            client_id=job.client_id,
            corpus_id=job.corpus_id,
            source_id=job.source_id,
            job_type=job.job_type,
            status=job.status,
            total_sources=job.total_sources,
            processed_sources=job.processed_sources,
            failed_sources=job.failed_sources,
            metadata=metadata,
            error_message=job.error_message,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )

    def _require_job(self, job_id: str) -> RagIngestionJob:
        job = self.get_by_job_id(job_id)

        if job is None:
            raise ValueError(f"Job RAG introuvable: {job_id}")

        return job
