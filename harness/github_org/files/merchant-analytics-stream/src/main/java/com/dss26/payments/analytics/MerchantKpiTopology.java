package com.dss26.payments.analytics;

import com.dss26.payments.CardAuthEvent;
import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KGroupedStream;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.Named;
import org.apache.kafka.streams.kstream.TimeWindows;
import org.apache.kafka.streams.state.WindowStore;

import java.time.Duration;

/**
 * cards.authorisation.requested.v1 -> re-key by merchant -> tumbling windows.
 *
 * Processor and store names are fixed with Named/Materialized: renaming one
 * changes the internal topic names and needs an application reset (see README).
 */
public final class MerchantKpiTopology {

    public static final String INPUT_TOPIC = "cards.authorisation.requested.v1";
    public static final String STORE_5M = "merchant-kpi-5m";
    public static final String STORE_1H = "merchant-kpi-1h";

    static final Duration GRACE = Duration.ofMinutes(2);
    static final Duration RETENTION = Duration.ofDays(8);

    private MerchantKpiTopology() {
    }

    public static Topology build(Serde<CardAuthEvent> authSerde, Serde<MerchantKpi> kpiSerde) {
        StreamsBuilder builder = new StreamsBuilder();

        KGroupedStream<String, CardAuthEvent> byMerchant = builder
                .stream(INPUT_TOPIC, Consumed.with(Serdes.String(), authSerde).withName("authorisations"))
                .filter((key, auth) -> auth != null && "prod".equals(auth.getTier()), Named.as("prod-tier-only"))
                .selectKey((key, auth) -> auth.getMerchantId(), Named.as("key-by-merchant"))
                .groupByKey(Grouped.with("by-merchant", Serdes.String(), authSerde));

        windowed(byMerchant, Duration.ofMinutes(5), STORE_5M, kpiSerde);
        windowed(byMerchant, Duration.ofHours(1), STORE_1H, kpiSerde);

        return builder.build();
    }

    private static void windowed(KGroupedStream<String, CardAuthEvent> byMerchant, Duration size,
                                 String store, Serde<MerchantKpi> kpiSerde) {
        byMerchant
                .windowedBy(TimeWindows.ofSizeAndGrace(size, GRACE))
                .aggregate(
                        KpiAggregator::empty,
                        (merchantId, auth, kpi) -> KpiAggregator.add(kpi, auth),
                        Named.as(store + "-aggregate"),
                        Materialized.<String, MerchantKpi, WindowStore<Bytes, byte[]>>as(store)
                                .withKeySerde(Serdes.String())
                                .withValueSerde(kpiSerde)
                                .withRetention(RETENTION));
    }
}
