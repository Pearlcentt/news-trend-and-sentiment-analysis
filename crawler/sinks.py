from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from .records import ArticleRecord
from .config import StorageSettings

LOG = logging.getLogger("crawler.sinks")


class Sink(ABC):
    @abstractmethod
    def write(self, records: Iterable[ArticleRecord]) -> None:  # pragma: no cover - interface
        ...


class JsonlSink(Sink):
    """Persist records to a JSONL file under the configured directory."""

    def __init__(self, output_dir: Path, filename_prefix: str):
        self.output_dir = output_dir
        self.filename_prefix = filename_prefix

    def _target_path(self) -> Path:
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        return self.output_dir / f"{self.filename_prefix}_{timestamp}.jsonl"

    def write(self, records: Iterable[ArticleRecord]) -> None:
        rows: List[ArticleRecord] = list(records)
        if not rows:
            LOG.info("No records to persist.")
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)
        target = self._target_path()
        with target.open("a", encoding="utf-8") as handle:
            for record in rows:
                handle.write(json.dumps(record.to_dict(), ensure_ascii=False))
                handle.write("\n")
        LOG.info("Wrote %d articles to %s", len(rows), target)


class StdoutSink(Sink):
    """Preview records on stdout/logs for quick demos."""

    def __init__(self, max_records: int = 5):
        self.max_records = max_records

    def write(self, records: Iterable[ArticleRecord]) -> None:
        for idx, record in enumerate(records):
            if idx >= self.max_records:
                LOG.info("Previewed %d records to stdout.", idx)
                return
            LOG.info("Record preview %d: %s", idx + 1, json.dumps(record.to_dict(), ensure_ascii=False))


def build_sink(settings: StorageSettings) -> Sink:
    mode = settings.mode.lower()
    if mode == "jsonl":
        return JsonlSink(settings.output_dir, settings.filename_prefix)
    if mode == "stdout":
        return StdoutSink(settings.stdout_preview)
    raise ValueError(f"Unsupported storage mode: {settings.mode}")
