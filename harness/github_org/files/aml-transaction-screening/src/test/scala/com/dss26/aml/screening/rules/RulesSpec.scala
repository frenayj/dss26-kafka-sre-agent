package com.dss26.aml.screening.rules

import com.dss26.aml.screening.model._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

import java.time.Instant

class RulesSpec extends AnyFlatSpec with Matchers {

  private val config = RulesConfig(
    largeValueEur = BigDecimal(10000),
    roundAmountMinEur = BigDecimal(5000),
    structuringBandLowEur = BigDecimal(9000),
    structuringBandHighEur = BigDecimal(10000),
    structuringCount24h = 3,
    highRiskMerchants = Set("MRC-0099120")
  )
  private val rules = new Rules(config, new FxRates(Map("USD" -> BigDecimal("1.0812"))))

  private def tx(amount: BigDecimal, currency: String = "EUR", merchant: String = "MRC-0004410") =
    ClearedTransaction("clr-1", "auth-1", "tok_1f2e3d", merchant, amount, currency, Some("CUST-77120"),
      Instant.parse("2026-03-02T10:00:00Z"))

  "screen" should "clear an ordinary purchase" in {
    rules.screen(tx(BigDecimal("84.20"))).outcome shouldBe Outcome.Clear
  }

  it should "alert on a large value in EUR equivalent" in {
    val result = rules.screen(tx(BigDecimal("11000.00"), "USD"))
    result.outcome shouldBe Outcome.Alerted
    result.rulesFired should contain("LARGE_VALUE")
  }

  it should "only flag a round amount below the large-value threshold" in {
    val result = rules.screen(tx(BigDecimal("6000.00")))
    result.outcome shouldBe Outcome.Flagged
    result.typology shouldBe None
  }

  it should "alert on a high-risk merchant whatever the amount" in {
    rules.screen(tx(BigDecimal("12.00"), merchant = "MRC-0099120")).typology shouldBe Some("HIGH_RISK_COUNTERPARTY")
  }

  "structuring" should "use the band just under the threshold" in {
    rules.inStructuringBand(tx(BigDecimal("9500.00"))) shouldBe true
    rules.inStructuringBand(tx(BigDecimal("10000.00"))) shouldBe false
    rules.isStructuring(3) shouldBe true
    rules.isStructuring(2) shouldBe false
  }
}
