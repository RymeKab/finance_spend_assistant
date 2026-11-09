"""
The audit log: one line of JSON per question, appended to backend/logs/audit.jsonl.

Why this exists
---------------
Policy §8.2 asks that anything transforming financial data keeps "a traceable
lineage from source to report". For every question this log records:

  * who and when (request ID, timestamp; user identity would be added with SSO),
  * the question and the final answer, status and warnings,
  * the exact prompt version and model,
  * every tool call with its parameters and outcome,
  * the data snapshot fingerprint (which version of the source files was used),
  * token usage (for cost tracking).

The API key is never written here.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLog:
    def __init__(self, directory: Path, filename: str = "audit.jsonl"):
        self.path = directory / filename
        self._lock = threading.Lock()  # requests can run in parallel; keep lines intact

    def write(self, record: dict[str, Any]) -> None:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
        line = json.dumps(entry, default=str, ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
