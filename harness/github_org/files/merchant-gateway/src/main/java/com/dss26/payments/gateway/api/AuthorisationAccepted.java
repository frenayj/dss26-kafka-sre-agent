package com.dss26.payments.gateway.api;

/**
 * 202 body: the auth id the approve or decline will be reported against.
 */
public record AuthorisationAccepted(String authId, String status) {
}
