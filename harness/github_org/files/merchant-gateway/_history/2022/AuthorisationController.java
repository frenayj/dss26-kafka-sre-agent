package com.dss26.payments.gateway.api;

import java.time.Instant;
import java.util.UUID;

import javax.validation.Valid;

import org.apache.avro.generic.GenericRecord;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.dss26.payments.gateway.events.AuthorisationEventPublisher;
import com.dss26.payments.gateway.events.CardAuthEventMapper;
import com.dss26.payments.gateway.events.LegacyAuthorisationPublisher;

@RestController
@RequestMapping("/v1/authorisations")
public class AuthorisationController {

    private final CardAuthEventMapper mapper;
    private final AuthorisationEventPublisher publisher;
    private final LegacyAuthorisationPublisher legacyPublisher;

    public AuthorisationController(CardAuthEventMapper mapper, AuthorisationEventPublisher publisher,
            LegacyAuthorisationPublisher legacyPublisher) {
        this.mapper = mapper;
        this.publisher = publisher;
        this.legacyPublisher = legacyPublisher;
    }

    @PostMapping
    public ResponseEntity<AuthorisationAccepted> authorise(@Valid @RequestBody AuthorisationRequest request) {
        String authId = UUID.randomUUID().toString();
        Instant receivedAt = Instant.now();
        GenericRecord event = mapper.toEvent(authId, request, receivedAt);
        publisher.publish(request.getCardToken(), event);
        // Dual-write until fraud-scoring reads cards.authorisation.requested.v1 (PAY-214).
        legacyPublisher.publish(authId, request, receivedAt);
        return ResponseEntity.accepted().body(new AuthorisationAccepted(authId, "PENDING"));
    }
}
