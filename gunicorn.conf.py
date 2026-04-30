"""
Gunicorn configuration for AI Sniper.

Background services (sniper loop, SL/TP monitor) must run inside the
worker process so they share the same `central_state` that the Flask
routes read.  Using a `post_fork` hook guarantees they are started
after the worker has been forked from the master.
"""

import os

# ---------------------------------------------------------------------------
# Server socket
# ---------------------------------------------------------------------------
bind = f"0.0.0.0:{os.getenv('PORT', '8080')}"

# ---------------------------------------------------------------------------
# Worker model
# ---------------------------------------------------------------------------
# gthread allows background threads to coexist with the gunicorn worker
# without blocking request handling.
worker_class = "gthread"
workers = 1
threads = 4

# Generous timeout so heavy market-scan cycles do not kill the worker.
timeout = 120
graceful_timeout = 30

# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

def post_fork(server, worker):
    """Start background services inside the worker process."""
    try:
        from main_web import start_runtime_services
        start_runtime_services()
    except Exception as exc:
        import logging
        logging.getLogger("gunicorn.error").error(
            "post_fork: start_runtime_services falhou: %s", exc, exc_info=True
        )
