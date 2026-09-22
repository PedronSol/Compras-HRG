"""Cabeçalhos de segurança HTTP (CSP, HSTS, anti-clickjacking, cache)."""
from __future__ import annotations

from flask import current_app, request

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "connect-src 'self'",
    "worker-src 'self'",
    "manifest-src 'self'",
    "frame-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


def aplicar_cabecalhos(resposta):
    h = resposta.headers
    h.setdefault("Content-Security-Policy", CSP)
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=(), payment=(), usb=()")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    h.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    if current_app.config["SESSION_COOKIE_SECURE"]:
        h.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    if request.path.startswith("/api/"):
        h["Cache-Control"] = "no-store"
        h["Pragma"] = "no-cache"
    elif request.path.endswith((".png", ".svg", ".ico", ".woff2")):
        h["Cache-Control"] = "public, max-age=604800"
    else:
        # HTML, JS, CSS e manifest: sempre revalidados (ETag) para refletir novas versões imediatamente
        h["Cache-Control"] = "no-cache"
    return resposta
