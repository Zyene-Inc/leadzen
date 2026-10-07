# Production admin login verification — October 5, 2026

Scope: live LeadZen API configuration and Vercel domain routing. No application source was changed for this incident.

- The public login initially returned `Unauthorized` even for synthetic credentials. The API service token configured on the Google Cloud VM differed from the protected production token saved for Vercel.
- Updated the VM's `LEADZEN_DASHBOARD_TOKEN` in `/etc/leadzen.env`, restarted `leadzen.service`, verified the running process uses the intended token, and removed the temporary transfer file. The authenticated API health endpoint returned HTTP 200.
- The current main Vercel deployment returned `Incorrect email or password` for synthetic credentials, showing that requests reached the password check. `leadzen.zyene.com` was still aliased to an older deployment.
- After fresh user approval, assigned `leadzen.zyene.com` to `leadzen-dashboard-gopvo168h-zyenes-projects.vercel.app`. The public login page returned HTTP 200, and a synthetic login returned `Incorrect email or password` rather than `Unauthorized`.
- In the user's Chrome browser, signing in as `support@zyene.com` succeeded. The `/admin` page displayed the administrator identity and the employee accounts view.

This verifies the admin login path only. It does not certify the rest of the product or provider integrations. The admin password was shared in chat and should be changed to a new private password by the account owner.
