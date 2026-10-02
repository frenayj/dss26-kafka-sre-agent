package com.dss26.cards.statements.job;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** One partition per issuing BIN range, so the eight workers run in parallel on disjoint cards. */
@Component
public class BinRangePartitioner implements Partitioner {

    static final List<String[]> RANGES = List.of(
            new String[]{"400000", "419999"}, new String[]{"420000", "439999"},
            new String[]{"440000", "459999"}, new String[]{"460000", "499999"},
            new String[]{"510000", "529999"}, new String[]{"530000", "549999"},
            new String[]{"550000", "559999"}, new String[]{"222100", "272099"});

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
        for (String[] range : RANGES) {
            ExecutionContext ctx = new ExecutionContext();
            ctx.putString("binFrom", range[0]);
            ctx.putString("binTo", range[1]);
            partitions.put("bins-" + range[0] + "-" + range[1], ctx);
        }
        return partitions;
    }
}
