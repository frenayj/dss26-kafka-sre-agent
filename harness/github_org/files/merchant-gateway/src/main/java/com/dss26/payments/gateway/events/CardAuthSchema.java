package com.dss26.payments.gateway.events;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;

import org.apache.avro.Schema;
import org.springframework.stereotype.Component;

/**
 * Value schema of cards.authorisation.requested.v1, parsed from the .avsc that is
 * packaged with the service (src/main/avro). The release pipeline registers the
 * same file, so the records we build and the subject's latest version agree.
 */
@Component
public class CardAuthSchema {

    static final String RESOURCE = "avro/cards.authorisation.requested.v1.avsc";

    private final Schema schema;

    public CardAuthSchema() {
        this.schema = load();
    }

    public Schema schema() {
        return schema;
    }

    public static Schema load() {
        try (InputStream in = CardAuthSchema.class.getClassLoader().getResourceAsStream(RESOURCE)) {
            if (in == null) {
                throw new IllegalStateException(RESOURCE + " is not on the classpath");
            }
            return new Schema.Parser().parse(in);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
