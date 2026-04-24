import asyncio
import logging

from db.session import get_db
from services.survey_form_analyzer import SurveyFormAnalyzerService
from services.vllm_client import VLLMClient

logger = logging.getLogger(__name__)


def process_survey_job(processing_id: str) -> None:
    """
    Tâche RQ exécutée par le worker survey.
    Charge le job depuis PostgreSQL puis lance le traitement complet.
    """
    logger.info("Starting survey job processing_id=%s", processing_id)

    db_gen = get_db()
    db = next(db_gen)

    try:
        service = SurveyFormAnalyzerService(
            vllm_client=VLLMClient(),
            db=db,
        )

        asyncio.run(
            service.run_client_processing_job(
                processing_id=processing_id,
                request_id=None,
            )
        )

        logger.info("Survey job completed processing_id=%s", processing_id)

    except Exception:
        logger.exception("Survey job failed processing_id=%s", processing_id)
        raise
    finally:
        db.close()