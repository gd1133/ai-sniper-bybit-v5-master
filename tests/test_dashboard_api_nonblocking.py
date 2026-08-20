# -*- coding: utf-8 -*-
"""Smoke tests leves — validam contrato sem cold-start pesado do Gunicorn."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_WEB = (ROOT / 'main_web.py').read_text(encoding='utf-8')


def test_boot_workers_are_daemon_threads():
    assert 'threading.Thread(' in MAIN_WEB
    assert "name='sniper-worker'" in MAIN_WEB or 'sniper_worker_loop' in MAIN_WEB
    assert '_boot_background_workers' in MAIN_WEB
    assert 'daemon=True' in MAIN_WEB
    # Boot não bloqueia o bind: workers sobem em thread
    assert 'runtime-boot' in MAIN_WEB


def test_api_routes_exist():
    for route in ('/api/status', '/api/investidores', '/api/posicoes', '/api/health'):
        assert route in MAIN_WEB


def test_status_uses_background_refresh():
    assert '_schedule_status_refresh' in MAIN_WEB
    assert '_refresh_status_payload_background' in MAIN_WEB


def test_cors_and_bind_config():
    assert 'origins' in MAIN_WEB.lower() or "origins': '*'" in MAIN_WEB or 'origins": "*"' in MAIN_WEB
    assert "0.0.0.0" in MAIN_WEB
    assert 'PORT' in MAIN_WEB


def test_procfile_has_threads():
    proc = (ROOT / 'Procfile').read_text(encoding='utf-8')
    assert '0.0.0.0:$PORT' in proc
    assert '--threads' in proc
