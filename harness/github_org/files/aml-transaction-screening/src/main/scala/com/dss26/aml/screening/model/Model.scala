package com.dss26.aml.screening.model

import java.time.Instant

sealed abstract class Outcome(val name: String)

object Outcome {
  case object Clear   extends Outcome("CLEAR")
  case object Flagged extends Outcome("FLAGGED")
  case object Alerted extends Outcome("ALERTED")
}

/** A presentment joined with its match (auth_id) and, once known, the card's customer. */
final case class ClearedTransaction(
    clearingId: String,
    authId: String,
    cardToken: String,
    merchantId: String,
    amount: BigDecimal,
    currency: String,
    customerId: Option[String],
    clearedAt: Instant
)

final case class RuleHit(rule: String, typology: Option[String])

final case class ScreeningResult(
    screeningId: String,
    tx: ClearedTransaction,
    outcome: Outcome,
    hits: List[RuleHit],
    screenedAt: Instant
) {
  def rulesFired: List[String]   = hits.map(_.rule)
  def typology: Option[String]   = hits.flatMap(_.typology).headOption
  def customerId: String         = tx.customerId.getOrElse(tx.cardToken)
}
