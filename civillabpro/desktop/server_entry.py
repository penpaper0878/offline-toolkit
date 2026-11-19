"""Entry point of the bundled server (PyInstaller): the backend's one-process serve, unchanged."""

import sys

from app.serve import main

if __name__ == "__main__":
    sys.exit(main())
