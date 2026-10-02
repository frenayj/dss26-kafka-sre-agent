package com.dss26.cards.statements;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Runs one job and exits; scheduled by the platform (Kubernetes CronJob):
 * monthlyStatementJob on the 1st at 03:00, transactionReconciliationJob nightly.
 */
@SpringBootApplication
public class CardStatementsApplication {

    public static void main(String[] args) {
        System.exit(SpringApplication.exit(SpringApplication.run(CardStatementsApplication.class, args)));
    }
}
