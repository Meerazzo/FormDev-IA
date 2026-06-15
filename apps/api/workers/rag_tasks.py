import logging

from db.session import get_db
from services.rag.indexing.indexing_service import RagIndexingService
from services.rag.ingestion.ingest_service import RagIngestService
from services.rag.jobs.job_repository import RagJobRepository

logger = logging.getLogger(__name__)



def process_rag_ingest_job(source_id: str, job_id: str) -> None:
    """
    Tâche RQ d'ingestion complète RAG.

    Elle réalise :
    - parsing fichier/URL
    - chunking
    - écriture du .chunks.json
    - embeddings
    - indexation Qdrant
    """
    logger.info("Starting RAG ingest job_id=%s source_id=%s", job_id, source_id)

    db_gen = get_db()
    db = next(db_gen)

    try:
        job_repository = RagJobRepository(db)
        job_repository.mark_running(job_id)

        service = RagIngestService(db)
        response = service.ingest_source_and_index(source_id)

        job_repository.mark_succeeded(
            job_id,
            processed_sources=1,
            failed_sources=0,
            metadata={
                "chunks_indexed": response.chunks_indexed,
                "qdrant_collection": response.qdrant_collection,
                "final_source_status": response.status,
            },
        )

        logger.info(
            "RAG ingest job completed job_id=%s source_id=%s chunks=%s",
            job_id,
            source_id,
            response.chunks_indexed,
        )

    except Exception as exc:
        logger.exception("RAG ingest job failed job_id=%s source_id=%s", job_id, source_id)

        try:
            RagJobRepository(db).mark_failed(
                job_id,
                error_message=str(exc),
                processed_sources=0,
                failed_sources=1,
            )
        except Exception:
            logger.exception("Unable to mark RAG ingest job as failed job_id=%s", job_id)

        raise

    finally:
        db.close()


def process_rag_index_job(source_id: str, job_id: str) -> None:
    """
    Tâche RQ d'indexation RAG.
    """
    logger.info("Starting RAG index job_id=%s source_id=%s", job_id, source_id)

    db_gen = get_db()
    db = next(db_gen)

    try:
        job_repository = RagJobRepository(db)
        job_repository.mark_running(job_id)

        service = RagIndexingService(db)
        response = service.index_source(source_id)

        job_repository.mark_succeeded(
            job_id,
            processed_sources=1,
            failed_sources=0,
            metadata={
                "chunks_indexed": response.chunks_indexed,
                "qdrant_collection": response.qdrant_collection,
            },
        )

        logger.info(
            "RAG index job completed job_id=%s source_id=%s chunks=%s",
            job_id,
            source_id,
            response.chunks_indexed,
        )

    except Exception as exc:
        logger.exception("RAG index job failed job_id=%s source_id=%s", job_id, source_id)

        try:
            RagJobRepository(db).mark_failed(
                job_id,
                error_message=str(exc),
                processed_sources=0,
                failed_sources=1,
            )
        except Exception:
            logger.exception("Unable to mark RAG index job as failed job_id=%s", job_id)

        raise

    finally:
        db.close()


def process_rag_reindex_job(source_id: str, job_id: str) -> None:
    """
    Tâche RQ de réindexation RAG.
    """
    logger.info("Starting RAG reindex job_id=%s source_id=%s", job_id, source_id)

    db_gen = get_db()
    db = next(db_gen)

    try:
        job_repository = RagJobRepository(db)
        job_repository.mark_running(job_id)

        service = RagIndexingService(db)
        response = service.reindex_source(source_id)

        job_repository.mark_succeeded(
            job_id,
            processed_sources=1,
            failed_sources=0,
            metadata={
                "chunks_indexed": response.chunks_indexed,
                "qdrant_collection": response.qdrant_collection,
            },
        )

        logger.info(
            "RAG reindex job completed job_id=%s source_id=%s chunks=%s",
            job_id,
            source_id,
            response.chunks_indexed,
        )

    except Exception as exc:
        logger.exception("RAG reindex job failed job_id=%s source_id=%s", job_id, source_id)

        try:
            RagJobRepository(db).mark_failed(
                job_id,
                error_message=str(exc),
                processed_sources=0,
                failed_sources=1,
            )
        except Exception:
            logger.exception("Unable to mark RAG reindex job as failed job_id=%s", job_id)

        raise

    finally:
        db.close()


def process_rag_resync_job(
    client_id: str,
    corpus_id: str,
    job_id: str,
    include_pending: bool,
    include_error: bool,
) -> None:
    """
    Tâche RQ de resynchronisation d'un corpus RAG.
    """
    logger.info(
        "Starting RAG resync job_id=%s client_id=%s corpus_id=%s",
        job_id,
        client_id,
        corpus_id,
    )

    db_gen = get_db()
    db = next(db_gen)

    try:
        job_repository = RagJobRepository(db)
        job_repository.mark_running(job_id)

        service = RagIndexingService(db)
        response = service.resync_corpus(
            client_id=client_id,
            corpus_id=corpus_id,
            include_pending=include_pending,
            include_error=include_error,
        )

        result_payload = [
            result.model_dump()
            for result in response.results
        ]

        job_repository.mark_succeeded(
            job_id,
            processed_sources=response.indexed_sources + response.failed_sources,
            failed_sources=response.failed_sources,
            metadata={
                "total_sources": response.total_sources,
                "indexed_sources": response.indexed_sources,
                "failed_sources": response.failed_sources,
                "results": result_payload,
            },
        )

        logger.info(
            "RAG resync job completed job_id=%s client_id=%s corpus_id=%s indexed=%s failed=%s",
            job_id,
            client_id,
            corpus_id,
            response.indexed_sources,
            response.failed_sources,
        )

    except Exception as exc:
        logger.exception(
            "RAG resync job failed job_id=%s client_id=%s corpus_id=%s",
            job_id,
            client_id,
            corpus_id,
        )

        try:
            RagJobRepository(db).mark_failed(
                job_id,
                error_message=str(exc),
            )
        except Exception:
            logger.exception("Unable to mark RAG resync job as failed job_id=%s", job_id)

        raise

    finally:
        db.close()
