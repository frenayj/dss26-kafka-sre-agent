package com.dss26.aml.screening

import com.dss26.aml.screening.codec.AvroCodecs
import com.dss26.aml.screening.rules.{FxRates, Rules, RulesConfig}
import com.typesafe.config.{Config, ConfigFactory}
import io.confluent.kafka.streams.serdes.avro.GenericAvroSerde
import org.apache.avro.generic.GenericRecord
import org.apache.kafka.common.serialization.Serde
import org.apache.kafka.streams.errors.LogAndFailExceptionHandler
import org.apache.kafka.streams.{KafkaStreams, StreamsConfig}
import org.slf4j.LoggerFactory

import java.time.Duration
import java.util.Properties
import scala.jdk.CollectionConverters._

object Main {
  private val log = LoggerFactory.getLogger(getClass)

  def main(args: Array[String]): Unit = {
    val conf  = ConfigFactory.load().getConfig("aml-screening")
    val kafka = conf.getConfig("kafka")

    val props = new Properties()
    props.put(StreamsConfig.APPLICATION_ID_CONFIG, "aml-transaction-screening")
    props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, kafka.getString("bootstrap-servers"))
    props.put(StreamsConfig.PROCESSING_GUARANTEE_CONFIG, StreamsConfig.EXACTLY_ONCE_V2)
    props.put(StreamsConfig.REPLICATION_FACTOR_CONFIG, Int.box(3))
    props.put(StreamsConfig.NUM_STANDBY_REPLICAS_CONFIG, Int.box(1))
    // Every cleared transaction must be screened: a record we cannot read
    // stops the application and pages, it is never skipped.
    props.put(
      StreamsConfig.DEFAULT_DESERIALIZATION_EXCEPTION_HANDLER_CLASS_CONFIG,
      classOf[LogAndFailExceptionHandler]
    )
    props.put("schema.registry.url", kafka.getString("schema-registry-url"))
    kafka.getConfig("client").root().unwrapped().asScala.foreach { case (key, value) =>
      props.put(key, value)
    }

    implicit val avro: Serde[GenericRecord] = {
      val serde = new GenericAvroSerde()
      serde.configure(Map[String, AnyRef]("schema.registry.url" -> kafka.getString("schema-registry-url")).asJava, false)
      serde
    }

    val rules    = new Rules(rulesConfig(conf.getConfig("rules")), fxRates(conf.getConfig("fx")))
    val topology = ScreeningTopology.build(rules, new AvroCodecs)
    val streams  = new KafkaStreams(topology, props)

    sys.addShutdownHook(streams.close(Duration.ofSeconds(30)))
    log.info("Starting aml-transaction-screening\n{}", topology.describe())
    streams.start()
  }

  private def rulesConfig(c: Config): RulesConfig =
    RulesConfig(
      largeValueEur = BigDecimal(c.getString("large-value-eur")),
      roundAmountMinEur = BigDecimal(c.getString("round-amount-min-eur")),
      structuringBandLowEur = BigDecimal(c.getString("structuring.band-low-eur")),
      structuringBandHighEur = BigDecimal(c.getString("structuring.band-high-eur")),
      structuringCount24h = c.getLong("structuring.count-24h"),
      highRiskMerchants = c.getStringList("high-risk-merchants").asScala.toSet
    )

  private def fxRates(c: Config): FxRates =
    new FxRates(c.getConfig("per-eur").entrySet().asScala.map(e => e.getKey -> BigDecimal(e.getValue.unwrapped().toString)).toMap)
}
