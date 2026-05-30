---
description: Toggle/inspect the TDD auto-loop. The `tdd_runner.py` PostToolUse hook reads `.agent-toolkit/tdd.json` to decide whether to nudge after each Edit/Write.
allowed-tools: Read, Edit, Write, Bash
argument-hint: "on | off | status | run"
---

# /tdd — TDD auto-loop toggle

## Mục tiêu

Điều khiển hook `tdd_runner.py` (PostToolUse) — Phase 3 của Vibe-flow.
Hook đọc `<workspace>/.agent-toolkit/tdd.json` để quyết định:

- `enabled: false` → hook im lặng.
- `enabled: true, mode: "nudge"` → emit reminder nhắc agent chạy MCP
  `run_python_tests` trên file vừa edit.
- `enabled: true, mode: "run"` → hook tự subprocess chạy pytest (chậm hơn,
  rủi ro hơn — chỉ bật khi DEV thật sự muốn).

Argument: `$ARGUMENTS` ∈ `{on, off, status, run}`. Mặc định `status`.

## Quy trình

1. **Đọc `.agent-toolkit/tdd.json`** (tạo mặc định nếu chưa có):
   ```json
   {
     "enabled": true,
     "mode": "nudge",
     "test_glob": ["**/tests/test_*.py"],
     "source_glob": ["**/models/**.py", "**/controllers/**.py", "**/wizards/**.py"],
     "test_command": "{{PYTHON_BIN}} -m pytest -x"
   }
   ```

2. **Xử lý theo argument**:
   - `on` → set `enabled: true`, giữ `mode` cũ (default nudge).
   - `off` → set `enabled: false`.
   - `run` → set `enabled: true, mode: "run"`. Cảnh báo DEV: subprocess
     pytest có thể chậm + side effects.
   - `status` → in nội dung tdd.json + ví dụ file nào sẽ trigger.

3. **In trạng thái sau khi đổi** — 3-5 dòng:
   ```
   TDD auto: ON · mode: nudge
   - test_glob: **/tests/test_*.py
   - source_glob: **/models/**.py, **/controllers/**.py, **/wizards/**.py
   - Trigger: Edit/Write trên file khớp glob → hook emit reminder.
   ```

## Refuse / clarify khi

- `$ARGUMENTS` không hợp lệ → liệt kê 4 option.
- Mode "run" nhưng `test_command` không chạy được → cảnh báo, không apply.

## Không được làm

- KHÔNG sửa hook `tdd_runner.py` — chỉ sửa config.
- KHÔNG xóa file `tdd.json` (set enabled=false thay vì xóa).
