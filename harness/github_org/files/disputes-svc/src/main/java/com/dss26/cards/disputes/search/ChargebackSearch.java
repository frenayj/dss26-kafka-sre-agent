package com.dss26.cards.disputes.search;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.List;
import java.util.Map;

/**
 * Free-text search for the back-office, against the disputes-search alias.
 * Documents are written by sink-elastic-disputes-search (Cards Platform);
 * the mapping is ours: search/index-template.json.
 */
@Component
public class ChargebackSearch {

    static final String ALIAS = "disputes-search";

    private final RestClient elastic;

    public ChargebackSearch(RestClient.Builder builder, @Value("${disputes.search.url}") String url) {
        this.elastic = builder.baseUrl(url).build();
    }

    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> search(String merchantId, String reasonCategory, int size) {
        Map<String, Object> query = Map.of(
                "size", Math.min(size, 100),
                "sort", List.of(Map.of("opened_at", "desc")),
                "query", Map.of("bool", Map.of("filter", List.of(
                        Map.of("term", Map.of("merchant_id", merchantId)),
                        Map.of("term", Map.of("reason_category", reasonCategory))))));
        Map<String, Object> response = elastic.post()
                .uri("/{alias}/_search", ALIAS)
                .contentType(MediaType.APPLICATION_JSON)
                .body(query)
                .retrieve()
                .body(Map.class);
        Map<String, Object> hits = (Map<String, Object>) response.get("hits");
        return ((List<Map<String, Object>>) hits.get("hits")).stream()
                .map(hit -> (Map<String, Object>) hit.get("_source"))
                .toList();
    }
}
