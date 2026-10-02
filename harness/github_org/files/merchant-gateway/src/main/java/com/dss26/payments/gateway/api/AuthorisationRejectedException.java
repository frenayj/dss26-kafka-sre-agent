package com.dss26.payments.gateway.api;

import org.springframework.http.HttpStatus;

/**
 * A request we understood but will not publish. Rendered by
 * {@link ApiExceptionHandler} as problem+json carrying {@link #code()}.
 */
public class AuthorisationRejectedException extends RuntimeException {

    private final HttpStatus status;
    private final String code;

    public AuthorisationRejectedException(HttpStatus status, String code, String detail) {
        super(detail);
        this.status = status;
        this.code = code;
    }

    public static AuthorisationRejectedException idempotencyConflict(String key) {
        return new AuthorisationRejectedException(HttpStatus.CONFLICT, "idempotency_conflict",
                "Idempotency-Key " + key + " was already used for a different request");
    }

    public static AuthorisationRejectedException rateLimited(String merchantId) {
        return new AuthorisationRejectedException(HttpStatus.TOO_MANY_REQUESTS, "rate_limited",
                "Merchant " + merchantId + " is over its authorisation rate limit");
    }

    public HttpStatus status() {
        return status;
    }

    public String code() {
        return code;
    }
}
