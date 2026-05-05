# -*- coding: utf-8 -*-
"""
Utilitários de performance: cache TTL em memória e pool de conexões HTTP.

Usado por todos os módulos para evitar requisições redundantes e reutilizar
conexões TCP com as APIs externas (Gemini, Groq, Telegram, Bybit).
"""
import time
import threading
from typing import Any, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ---------------------------------------------------------------------------
# Cache TTL genérico (thread-safe)
# ---------------------------------------------------------------------------

class TTLCache:
    """
    Cache em memória com expiração por TTL (time-to-live).

    Thread-safe via RLock. Entradas expiradas são removidas de forma lazy
    (na próxima leitura) para não bloquear threads de background.
    """

    def __init__(self, default_ttl: float = 30.0, max_size: int = 512):
        self._store: dict = {}
        self._lock = threading.RLock()
        self.default_ttl = default_ttl
        self.max_size = max_size

    def get(self, key: str) -> Tuple[bool, Any]:
        """Retorna (hit, value). hit=False quando ausente ou expirado."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False, None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return False, None
            return True, value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Armazena value com expiração em ttl segundos."""
        ttl = ttl if ttl is not None else self.default_ttl
        expires_at = time.monotonic() + ttl
        with self._lock:
            # Evita crescimento ilimitado: descarta entradas mais antigas
            if len(self._store) >= self.max_size:
                self._evict()
            self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def _evict(self) -> None:
        """Remove entradas expiradas; se nenhuma, remove a mais antiga."""
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        if expired:
            for k in expired:
                del self._store[k]
        elif self._store:
            # Remove a entrada com menor TTL restante
            oldest = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest]


# ---------------------------------------------------------------------------
# Instâncias globais de cache (compartilhadas entre módulos)
# ---------------------------------------------------------------------------

# Cache para respostas de APIs de IA (Gemini / Groq) — TTL 60 s
ai_response_cache: TTLCache = TTLCache(default_ttl=60.0, max_size=256)

# Cache para preços de ticker — TTL 3 s (já existe no BybitClient, mas
# este é acessível de qualquer módulo sem instanciar o broker)
ticker_cache: TTLCache = TTLCache(default_ttl=3.0, max_size=128)

# Cache para dados de clientes do Supabase — TTL 30 s
client_cache: TTLCache = TTLCache(default_ttl=30.0, max_size=64)


# ---------------------------------------------------------------------------
# Pool de conexões HTTP reutilizável
# ---------------------------------------------------------------------------

def _build_http_session(
    pool_connections: int = 10,
    pool_maxsize: int = 20,
    max_retries: int = 2,
    backoff_factor: float = 0.5,
    timeout: float = 8.0,
) -> requests.Session:
    """
    Cria uma Session com connection pooling e retry automático.

    - pool_connections: número de pools de host distintos
    - pool_maxsize: conexões simultâneas por host
    - max_retries: tentativas em erros de rede (não em 4xx/5xx)
    - backoff_factor: espera entre retries = backoff * (2 ** (retry - 1))
    - timeout: timeout padrão (connect + read) em segundos
    """
    session = requests.Session()

    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        pool_connections=pool_connections,
        pool_maxsize=pool_maxsize,
        max_retries=retry_strategy,
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # Timeout padrão injetado em todas as requisições via event hook
    session._default_timeout = timeout  # type: ignore[attr-defined]

    # Monkey-patch leve: garante timeout mesmo quando o caller não passa
    _original_request = session.request

    def _request_with_timeout(method, url, **kwargs):
        kwargs.setdefault("timeout", session._default_timeout)  # type: ignore[attr-defined]
        return _original_request(method, url, **kwargs)

    session.request = _request_with_timeout  # type: ignore[method-assign]

    return session


# Sessão HTTP global — reutilizada por validator.py, main_web.py, etc.
http_session: requests.Session = _build_http_session()
