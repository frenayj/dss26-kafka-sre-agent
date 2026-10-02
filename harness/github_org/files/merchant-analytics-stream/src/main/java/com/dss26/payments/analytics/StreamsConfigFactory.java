package com.dss26.payments.analytics;

import io.confluent.kafka.serializers.AbstractKafkaSchemaSerDeConfig;
import org.apache.kafka.clients.CommonClientConfigs;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.config.SaslConfigs;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.errors.LogAndContinueExceptionHandler;

import java.util.Map;
import java.util.Properties;

/** Builds the Streams configuration from the pod environment (see deploy/values-prod.yaml). */
public final class StreamsConfigFactory {

    public static final String APPLICATION_ID = "merchant-analytics-stream";

    private StreamsConfigFactory() {
    }

    public static Properties fromEnv(Map<String, String> env) {
        Properties p = new Properties();
        p.put(StreamsConfig.APPLICATION_ID_CONFIG, APPLICATION_ID);
        p.put(StreamsConfig.CLIENT_ID_CONFIG, APPLICATION_ID + "-" + env.getOrDefault("HOSTNAME", "local"));
        p.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, required(env, "KAFKA_BOOTSTRAP_SERVERS"));
        p.put(StreamsConfig.PROCESSING_GUARANTEE_CONFIG, StreamsConfig.EXACTLY_ONCE_V2);
        p.put(StreamsConfig.COMMIT_INTERVAL_MS_CONFIG, 1000);
        p.put(StreamsConfig.NUM_STREAM_THREADS_CONFIG, Integer.parseInt(env.getOrDefault("NUM_STREAM_THREADS", "2")));
        p.put(StreamsConfig.NUM_STANDBY_REPLICAS_CONFIG, 1);
        p.put(StreamsConfig.REPLICATION_FACTOR_CONFIG, 3);
        p.put(StreamsConfig.STATE_DIR_CONFIG, env.getOrDefault("STATE_DIR", "/var/lib/merchant-analytics-stream"));
        p.put(StreamsConfig.STATESTORE_CACHE_MAX_BYTES_CONFIG, 64L * 1024 * 1024);
        p.put(StreamsConfig.APPLICATION_SERVER_CONFIG, env.getOrDefault("APPLICATION_SERVER", "localhost:8080"));
        // A record we cannot read is logged and skipped: KPIs are statistics,
        // not a ledger, and must not stop for one bad payload.
        p.put(StreamsConfig.DEFAULT_DESERIALIZATION_EXCEPTION_HANDLER_CLASS_CONFIG,
                LogAndContinueExceptionHandler.class);
        p.put(StreamsConfig.consumerPrefix(ConsumerConfig.MAX_POLL_RECORDS_CONFIG), 1000);

        p.put(AbstractKafkaSchemaSerDeConfig.SCHEMA_REGISTRY_URL_CONFIG, required(env, "SCHEMA_REGISTRY_URL"));

        String protocol = env.getOrDefault("KAFKA_SECURITY_PROTOCOL", "SASL_SSL");
        p.put(CommonClientConfigs.SECURITY_PROTOCOL_CONFIG, protocol);
        if (protocol.startsWith("SASL")) {
            p.put(SaslConfigs.SASL_MECHANISM, "SCRAM-SHA-512");
            p.put(SaslConfigs.SASL_JAAS_CONFIG, String.format(
                    "org.apache.kafka.common.security.scram.ScramLoginModule required username=\"%s\" password=\"%s\";",
                    required(env, "KAFKA_USERNAME"), required(env, "KAFKA_PASSWORD")));
        }
        return p;
    }

    private static String required(Map<String, String> env, String name) {
        String value = env.get(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(name + " is not set");
        }
        return value;
    }
}
