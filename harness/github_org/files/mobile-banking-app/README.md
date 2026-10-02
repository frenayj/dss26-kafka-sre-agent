# mobile-banking-app

The DSS26 Bank app for iOS and Android (React Native). Accounts, cards,
transactions, payments and card controls for retail customers.

Owned by **Digital Channels** (`@dss26-org/digital-channels`).
Slack `#digital-channels`.

## Architecture

The app only talks to the **mobile BFF** (`BFF_BASE_URL`, `/mobile/v1/...`),
which fans out to the backend services:

| Screen | BFF route | Backend |
|--------|-----------|---------|
| Card transactions | `GET /cards/{token}/transactions?before=` | txn-history-builder |
| Freeze / unfreeze | `POST` / `DELETE /cards/{token}/freeze` | card-lifecycle-svc |
| Lost or stolen | `POST /cards/{token}/block` | card-lifecycle-svc |
| Profile and consents | `/customers/me` | customer-profile-svc |

- Transactions page with a cursor (`nextBefore`) since DIG-702.
- The refresh token is stored in the Keychain / Android Keystore behind
  biometrics (`src/auth/session.ts`).
- Amounts arrive as decimal strings and are formatted, never computed, in the
  app (`src/utils/money.ts`).

## Accessibility

The app meets WCAG 2.1 AA as required by the European Accessibility Act
(in force for banking services since 28 June 2025): every interactive element
has a label, amounts have spoken labels, touch targets are at least 48 dp.
Accessibility issues are bugs with the `accessibility` label.

## Development

```bash
npm ci
npm run lint && npm run typecheck && npm test
npm run ios      # or: npm run android
```

`.env` files per environment are provided by the Digital Channels vault entry
(`BFF_BASE_URL` and the certificate pins); never commit them.

## Releases

Fortnightly train, cut on Monday, store submission on Wednesday. Hotfixes go
through the same pipeline with an expedited review.

## On-call

Tier 1 with the BFF: PagerDuty service `PSVC4ZL`, escalation policy
"Digital Channels - Primary". Crash-free sessions below 99.5% or login error
rate above 2% pages.
