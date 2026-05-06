import os
import sys
from main_web import app, start_runtime_services

# Get PORT from environment, default to 3000 for local development
PORT = int(os.environ.get('PORT', 3000))

# Validate port is in valid range
if not (1 <= PORT <= 65535):
    print(f"ERROR: Invalid PORT value: {PORT}", file=sys.stderr)
    sys.exit(1)

start_runtime_services()

if __name__ == '__main__':
    print(f"[WSGI] Starting Flask app on port {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False)
