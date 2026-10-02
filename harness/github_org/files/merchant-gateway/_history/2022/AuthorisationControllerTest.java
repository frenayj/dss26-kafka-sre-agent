package com.dss26.payments.gateway.api;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.apache.avro.generic.GenericRecord;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import com.dss26.payments.gateway.events.AuthorisationEventPublisher;
import com.dss26.payments.gateway.events.CardAuthEventMapper;
import com.dss26.payments.gateway.events.CardAuthSchema;
import com.dss26.payments.gateway.events.LegacyAuthorisationPublisher;

class AuthorisationControllerTest {

    private static final String VALID = "{"
            + "\"merchantId\": \"mch_lumen_coffee\","
            + "\"cardToken\": \"tok_4410982\","
            + "\"amount\": 42.50,"
            + "\"currency\": \"EUR\","
            + "\"merchantCountry\": \"FR\"}";

    private final AuthorisationEventPublisher publisher = mock(AuthorisationEventPublisher.class);
    private final LegacyAuthorisationPublisher legacyPublisher = mock(LegacyAuthorisationPublisher.class);
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        AuthorisationController controller = new AuthorisationController(
                new CardAuthEventMapper(new CardAuthSchema()), publisher, legacyPublisher);
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

        verify(publisher).publish(eq("tok_4410982"), any(GenericRecord.class));
        verify(legacyPublisher).publish(anyString(), any(AuthorisationRequest.class), any());
    }

    @Test
    void rejectsAMalformedCurrencyWith400() throws Exception {
        mvc.perform(post("/v1/authorisations").contentType(APPLICATION_JSON)
                        .content(VALID.replace("\"EUR\"", "\"euro\"")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("validation_failed"))
                .andExpect(jsonPath("$.errors[0].field").value("currency"));

        verifyNoInteractions(publisher, legacyPublisher);
    }
}
