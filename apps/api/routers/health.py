"""
Endpoint de healthcheck.

Utilisé pour :
- vérifier que l'API est opérationnelle
- monitoring (Docker, Kubernetes, load balancer)
- tests automatisés
"""

from fastapi import APIRouter

router = APIRouter(tags=["system"])

@router.get("/health")
def health():
    return {"status": "ok"}