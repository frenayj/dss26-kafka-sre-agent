package com.dss26.core.adapter.ledger;

import com.dss26.core.adapter.mq.CoreQueues;
import com.dss26.core.adapter.mq.MqGateway;
import com.dss26.ledger.events.JournalPosted;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.nio.charset.Charset;
import java.time.LocalDate;

/**
 * Posts every ledger.journal.posted.v1 entry to the core general ledger.
 * Ordered per key, one at a time: the core GL serialises postings per account
 * anyway, and a failure must stop the partition rather than skip a posting.
 */
@Component
public class JournalPostingListener {

    private static final Logger log = LoggerFactory.getLogger(JournalPostingListener.class);
    private static final Charset EBCDIC = Charset.forName("IBM1047");

    private final MqGateway mq;

    public JournalPostingListener(MqGateway mq) {
        this.mq = mq;
    }

    @KafkaListener(id = "gl-postings", topics = "ledger.journal.posted.v1", groupId = "core-banking-adapter")
    public void onJournal(JournalPosted journal) {
        byte[] record = GlPostingEncoder.encode(
                journal.getJournalId(),
                journal.getSourceSystem(),
                journal.getSourceReference(),
                journal.getDebitAccount(),
                journal.getCreditAccount(),
                BigDecimal.valueOf(journal.getAmount()).setScale(2, java.math.RoundingMode.HALF_EVEN),
                journal.getCurrency(),
                LocalDate.parse(journal.getValueDate()));
        // Correlation id = journal id: a redelivered journal is answered from
        // the core's duplicate log instead of being posted twice.
        byte[] reply = mq.requestReply(CoreQueues.GL_POST_REQUEST, CoreQueues.GL_POST_REPLY, record,
                journal.getJournalId());
        String returnCode = new String(reply, 0, 2, EBCDIC);
        if (!"00".equals(returnCode) && !"02".equals(returnCode)) {
            throw new IllegalStateException("Core GL rejected journal " + journal.getJournalId() + " with RC " + returnCode);
        }
        log.debug("Posted journal {} (RC {})", journal.getJournalId(), returnCode);
    }
}
