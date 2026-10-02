"""Analyst API: resolve cases and record cardholder-reported fraud."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext, StringSerializer
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from fraud_cases.config import CASE_OPENED_TOPIC, CASE_RESOLVED_TOPIC, Settings
from fraud_cases.store import CaseStore

settings = Settings.from_env()
registry = SchemaRegistryClient({"url": settings.schema_registry_url})
_serializer_conf = {"auto.register.schemas": False, "use.latest.version": True}
resolved_serializer = AvroSerializer(registry, open("schemas/fraud.case.resolved.v1.avsc").read(),
                                     conf=_serializer_conf)
opened_serializer = AvroSerializer(registry, open("schemas/fraud.case.opened.v1.avsc").read(),
                                   conf=_serializer_conf)
producer = Producer(settings.producer_config())
store = CaseStore(settings.database_url)
key = StringSerializer("utf_8")

app = FastAPI(title="fraud-case-management")


class Resolution(BaseModel):
    outcome: Literal["CONFIRMED_FRAUD", "FALSE_POSITIVE", "INCONCLUSIVE", "REFERRED_LAW_ENFORCEMENT"]
    actions_taken: list[str] = Field(default_factory=list)
    loss_amount: Decimal = Decimal("0")
    currency: str = Field(min_length=3, max_length=3)


class CardholderReport(BaseModel):
    customer_id: str
    card_token: str
    priority: Literal["P1", "P2", "P3", "P4"] = "P2"


@app.post("/cases/{case_id}/resolution")
def resolve(case_id: str, body: Resolution) -> dict:
    case = store.resolve_case(case_id, outcome=body.outcome, actions=body.actions_taken,
                              loss_amount=body.loss_amount, currency=body.currency)
    if case is None:
        raise HTTPException(status_code=409, detail="case not found or already resolved")
    producer.produce(CASE_RESOLVED_TOPIC, key=key(case_id), value=resolved_serializer({
        "case_id": case_id,
        "outcome": case["outcome"],
        "actions_taken": case["actions_taken"],
        "loss_amount": float(case["loss_amount"]),
        "currency": case["currency"],
        "resolved_at": case["resolved_at"],
    }, SerializationContext(CASE_RESOLVED_TOPIC, MessageField.VALUE)))
    producer.flush(10)
    return {"case_id": case_id, "status": "RESOLVED"}


@app.post("/cases", status_code=201)
def report(body: CardholderReport) -> dict:
    case = store.open_case(customer_id=body.customer_id, card_token=body.card_token,
                           trigger="CARDHOLDER_REPORT", priority=body.priority, triggering_auth_id=None)
    producer.produce(CASE_OPENED_TOPIC, key=key(case["case_id"]), value=opened_serializer({
        "case_id": case["case_id"],
        "customer_id": case["customer_id"],
        "card_token": case["card_token"],
        "trigger": "CARDHOLDER_REPORT",
        "triggering_auth_id": None,
        "priority": case["priority"],
        "opened_at": case["opened_at"],
    }, SerializationContext(CASE_OPENED_TOPIC, MessageField.VALUE)))
    producer.flush(10)
    return {"case_id": case["case_id"]}
