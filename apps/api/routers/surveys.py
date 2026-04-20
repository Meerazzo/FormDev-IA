"""
Routes HTTP d'analyse des questionnaires de satisfaction.

API publique retenue :
- POST /surveys/forms/analyze
- GET  /surveys/processings/{processing_id}
- POST /surveys/feedback

Les endpoints sont protégés par clé API et soumis au rate limiting.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from core.config import settings
from core.rate_limit import limiter
from core.security import authenticate
from db.session import get_db
from schemas.surveys import (
    SurveyFeedbackRequest,
    SurveyFeedbackResponse,
    SurveyFormAnalyzeRequest,
    SurveyProcessingCreateResponse,
    SurveyProcessingStatusResponse,
)
from services.survey_feedback import SurveyFeedbackService
from services.survey_form_analyzer import SurveyFormAnalyzerService
from services.vllm_client import VLLMClient

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
RATE_LIMIT_RPM = settings.RATE_LIMIT_RPM

router = APIRouter(prefix="/surveys", tags=["surveys"])


@router.post(
    "/forms/analyze",
    response_model=SurveyProcessingCreateResponse,
    summary="Lancer l'analyse complète d'un formulaire",
    description="""
Crée un traitement d'analyse de formulaire et retourne immédiatement un identifiant de traitement.

Le traitement complet est ensuite exécuté en arrière-plan.

### Étapes du traitement
- extraction des questions distinctes
- sélection automatique des questions pertinentes
- stockage de toutes les réponses
- analyse uniquement des réponses retenues
- enregistrement du résultat final

### Suivi
Le client peut ensuite interroger :
`GET /surveys/processings/{processing_id}`
pour suivre l'état du traitement et récupérer le résultat final.
""",
    responses={
        200: {"description": "Traitement créé avec succès"},
        400: {"description": "Requête invalide"},
        401: {"description": "Clé API invalide ou absente"},
        429: {"description": "Trop de requêtes"},
        502: {"description": "Erreur de communication avec le serveur d'inférence"},
    },
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def analyze_form(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: SurveyFormAnalyzeRequest,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
):
    _, client_id = authenticate(api_key)
    req_id = getattr(request.state, "request_id", None)

    service = SurveyFormAnalyzerService(
        vllm_client=VLLMClient(),
        db=db,
    )

    try:
        job = service.create_processing_job(
            survey_id=payload.survey_id,
            items=[item.model_dump() for item in payload.items],
            metadata=payload.metadata,
            client_id=client_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    background_tasks.add_task(
        _run_form_processing_task,
        processing_id=job.processing_id,
        request_id=req_id,
    )

    return {
        "processing_id": job.processing_id,
        "status": job.status,
    }


@router.get(
    "/processings/{processing_id}",
    response_model=SurveyProcessingStatusResponse,
    summary="Consulter l'état d'un traitement",
    description="""
Retourne l'état d'un traitement d'analyse de formulaire.

Statuts possibles :
- `PENDING`
- `STARTED`
- `FINISHED`
- `FAILED`

Si le traitement est terminé, le résultat complet est renvoyé.
""",
    responses={
        200: {"description": "Statut du traitement récupéré avec succès"},
        401: {"description": "Clé API invalide ou absente"},
        404: {"description": "Traitement introuvable"},
    },
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def get_processing_status(
    request: Request,
    processing_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
):
    _, client_id = authenticate(api_key)

    service = SurveyFormAnalyzerService(
        vllm_client=VLLMClient(),
        db=db,
    )

    job = service.get_processing_job(processing_id=processing_id, client_id=client_id)
    if not job:
        raise HTTPException(status_code=404, detail="Processing not found")

    return {
        "processing_id": job.processing_id,
        "status": job.status,
        "survey_id": job.survey_id,
        "error_message": job.error_message,
        "result": job.result_json if job.status == "FINISHED" else None,
    }


@router.post(
    "/feedback",
    response_model=SurveyFeedbackResponse,
    summary="Enregistrer un feedback opérateur sur les points analysés",
    description="""
Enregistre la validation ou la correction opérateur d'une réponse analysée.

Cette route permet de :
- valider un point tel quel
- corriger le texte d'un point
- corriger son sentiment
- corriger sa catégorie
- supprimer métierement un point
- ajouter un point manuel

Le feedback est enregistré dans la table `point_feedback`.
Les données finales corrigées sont maintenues dans `validated_response_points`.
La mémoire vectorielle Qdrant est mise à jour en best effort.
""",
    responses={
        200: {"description": "Feedback enregistré avec succès"},
        401: {"description": "Clé API invalide ou absente"},
        429: {"description": "Trop de requêtes"},
        502: {"description": "Erreur interne"},
    },
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def save_survey_feedback(
    request: Request,
    payload: SurveyFeedbackRequest,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
):
    authenticate(api_key)

    service = SurveyFeedbackService(db=db)

    return service.save_feedback(
        response_id=payload.response_id,
        points=[point.model_dump() for point in payload.points],
        operator_id=payload.operator_id,
        metadata=payload.metadata,
    )


async def _run_form_processing_task(
    processing_id: str,
    request_id: str | None = None,
) -> None:
    """
    Lance le traitement complet d'un formulaire en arrière-plan.
    Cette fonction recrée sa propre session DB.
    """
    db_gen = get_db()
    db = next(db_gen)
    try:
        service = SurveyFormAnalyzerService(
            vllm_client=VLLMClient(),
            db=db,
        )
        await service.run_processing_job(
            processing_id=processing_id,
            request_id=request_id,
        )
    finally:
        db.close()