package com.dss26.payments.gateway.api;

public class AuthorisationAccepted {

    private final String authId;
    private final String status;

    public AuthorisationAccepted(String authId, String status) {
        this.authId = authId;
        this.status = status;
    }

    public String getAuthId() {
        return authId;
    }

    public String getStatus() {
        return status;
    }
}
