# internet-banking-web

DSS26 Bank internet banking for desktop browsers: accounts, card
transactions, statements, payments and settings. React single-page app
served from the same origin as the web BFF.

Owned by **Digital Channels** (`@dss26-org/digital-channels`).
Slack `#digital-channels`.

## Architecture

Static assets on the CDN; every API call goes to the web BFF under `/web/v1`
with the HttpOnly session cookie. The BFF fans out to the backend services:

| Page | BFF route | Backend |
|------|-----------|---------|
| Card transactions | `GET /cards/{token}/transactions?before=` | txn-history-builder |
| Statements | `GET /cards/{token}/statements` | card-statements-batch archive (S3) |
| Profile, consents | `/customers/me` | customer-profile-svc |

Languages: English, French, Dutch and German (`src/i18n`).

## Accessibility

WCAG 2.1 AA, required by the European Accessibility Act since 28 June 2025:
skip link, landmarks, table captions and headers, `aria-live` for loading
and errors, `eslint-plugin-jsx-a11y` in CI. Accessibility defects are bugs
with the `accessibility` label.

## Development

```bash
npm ci
npm run dev        # http://localhost:3000, proxies /web to BFF_DEV_URL
npm test
npm run build
```

## On-call

Tier 1 with the web BFF: PagerDuty service `PSVC1GV`, escalation policy
"Digital Channels - Primary".
