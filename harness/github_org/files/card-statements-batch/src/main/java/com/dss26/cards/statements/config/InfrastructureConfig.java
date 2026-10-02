package com.dss26.cards.statements.config;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

/**
 * Connections that are not the batch's own database: txn-history-builder's
 * read replica (statement lines), its primary (reconciliation writes only),
 * and the document archive bucket.
 */
@Configuration
public class InfrastructureConfig {

    @Bean
    NamedParameterJdbcTemplate txnHistoryJdbc(@Value("${statements.txn-history.read-url}") String url,
                                              @Value("${TXN_HISTORY_READER_USER}") String user,
                                              @Value("${TXN_HISTORY_READER_PASSWORD}") String password) {
        return new NamedParameterJdbcTemplate(pool("txn-history-replica", url, user, password, true));
    }

    @Bean
    NamedParameterJdbcTemplate txnHistoryWriteJdbc(@Value("${statements.txn-history.write-url}") String url,
                                                   @Value("${TXN_HISTORY_RECONCILER_USER}") String user,
                                                   @Value("${TXN_HISTORY_RECONCILER_PASSWORD}") String password) {
        return new NamedParameterJdbcTemplate(pool("txn-history-reconciler", url, user, password, false));
    }

    @Bean
    S3Client s3() {
        return S3Client.builder().region(Region.EU_WEST_1).build();
    }

    private static HikariDataSource pool(String name, String url, String user, String password, boolean readOnly) {
        HikariDataSource ds = new HikariDataSource();
        ds.setPoolName(name);
        ds.setJdbcUrl(url);
        ds.setUsername(user);
        ds.setPassword(password);
        ds.setReadOnly(readOnly);
        ds.setMaximumPoolSize(8);
        return ds;
    }
}
