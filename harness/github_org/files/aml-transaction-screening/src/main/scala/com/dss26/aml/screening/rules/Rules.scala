package com.dss26.aml.screening.rules

import com.dss26.aml.screening.model._

import java.time.Instant
import java.util.UUID

final case class RulesConfig(
    largeValueEur: BigDecimal,
    roundAmountMinEur: BigDecimal,
    structuringBandLowEur: BigDecimal,
    structuringBandHighEur: BigDecimal,
    structuringCount24h: Long,
    highRiskMerchants: Set[String]
)

/**
 * Transaction-level AML rules. Typologies and their regulatory references are
 * in docs/typologies.md; every rule name here appears there.
 */
final class Rules(config: RulesConfig, fx: FxRates) {

  def screen(tx: ClearedTransaction, now: Instant = Instant.now()): ScreeningResult = {
    val eur = fx.toEur(tx.amount, tx.currency)
    val hits = List(
      Option.when(eur >= config.largeValueEur)(RuleHit("LARGE_VALUE", Some("LARGE_VALUE"))),
      Option.when(eur >= config.roundAmountMinEur && isRound(eur))(RuleHit("ROUND_AMOUNT", None)),
      Option.when(config.highRiskMerchants.contains(tx.merchantId))(
        RuleHit("HIGH_RISK_MERCHANT", Some("HIGH_RISK_COUNTERPARTY"))
      )
    ).flatten

    val outcome =
      if (hits.exists(_.typology.isDefined)) Outcome.Alerted
      else if (hits.nonEmpty) Outcome.Flagged
      else Outcome.Clear

    ScreeningResult(UUID.randomUUID().toString, tx, outcome, hits, now)
  }

  /** Just under the large-value threshold: the band structuring hides in. */
  def inStructuringBand(tx: ClearedTransaction): Boolean = {
    val eur = fx.toEur(tx.amount, tx.currency)
    eur >= config.structuringBandLowEur && eur < config.structuringBandHighEur
  }

  def isStructuring(countIn24h: Long): Boolean = countIn24h >= config.structuringCount24h

  private def isRound(eur: BigDecimal): Boolean = eur.remainder(BigDecimal(1000)) == 0
}
