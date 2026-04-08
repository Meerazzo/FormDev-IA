"""
Routes HTTP d'analyse des questionnaires de satisfaction.

Ce module expose les endpoints permettant d'analyser des réponses ouvertes
issues de questionnaires de satisfaction :
- segmentation en points
- classification par sentiment
- catégorisation métier

Les endpoints sont protégés par clé API et soumis au rate limiting.
"""

from fastapi import APIRouter, Depends, Request, Security, HTTPException
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
    SurveyFormAnalyzeResponse,
)
from services.survey_form_analyzer import SurveyFormAnalyzerService
from services.survey_question_selector import SurveyQuestionSelectorService
from services.survey_analyzer import SurveyAnalyzerService
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

    return await selector.select_questions(distinct_questions)

@router.post(
    "/analyze",
    response_model=SurveyAnalyzeResponse,
    summary="Analyser une réponse ouverte de questionnaire",
    description="""
Analyse une réponse ouverte issue d'un questionnaire de satisfaction.

Cette route permet de :
- normaliser la réponse,
- segmenter le texte en plusieurs points élémentaires,
- attribuer à chaque point un sentiment,
- attribuer à chaque point une catégorie métier,
- stocker le résultat en base de données.

### Fonctionnement
L'analyse se fait **réponse par réponse** et non questionnaire complet.
Le backend génère automatiquement un `response_id` unique.

### Cas particuliers
- réponse vide → `points = []`
- réponses du type `RAS`, `néant`, `/` → `points = []`
- réponse courte simple (`bien`, `ok`, etc.) → un point unique avec classification simple
- en cas d'ambiguïté, le système préfère `unknown` ou `autre` plutôt qu'une mauvaise classification

### Sécurité
Cette route est protégée par clé API (`X-API-Key`) et soumise au rate limiting.
""",
    responses={
        200: {
            "description": "Analyse réalisée avec succès",
        },
        401: {
            "description": "Clé API invalide ou absente",
        },
        429: {
            "description": "Trop de requêtes",
        },
        502: {
            "description": "Erreur de communication avec le serveur d'inférence",
        },
    },
    openapi_extra={  # 👈 AJOUT ICI
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
    """
    Analyse une réponse ouverte de questionnaire et retourne une version structurée.
    """
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
    response_model=SurveyFormAnalyzeResponse,
    summary="Analyser un formulaire complet de satisfaction",
    description="""
Analyse un formulaire complet contenant plusieurs couples question/réponse.

Étapes :
- extraction des questions distinctes,
- sélection automatique des questions pertinentes,
- stockage de toutes les réponses,
- analyse uniquement des réponses associées aux questions retenues.

Les réponses ignorées sont également stockées en base avec une indication
de décision dans les métadonnées.
""",
    responses={
        200: {"description": "Analyse du formulaire réalisée avec succès"},
        401: {"description": "Clé API invalide ou absente"},
        429: {"description": "Trop de requêtes"},
        502: {"description": "Erreur de communication avec le serveur d'inférence"},
    },
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def analyze_form(
    request: Request,
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
        return await service.analyze_form(
            survey_id=payload.survey_id,
            items=[item.model_dump() for item in payload.items],
            metadata=payload.metadata,
            request_id=req_id,
            client_id=client_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))