package com.dss26.cards.clearing.settlement;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Re-runs the daily cut-off after a failure. Exposed on the internal ingress only. */
@RestController
@RequestMapping("/admin/settlement")
public class SettlementAdminController {

    private final SettlementBatchJob job;

    public SettlementAdminController(SettlementBatchJob job) {
        this.job = job;
    }

    @PostMapping("/run")
    public ResponseEntity<Void> run() {
        job.cutOff();
        return ResponseEntity.accepted().build();
    }
}
