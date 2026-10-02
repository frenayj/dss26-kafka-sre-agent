package com.dss26.payments.analytics;

import org.apache.kafka.streams.StreamsConfig;
import org.junit.jupiter.api.Test;

import java.util.Map;
import java.util.Properties;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StreamsConfigFactoryTest {

    private static final Map<String, String> ENV = Map.of(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092",
            "SCHEMA_REGISTRY_URL", "http://localhost:8081",
            "KAFKA_SECURITY_PROTOCOL", "PLAINTEXT");

    @Test
    void applicationIdIsTheConsumerGroup() {
        Properties p = StreamsConfigFactory.fromEnv(ENV);
        assertEquals("merchant-analytics-stream", p.get(StreamsConfig.APPLICATION_ID_CONFIG));
    }

    @Test
    void runsExactlyOnce() {
        Properties p = StreamsConfigFactory.fromEnv(ENV);
        assertEquals(StreamsConfig.EXACTLY_ONCE_V2, p.get(StreamsConfig.PROCESSING_GUARANTEE_CONFIG));
    }

    @Test
    void failsFastWithoutBootstrapServers() {
        assertThrows(IllegalStateException.class,
                () -> StreamsConfigFactory.fromEnv(Map.of("SCHEMA_REGISTRY_URL", "http://localhost:8081")));
    }
}
