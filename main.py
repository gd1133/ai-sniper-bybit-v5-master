# -*- coding: utf-8 -*-
"""
Ponto de entrada principal para execução via linha de comando Python.
Compatível com Railway (nixpacks) sem dependências de Node/NPM.

Uso:
    python main.py
"""
import os
from main_web import app, start_runtime_services

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))

    start_runtime_services()

    print(f"✅ Sistema iniciado via Python na porta {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
