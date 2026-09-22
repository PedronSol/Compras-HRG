"""Ponto de entrada WSGI (produção).

Linux:  gunicorn -w 2 -k gthread --threads 64 -b 0.0.0.0:8000 wsgi:app
        (WebSockets exigem worker gthread; cada conexão ativa ocupa uma thread)
"""
from dotenv import load_dotenv

load_dotenv()

from rg import create_app  # noqa: E402

app = create_app()
