"""Servidor de desenvolvimento (HTTP + WebSocket).

Uso: python run.py   →  http://localhost:8000
"""
import os

from dotenv import load_dotenv

load_dotenv()

from rg import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    porta = int(os.environ.get("RG_PORTA", "8000"))
    app.run(host=os.environ.get("RG_HOST", "127.0.0.1"), port=porta, threaded=True, use_reloader=False)
