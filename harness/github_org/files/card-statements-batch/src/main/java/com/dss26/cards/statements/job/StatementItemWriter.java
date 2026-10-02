package com.dss26.cards.statements.job;

import com.dss26.cards.statements.events.StatementGeneratedPublisher;
import com.dss26.cards.statements.job.Model.CardStatement;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.ServerSideEncryption;

/** Stores each PDF in the document archive, then announces it. */
@Component
public class StatementItemWriter implements ItemWriter<CardStatement> {

    private final S3Client s3;
    private final StatementPdfRenderer renderer;
    private final StatementGeneratedPublisher events;
    private final String bucket;

    public StatementItemWriter(S3Client s3, StatementPdfRenderer renderer, StatementGeneratedPublisher events,
                               @Value("${statements.archive-bucket}") String bucket) {
        this.s3 = s3;
        this.renderer = renderer;
        this.events = events;
        this.bucket = bucket;
    }

    @Override
    public void write(Chunk<? extends CardStatement> chunk) {
        for (CardStatement statement : chunk) {
            String key = "statements/%s/%s/%s.pdf".formatted(statement.cycle().period(),
                    statement.cycle().customerId(), statement.statementId());
            s3.putObject(PutObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .contentType("application/pdf")
                            .serverSideEncryption(ServerSideEncryption.AWS_KMS)
                            .build(),
                    RequestBody.fromBytes(renderer.render(statement)));
            events.generated(statement);
        }
    }
}
