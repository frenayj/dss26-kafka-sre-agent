package com.dss26.payments.gateway.api;

import java.time.Instant;
import java.util.UUID;

import javax.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.dss26.payments.gateway.events.LegacyAuthorisationPublisher;

@RestController
@RequestMapping("/v1/authorisations")
public class AuthorisationController {

    private final LegacyAuthorisationPublisher publisher;

    public AuthorisationController(LegacyAuthorisationPublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping
    public ResponseEntity<AuthorisationAccepted> authorise(@Valid @RequestBody AuthorisationRequest request) {
        String authId = UUID.randomUUID().toString();
        publisher.publish(authId, request, Instant.now());
        return ResponseEntity.accepted().body(new AuthorisationAccepted(authId, "PENDING"));
    }
}
