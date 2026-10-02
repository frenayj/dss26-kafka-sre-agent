"""Keep the suite hermetic: no local env file, no trace export.

``agent.config`` loads the repo's env file at import time; a developer's live
credentials or dry-run switches must not change what the tests see, so the
loader is disabled before any ``agent`` module is imported.
"""

from __future__ import annotations

import os

import dotenv

dotenv.load_dotenv = lambda *args, **kwargs: False
os.environ["OTEL_SDK_DISABLED"] = "true"
