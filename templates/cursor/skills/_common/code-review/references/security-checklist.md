# Security Checklist — Code Review Reference

Open this file when walking Dimension 4 (HTTP controllers / API), Dimension 9
(Config / security / data XML), or whenever a finding touches auth, input,
secrets, or external systems. Use as a *checklist*, not a tutorial — every
unchecked item is either a finding (with PROOF) or an explicit
"none — verified by …".

The checklist mixes stack-agnostic items with Odoo-specific items. Pick the
ones that apply to the surface in scope; mark the rest N/A.

---

## Pre-commit / secrets

- [ ] No credentials / API keys / tokens in committed code (grep `password`, `secret`, `api_key`, `token`, `Bearer`, `aws_`).
- [ ] `.codex/mcp.local.env` (or equivalent) is gitignored — sample file uses placeholders only.
- [ ] `.env`, `*.pem`, `*.key`, `mcp.local.env`, `mcp.json` covered by `.gitignore`.
- [ ] Connection strings parameterized, not embedded.
- [ ] No hard-coded internal IPs / hostnames in committed config (except documented dev defaults).

## Input validation (Dimension 4 + Dimension 10)

- [ ] User input validated at the **system boundary** (HTTP route, RPC handler, form action), not deep in business logic.
- [ ] Validation uses allowlists where possible (not denylists).
- [ ] String lengths bounded (min/max) where downstream code assumes bounded input.
- [ ] Numeric ranges validated (no implicit Python int overflow assumptions for downstream C/SQL paths).
- [ ] File uploads: extension allowlist + content-type check + size cap + scan for nested archive bombs.
- [ ] Decompression: explicit max-output-bytes cap before `gzip.decompress` / `zipfile.extractall` / equivalent. Refuse early when the announced size exceeds the cap.
- [ ] URLs validated before redirect (prevent open-redirect).
- [ ] JSON depth + size capped if the endpoint accepts attacker-controlled JSON.

## SQL injection / ORM safety

- [ ] All raw SQL parameterized — no `%` / f-string concatenation of user values into the query string. Use `self.env.cr.execute('... WHERE x = %s', (value,))` shape in Odoo.
- [ ] ORM domain leaves never built by string concatenation (`('field', '=', user_input)`, not `[(eval(...))]`).
- [ ] `search()` / `read()` results escaped before going into rendered HTML / QWeb (use auto-escaping; `t-raw` is XSS-risk in 12, deprecated in 17).
- [ ] No `eval()` / `exec()` / `pickle.loads` on attacker-controlled data.

## Authentication

- [ ] Every protected endpoint declares the correct `auth` level (`public`, `user`, `none`). Default to `auth='user'`.
- [ ] Passwords hashed via Odoo's stored password mechanism — never plaintext, never custom SHA-256.
- [ ] Session cookies: `httpOnly`, `secure`, `sameSite`.
- [ ] Password reset tokens: time-limited (≤1 h), single-use.
- [ ] Rate limiting on login + reset endpoints (Odoo: extend `res.users._login` or wrap controller).
- [ ] No long-lived bearer tokens in `localStorage` / committed config.

## Authorization (IDOR)

- [ ] Every endpoint that reads / mutates a record verifies the user **owns or has access** to that record — not just that the user is authenticated.
- [ ] Admin-only endpoints check `env.user.has_group('base.group_system')` or stricter.
- [ ] `_check_company` called on multi-company records before write.
- [ ] Multi-company `ir.rule` declared for any new model that ties to a company / partner.

## CSRF policy (Odoo)

- [ ] State-changing **form** endpoints (`type='http'` with form-encoded body) MUST keep `csrf=True` (default). Flag MEDIUM if `csrf=False`.
- [ ] State-changing **JSON-RPC** endpoints (`type='json'`): `csrf=False` is the Odoo convention because JSON-RPC frames don't accept cross-site form-encoded POSTs. Flag LOW (cosmetic) only if no `Content-Type` enforcement; not MEDIUM.
- [ ] GET endpoints never mutate state.
- [ ] CSRF-exempted endpoints documented with one-line comment ("why exempted").

## `sudo()` discipline (Odoo)

- [ ] Every `sudo()` call has a one-line comment explaining why bypassing record rules is correct.
- [ ] `sudo()` only used to widen scope for a specific operation, then dropped (avoid `self.sudo()` for the rest of the method).
- [ ] No `sudo()` used to bypass `ir.rule` for actions the user clearly shouldn't perform.

## `ir.model.access` + `ir.rule` (Odoo)

- [ ] Every new `models.Model` (not `TransientModel` / `AbstractModel`) has at least one `ir.model.access.csv` row.
- [ ] Permissions match the model's intent (no `perm_unlink=1` on audit-log models).
- [ ] Models referenced in actions / menus have access rules for the groups that see those actions.
- [ ] Multi-company models: `ir.rule` aligned with parent `_inherit` chain.
- [ ] No hard-coded `xmlid` references like `base.user_admin` in `security.xml` — use the standard groups.

## Output encoding

- [ ] HTML output goes through QWeb auto-escaping (`t-esc`, not `t-raw`).
- [ ] JSON output: `ensure_ascii=False` on `json.dumps` if the data may contain non-ASCII (Vietnamese function names, partner names).
- [ ] Error responses don't leak stack traces / SQL fragments in production. `_logger.exception` server-side, generic message client-side.

## Security headers (when reverse proxy isn't enforcing them)

- [ ] `Content-Security-Policy: default-src 'self'` — relax only when necessary, document why.
- [ ] `Strict-Transport-Security: max-age=31536000; includeSubDomains` (HTTPS only).
- [ ] `X-Content-Type-Options: nosniff`.
- [ ] `X-Frame-Options: DENY` (or `SAMEORIGIN` if the app embeds itself).
- [ ] `Referrer-Policy: strict-origin-when-cross-origin`.

## CORS

- [ ] No `Access-Control-Allow-Origin: *` on endpoints that read user-bound data.
- [ ] Origin allowlist matches deployed front-ends only.
- [ ] `credentials: true` only when the front-end actually needs cookies cross-origin.

## Logging / observability

- [ ] No passwords, tokens, full credit-card numbers in `_logger` output.
- [ ] No raw `request.params` dumped at INFO level (may contain PII).
- [ ] Authentication failures + permission denials logged at WARNING with user id + endpoint.

## External integrations

- [ ] HTTP client calls: explicit timeout (no unbounded blocking) + verified TLS certs.
- [ ] Webhook receivers: signature verification (HMAC) on every payload.
- [ ] Outbound URLs allowlisted when the source is user-controlled (SSRF defense).
- [ ] Background tasks that hit external systems wrap in try/except + log failure + don't retry forever.

## Dependency security

- [ ] New Python deps audited with `pip-audit` (or equivalent).
- [ ] Odoo addons from external sources reviewed for the same items in this checklist before bundling.
- [ ] License compatible with the project (LGPL-3 / OEEL-1 typical for NAKIVO; GPL conflicts with proprietary Enterprise modules).

## Install / uninstall symmetry (Odoo)

- [ ] Registry patches (`setattr(BaseModel, …)`) have a teardown path that restores the original — verify by reading both `_register_hook` and `uninstall_hook`.
- [ ] Cron records have an explicit `noupdate="0"` on first install, `noupdate="1"` afterwards (so user-edited schedules survive upgrades).
- [ ] No `data/` records reference an `xmlid` from a not-yet-loaded file — verify `__manifest__.py` load order.

## OWASP Top 10 quick map

| # | Item | Where to look |
|---|------|---------------|
| 1 | Broken Access Control | Authorization section, IDOR checks |
| 2 | Cryptographic Failures | HTTPS, password hashing, secrets |
| 3 | Injection | SQL injection / ORM safety, output encoding |
| 4 | Insecure Design | This whole list as a threat-model snapshot |
| 5 | Security Misconfiguration | Security headers, CORS, `sudo()` |
| 6 | Vulnerable Components | Dependency security |
| 7 | Auth Failures | Authentication section |
| 8 | Data Integrity Failures | Install/uninstall symmetry, signed payloads |
| 9 | Logging Failures | Logging / observability |
| 10 | SSRF | External integrations |

## When to escalate severity

- **BLOCKER**: any of {RCE, SQL injection on user-reachable path, IDOR on a record that contains PII, secret in committed code, auth bypass, `sudo()` used to grant write where rule explicitly denies}.
- **MEDIUM**: any of {CSRF on form endpoint, decompression bomb without cap, `ensure_ascii=True` mangling Unicode, missing `ir.rule` for multi-company, `httpOnly`/`secure` cookie flags missing, slow rate limit allowing brute force}.
- **LOW**: any of {hard-coded `base.user_admin`, missing security header on UI-only endpoint, comment-only documentation of an exempt CSRF, weak password complexity rule with mitigations elsewhere}.
