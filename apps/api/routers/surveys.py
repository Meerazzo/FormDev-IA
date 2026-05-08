"""
Routes HTTP d'analyse des questionnaires de satisfaction.

API publique retenue :
- POST /surveys/analyze
- GET  /surveys/processings/{processing_id}
- POST /surveys/feedback

Les endpoints sont protégés par clé API et soumis au rate limiting.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Security, Body
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from core.config import settings
from core.rate_limit import limiter
from core.security import authenticate
from db.session import get_db
from schemas.surveys import (
    SurveyFeedbackListResponse,
    SurveyFeedbackRequest,
    SurveyFeedbackResponse,
    SurveyProcessingCreateResponse,
    SurveyProcessingStatusResponse,
)
from schemas.survey_client import ClientQuestionnaireAnalyzeRequest
from services.survey_feedback import SurveyFeedbackService
from services.survey_form_analyzer import SurveyFormAnalyzerService
from services.vllm_client import VLLMClient
from services.survey_queue import enqueue_survey_job
from services.survey_example_memory import SurveyExampleMemoryService

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
RATE_LIMIT_RPM = settings.RATE_LIMIT_RPM

router = APIRouter(prefix="/surveys", tags=["surveys"])


@router.post(
    "/analyze",
    response_model=SurveyProcessingCreateResponse,
    summary="Lancer l'analyse asynchrone d'un ou plusieurs questionnaires",
    description="""
Crée un traitement d'analyse asynchrone à partir du format questionnaire client.

### Format attendu
La requête doit utiliser le format hiérarchique métier :
- `questionnaires[]`
- `availableCategories`
- `questions[]`
- `answers[]` ou `answer` selon le type de question

### Types de questions pris en charge
- `OPEN`
- `SINGLE_CHOICE`
- `MULTIPLE_CHOICE`
- `RATING`
- `CHECKBOX`

### Fonctionnement
L'API :
- enregistre immédiatement un traitement
- retourne un `processing_id`
- exécute ensuite l'analyse en arrière-plan

### Suivi
Le client peut ensuite interroger :
`GET /surveys/processings/{processing_id}`

pour suivre l'état du traitement et récupérer le résultat final une fois terminé.
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
async def analyze_surveys(
    request: Request,
    payload: ClientQuestionnaireAnalyzeRequest = Body(
        ...,
        openapi_examples={
            "questionnaire_complet": {
                "summary": "Questionnaire complet avec plusieurs types de questions",
                "description": "Exemple complet contenant une question ouverte, une question à choix simple, une question à choix multiples, une note et une case à cocher.",
                "value": {
                    "questionnaires": [
                        {
                            "id": 1,
                            "availableCategories": [
                                {"id": 10, "label": "Satisfaction", "metadata": {}},
                                {"id": 11, "label": "Amélioration", "metadata": {}}
                            ],
                            "questions": [
                                {
                                    "id": 100,
                                    "label": "Avez-vous des suggestions ?",
                                    "type": "OPEN",
                                    "answers": [
                                        {
                                            "id": 2000,
                                            "type": "FREE_TEXT",
                                            "label": "Plus de choix de produits et un service client plus réactif serait apprécié.",
                                            "metadata": {}
                                        }
                                    ],
                                    "metadata": {}
                                },
                                {
                                    "id": 101,
                                    "label": "Comment évaluez-vous notre service ?",
                                    "type": "SINGLE_CHOICE",
                                    "availableAnswers": [
                                        {"id": 1000, "label": "Excellent", "metadata": {}},
                                        {"id": 1001, "label": "Bon", "metadata": {}},
                                        {"id": 1002, "label": "Moyen", "metadata": {}},
                                        {"id": 1003, "label": "Mauvais", "metadata": {}}
                                    ],
                                    "answer": {
                                        "id": 2001,
                                        "type": "CHOICE",
                                        "idAvailableAnswer": 1001,
                                        "metadata": {}
                                    },
                                    "metadata": {}
                                },
                                {
                                    "id": 102,
                                    "label": "Quels aspects appréciez-vous ?",
                                    "type": "MULTIPLE_CHOICE",
                                    "availableAnswers": [
                                        {"id": 1010, "label": "Accueil", "metadata": {}},
                                        {"id": 1011, "label": "Prix", "metadata": {}},
                                        {"id": 1012, "label": "Qualité", "metadata": {}}
                                    ],
                                    "answers": [
                                        {"id": 2002, "type": "CHOICE", "idAvailableAnswer": 1010, "metadata": {}},
                                        {"id": 2003, "type": "CHOICE", "idAvailableAnswer": 1012, "metadata": {}}
                                    ],
                                    "metadata": {}
                                },
                                {
                                    "id": 103,
                                    "label": "Notez notre site",
                                    "type": "RATING",
                                    "maxValue": 5,
                                    "value": 4,
                                    "metadata": {}
                                },
                                {
                                    "id": 104,
                                    "label": "Souhaitez-vous recevoir la newsletter ?",
                                    "type": "CHECKBOX",
                                    "checked": True,
                                    "metadata": {}
                                }
                            ],
                            "metadata": {
                                "client_id": "client_demo",
                                "formation": "Questionnaire complet nominal"
                            }
                        }
                    ]
                },
            },
            "questionnaire_partiel": {
                "summary": "Questionnaire partiel avec réponses absentes",
                "description": "Exemple utile pour vérifier le comportement lorsque certaines réponses sont absentes ou nulles.",
                "value": {
                    "questionnaires": [
                        {
                            "id": 3,
                            "availableCategories": [
                                {"id": 10, "label": "Satisfaction", "metadata": {}},
                                {"id": 11, "label": "Amélioration", "metadata": {}}
                            ],
                            "questions": [
                                {
                                    "id": 300,
                                    "label": "Avez-vous des suggestions ?",
                                    "type": "OPEN",
                                    "answers": [],
                                    "metadata": {}
                                },
                                {
                                    "id": 301,
                                    "label": "Comment évaluez-vous notre service ?",
                                    "type": "SINGLE_CHOICE",
                                    "availableAnswers": [
                                        {"id": 3000, "label": "Excellent", "metadata": {}},
                                        {"id": 3001, "label": "Bon", "metadata": {}}
                                    ],
                                    "answer": None,
                                    "metadata": {}
                                }
                            ],
                            "metadata": {
                                "client_id": "client_demo",
                                "formation": "Questionnaire partiel"
                            }
                        }
                    ]
                },
            },
        },
    ),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
): 
    authenticate(api_key)

    client_ids = {
        questionnaire.get_client_id()
        for questionnaire in payload.questionnaires
        if questionnaire.get_client_id()
    }

    if not client_ids:
        raise HTTPException(
            status_code=422,
            detail="metadata.client_id is required on each questionnaire",
        )

    if len(client_ids) > 1:
        raise HTTPException(
            status_code=422,
            detail="All questionnaires in the same request must use the same metadata.client_id",
        )

    client_id = next(iter(client_ids))
    req_id = getattr(request.state, "request_id", None)

    service = SurveyFormAnalyzerService(
        vllm_client=VLLMClient(),
        db=db,
    )

    try:
        job = service.create_client_processing_job(
            payload=payload,
            client_id=client_id,
            request_id=req_id,
        )

        try:
            rq_job_id = enqueue_survey_job(job.processing_id, request_id=req_id)
        except Exception as e:
            service.mark_processing_job_enqueue_failed(
                processing_id=job.processing_id,
                error_message=f"Queue enqueue failed: {str(e)}",
            )
            return {
                "processing_id": job.processing_id,
                "status": "RECEIVED",
            }

        job = service.mark_processing_job_queued(
            processing_id=job.processing_id,
            rq_job_id=rq_job_id,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


    return {
        "processing_id": job.processing_id,
        "status": job.status,
    }


@router.get(
    "/processings/{processing_id}",
    response_model=SurveyProcessingStatusResponse,
    summary="Consulter l'état et le résultat d'un traitement d'analyse",
    description="""
Retourne l'état d'un traitement d'analyse précédemment créé via `POST /surveys/analyze`.

### Statuts possibles
- `RECEIVED` : traitement reçu par FastAPI et enregistré en base
- `QUEUED` : traitement envoyé dans Redis/RQ
- `STARTED` : traitement pris par un worker
- `FINISHED` : traitement terminé avec succès
- `FAILED` : traitement terminé en erreur

### Résultat
Quand le statut est `FINISHED`, le champ `result` contient la sortie finale d'analyse au format client enrichi avec les segments.
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
    client_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
):
    authenticate(api_key)

    service = SurveyFormAnalyzerService(
        vllm_client=VLLMClient(),
        db=db,
    )

    job = service.get_processing_job(
        processing_id=processing_id,
        client_id=client_id,
    )
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
    summary="Enregistrer un feedback opérateur sur une analyse",
    description="""
Enregistre une validation ou une correction opérateur sur les points issus d'une analyse.

### Actions possibles
- `update` : corriger un point existant
- `delete` : désactiver un point existant
- `add` : ajouter un nouveau point manuel

### Effets
L'API :
- enregistre le feedback dans `point_feedback`
- met à jour les données finales dans `validated_response_points`
- met à jour la mémoire Qdrant en best effort pour les futurs cas similaires
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
    client_id: str,
    payload: SurveyFeedbackRequest = Body(
        ...,
        openapi_examples={
            "correction_point_existant": {
                "summary": "Correction d'un point existant",
                "description": "Exemple de correction d'un point produit par le modèle.",
                "value": {
                    "response_id": "83744cf8-878e-4a3d-b0ed-e523aac431ef",
                    "operator_id": "op_test_001",
                    "metadata": {
                        "review_source": "manual_test"
                    },
                    "points": [
                        {
                            "point_id": "83744cf8-878e-4a3d-b0ed-e523aac431ef_pt_1",
                            "is_correct": False,
                            "corrected_text": "Service jugé satisfaisant",
                            "corrected_sentiment": 4,
                            "corrected_category": "Satisfaction",
                            "action": "update"
                        }
                    ]
                },
            },
            "ajout_point_manuel": {
                "summary": "Ajout manuel d'un point",
                "description": "Exemple d'ajout d'un nouveau point qui n'avait pas été détecté automatiquement.",
                "value": {
                    "response_id": "83744cf8-878e-4a3d-b0ed-e523aac431ef",
                    "operator_id": "op_test_001",
                    "metadata": {
                        "review_source": "manual_test"
                    },
                    "points": [
                        {
                            "point_id": None,
                            "is_correct": False,
                            "corrected_text": "Navigation à améliorer",
                            "corrected_sentiment": 2,
                            "corrected_category": "Amélioration",
                            "action": "add"
                        }
                    ]
                },
            },
            "suppression_point": {
                "summary": "Suppression d'un point",
                "description": "Exemple de désactivation d'un point jugé non pertinent.",
                "value": {
                    "response_id": "83744cf8-878e-4a3d-b0ed-e523aac431ef",
                    "operator_id": "op_test_001",
                    "metadata": {
                        "review_source": "manual_test"
                    },
                    "points": [
                        {
                            "point_id": "83744cf8-878e-4a3d-b0ed-e523aac431ef_pt_1",
                            "is_correct": False,
                            "corrected_text": None,
                            "corrected_sentiment": None,
                            "corrected_category": None,
                            "action": "delete"
                        }
                    ]
                },
            },
        },
    ),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
):
    authenticate(api_key)

    service = SurveyFeedbackService(db=db)
    try:
        return service.save_feedback(
            response_id=payload.response_id,
            points=[point.model_dump() for point in payload.points],
            operator_id=payload.operator_id,
            metadata=payload.metadata,
            client_id=client_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get(
    "/feedback",
    response_model=SurveyFeedbackListResponse,
    summary="Lister les corrections/mémoires de feedback d'un client",
    description="""
Retourne les exemples actifs stockés dans Qdrant pour un client.

Cette route lit la mémoire vectorielle utilisée pour l'apprentissage dynamique.
Paramètres :
- client_id : identifiant client à lire dans Qdrant
- category : filtre optionnel par catégorie finale
- question_type : filtre optionnel par type de question
- limit : nombre maximum de résultats à retourner. Si absent, aucune limite n'est appliquée.
""",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def list_survey_feedback(
    request: Request,
    client_id: str,
    questionnaire_id: str | None = None,
    limit: int | None = None,
    question_type: str | None = None,
    category: str | None = None,
    api_key: str | None = Security(api_key_header),
):
    authenticate(api_key)

    memory = SurveyExampleMemoryService(
        qdrant_url=settings.QDRANT_URL,
        collection_name=settings.QDRANT_COLLECTION,
        embedding_model=settings.QDRANT_EMBEDDING_MODEL,
        vector_size=settings.QDRANT_VECTOR_SIZE,
    )

    try:
        items = memory.list_feedback_examples(
            client_id=client_id,
            limit=limit,
            question_type=question_type,
            category=category,
            questionnaire_id=questionnaire_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to read feedback memory: {str(e)}",
        ) from e

    return {
        "client_id": client_id,
        "count": len(items),
        "items": items,
    }