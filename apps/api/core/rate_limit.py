from slowapi import Limiter
from slowapi.util import get_remote_address
from core.config import RATE_LIMIT_RPM

limiter = Limiter(key_func=get_remote_address, default_limits=[f"{RATE_LIMIT_RPM}/minute"])