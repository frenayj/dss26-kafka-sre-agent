package com.dss26.aml.screening.rules

import scala.math.BigDecimal.RoundingMode

/**
 * EUR equivalents for thresholds that the regulation sets in euro. Rates are
 * the ECB euro foreign exchange reference rates (units of currency per EUR),
 * loaded daily from treasury's feed into the application config.
 */
final class FxRates(perEur: Map[String, BigDecimal]) {
  def toEur(amount: BigDecimal, currency: String): BigDecimal =
    if (currency == "EUR") amount
    else
      perEur.get(currency) match {
        case Some(rate) if rate > 0 => (amount / rate).setScale(2, RoundingMode.HALF_EVEN)
        // Unknown currency: screen at face value rather than skip the rule.
        case _ => amount
      }
}

object FxRates {
  val Identity = new FxRates(Map.empty)
}
