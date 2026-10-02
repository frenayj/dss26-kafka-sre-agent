package com.dss26.core.adapter.accounts;

import com.dss26.core.adapter.mq.CoreQueues;
import com.dss26.core.adapter.mq.MqGateway;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.nio.charset.Charset;
import java.util.Map;

/** Opens an account in the core (ACCTOPN1). The core allocates the account number. */
@RestController
public class AccountOpeningController {

    private static final Charset EBCDIC = Charset.forName("IBM1047");
    private final MqGateway mq;

    public AccountOpeningController(MqGateway mq) {
        this.mq = mq;
    }

    @PostMapping("/v1/accounts")
    @ResponseStatus(HttpStatus.CREATED)
    public Map<String, String> open(@RequestBody Map<String, String> request) {
        String customerId = request.get("customerId");
        String productCode = request.get("productCode");
        byte[] record = (String.format("%-36s", customerId) + String.format("%-16s", productCode)).getBytes(EBCDIC);
        // Same customer and product = same correlation id: a retried call gets the same account.
        byte[] reply = mq.requestReply(CoreQueues.OPEN_REQUEST, CoreQueues.OPEN_REPLY, record, customerId + productCode);
        String rc = new String(reply, 0, 2, EBCDIC);
        if (!"00".equals(rc)) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY, "Core refused account opening, RC " + rc);
        }
        return Map.of("accountNumber", new String(reply, 2, 20, EBCDIC).trim());
    }
}
