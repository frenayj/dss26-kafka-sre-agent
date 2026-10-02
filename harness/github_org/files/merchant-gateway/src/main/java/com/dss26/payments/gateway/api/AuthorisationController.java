package com.dss26.payments.gateway.api;

import java.time.Clock;
import java.util.Optional;
import java.util.UUID;

import org.apache.avro.generic.GenericRecord;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.dss26.payments.gateway.events.AuthorisationEventPublisher;
import com.dss26.payments.gateway.events.CardAuthEventMapper;
import com.dss26.payments.gateway.idempotency.IdempotencyStore;
import com.dss26.payments.gateway.policy.AuthorisationPolicy;
import com.dss26.payments.gateway.policy.MerchantRateLimiter;

import jakarta.validation.Valid;

/**
 * Merchant-facing authorisation API. An accepted request is published to
 * cards.authorisation.requested.v1 and acknowledged with 202; the approve or
 * decline decision is returned asynchronously by fraud decisioning.
 */
@RestController
@RequestMapping("/v1/authorisations")
public class AuthorisationController {

    private final CardAuthEventMapper mapper;
    private final AuthorisationEventPublisher publisher;
    private final Clock clock;
    private final IdempotencyStore idempotency;
    private final MerchantRateLimiter rateLimiter;
    private final AuthorisationPolicy policy;

    public AuthorisationController(
            CardAuthEventMapper mapper,
            AuthorisationEventPublisher publisher,
            Clock clock,
            IdempotencyStore idempotency,
            MerchantRateLimiter rateLimiter,
            AuthorisationPolicy policy) {
        this.mapper = mapper;
        this.publisher = publisher;
        this.clock = clock;
        this.idempotency = idempotency;
        this.rateLimiter = rateLimiter;
        this.policy = policy;
    }

    @PostMapping
    public ResponseEntity<AuthorisationAccepted> authorise(
            @Valid @RequestBody AuthorisationRequest request,
            @RequestHeader(name = "Idempotency-Key", required = false) String idempotencyKey,
            @RequestHeader(name = "X-Request-Id", required = false) String requestId) {
        if (!rateLimiter.tryAcquire(request.merchantId())) {
            throw AuthorisationRejectedException.rateLimited(request.merchantId());
        }
        policy.check(request);

        String authId = UUID.randomUUID().toString();
        if (idempotencyKey != null) {
            Optional<String> previous = idempotency.reserve(request.merchantId() + ":" + idempotencyKey, request, authId);
            if (previous.isPresent()) {
                return ResponseEntity.accepted().body(new AuthorisationAccepted(previous.get(), "PENDING"));
            }
        }

        GenericRecord event = mapper.toEvent(authId, request, clock.instant());
        publisher.publish(request.cardToken(), event, requestId);
        return ResponseEntity.accepted().body(new AuthorisationAccepted(authId, "PENDING"));
    }
}
