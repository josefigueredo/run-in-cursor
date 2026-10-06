#!/usr/bin/env python3
"""Entry point: puts the skill folder on sys.path and runs the ric CLI."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ric.cli import main  # noqa: E402

sys.exit(main())
