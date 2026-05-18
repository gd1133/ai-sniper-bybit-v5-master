import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import main_web


def test_is_rate_limit_error_detects_common_messages():
    assert main_web._is_rate_limit_error(Exception('Error code: 429 (Rate Limit)'))
    assert main_web._is_rate_limit_error(Exception('rate limit exceeded'))
    assert not main_web._is_rate_limit_error(Exception('timeout while connecting'))


def test_apply_ai_rate_limit_cooldown_sleeps_and_logs(monkeypatch, capsys):
    sleep_calls = []
    monkeypatch.setattr(main_web.time, 'sleep', lambda seconds: sleep_calls.append(seconds))

    handled = main_web._apply_ai_rate_limit_cooldown(Exception('429 Too Many Requests'))

    captured = capsys.readouterr()
    assert handled is True
    assert sleep_calls == [60]
    assert '⚠️ [AGUARDANDO COOLDOWN] Limite atingido. Pausando robô por 60 segundos antes de tentar novamente...' in captured.out


def test_apply_ai_rate_limit_cooldown_ignores_other_errors(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr(main_web.time, 'sleep', lambda seconds: sleep_calls.append(seconds))

    handled = main_web._apply_ai_rate_limit_cooldown(Exception('503 service unavailable'))

    assert handled is False
    assert sleep_calls == []
