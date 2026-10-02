package com.dss26.payments.gateway.api;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import com.dss26.payments.gateway.events.LegacyAuthorisationPublisher;

class AuthorisationControllerTest {

    private static final String VALID = "{"
            + "\"merchantId\": \"mch_lumen_coffee\","
            + "\"cardToken\": \"tok_4410982\","
            + "\"amount\": 42.50,"
            + "\"currency\": \"EUR\","
            + "\"merchantCountry\": \"FR\"}";

    private final LegacyAuthorisationPublisher publisher = mock(LegacyAuthorisationPublisher.class);
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders.standaloneSetup(new AuthorisationController(publisher)).build();
    }

    @Test
    void acceptsAValidRequestAndPublishesIt() throws Exception {
        mvc.perform(post("/v1/authorisations").contentType(APPLICATION_JSON).content(VALID))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.authId").isNotEmpty())
                .andExpect(jsonPath("$.status").value("PENDING"));

        verify(publisher).publish(anyString(), any(AuthorisationRequest.class), any());
    }

    @Test
    void rejectsAMalformedCurrencyWith400() throws Exception {
        mvc.perform(post("/v1/authorisations").contentType(APPLICATION_JSON)
                        .content(VALID.replace("\"EUR\"", "\"euro\"")))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(publisher);
    }
}
