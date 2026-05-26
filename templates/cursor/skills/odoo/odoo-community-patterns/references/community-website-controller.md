# Community website / eCommerce controller — depth reference

Companion to `SKILL.md` §3 (Website / eCommerce controller routing).
All examples use placeholders — discover real route names via
`codebase.search_xml_ids` or `Grep` for `@http.route`.

## `@http.route` decorator matrix (Community)

| Argument | Default 12–15 | Default 16+ | Purpose |
|---|---|---|---|
| `type` | `'http'` | `'http'` | `http` = render template, `json` = JSON-RPC, `jsonrpc` (17+) |
| `auth` | `'user'` | `'user'` | `public` / `user` / `none` / `bearer` (17+) |
| `methods` | `['GET']` | `['GET']` | Explicit allow-list; never wildcard |
| `csrf` | `False` (`type='http'`) | `True` | Must include `<input name="csrf_token" .../>` in form |
| `website` | `False` | `False` | When `True`, route appears in sitemap + supports `website_id` filter |
| `sitemap` | `True` (if `website=True`) | Same | Set to a callable for dynamic URLs |
| `multilang` | `True` (if `website=True`) | Same | Set `False` for API-style routes |

> The `csrf=` default flipped from `False` to `True` somewhere in the
> 14→17 range; the exact major depends on the release. Always declare
> `csrf=` explicitly in code instead of relying on the default —
> confirm against the target version's release notes before claiming
> a specific cutoff in a customer-facing report.

## Auth modes — what runs as whom

| `auth=` | Effective user | Use case | Trap |
|---|---|---|---|
| `'user'` | Logged-in `res.users` | Backend / portal | Returns 302 to `/web/login` for anonymous |
| `'public'` | `base.public_user` (uid usually 4) | Website forms, landing pages | `request.env[...].create()` runs as public — ACL applies; widespread `sudo()` is a leak |
| `'none'` | NO env at all | Health checks, static assets | `request.env` raises; only `request.httprequest` available |
| `'bearer'` (17+) | Looked up from `Authorization: Bearer` | API routes | Requires `auth_api_key` module |

## Sitemap visibility

`website._enumerate_pages()` walks all controllers and yields routes
where:
1. `website=True` in the decorator.
2. `sitemap=True` (or a callable returning `True`).
3. The route URL has no `<dynamic>` segments without a sitemap callable.

To list what your site exposes:

```python
def audit_sitemap(self):
    Website = self.env['website']
    site = Website.search([], limit=1)
    return list(site._enumerate_pages())
```

Routes missing from this list are invisible to Google Search Console
even if otherwise public.

## CSRF — the silent break in 16+

Forms that POST to `csrf=True` routes MUST render `csrf_token`. QWeb
template snippet (works on all versions):

```xml
<form action="/my/submit" method="post">
    <input type="hidden" name="csrf_token" t-att-value="request.csrf_token()"/>
    <!-- other fields -->
    <button type="submit">Submit</button>
</form>
```

For AJAX POST, include the token in the request body or `X-CSRF-Token`
header.

## `sudo()` discipline on public routes

The rule: **`sudo()` is a privilege escalation; treat it like `setuid`.**

```python
# BAD: sudo()-wide on raw user input
@http.route('/my/save', type='http', auth='public', csrf=True)
def save(self, **post):
    return request.env['my.model'].sudo().create(post)  # arbitrary fields!

# GOOD: validate + whitelist + narrow sudo
@http.route('/my/save', type='http', auth='public', csrf=True, website=True)
def save(self, **post):
    ALLOWED = {'name', 'email', 'phone', 'message'}
    vals = {k: v for k, v in post.items() if k in ALLOWED}
    if not vals.get('email') or '@' not in vals['email']:
        return request.render('website.404')
    request.env['my.lead'].sudo().with_context(
        mail_create_nolog=True,
    ).create(vals)
    return request.render('my_module.thanks')
```

## `request.env` vs `request.session`

- `request.env` — ORM env for the current `auth` user (public or
  logged-in). ACL applies.
- `request.session` — werkzeug session dict; safe for transient state
  (cart contents, form draft) but NOT for security-sensitive data.
- `request.httprequest` — raw werkzeug request; use for headers, IP,
  remote_addr, custom multipart handling.

## eCommerce-specific (no `website_sale_subscription` on Community)

Community ships `website_sale` (eCommerce cart) but NOT
`website_sale_subscription` (recurring cart). To detect recurring
products on Community + sell them as one-shot:

```python
def _cart_supports_recurring(self):
    return self._has_module('website_sale_subscription')

def _add_to_cart(self, product, qty):
    if product.recurring_invoice and not self._cart_supports_recurring():
        raise UserError(_(
            "This product is recurring — install website_sale_subscription "
            "(Enterprise) or contact sales."
        ))
    # normal cart add
    ...
```

## Sibling references

- `references/community-vs-enterprise-detection.md` — `_has_module()`.
- `odoo-multi-company` skill — `website_id` + `company_id` interplay
  on multi-tenant sites.
- `odoo-owl-components` skill — frontend (OWL) widgets on Community
  storefront pages.
