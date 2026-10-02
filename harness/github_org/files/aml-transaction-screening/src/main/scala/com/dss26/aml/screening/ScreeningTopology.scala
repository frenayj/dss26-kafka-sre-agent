package com.dss26.aml.screening

import com.dss26.aml.screening.codec.AvroCodecs
import com.dss26.aml.screening.model._
import com.dss26.aml.screening.rules.Rules
import org.apache.avro.generic.GenericRecord
import org.apache.kafka.common.serialization.Serde
import org.apache.kafka.streams.Topology
import org.apache.kafka.streams.kstream.{JoinWindows, TimeWindows}
import org.apache.kafka.streams.scala.ImplicitConversions._
import org.apache.kafka.streams.scala.StreamsBuilder
import org.apache.kafka.streams.scala.kstream.{KStream, Materialized}
import org.apache.kafka.streams.scala.serialization.Serdes._

import java.time.Duration

object ScreeningTopology {
  val ClearingReceived = "cards.clearing.received.v1"
  val ClearingMatched  = "cards.clearing.matched.v1"
  val CardIssued       = "cards.card.issued.v1"
  val Screened         = "aml.transaction.screened.v1"
  val Alerts           = "aml.alert.raised.v1"

  def build(rules: Rules, codecs: AvroCodecs)(implicit avro: Serde[GenericRecord]): Topology = {
    val builder = new StreamsBuilder()

    val received   = builder.stream[String, GenericRecord](ClearingReceived)
    val matched    = builder.stream[String, GenericRecord](ClearingMatched)
    val cardOwners = builder.globalTable[String, GenericRecord](CardIssued)

    // Both clearing topics are keyed by clearing_id. A match normally follows
    // its presentment within seconds; exceptions can take days.
    val cleared: KStream[String, ClearedTransaction] = received
      .join(matched)(
        (r: GenericRecord, m: GenericRecord) => codecs.cleared(r, m),
        JoinWindows.ofTimeDifferenceAndGrace(Duration.ofDays(3), Duration.ofHours(6))
      )
      .leftJoin(cardOwners)(
        (_, tx) => tx.cardToken,
        (tx, card) => tx.copy(customerId = Option(card).map(_.get("customer_id").toString))
      )
      .selectKey((_, tx) => tx.customerId.getOrElse(tx.cardToken))

    val screened = cleared.mapValues(tx => rules.screen(tx))
    screened.mapValues(r => codecs.screened(r)).to(Screened)
    screened
      .filter((_, r) => r.outcome == Outcome.Alerted)
      .mapValues(r => codecs.alert(r))
      .to(Alerts)

    // Structuring: several cleared transactions just under the threshold for
    // one customer inside 24 hours.
    cleared
      .filter((_, tx) => rules.inStructuringBand(tx))
      .mapValues(tx => tx.clearingId)
      .groupByKey
      .windowedBy(TimeWindows.ofSizeAndGrace(Duration.ofHours(24), Duration.ofHours(1)))
      .count()(Materialized.as("structuring-band-24h"))
      .toStream
      .filter((_, count) => rules.isStructuring(count))
      .map((window, count) => (window.key(), codecs.structuringAlert(window.key(), count)))
      .to(Alerts)

    builder.build()
  }
}
