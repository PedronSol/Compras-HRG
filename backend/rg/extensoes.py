"""Extensões Flask compartilhadas."""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from flask.json.provider import DefaultJSONProvider
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sock import Sock

limiter = Limiter(key_func=get_remote_address, headers_enabled=True)
sock = Sock()


class ProvedorJSON(DefaultJSONProvider):
    """Serialização ISO-8601 para datas e numérica para Decimal."""

    ensure_ascii = False
    sort_keys = False

    @staticmethod
    def default(o):
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, date):
            return o.isoformat()
        if isinstance(o, time):
            return o.strftime("%H:%M")
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, UUID):
            return str(o)
        if isinstance(o, (set, frozenset)):
            return list(o)
        return DefaultJSONProvider.default(o)
