from redis import Redis
from rq import Worker
from core.logging import setup_logging
from core.config import settings


def main() -> None:
    setup_logging()
    redis_conn = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
    )

    worker = Worker(
        queues=[settings.RQ_SURVEY_QUEUE],
        connection=redis_conn,
    )
    worker.work()


if __name__ == "__main__":
    main()