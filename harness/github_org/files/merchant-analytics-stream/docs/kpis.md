# Merchant KPI definitions

Agreed with the merchant portal team. All windows are tumbling, aligned to the
epoch, in UTC; the portal converts to the merchant's time zone.

| KPI | Definition |
|-----|------------|
| Authorisations | Count of `cards.authorisation.requested.v1` records for the merchant in the window, `tier=prod` only. Requests, not approvals. |
| Requested value | Sum of `amount` per `currency`, major units. Never converted: the portal shows one line per currency. |
| Average ticket | Requested value / authorisations, per currency. Computed at read time. |
| Largest ticket | Maximum single `amount` in the window, any currency. |

Late records (event time more than 2 minutes behind the window end) are
dropped and counted in the `dropped-records` Streams metric.

## Channel mix

Requests per `channel` (`CARD_PRESENT`, `ECOM`, `RECURRING`, `MOTO`) in the
same windows. The portal shows the e-commerce share.

## Risk-flagged share

Requests that arrived with at least one entry in `risk_signals`, divided by
authorisations. A rising share is an early hint of card testing at a merchant;
acquiring ops watch it on the hourly view.
