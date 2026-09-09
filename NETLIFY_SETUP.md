# DRIVEBOX on Netlify

The current storefront is served from `dist`, built by `scripts/build-public.mjs`.
Netlify Functions serve `/api/*` with the same contract as the local Python server.
Netlify Database stores orders, inventory, sessions, webhook events and the email outbox.
SQL migrations in `netlify/database/migrations` run automatically at publication.
Local SQLite data and Sandbox buyer information are NOT uploaded or migrated.

## First publication: Sandbox only

The database has already been created in the Netlify project. Keep its personal-token
write-access option disabled. `@netlify/database` resolves the deploy's connection.

In Netlify Environment variables, add these values for Functions (not browser code):

- `APP_ENV=development` (intentional: this is the public Sandbox validation stage)
- `PAYPAL_ENV=sandbox`
- `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`: existing local Sandbox credentials
- `PUBLIC_URL=https://euphonious-blini-108c7b.netlify.app`
- `ADMIN_PASSWORD`: a new manager password of at least 16 characters
- `ALLOW_COD=true`

After first publication, register the Sandbox webhook URL:
`https://euphonious-blini-108c7b.netlify.app/api/paypal/webhook`
Subscribe to CHECKOUT.ORDER.APPROVED, PAYMENT.CAPTURE.COMPLETED,
PAYMENT.CAPTURE.PENDING, PAYMENT.CAPTURE.DENIED, PAYMENT.CAPTURE.REFUNDED,
and PAYMENT.CAPTURE.REVERSED. Save its ID as `PAYPAL_WEBHOOK_ID` and redeploy.

For email notifications configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
`SMTP_PASSWORD`, `SMTP_FROM`, `SELLER_EMAIL`. The scheduled function retries
outbox emails every five minutes. SMTP delivery is at-least-once: a crash after
SMTP acceptance but before the DB update can cause a duplicate notification.

## Validation

Run `pnpm test` and `pnpm build` before pushing. Local PostgreSQL tests use PGlite
and mock PayPal responses; they do not validate a deployed database or real webhook.
On the public site verify config, catalog, checkout, manager login, a Sandbox payment,
page reload, cancellation and a real signed refund webhook. Inspect Netlify function
logs if an endpoint returns a server error. Do not enable real payments until these pass.

## Live

Only after explicit approval: use Live credentials and webhook, `APP_ENV=production`,
complete seller settings from DEPLOYMENT.md, SMTP, `LEGAL_CONFIRMED=true` and
`FULFILLMENT_CONFIRMED=true`. Production checkout blocks incomplete settings.
Archive/remove test orders using a separate reviewed migration before real sales;
never silently copy the local SQLite database into production.

Official references:
- https://docs.netlify.com/build/data-and-storage/netlify-database/api/
- https://docs.netlify.com/build/data-and-storage/netlify-database/migrations/
