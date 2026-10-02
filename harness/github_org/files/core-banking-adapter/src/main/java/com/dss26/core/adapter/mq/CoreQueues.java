package com.dss26.core.adapter.mq;

/** Queue names on the core queue manager (QM DSS26CORE1, shared with the batch window). */
public final class CoreQueues {
    public static final String BALANCE_REQUEST = "DSS26.CORE.ACCT.BAL.REQ";
    public static final String BALANCE_REPLY = "DSS26.CORE.ACCT.BAL.RPY";
    public static final String OPEN_REQUEST = "DSS26.CORE.ACCT.OPEN.REQ";
    public static final String OPEN_REPLY = "DSS26.CORE.ACCT.OPEN.RPY";
    public static final String GL_POST_REQUEST = "DSS26.CORE.GL.POST.REQ";
    public static final String GL_POST_REPLY = "DSS26.CORE.GL.POST.RPY";

    private CoreQueues() {
    }
}
