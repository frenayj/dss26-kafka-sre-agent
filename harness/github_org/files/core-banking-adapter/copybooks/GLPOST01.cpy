      ******************************************************************
      * GLPOST01 - GENERAL LEDGER POSTING REQUEST                       *
      * REQUEST QUEUE  DSS26.CORE.GL.POST.REQ                          *
      * REPLY QUEUE    DSS26.CORE.GL.POST.RPY  (COPYBOOK GLPOST02)     *
      * CODEPAGE       IBM-1047, FIXED LENGTH 172                      *
      ******************************************************************
       01  GL-POST-REQUEST.
           05  GLP-JOURNAL-ID            PIC X(36).
           05  GLP-SOURCE-SYSTEM         PIC X(24).
           05  GLP-SOURCE-REF            PIC X(36).
           05  GLP-DEBIT-ACCOUNT         PIC X(20).
           05  GLP-CREDIT-ACCOUNT        PIC X(20).
           05  GLP-AMOUNT                PIC S9(13)V99 COMP-3.
           05  GLP-CURRENCY              PIC X(3).
           05  GLP-VALUE-DATE            PIC 9(8).
           05  FILLER                    PIC X(17).
