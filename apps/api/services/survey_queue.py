from redis import Redis
from rq import Queue

from core.config import settings
from workers.survey_tasks import process_survey_job


def get_redis_connection() -> Redis:
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
    )


def get_survey_queue() -> Queue:
    return Queue(
        name=settings.RQ_SURVEY_QUEUE,
        connection=get_redis_connection(),
        default_timeout=settings.RQ_DEFAULT_TIMEOUT,
    )


def enqueue_survey_job(processing_id: str) -> str:
    """
    Enfile un traitement d'analyse survey dans la queue RQ.
    Retourne l'identifiant du job RQ.
    """
    queue = get_survey_queue()
    job = queue.enqueue(
        process_survey_job,
        processing_id,
        result_ttl=settings.RQ_RESULT_TTL,
        failure_ttl=settings.RQ_FAILURE_TTL,
    )
    return job.id