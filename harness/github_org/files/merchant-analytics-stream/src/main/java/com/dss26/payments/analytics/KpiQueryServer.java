package com.dss26.payments.analytics;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.KeyQueryMetadata;
import org.apache.kafka.streams.StoreQueryParameters;
import org.apache.kafka.streams.state.QueryableStoreTypes;
import org.apache.kafka.streams.state.ReadOnlyWindowStore;
import org.apache.kafka.streams.state.WindowStoreIterator;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * GET /merchants/{merchantId}/kpis?window=5m|1h&hours=N
 *
 * Interactive queries for the merchant portal BFF. A merchant's windows live
 * on one instance; any other instance answers with a 307 to the owner.
 */
public final class KpiQueryServer {

    record KpiView(String windowStart, long authCount, Map<String, Double> amountByCurrency,
                   double maxAmount, Map<String, Long> channelCounts, long riskFlaggedCount) {
    }

    private final KafkaStreams streams;
    private final HttpServer server;
    private final String self;
    private final ObjectMapper json = new ObjectMapper();

    public KpiQueryServer(KafkaStreams streams, String applicationServer, int port) throws IOException {
        this.streams = streams;
        this.self = applicationServer;
        this.server = HttpServer.create(new InetSocketAddress(port), 0);
        this.server.createContext("/merchants/", this::handle);
        this.server.createContext("/health", ex -> respond(ex, streams.state().isRunningOrRebalancing() ? 200 : 503, "{}"));
    }

    public void start() {
        server.start();
    }

    public void stop() {
        server.stop(1);
    }

    private void handle(HttpExchange ex) throws IOException {
        String[] parts = ex.getRequestURI().getPath().split("/");
        if (parts.length != 4 || !"kpis".equals(parts[3])) {
            respond(ex, 404, "{\"error\":\"not found\"}");
            return;
        }
        String merchantId = parts[2];
        Map<String, String> query = Query.parse(ex.getRequestURI().getRawQuery());
        String store = "1h".equals(query.get("window")) ? MerchantKpiTopology.STORE_1H : MerchantKpiTopology.STORE_5M;
        long hours = Math.min(Long.parseLong(query.getOrDefault("hours", "24")), 168);

        KeyQueryMetadata owner = streams.queryMetadataForKey(store, merchantId, Serdes.String().serializer());
        String ownerHost = owner.activeHost().host() + ":" + owner.activeHost().port();
        if (!ownerHost.equals(self)) {
            ex.getResponseHeaders().add("Location", "http://" + ownerHost + ex.getRequestURI());
            respond(ex, 307, "");
            return;
        }

        ReadOnlyWindowStore<String, MerchantKpi> windows = streams.store(
                StoreQueryParameters.fromNameAndType(store, QueryableStoreTypes.windowStore()));
        Instant to = Instant.now();
        List<KpiView> views = new ArrayList<>();
        try (WindowStoreIterator<MerchantKpi> it = windows.fetch(merchantId, to.minus(Duration.ofHours(hours)), to)) {
            it.forEachRemaining(kv -> views.add(new KpiView(Instant.ofEpochMilli(kv.key).toString(), kv.value.getAuthCount(),
                    kv.value.getAmountByCurrency(), kv.value.getMaxAmount(), kv.value.getChannelCounts(),
                    kv.value.getRiskFlaggedCount())));
        }
        respond(ex, 200, json.writeValueAsString(views));
    }

    private static void respond(HttpExchange ex, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().add("Content-Type", "application/json");
        ex.sendResponseHeaders(status, bytes.length == 0 ? -1 : bytes.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static final class Query {
        static Map<String, String> parse(String raw) {
            Map<String, String> out = new java.util.HashMap<>();
            if (raw == null || raw.isEmpty()) {
                return out;
            }
            for (String pair : raw.split("&")) {
                int eq = pair.indexOf('=');
                if (eq > 0) {
                    out.put(pair.substring(0, eq), java.net.URLDecoder.decode(pair.substring(eq + 1), StandardCharsets.UTF_8));
                }
            }
            return out;
        }
    }
}
