# -*- coding: utf-8 -*-
"""
Ponto de entrada principal para execução via linha de comando Python.
Compatível com Railway (nixpacks) sem dependências de Node/NPM.

Uso:
    python main.py
"""
import os
from gunicorn.app.base import BaseApplication
from main_web import app, start_runtime_services


class _StandaloneApplication(BaseApplication):
    def __init__(self, wsgi_app, options=None):
        self.options = options or {}
        self.application = wsgi_app
        super().__init__()

    def load_config(self):
        for key, value in self.options.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))

    start_runtime_services()

    print(f"✅ Sistema iniciado via Python na porta {port}")
    _StandaloneApplication(app, {
        "bind": f"0.0.0.0:{port}",
        "workers": 2,
        "timeout": 120,
    }).run()
