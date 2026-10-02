package com.dss26.payments.gateway.api;

import java.math.BigDecimal;
import java.util.List;

import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

/**
 * Body of {@code POST /v1/authorisations}. {@code amount} is in major units of
 * {@code currency}; {@code cardToken} is the acquirer's token, never a PAN.
 */
public record AuthorisationRequest(
        @NotBlank @Pattern(regexp = "mch_[a-z0-9_]{3,60}") String merchantId,
        @NotBlank @Pattern(regexp = "tok_[A-Za-z0-9]{6,40}") String cardToken,
        @NotNull @Positive @Digits(integer = 13, fraction = 3) BigDecimal amount,
        @NotBlank @Pattern(regexp = "[A-Z]{3}") String currency,
        @NotBlank @Pattern(regexp = "[A-Z]{2}") String merchantCountry,
        @Size(max = 16) List<@Pattern(regexp = "[A-Z][A-Z0-9_]{2,31}") String> riskSignals,
        Channel channel) {

    public AuthorisationRequest {
        riskSignals = riskSignals == null ? List.of() : List.copyOf(riskSignals);
        channel = channel == null ? Channel.ECOM : channel;
    }
}
