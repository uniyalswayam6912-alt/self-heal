import json
import os

from kafka import KafkaProducer


KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "kafka:9092",
)

kafka_producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda value: json.dumps(value).encode("utf-8"),
)


def publish_job_event(event_type: str, job_id: int):
    event = {
        "event_type": event_type,
        "job_id": job_id,
    }

    kafka_producer.send(
        "job-events",
        value=event,
    )


def enqueue_job(job_id: int, retry_count: int = 0):
    message = {
        "job_id": job_id,
        "retry_count": retry_count,
    }

    kafka_producer.send(
        "background-jobs",
        value=message,
    )

    kafka_producer.flush()