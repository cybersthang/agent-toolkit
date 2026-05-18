---
description: Capture test environment URL (+ optional credentials reference) into `.agent-toolkit/test_env.json`. Used by /grill auto-chain (Change 2 — compress phases) to enable auto-/go.
allowed-tools: Read, Write, Bash
argument-hint: "<url> [--spec <slug>] [--creds inline|<key-ref>]"
---

# /test-env — Capture test environment URL for auto-/go

## Mục tiêu

Cho phép DEV cung cấp URL test environment 1 lần (Plan → Grill → review)
rồi /grill (hoặc /go) tự dùng. Đây là 1 trong 2 DEV touch points của
Vibe-flow sau Change 2 (touch point kia: review spec sau /plan).

Lý do tách thành command riêng (không nhét vào /grill arg) — DEV có thể
provide URL trước khi grill xong, hoặc đổi URL giữa chừng.

## Quy trình

1. **Parse `$ARGUMENTS`**:
   - Token 1: URL (bắt buộc). Phải match `https?://[\w.:/-]+`.
   - `--spec <slug>` (optional): gắn URL với spec cụ thể. Mặc định: spec
     đang active trong `.autonomy_active.json` HOẶC spec duy nhất ở
     `.agent-toolkit/specs/`.
   - `--creds <ref>` (optional): reference đến credentials, KHÔNG phải
     password thật. Giá trị hợp lệ: `inline` (DEV sẽ paste khi cần),
     `env:<VAR>` (đọc từ env var), `keychain:<key>` (đọc từ keychain).
     Mặc định: `inline`.

2. **Validate URL**:
   - HTTPS hoặc HTTP. Reject `file://`, `data:`, JS schemes.
   - Reject URL trỏ vào production (heuristic: domain match `prod`,
     `production`, hoặc whitelisted env var `AGENT_TOOLKIT_PROD_DOMAINS`).
   - Reject URL > 2048 chars (suspicious).
   - Smoke-test bằng `Bash curl -s -o /dev/null -w "%{http_code}" <URL>`:
     - 2xx / 3xx / 401 / 403 → OK, accept.
     - 0 / 5xx / timeout → warn nhưng vẫn lưu (có thể là VPN/firewall).

3. **Write `.agent-toolkit/test_env.json`**:

   ```json
   {
     "url": "<URL>",
     "spec": "<slug or null>",
     "credentials_ref": "<inline | env:<VAR> | keychain:<key>>",
     "captured_at": "<ISO local now>",
     "captured_by": "/test-env slash command",
     "smoke_status": "<http code or 'timeout'>"
   }
   ```

   - File CHỈ chứa URL + reference, KHÔNG bao giờ password thật.
   - Atomic write (xem `_common.atomic_write_json`).

4. **In confirm** (3-5 dòng):

   ```
   ✓ Test env captured
     · URL: <URL>
     · spec: <slug>
     · creds: <ref>
     · smoke: <status>
   → /grill xong sẽ auto-chain /go (Change 2). Đổi URL: gõ /test-env <new>.
   ```

5. **Side-effect check**:
   - Nếu spec đang ở `status: grilled` + `eval_status: defined` → /grill
     auto-chain đã đủ điều kiện chạy /go. In thêm dòng:
     `→ Gõ /go <slug> bây giờ HOẶC /grill <slug> done để trigger auto.`

## Refuse / clarify khi

- URL không match regex → in format hợp lệ, hỏi lại.
- `--creds` chứa raw password thật (heuristic: chuỗi > 12 chars không có
  prefix `inline`/`env:`/`keychain:`) → REFUSE, warn DEV: "credentials
  không được lưu vào file. Dùng `--creds inline` rồi paste khi agent
  yêu cầu, hoặc `--creds env:MY_TEST_PWD`."
- Spec slug không tồn tại ở `.agent-toolkit/specs/` → warn nhưng vẫn lưu
  (DEV có thể provide URL trước /plan).
- Smoke-test 5xx → warn "server down? vẫn lưu URL, nhưng /verify sẽ fail.".

## Không được làm

- KHÔNG persist raw credentials. Chỉ `credentials_ref`.
- KHÔNG override `.agent-toolkit/test_env.json` silently nếu URL khác —
  prompt DEV confirm hoặc tự backup file cũ thành `test_env.<timestamp>.json`.
- KHÔNG gọi /go inline từ command này — DEV vẫn phải /grill done để chain.
  Lý do: /test-env có thể được gõ trước khi spec sẵn sàng.

## Sibling

- `/plan` — Phase 1, sinh spec (kèm `acceptance_evals:` skeleton từ Change 2).
- `/grill` — Phase 2, refine + auto-chain /go nếu test_env.json sẵn sàng.
- `/go` — Phase 3, autonomy ON. Đọc test_env.json để show banner.
- `/verify` — Phase 5, dùng URL từ test_env.json cho HTTP probes / Playwright.
