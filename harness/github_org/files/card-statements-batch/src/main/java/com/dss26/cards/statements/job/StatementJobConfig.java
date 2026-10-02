package com.dss26.cards.statements.job;

import com.dss26.cards.statements.job.Model.CardStatement;
import com.dss26.cards.statements.job.Model.StatementCycle;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.database.JdbcPagingItemReader;
import org.springframework.batch.item.database.Order;
import org.springframework.batch.item.database.builder.JdbcPagingItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.SimpleAsyncTaskExecutor;
import org.springframework.jdbc.core.DataClassRowMapper;
import org.springframework.transaction.PlatformTransactionManager;
import software.amazon.awssdk.core.exception.SdkClientException;

import javax.sql.DataSource;
import java.util.Map;

@Configuration
public class StatementJobConfig {

    @Bean
    Job monthlyStatementJob(JobRepository jobRepository, Step statementManagerStep) {
        return new JobBuilder("monthlyStatementJob", jobRepository)
                .start(statementManagerStep)
                .build();
    }

    @Bean
    Step statementManagerStep(JobRepository jobRepository, Step statementWorkerStep, BinRangePartitioner partitioner) {
        return new StepBuilder("statementManagerStep", jobRepository)
                .partitioner("statementWorkerStep", partitioner)
                .step(statementWorkerStep)
                .gridSize(BinRangePartitioner.RANGES.size())
                .taskExecutor(new SimpleAsyncTaskExecutor("statements-"))
                .build();
    }

    @Bean
    Step statementWorkerStep(JobRepository jobRepository, PlatformTransactionManager tx,
                             JdbcPagingItemReader<StatementCycle> cycleReader, StatementItemProcessor processor,
                             StatementItemWriter writer) {
        return new StepBuilder("statementWorkerStep", jobRepository)
                .<StatementCycle, CardStatement>chunk(100, tx)
                .reader(cycleReader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .retry(SdkClientException.class)
                .retryLimit(3)
                .build();
    }

    /** Cards with a cycle closing in the period, one BIN range per partition. */
    @Bean
    @StepScope
    JdbcPagingItemReader<StatementCycle> cycleReader(DataSource dataSource,
                                                     @Value("#{jobParameters['period']}") String period,
                                                     @Value("#{stepExecutionContext['binFrom']}") String binFrom,
                                                     @Value("#{stepExecutionContext['binTo']}") String binTo) {
        return new JdbcPagingItemReaderBuilder<StatementCycle>()
                .name("cycleReader")
                .dataSource(dataSource)
                .selectClause("SELECT card_token, customer_id, period, opening_balance, currency")
                .fromClause("FROM statement_cycle")
                .whereClause("WHERE period = :period AND bin BETWEEN :binFrom AND :binTo")
                .parameterValues(Map.of("period", period, "binFrom", binFrom, "binTo", binTo))
                .sortKeys(Map.of("card_token", Order.ASCENDING))
                .pageSize(500)
                .rowMapper(new DataClassRowMapper<>(StatementCycle.class))
                .build();
    }
}
