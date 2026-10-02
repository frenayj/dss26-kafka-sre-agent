# AML typologies screened on card transactions

Owner: Compliance Platform, with the MLRO's office. Thresholds are
configuration and change only with MLRO sign-off.

| Rule | Typology | What fires it | Reference |
|------|----------|---------------|-----------|
| `LARGE_VALUE` | LARGE_VALUE | One cleared transaction of EUR 10,000 or more (EUR equivalent at the ECB reference rate) | EU AMLD occasional-transaction threshold; EBA ML/TF risk factors guidelines |
| `ROUND_AMOUNT` | (flag only) | EUR 5,000 or more in whole thousands | EBA ML/TF risk factors guidelines, unusual transaction patterns |
| `HIGH_RISK_MERCHANT` | HIGH_RISK_COUNTERPARTY | Merchant on the FIU's high-risk merchant list | Internal risk assessment |
| structuring window | STRUCTURING | Three or more cleared transactions between EUR 9,000 and 10,000 for one customer within 24 hours | EU AMLD, linked transactions |

**Flag** means the screening record is kept with outcome `FLAGGED` for the
periodic review. **Alert** means an `aml.alert.raised.v1` record and a case for
the Financial Intelligence Unit.

## Retention

Screening records and alerts are kept five years after the end of the
customer relationship (AMLD article 40). The record of evidence is the FIU's
case management system, not this service.

## AMLR

The EU AML Regulation (EU) 2024/1624 applies from 10 July 2027 and replaces the
national transpositions of the directive. Mapping of each rule to the AMLR
articles: CMP-1310 (in progress). Thresholds above are unchanged by it.
