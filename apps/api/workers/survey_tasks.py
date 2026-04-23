from db.session import get_db
from services.survey_form_analyzer import SurveyFormAnalyzerService
from services.vllm_client import VLLMClient


def process_survey_job(processing_id: str) -> None:
    """
    Tâche RQ exécutée par le worker survey.
    Charge le job depuis PostgreSQL puis lance le traitement complet.
    """
    db_gen = get_db()
    db = next(db_gen)

    try:
        service = SurveyFormAnalyzerService(
            vllm_client=VLLMClient(),
            db=db,
        )

        import asyncio
        asyncio.run(
            service.run_client_processing_job(
                processing_id=processing_id,
                request_id=None,
            )
        )
    finally:
        db.close()