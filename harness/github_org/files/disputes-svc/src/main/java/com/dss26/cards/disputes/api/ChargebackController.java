package com.dss26.cards.disputes.api;

import com.dss26.cards.disputes.chargeback.CardNetwork;
import com.dss26.cards.disputes.chargeback.Chargeback;
import com.dss26.cards.disputes.chargeback.ChargebackService;
import com.dss26.cards.disputes.search.ChargebackSearch;
import com.dss26.cards.events.ChargebackOutcome;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/v1/chargebacks")
public class ChargebackController {

    public record OpenRequest(@NotBlank String authId, @NotBlank String merchantId, @NotNull CardNetwork network,
                              @Positive BigDecimal amount, @NotBlank String currency, @NotBlank String reasonCode) {
    }

    public record ResolveRequest(@NotNull ChargebackOutcome outcome, @NotNull BigDecimal recoveredAmount) {
    }

    private final ChargebackService service;
    private final ChargebackSearch search;

    public ChargebackController(ChargebackService service, ChargebackSearch search) {
        this.service = service;
        this.search = search;
    }

    @PostMapping
    public Chargeback open(@Valid @RequestBody OpenRequest req) {
        return service.open(req.authId(), req.merchantId(), req.network(), req.amount(), req.currency(),
                req.reasonCode());
    }

    @PostMapping("/{id}/resolution")
    public Chargeback resolve(@PathVariable String id, @Valid @RequestBody ResolveRequest req) {
        return service.resolve(id, req.outcome(), req.recoveredAmount());
    }

    @GetMapping("/search")
    public List<Map<String, Object>> search(@RequestParam String merchantId, @RequestParam String category,
                                            @RequestParam(defaultValue = "50") int size) {
        return search.search(merchantId, category, size);
    }
}
