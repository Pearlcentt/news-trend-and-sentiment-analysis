from __future__ import annotations

import json
import logging
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

from confluent_kafka import KafkaError, Producer
from fastavro import parse_schema, schemaless_writer

from schema_registry import SchemaRegistry

LOG = logging.getLogger("news_crawler.avro_producer")


class AvroKafkaProducer:
    """Minimal Avro producer compatible with Confluent wire format."""

    MAGIC_BYTE = b"\x00"

    def __init__(
        self,
        producer: Producer,
        schema_registry: SchemaRegistry,
        schema_path: Path,
        subject: str,
    ):
        self.producer = producer
        self.schema_path = schema_path

        if not self.schema_path.exists():
            raise FileNotFoundError(f"Avro schema file not found: {self.schema_path}")

        self.schema_dict = json.loads(self.schema_path.read_text(encoding="utf-8"))
        self.schema = parse_schema(self.schema_dict)
        self.schema_id = schema_registry.ensure_schema(subject, self.schema_dict)

    def encode(self, record: Dict[str, Any]) -> bytes:
        buffer = BytesIO()
        buffer.write(self.MAGIC_BYTE)
        buffer.write(self.schema_id.to_bytes(4, byteorder="big"))
        schemaless_writer(buffer, self.schema, record)
        return buffer.getvalue()

    def send(self, topic: str, key: str, record: Dict[str, Any]) -> None:
        payload = self.encode(record)
        self.producer.produce(
            topic=topic,
            key=key.encode("utf-8"),
            value=payload,
            on_delivery=self._delivery_cb,
        )

    @staticmethod
    def _delivery_cb(err: Optional[KafkaError], msg) -> None:
        if err is not None:
            LOG.error("Delivery failed for key=%s: %s", msg.key(), err)
        else:
            LOG.debug(
                "Delivered key=%s partition=%s offset=%s",
                msg.key(),
                msg.partition(),
                msg.offset(),
            )
