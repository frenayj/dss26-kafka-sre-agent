package com.dss26.payments.analytics;

import com.dss26.payments.CardAuthEvent;
import io.confluent.kafka.serializers.AbstractKafkaSchemaSerDeConfig;
import io.confluent.kafka.streams.serdes.avro.SpecificAvroSerde;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.errors.StreamsUncaughtExceptionHandler.StreamThreadExceptionResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.Properties;

public final class MerchantAnalyticsApp {

    private static final Logger log = LoggerFactory.getLogger(MerchantAnalyticsApp.class);

    private MerchantAnalyticsApp() {
    }

    public static void main(String[] args) throws Exception {
        Properties props = StreamsConfigFactory.fromEnv(System.getenv());

        Map<String, Object> serdeConfig = new HashMap<>();
        props.stringPropertyNames().forEach(name -> serdeConfig.put(name, props.getProperty(name)));
        serdeConfig.put(AbstractKafkaSchemaSerDeConfig.SCHEMA_REGISTRY_URL_CONFIG,
                props.getProperty(AbstractKafkaSchemaSerDeConfig.SCHEMA_REGISTRY_URL_CONFIG));

        SpecificAvroSerde<CardAuthEvent> authSerde = new SpecificAvroSerde<>();
        authSerde.configure(serdeConfig, false);
        SpecificAvroSerde<MerchantKpi> kpiSerde = new SpecificAvroSerde<>();
        kpiSerde.configure(serdeConfig, false);

        Topology topology = MerchantKpiTopology.build(authSerde, kpiSerde);
        log.info("Topology:\n{}", topology.describe());

        KafkaStreams streams = new KafkaStreams(topology, props);
        streams.setUncaughtExceptionHandler(e -> {
            log.error("Stream thread died, replacing it", e);
            return StreamThreadExceptionResponse.REPLACE_THREAD;
        });

        String appServer = props.getProperty(StreamsConfig.APPLICATION_SERVER_CONFIG);
        int port = Integer.parseInt(appServer.substring(appServer.lastIndexOf(':') + 1));
        KpiQueryServer queries = new KpiQueryServer(streams, appServer, port);

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            queries.stop();
            streams.close(Duration.ofSeconds(30));
        }, "shutdown"));

        streams.start();
        queries.start();
    }
}
