"""Debug NDJSON logger for session 492ce3."""
from __future__ import annotations

import json
import os
import time

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_LOG_CANDIDATES = [
    os.path.join(_ROOT, 'debug-492ce3.log'),
    os.path.join(os.getcwd(), 'debug-492ce3.log'),
    'debug-492ce3.log',
]


def agent_dbg(hypothesis_id: str, location: str, message: str, data=None, run_id: str = 'pre-fix'):
    # #region agent log
    payload = {
        'sessionId': '492ce3',
        'runId': run_id,
        'hypothesisId': hypothesis_id,
        'location': location,
        'message': message,
        'data': data or {},
        'timestamp': int(time.time() * 1000),
    }
    line = json.dumps(payload, ensure_ascii=False)
    for path in _LOG_CANDIDATES:
        try:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
            break
        except Exception:
            continue
    try:
        print(f'DBG492ce3 {line}', flush=True)
    except Exception:
        pass
    # #endregion
