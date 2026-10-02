package com.dss26.payments.hub.api;

import com.dss26.payments.hub.iban.Iban;
import com.dss26.payments.hub.iso20022.Pacs008Builder;
import com.dss26.payments.hub.routing.Scheme;
import com.dss26.payments.hub.routing.SchemeRouter;
import com.dss26.payments.hub.screening.SanctionsScreeningClient;
import com.dss26.payments.hub.vop.VerificationOfPayeeService;
import com.prowidesoftware.swift.model.mx.MxPacs00800108;
import org.springframework.http.ResponseEntity;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/v1/payments")
public class PaymentController {

    private final SanctionsScreeningClient sanctions;
    private final VerificationOfPayeeService vop;
    private final JmsTemplate gateway;

    public PaymentController(SanctionsScreeningClient sanctions, VerificationOfPayeeService vop, JmsTemplate gateway) {
        this.sanctions = sanctions;
        this.vop = vop;
        this.gateway = gateway;
    }

    /** Step 1 of the channel flow: VoP before the customer confirms (SEPA only). */
    @PostMapping("/payee-verification")
    public VerificationOfPayeeService.Outcome verifyPayee(@RequestBody PaymentRequest req) {
        return vop.verify(Iban.parse(req.getCreditorIban()).toString(), req.getCreditorName());
    }

    /** Step 2: the customer confirmed; route, screen and send. */
    @PostMapping
    public ResponseEntity<Map<String, String>> submit(@RequestBody PaymentRequest req) {
        Iban creditor = Iban.parse(req.getCreditorIban());
        Scheme scheme = SchemeRouter.route(creditor, req.getCurrency(), req.getAmount(), req.isInstant(), req.isUrgent());

        Map<String, String> body = new LinkedHashMap<>();
        body.put("scheme", scheme.name());
        if (scheme == Scheme.SWIFT_CBPR && !sanctions.isClear(req.getCustomerId(), req.getCreditorName())) {
            body.put("status", "HELD_FOR_SCREENING");
            return ResponseEntity.accepted().body(body);
        }

        String uetr = UUID.randomUUID().toString();
        String txId = "DSS26" + uetr.replace("-", "").substring(0, 25).toUpperCase();
        MxPacs00800108 pacs008 = Pacs008Builder.build(req, scheme, txId, txId, uetr, LocalDate.now());
        gateway.convertAndSend("payments.out." + scheme.name().toLowerCase(), pacs008.message());

        body.put("status", "SENT");
        body.put("uetr", uetr);
        return ResponseEntity.accepted().body(body);
    }
}
