"""
Configuration du rate limiting de l'API.

Le rate limiter protège le serveur d'inférence contre :
- les abus
- les erreurs de boucle côté client
- la surcharge GPU

La limite est définie par la variable RATE_LIMIT_RPM.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from core.config import settings

RATE_LIMIT_RPM = settings.RATE_LIMIT_RPM # Limiteur global appliqué aux routes FastAPI

limiter = Limiter(key_func=get_remote_address, default_limits=[f"{RATE_LIMIT_RPM}/minute"])