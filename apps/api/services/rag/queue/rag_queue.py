from redis import Redis
from rq import Queue

from core.config import settings
from workers.rag_tasks import (
    process_rag_ingest_job,
    process_rag_index_job,
    process_rag_reindex_job,
    process_rag_resync_job,
)


def get_redis_connection() -> Redis:
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
    )


def get_rag_queue() -> Queue:
    return Queue(
        name=settings.RQ_RAG_QUEUE,
        connection=get_redis_connection(),
        default_timeout=settings.RQ_DEFAULT_TIMEOUT,
    )



def enqueue_rag_ingest_job(
    *,
    source_id: str,
    job_id: str,
) -> str:
    queue = get_rag_queue()

    job = queue.enqueue(
        process_rag_ingest_job,
        source_id,
        job_id,
        result_ttl=settings.RQ_RESULT_TTL,
        failure_ttl=settings.RQ_FAILURE_TTL,
    )

    return job.id


def enqueue_rag_index_job(
    *,
    source_id: str,
    job_id: str,
) -> str:
    queue = get_rag_queue()

    job = queue.enqueue(
        process_rag_index_job,
        source_id,
        job_id,
        result_ttl=settings.RQ_RESULT_TTL,
        failure_ttl=settings.RQ_FAILURE_TTL,
    )

    return job.id


def enqueue_rag_reindex_job(
    *,
    source_id: str,
    job_id: str,
) -> str:
    queue = get_rag_queue()

    job = queue.enqueue(
        process_rag_reindex_job,
        source_id,
        job_id,
        result_ttl=settings.RQ_RESULT_TTL,
        failure_ttl=settings.RQ_FAILURE_TTL,
    )

    return job.id


def enqueue_rag_resync_job(
    *,
    client_id: str,
    corpus_id: str,
    job_id: str,
    include_pending: bool,
    include_error: bool,
) -> str:
    queue = get_rag_queue()

    job = queue.enqueue(
        process_rag_resync_job,
        client_id,
        corpus_id,
        job_id,
        include_pending,
        include_error,
        result_ttl=settings.RQ_RESULT_TTL,
        failure_ttl=settings.RQ_FAILURE_TTL,
    )

    return job.id
