package com.dss26.payments.gateway.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.apache.avro.generic.GenericRecord;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import com.dss26.payments.gateway.events.AuthorisationEventPublisher;
import com.dss26.payments.gateway.events.CardAuthEventMapper;
import com.dss26.payments.gateway.events.CardAuthSchema;
import com.dss26.payments.gateway.idempotency.IdempotencyStore;
import com.dss26.payments.gateway.policy.AuthorisationPolicy;
import com.dss26.payments.gateway.policy.MerchantRateLimiter;

class AuthorisationControllerTest {

    private static final String VALID = """
            {
              "merchantId": "mch_lumen_coffee",
              "cardToken": "tok_4410982",
              "amount": 42.50,
              "currency": "EUR",
              "merchantCountry": "FR"
            }
            """;

    private final AuthorisationEventPublisher publisher = mock(AuthorisationEventPublisher.class);
    private final MerchantRateLimiter rateLimiter = mock(MerchantRateLimiter.class);
    private final Clock clock = Clock.fixed(Instant.parse("2023-02-06T09:00:00Z"), ZoneOffset.UTC);
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        when(rateLimiter.tryAcquire(anyString())).thenReturn(true);
        AuthorisationController controller = new AuthorisationController(
                new CardAuthEventMapper(CardAuthSchema.load(), "prod"),
                publisher,
                clock,
                new IdempotencyStore(Duration.ofHours(24), clock),
                rateLimiter,
                new AuthorisationPolicy());
        mvc = MockMvcBuilders.standaloneSetup(controller)
                .setControllerAdvice(new ApiExceptionHandler())
                .build();
    }

    @Test
    void acceptsAValidRequestAndPublishesIt() throws Exception {
        mvc.perform(post("/v1/authorisations").contentType(APPLICATION_JSON).content(VALID))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.authId").isNotEmpty())
                .andExpect(jsonPath("$.status").value("PENDING"));

        verify(publisher).publish(eq("tok_4410982"), any(GenericRecord.class), isNull());
    }

    @Test
    void rejectsAMalformedCurrencyWith400() throws Exception {
        mvc.perform(post("/v1/authorisations").contentType(APPLICATION_JSON)
                        .content(VALID.replace("\"EUR\"", "\"euro\"")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("validation_failed"))
                .andExpect(jsonPath("$.errors[0].field").value("currency"));

        verifyNoInteractions(publisher);
    }

    @Test
    void rejectsAMissingCardTokenWith400() throws Exception {
        mvc.perform(post("/v1/authorisations").contentType(APPLICATION_JSON)
                        .content(VALID.replace("\"cardToken\": \"tok_4410982\",", "")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field").value("cardToken"));

        verifyNoInteractions(publisher);
    }

    @Test
    void replayWithTheSameKeyReturnsTheOriginalAuthId() throws Exception {
        String first = authorise(VALID, "5c1e7f0a-replay").andExpect(status().isAccepted())
                .andReturn().getResponse().getContentAsString();
        String second = authorise(VALID, "5c1e7f0a-replay").andExpect(status().isAccepted())
                .andReturn().getResponse().getContentAsString();

        assertThat(second).isEqualTo(first);
        verify(publisher, times(1)).publish(anyString(), any(), any());
    }

    @Test
    void reusingAKeyForADifferentRequestIs409() throws Exception {
        authorise(VALID, "5c1e7f0a-conflict").andExpect(status().isAccepted());

        authorise(VALID.replace("42.50", "99.00"), "5c1e7f0a-conflict")
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("idempotency_conflict"));
    }

    @Test
    void merchantOverItsRateLimitGets429() throws Exception {
        when(rateLimiter.tryAcquire("mch_lumen_coffee")).thenReturn(false);

        mvc.perform(post("/v1/authorisations").contentType(APPLICATION_JSON).content(VALID))
                .andExpect(status().isTooManyRequests())
                .andExpect(header().string("Retry-After", "1"))
                .andExpect(jsonPath("$.code").value("rate_limited"));

        verifyNoInteractions(publisher);
    }

    @Test
    void yenWithMinorUnitsIs422() throws Exception {
        mvc.perform(post("/v1/authorisations").contentType(APPLICATION_JSON)
                        .content(VALID.replace("42.50", "1500.5").replace("\"EUR\"", "\"JPY\"")))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value("invalid_amount_scale"));

        verifyNoInteractions(publisher);
    }

    @Test
    void passesTheRequestIdToThePublisher() throws Exception {
        mvc.perform(post("/v1/authorisations").contentType(APPLICATION_JSON)
                        .header("X-Request-Id", "req-20260114-0042").content(VALID))
                .andExpect(status().isAccepted());

        verify(publisher).publish(eq("tok_4410982"), any(GenericRecord.class), eq("req-20260114-0042"));
    }

    @Test
    void sameKeyFromTwoMerchantsIsTwoAuthorisations() throws Exception {
        authorise(VALID, "0b5d9e61-shared").andExpect(status().isAccepted());
        authorise(VALID.replace("mch_lumen_coffee", "mch_halcyon_retail"), "0b5d9e61-shared")
                .andExpect(status().isAccepted());

        verify(publisher, times(2)).publish(anyString(), any(), any());
    }

    @Test
    void malformedJsonIs400() throws Exception {
        mvc.perform(post("/v1/authorisations").contentType(APPLICATION_JSON).content("{\"merchantId\": "))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(publisher);
    }

    @Test
    void unknownChannelIs400() throws Exception {
        mvc.perform(post("/v1/authorisations").contentType(APPLICATION_JSON)
                        .content(VALID.replace("\"FR\"", "\"FR\", \"channel\": \"TELEPATHY\"")))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(publisher);
    }

    private ResultActions authorise(String body, String idempotencyKey) throws Exception {
        return mvc.perform(post("/v1/authorisations").contentType(APPLICATION_JSON)
                .header("Idempotency-Key", idempotencyKey).content(body));
    }
}
