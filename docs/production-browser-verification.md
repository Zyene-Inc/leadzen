# Trusted HTTPS browser verification

`dashboard/e2e/stage.py` creates a fresh private fixture, starts the candidate
dashboard and API in production mode, and exposes only that synthetic fixture
through a temporary HTTPS Quick Tunnel. It downloads a pinned cloudflared
release and verifies its checksum. It refuses inherited LeadZen/provider
variables, production database paths, non-HTTPS origins, certificate bypasses,
and a fixture whose source SHA-256 changes during the build.

The browser workflow runs the five Playwright scenarios in
`dashboard/e2e/production.spec.ts` over the trusted tunnel. The fixture rejects
provider/network/process actions before Django starts and the test fixture
identity endpoint must report `provider_disabled=true`, `blocked_external_calls=0`
and the same candidate source hash. The tests cover:

- CSP nonce, HSTS, no-store/no-transform, frame/referrer/nosniff headers,
  hydration, console/network failures, focus, keyboard navigation and contrast;
- login, secure HttpOnly SameSite cookie, logout and protected-route redirect;
- contact create/edit/delete and direct-object/cross-employee isolation;
- settings persistence, mobile navigation and overflow;
- invitation setup, password creation, onboarding and provider-disabled mailbox;
- forced password change, old-session revocation and new-login behavior.

Run locally only when a disposable public synthetic fixture is authorized:

```sh
python dashboard/e2e/stage.py --authorize-public-synthetic-fixture --test
```

This uses a free, temporary `trycloudflare.com` tunnel; it is not a staging
service or production certificate. The tunnel has no uptime guarantee and does
not establish deployment readiness. No fixture manifest, password, token,
database or private log is uploaded by CI. Cloudflare HTML rewriting must remain
disabled for the real production edge; the application emits `private, no-store,
no-transform` to preserve nonce-bearing SSR bytes.

The October 4 local browser session used the trusted synthetic tunnel for login,
home, theme and contact create/edit checks. The full automated browser gate is
repeatable in CI; any missing tunnel, HTTPS, fixture identity, source match,
provider block or browser assertion fails the job. No real customer account,
credential, email, AI request or paid provider operation was used.
