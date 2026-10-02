package com.dss26.aml.screening.codec

import com.dss26.aml.screening.model._
import org.apache.avro.Schema
import org.apache.avro.generic.{GenericData, GenericRecord}

import java.time.Instant
import java.util.UUID
import scala.jdk.CollectionConverters._

/** GenericRecord in and out; output schemas are the registered subjects' copies in src/main/avro. */
final class AvroCodecs {
  private def load(name: String): Schema =
    new Schema.Parser().parse(getClass.getResourceAsStream(s"/avro/$name.avsc"))

  private val screenedSchema = load("aml.transaction.screened.v1")
  private val alertSchema    = load("aml.alert.raised.v1")

  def cleared(received: GenericRecord, matched: GenericRecord): ClearedTransaction =
    ClearedTransaction(
      clearingId = received.get("clearing_id").toString,
      authId = matched.get("auth_id").toString,
      cardToken = received.get("card_token").toString,
      merchantId = received.get("merchant_id").toString,
      amount = BigDecimal(received.get("amount").asInstanceOf[Double]),
      currency = received.get("currency").toString,
      customerId = None,
      clearedAt = Instant.ofEpochMilli(matched.get("matched_at").asInstanceOf[Long])
    )

  def screened(r: ScreeningResult): GenericRecord = {
    val rec = new GenericData.Record(screenedSchema)
    rec.put("screening_id", r.screeningId)
    rec.put("auth_id", r.tx.authId)
    rec.put("customer_id", r.customerId)
    rec.put("outcome", new GenericData.EnumSymbol(screenedSchema.getField("outcome").schema(), r.outcome.name))
    rec.put("rules_fired", r.rulesFired.asJava)
    rec.put("typology", r.typology.orNull)
    rec.put("screened_at", r.screenedAt.toEpochMilli)
    rec
  }

  def alert(r: ScreeningResult, severity: String = "MEDIUM"): GenericRecord = {
    val rec = new GenericData.Record(alertSchema)
    rec.put("alert_id", UUID.randomUUID().toString)
    rec.put("screening_id", r.screeningId)
    rec.put("customer_id", r.customerId)
    rec.put("typology", r.typology.getOrElse("UNSPECIFIED"))
    rec.put("severity", new GenericData.EnumSymbol(alertSchema.getField("severity").schema(), severity))
    rec.put("assigned_team", "fiu-card-monitoring")
    rec.put("raised_at", r.screenedAt.toEpochMilli)
    rec
  }

  /** Structuring is a pattern over a customer's day, not one transaction. */
  def structuringAlert(customerId: String, countIn24h: Long): GenericRecord = {
    val rec = new GenericData.Record(alertSchema)
    rec.put("alert_id", UUID.randomUUID().toString)
    rec.put("screening_id", s"window-24h-$customerId-$countIn24h")
    rec.put("customer_id", customerId)
    rec.put("typology", "STRUCTURING")
    rec.put("severity", new GenericData.EnumSymbol(alertSchema.getField("severity").schema(), "HIGH"))
    rec.put("assigned_team", "fiu-card-monitoring")
    rec.put("raised_at", Instant.now().toEpochMilli)
    rec
  }
}
