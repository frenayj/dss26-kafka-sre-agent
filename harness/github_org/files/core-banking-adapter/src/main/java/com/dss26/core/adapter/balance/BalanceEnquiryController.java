package com.dss26.core.adapter.balance;

import com.dss26.core.adapter.mq.CoreQueues;
import com.dss26.core.adapter.mq.MqGateway;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.nio.charset.Charset;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/** Real-time balance from the core (ACCTBAL1), for the channels and payments-hub. */
@RestController
public class BalanceEnquiryController {

    private static final Charset EBCDIC = Charset.forName("IBM1047");
    private final MqGateway mq;

    public BalanceEnquiryController(MqGateway mq) {
        this.mq = mq;
    }

    @GetMapping("/v1/accounts/{accountNumber}/balance")
    public ResponseEntity<Map<String, Object>> balance(@PathVariable String accountNumber) {
        byte[] request = String.format("%-20s", accountNumber).getBytes(EBCDIC);
        byte[] reply = mq.requestReply(CoreQueues.BALANCE_REQUEST, CoreQueues.BALANCE_REPLY, request,
                UUID.randomUUID().toString());
        String rc = new String(reply, 20, 2, EBCDIC);
        if ("04".equals(rc)) {
            return ResponseEntity.notFound().build();
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("accountNumber", accountNumber);
        body.put("ledgerBalance", unpack(reply, 22, 8, 2));
        body.put("availableBalance", unpack(reply, 30, 8, 2));
        body.put("currency", new String(reply, 38, 3, EBCDIC));
        return ResponseEntity.ok(body);
    }

    static BigDecimal unpack(byte[] data, int offset, int length, int scale) {
        StringBuilder digits = new StringBuilder();
        for (int i = offset; i < offset + length; i++) {
            int b = data[i] & 0xFF;
            digits.append(b >> 4);
            if (i < offset + length - 1) {
                digits.append(b & 0x0F);
            }
        }
        int sign = data[offset + length - 1] & 0x0F;
        BigDecimal value = new BigDecimal(new BigInteger(digits.toString()), scale);
        return sign == 0x0D ? value.negate() : value;
    }
}
