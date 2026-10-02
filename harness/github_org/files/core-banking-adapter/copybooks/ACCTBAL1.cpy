      ******************************************************************
      * ACCTBAL1 - ACCOUNT BALANCE ENQUIRY                             *
      * REQUEST QUEUE  DSS26.CORE.ACCT.BAL.REQ                         *
      * REPLY QUEUE    DSS26.CORE.ACCT.BAL.RPY                         *
      ******************************************************************
       01  ACCT-BAL-REQUEST.
           05  ABQ-ACCOUNT-NUMBER        PIC X(20).
       01  ACCT-BAL-REPLY.
           05  ABR-ACCOUNT-NUMBER        PIC X(20).
           05  ABR-RETURN-CODE           PIC X(2).
               88  ABR-OK                VALUE '00'.
               88  ABR-NOT-FOUND         VALUE '04'.
           05  ABR-LEDGER-BALANCE        PIC S9(13)V99 COMP-3.
           05  ABR-AVAILABLE-BALANCE     PIC S9(13)V99 COMP-3.
           05  ABR-CURRENCY              PIC X(3).
