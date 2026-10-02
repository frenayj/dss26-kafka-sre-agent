# Schemes and cut-offs

| Scheme | CSM | Message | Cut-off (Europe/Paris) | Settlement |
|--------|-----|---------|------------------------|------------|
| SCT | EBA STEP2 | pacs.008 (SEPA usage rules) | 15:30 for same-day processing | D+1 |
| SCT Inst | EBA RT1, TIPS | pacs.008 (SCT Inst) | 24/7/365 | 10 seconds |
| T2 RTGS | T2 | pacs.008 (HVPS+) | 17:00 customer payments | real time |
| SWIFT CBPR+ | SWIFTNet FIN+ | pacs.008 (CBPR+) | 16:00 | correspondent dependent |

- T2 replaced TARGET2 on 20 March 2023; messages are ISO 20022 only.
- SWIFT MT103 is not produced any more: the MT/MX coexistence for
  cross-border payments ended in November 2025.
- Since 9 October 2025 every SCT Inst is preceded by Verification of Payee,
  and instant is priced like standard (Instant Payments Regulation).
