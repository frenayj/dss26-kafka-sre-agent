      ******************************************************************
      * ACCTOPN1 - OPEN CUSTOMER ACCOUNT                               *
      * REQUEST QUEUE  DSS26.CORE.ACCT.OPEN.REQ                        *
      * REPLY QUEUE    DSS26.CORE.ACCT.OPEN.RPY                        *
      ******************************************************************
       01  ACCT-OPEN-REQUEST.
           05  AOQ-CUSTOMER-ID           PIC X(36).
           05  AOQ-PRODUCT-CODE          PIC X(16).
       01  ACCT-OPEN-REPLY.
           05  AOR-RETURN-CODE           PIC X(2).
           05  AOR-ACCOUNT-NUMBER        PIC X(20).
