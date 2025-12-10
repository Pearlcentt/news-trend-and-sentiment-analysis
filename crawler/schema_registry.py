from __future__ import annotations

import json
import logging
from typing import Any, Dict

import requests

LOG = logging.getLogger("news_crawler.schema_registry")


class SchemaRegistry:
    """Lightweight client for Confluent Schema Registry."""

    def __init__(self, base_url: str, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _subject_url(self, subject: str) -> str:
        return f"{self.base_url}/subjects/{subject}/versions"

    def _schema_id_url(self, schema_id: int) -> str:
        return f"{self.base_url}/schemas/ids/{schema_id}"

    def ensure_schema(self, subject: str, schema_dict: Dict[str, Any]) -> int:
        """Register schema if needed and return its id."""
        payload = {"schema": json.dumps(schema_dict)}
        try:
            response = requests.post(
                self._subject_url(subject),
                headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
                data=json.dumps(payload),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Schema registry unreachable: {exc}") from exc

        if response.status_code in (200, 201):
            schema_id = response.json()["id"]
            LOG.debug("Registered schema subject=%s id=%s", subject, schema_id)
            return schema_id

        if response.status_code == 409:
            latest = requests.get(
                f"{self._subject_url(subject)}/latest", timeout=self.timeout
            )
            latest.raise_for_status()
            schema_id = latest.json()["id"]
            LOG.debug("Schema already registered subject=%s id=%s", subject, schema_id)
            return schema_id

        raise RuntimeError(
            f"Schema registration failed for subject {subject}: {response.text}"
        )

    def get_schema_by_id(self, schema_id: int) -> Dict[str, Any]:
        """Fetch schema content by id."""
        try:
            response = requests.get(self._schema_id_url(schema_id), timeout=self.timeout)
        except requests.RequestException as exc:
            raise RuntimeError(f"Schema registry unreachable while fetching id {schema_id}: {exc}") from exc

        response.raise_for_status()
        data = response.json()
        return json.loads(data["schema"])
