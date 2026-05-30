# Khi Odoo 21+ ra mắt — chỉ cần thêm files

Toolkit hiện đã ship **14 Odoo skills version-aware** (Odoo 12 → 20). Khi
Odoo 21 (hoặc 22, 23…) ra mắt, **không cần sửa skill body, không cần
sửa preset gốc, không cần sửa intent_router**. Chỉ cần drop 5 file
reference vào đúng chỗ — Step 0 của mỗi skill tự đọc `__manifest__.py`
của module rồi load reference tương ứng.

## Bước 1 — Drop 5 reference files (BẮT BUỘC)

Đây là phần duy nhất *bắt buộc*. Toolkit tự cascade `17 → 18 → 19 → 20`,
nên nếu Odoo 21 gần giống 20 anh có thể copy nội dung `odoo-20-*.md`
sang làm baseline rồi chỉnh delta.

```
templates/cursor/skills/odoo/
├── odoo-code-patterns/references/odoo-21-patterns.md
├── odoo-code-review/references/odoo-21-rules.md
├── odoo-debug-troubleshoot/references/odoo-21-pitfalls.md
├── odoo-module-scaffold/references/odoo-21-scaffold.md
└── odoo-tdd/references/odoo-21-tdd-pitfalls.md
```

> 4 skills còn lại (`odoo-codebase-discovery`, `odoo-data-verification`,
> `odoo-deterministic-answers`, `odoo-jira-workflow`) là 100% version-agnostic
> — không có folder `references/`, không cần đụng đến.

## Bước 2 — Optional: thêm preset `odoo-21` (chỉ nếu muốn `--preset odoo-21`)

```json
// presets/odoo-21.json
{
  "description": "Odoo 21 stack — Python 3.12+, OWL, recordset-by-default",
  "extends": "odoo-17",
  "stack_label": "Odoo 21",
  "stack": {
    "language_version": "3.12",
    "framework_version": "21"
  }
}
```

Nếu bỏ qua bước này — toolkit vẫn chạy đúng với preset `odoo-17` (hoặc
`odoo-12`); Step 0 của skill đọc `__manifest__.py` thấy `'version':
'21.0.x.x.x'` rồi load `odoo-21-*.md` reference. **Preset chỉ phục vụ
mục đích default config (Python version, MCP servers), không quyết định
skill nào được dùng.**

## Bước 3 — Optional: rules + memory + canonical_decisions

Hoàn toàn optional (giống Bước 2 — bỏ qua được, fallback về `odoo-17`):

```
templates/cursor/rules/odoo-21/         # nếu Cursor IDE cần rules riêng cho v21
templates/memory/odoo-21/               # nếu cần memory pack stack-specific
templates/codex/canonical_decisions.odoo-21.json
```

## Bước 4 — Bump toolkit version

```python
# lib/installer.py
__version__ = '0.6.0'  # bump khi schema_version đổi hoặc CLI flags break compat
```

Plus `CHANGELOG.md` entry.

## Tóm tắt — "Odoo 21 support trong 30 phút"

| File | Bắt buộc? | Effort |
|------|----------|--------|
| 5 × `references/odoo-21-*.md` | ✅ YES | 20 phút (copy `odoo-20-*.md` + chỉnh delta) |
| `presets/odoo-21.json` | ⚠️ Optional | 2 phút |
| `templates/cursor/rules/odoo-21/*.mdc` | ⚠️ Optional | tùy delta |
| `templates/memory/odoo-21/*.md` | ⚠️ Optional | tùy delta |
| `templates/codex/canonical_decisions.odoo-21.json` | ⚠️ Optional | tùy delta |
| Skill body / intent_router / preset cũ | ❌ NO TOUCH | 0 phút |

**Verify:**

```bash
# Vẫn pass đầy đủ test sau khi thêm Odoo 21
python -m pytest tests/ -v   # 72+ pass

# Install thử vào project Odoo 21
python setup.py init /path/to/odoo21-proj --preset odoo-21 --yes
# (hoặc --preset odoo-17 nếu chưa tạo odoo-21.json — vẫn chạy đúng)
```

> **Non-Odoo stacks (Django, Rails, FastAPI…)**: technically supported
> via the same preset mechanism, but you'll need to author the
> stack-specific rules, skills, MCP servers, and canonical decisions
> yourself. See [`PORTING.md`](../templates/agent_toolkit/PORTING.md) for
> the porting guide. The shipped Odoo MCP servers (`realdata_test`,
> `jira`) are Odoo-specific and won't transfer.
