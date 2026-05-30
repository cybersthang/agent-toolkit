# 🇻🇳 Tiếng Việt — Hướng dẫn đầy đủ

**Hạ tầng AI agent (Claude Code / Cursor / Codex) cho spec-driven dev — cài 1 lần, chạy mọi project.**

Agent AI hay ship code lỗi khi không có gì **ép cơ học**. Toolkit này biến
6 rule thành un-skip-able: chặn xóa invariant, audit claim không có proof,
verify trên data thật, chặn agent commit/push, banner cảnh báo kill-switch,
alert khi bypass quá nhiều.

## Cài đặt

```bash
git clone <toolkit-repo> ~/agent-toolkit
python ~/agent-toolkit/setup.py init /đường-dẫn-tới-project --preset odoo-12 --yes
```

Preset khác: `odoo-13` … `odoo-20`, `generic`. Thêm preset mới (Django/Rails/Go) chỉ là 1 PR — xem [PORTING.md](../templates/agent_toolkit/PORTING.md).

## Tại sao dùng agent-toolkit?

- 🛡️ **Enforce cơ học, không phải honor-system.** 30+ hook DENY ở
  Claude Code harness — strip invariant, claim không proof, git
  destructive, fake progress đều bị chặn.
- 🔬 **Verify trên data thật hoặc không ship.** `/verify` chạy MCP probe
  lên DB live; `evidence_audit` Stop hook BLOCK "test pass" claim nếu
  turn không có `mcp__realdata_test__*` / `mcp__postgres__*` call.
- 📐 **6-8 phase Spec Kit workflow với hook gate.** `/plan → /clarify →
  /tasks → /analyze → /implement → /verify` — mỗi transition có hook
  từ chối tiến nếu phase trước có GAP.
- 🧭 **Hệ thống rule 3 tầng.** Constitution (nguyên tắc) → ADR (lý do
  decision) → invariants.json (pattern cơ học). Cross-link, auditable,
  append-only. Không upstream toolkit nào có layout này.
- 🔌 **Core stack-agnostic + preset overlay.** Picker
  `<file>.<framework>.json` install config đúng theo preset. Odoo 12-20
  ship sẵn; Django/Rails/Go chỉ thêm config, không fork.
- 📡 **Observability built-in.** `emit_fire_event` ring buffer, hook-health
  aggregator, bypass-rate alert, hook-crash banner — biết rule nào đang
  bị sidestep TRƯỚC khi nó rot.

## Workflow cho DEV

DEV chỉ làm **3 bước manual** — agent tự lo 6-8 phase còn lại dưới autonomy:

```
DEV gõ:  /plan <ý tưởng>      →  spec.md có cấu trúc
         /clarify <slug>       →  đóng GAP, agent tự /tasks rồi STOP
         /implement <slug>     →  bật autonomy +1h (default)
         
AGENT tự: /analyze → execute tasks → /verify → report PASS/GAP
```

Mỗi feature xong → sidecar `<slug>.implement-noted.md` capture scope
deviation + trade-off + follow-up + confidence để DEV review trước merge.

## Hướng dẫn chi tiết tiếng Việt

Đọc [USAGE.md](../USAGE.md) — full guide 861 dòng, có Mục lục 4 nhóm:
- **A. Cài đặt** (§1-4): clone, install vào project, config trung tâm
- **B. Workflow** (§5-6): spec-driven workflow theo từng preset
- **C. Bảo trì** (§7-9): cấu trúc cài, update toolkit, thêm preset mới
- **D. Khi có vấn đề** (§10-12): verify install, troubleshooting, FAQ

## Trạng thái sản xuất

Toolkit đang **dùng thực tế** trên một Odoo 12
Enterprise workspace thật từ tháng 5/2026. Các con số minh hoạ từ dogfooding cục bộ
(không phải benchmark): mỗi session điển hình ~57 hook fire-event, ~26% block,
~3.5% bypass. **30+ hook** active, **995 unit test** (tính đến v0.30.0) trên CI
(matrix: Ubuntu / macOS / Windows × Python 3.8 / 3.10 / 3.12 — all green).
Con số coverage % chỉ đo `setup.py` + `lib/`; các enforcement hook (`templates/claude/hooks/`, ~11k LOC) được ruff-lint check và behavior-test qua subprocess (`tests/test_hooks.py` + các suite per-hook) nhưng không được đo line-coverage vì chúng chạy dưới dạng subprocess.

## Liên hệ tác giả

- Email: [ducthangict.dhtn@gmail.com](mailto:ducthangict.dhtn@gmail.com)
- Zalo: [0989 464 344](tel:+84989464344)
- Mở issue trên repo hoặc liên hệ qua email/Zalo.

License **MIT** — xem [LICENSE](../LICENSE) và [NOTICE](../NOTICE) cho attribution upstream.
