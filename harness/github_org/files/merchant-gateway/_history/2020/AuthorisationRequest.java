package com.dss26.payments.gateway.api;

import java.math.BigDecimal;

import javax.validation.constraints.Digits;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotNull;
import javax.validation.constraints.Pattern;
import javax.validation.constraints.Positive;

public class AuthorisationRequest {

    @NotBlank
    @Pattern(regexp = "mch_[a-z0-9_]{3,60}")
    private String merchantId;

    @NotBlank
    @Pattern(regexp = "tok_[A-Za-z0-9]{6,40}")
    private String cardToken;

    @NotNull
    @Positive
    @Digits(integer = 13, fraction = 3)
    private BigDecimal amount;

    @NotBlank
    @Pattern(regexp = "[A-Z]{3}")
    private String currency;

    @NotBlank
    @Pattern(regexp = "[A-Z]{2}")
    private String merchantCountry;

    public String getMerchantId() {
        return merchantId;
    }

    public void setMerchantId(String merchantId) {
        this.merchantId = merchantId;
    }

    public String getCardToken() {
        return cardToken;
    }

    public void setCardToken(String cardToken) {
        this.cardToken = cardToken;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }

    public String getCurrency() {
        return currency;
    }

    public void setCurrency(String currency) {
        this.currency = currency;
    }

    public String getMerchantCountry() {
        return merchantCountry;
    }

    public void setMerchantCountry(String merchantCountry) {
        this.merchantCountry = merchantCountry;
    }
}
