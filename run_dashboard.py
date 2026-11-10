"""Launch the Claude Trading Dashboard server."""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from src.api.server import run_server

PORT = 8000

if __name__ == "__main__":
    httpd = run_server(port=PORT)
    print(f"Claude Trading Dashboard running at http://localhost:{PORT}/")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        httpd.server_close()
