package com.dss26.payments.hub.vop;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.time.Duration;
import java.util.Map;

/**
 * Verification of Payee (Instant Payments Regulation, article 5c; EPC VOP
 * scheme). Before the customer authorises a SEPA transfer we ask the
 * payee's bank, through the VOP directory, whether name and IBAN match, and
 * show the answer. The customer may still send after a mismatch warning.
 */
@Service
public class VerificationOfPayeeService {

    public enum Result { MATCH, CLOSE_MATCH, NO_MATCH, NOT_POSSIBLE }

    public static final class Outcome {
        private final Result result;
        private final String suggestedName;

        public Outcome(Result result, String suggestedName) {
            this.result = result;
            this.suggestedName = suggestedName;
        }

        public Result getResult() {
            return result;
        }

        /** Only returned on CLOSE_MATCH, as the scheme allows. */
        public String getSuggestedName() {
            return suggestedName;
        }
    }

    private final RestTemplate rest;

    public VerificationOfPayeeService(RestTemplateBuilder builder, @Value("${hub.vop.base-url}") String baseUrl) {
        this.rest = builder.rootUri(baseUrl)
                .setConnectTimeout(Duration.ofSeconds(1))
                // The scheme gives the responding bank 5 seconds; we stop waiting at 4.
                .setReadTimeout(Duration.ofSeconds(4))
                .build();
    }

    @SuppressWarnings("unchecked")
    public Outcome verify(String creditorIban, String creditorName) {
        try {
            Map<String, String> resp = rest.postForObject("/vop/v1/payee-verifications",
                    Map.of("partyAccount", creditorIban, "partyName", creditorName), Map.class);
            if (resp == null) {
                return new Outcome(Result.NOT_POSSIBLE, null);
            }
            Result result = Result.valueOf(resp.getOrDefault("result", "NOT_POSSIBLE"));
            return new Outcome(result, result == Result.CLOSE_MATCH ? resp.get("matchedName") : null);
        } catch (RuntimeException e) {
            return new Outcome(Result.NOT_POSSIBLE, null);
        }
    }
}
