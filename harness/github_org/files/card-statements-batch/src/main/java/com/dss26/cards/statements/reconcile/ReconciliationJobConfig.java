package com.dss26.cards.statements.reconcile;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

/**
 * Nightly: every authorisation that cleared yesterday must be in the card
 * transaction history. Anything txn-history-builder skipped (an unreadable
 * record, a deploy gap) is inserted from the clearing replica, and cleared
 * rows are marked SETTLED. Runs before the statement job reads the table.
 */
@Configuration
public class ReconciliationJobConfig {

    private static final Logger log = LoggerFactory.getLogger(ReconciliationJobConfig.class);

    @Bean
    Job transactionReconciliationJob(JobRepository jobRepository, Step backfillStep) {
        return new JobBuilder("transactionReconciliationJob", jobRepository).start(backfillStep).build();
    }

    @Bean
    Step backfillStep(JobRepository jobRepository, PlatformTransactionManager tx,
                      @Qualifier("txnHistoryWriteJdbc") NamedParameterJdbcTemplate history) {
        return new StepBuilder("backfillStep", jobRepository)
                .tasklet((contribution, context) -> {
                    int inserted = history.update("""
                            INSERT INTO card_transaction (auth_id, card_token, merchant_id, amount, currency, status,
                                                          authorised_at, source_partition, source_offset)
                            SELECT c.auth_id, c.card_token, c.merchant_id, c.amount, c.currency, 'SETTLED',
                                   c.received_at, -1, -1
                              FROM clearing_replica.cleared_yesterday c
                             WHERE NOT EXISTS (SELECT 1 FROM card_transaction t WHERE t.auth_id = c.auth_id)
                            """, new MapSqlParameterSource());
                    int settled = history.update("""
                            UPDATE card_transaction t SET status = 'SETTLED'
                              FROM clearing_replica.cleared_yesterday c
                             WHERE t.auth_id = c.auth_id AND t.status = 'PENDING'
                            """, new MapSqlParameterSource());
                    contribution.incrementWriteCount(inserted + settled);
                    log.info("Reconciliation: {} transactions backfilled, {} marked settled", inserted, settled);
                    return RepeatStatus.FINISHED;
                }, tx)
                .build();
    }
}
