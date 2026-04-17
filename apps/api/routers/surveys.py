"""
Routes HTTP d'analyse des questionnaires de satisfaction.

Ce module expose les endpoints permettant :
- d'analyser une réponse ouverte unitaire
- de prévisualiser les questions pertinentes d'un formulaire
- de lancer un traitement complet de formulaire
- de suivre l'état d'un traitement asynchrone

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
    SurveyAnalyzeRequest,
    SurveyAnalyzeResponse,
    SurveyFormPreviewRequest,
    SurveyFormPreviewResponse,
    SurveyFormAnalyzeRequest,
    SurveyProcessingCreateResponse,
    SurveyProcessingStatusResponse,
    SurveyFeedbackRequest,
    SurveyFeedbackResponse,
)
from services.survey_analyzer import SurveyAnalyzerService
from services.survey_form_analyzer import SurveyFormAnalyzerService
from services.survey_question_selector import SurveyQuestionSelectorService
from services.survey_feedback import SurveyFeedbackService
from services.vllm_client import VLLMClient

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
RATE_LIMIT_RPM = settings.RATE_LIMIT_RPM

router = APIRouter(prefix="/surveys", tags=["surveys"])


@router.post(
    "/forms/preview",
    response_model=SurveyFormPreviewResponse,
    summary="Prévisualiser les questions pertinentes d'un formulaire",
    description="""
Extrait les questions distinctes d'un formulaire et propose, via le modèle,
quelles questions doivent être analysées ou ignorées pour la suite du traitement.

Cette route sert de pré-étape au traitement d'un formulaire complet.
Elle permet de sélectionner uniquement les questions réellement pertinentes
pour une analyse d'avis sur la formation.
""",
    responses={
        200: {"description": "Prévisualisation réalisée avec succès"},
        401: {"description": "Clé API invalide ou absente"},
        429: {"description": "Trop de requêtes"},
        502: {"description": "Erreur de communication avec le serveur d'inférence"},
    },
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def preview_form_questions(
    request: Request,
    payload: SurveyFormPreviewRequest,
    api_key: str | None = Security(api_key_header),
):
    _, _client_id = authenticate(api_key)

    selector = SurveyQuestionSelectorService(
        vllm_client=VLLMClient(),
    )

    distinct_questions = selector.extract_distinct_questions(
        [item.model_dump() for item in payload.items]
    )

    return await selector.select_questions_in_chunks(distinct_questions)


@router.post(
    "/analyze",
    response_model=SurveyAnalyzeResponse,
    summary="Analyser une réponse ouverte de questionnaire",
    description="""
Analyse une réponse ouverte issue d'un questionnaire de satisfaction.

Cette route permet de :
- normaliser la réponse,
- segmenter le texte en plusieurs points élémentaires,
- attribuer à chaque point un sentiment sur 5,
- attribuer à chaque point une catégorie métier,
- stocker le résultat en base de données.

### Fonctionnement
L'analyse se fait **réponse par réponse** et non questionnaire complet.
Le backend génère automatiquement un `response_id` unique.

### Échelle de sentiment
- 1 = très négatif
- 2 = négatif
- 3 = neutre
- 4 = positif
- 5 = très positif

### Cas particuliers
- réponse vide → `points = []`
- réponses du type `RAS`, `néant`, `/` → `points = []`
- réponse courte simple (`bien`, `ok`, etc.) → un point unique avec score simplifié

### Sécurité
Cette route est protégée par clé API (`X-API-Key`) et soumise au rate limiting.
""",
    responses={
        200: {"description": "Analyse réalisée avec succès"},
        401: {"description": "Clé API invalide ou absente"},
        429: {"description": "Trop de requêtes"},
        502: {"description": "Erreur de communication avec le serveur d'inférence"},
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "cas_positif": {
                            "summary": "Réponse positive multi-points",
                            "value": {
                                "survey_id": "formation_word_mars_2026",
                                "question_id": "q_appreciation",
                                "question_text": "Ce que vous avez particulièrement apprécié :",
                                "response_text": "Petit groupe, tout le monde peut prendre la parole. Changement d'intervenant stimulant.",
                                "metadata": {
                                    "formation": "Word avancé",
                                    "client": "Entreprise X"
                                }
                            }
                        },
                        "cas_mixte": {
                            "summary": "Réponse mixte",
                            "value": {
                                "survey_id": "formation_excel",
                                "question_id": "q_amelioration",
                                "question_text": "Les points d'amélioration :",
                                "response_text": "Salle trop froide, café mauvais, mais formateur très clair.",
                                "metadata": {}
                            }
                        },
                        "cas_ras": {
                            "summary": "Réponse vide métier",
                            "value": {
                                "survey_id": "formation_test",
                                "question_id": "q1",
                                "question_text": "Ce que vous avez particulièrement apprécié :",
                                "response_text": "RAS",
                                "metadata": {}
                            }
                        }
                    }
                }
            }
        }
    },
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def analyze_survey(
    request: Request,
    payload: SurveyAnalyzeRequest,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
):
    _, client_id = authenticate(api_key)
    req_id = getattr(request.state, "request_id", None)

    service = SurveyAnalyzerService(
        vllm_client=VLLMClient(),
        db=db,
    )

    return await service.analyze(
        survey_id=payload.survey_id,
        question_id=payload.question_id,
        question_text=payload.question_text,
        response_text=payload.response_text,
        metadata=payload.metadata,
        request_id=req_id,
        client_id=client_id,
    )


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
        raise HTTPException(status_code=400, detail=str(e))

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

Le feedback est enregistré dans la table `point_feedback` sans modifier destructivement
les données initiales issues du modèle.
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
    _, client_id = authenticate(api_key)

    service = SurveyFeedbackService(db=db)

    return service.save_feedback(
        response_id=payload.response_id,
        points=[point.model_dump() for point in payload.points],
        operator_id=payload.operator_id,
        metadata=payload.metadata,
    )