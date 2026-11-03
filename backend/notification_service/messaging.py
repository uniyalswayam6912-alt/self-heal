import json
import os

from kafka import KafkaConsumer, KafkaProducer


KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "kafka:9092",
)

kafka_producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda value: json.dumps(value).encode("utf-8"),
)

kafka_consumer = KafkaConsumer(
    "notification-events",
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_deserializer=lambda value: json.loads(value.decode("utf-8")),
    group_id="notification-service",
    auto_offset_reset="earliest",
    enable_auto_commit=False,
)

def publish_notification_event(event: dict):
    kafka_producer.send(
        "notification-events",
        value=event,
    )
    kafka_producer.flush()

def consume_notification_events():
    for message in kafka_consumer:
        yield message

def publish_dead_letter_event(event: dict):
    kafka_producer.send(
        "notification-dead-letter",
        value=event,
    )
    kafka_producer.flush()

