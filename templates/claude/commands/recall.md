---
description: Quick search across `specs/`, `decision-log.md`, `invariants.json`, memory files — ranked by recency. Bridges the "what was decided about X" use-case without needing a vector index.
allowed-tools: Read, Bash, Grep, Glob
argument-hint: "<query keyword(s)>"
---

# /recall — Cross-source lookup

## Mục tiêu

Trả lời câu hỏi "tuần trước em đã quyết gì về X" trong < 3 giây bằng cách
grep song song trên tất cả nguồn persistence:

- `.agent-toolkit/specs/*.md` (spec / Open Questions / Implementation Decisions)
- `.agent-toolkit/decision-log.md` (ADR)
- `.agent-toolkit/invariants.json` (rule must-keep)
- `~/.claude/projects/<encoded>/memory/*.md` (auto memory)
- `CLAUDE.md`, `AGENTS.md` (top-level rules)

## Quy trình

1. **Parse `$ARGUMENTS`** thành keyword list. Nếu rỗng → in usage + danh sách
   nguồn hiện có.

2. **Resolve workspace** (cwd) + memory path
   (`~/.claude/projects/<encoded>/memory/`).

3. **Chạy `grep -rin` song song** trên 5 nguồn. Mỗi nguồn ra danh sách
   `file:line: matched_line`.

4. **Rank kết quả**:
   - Ưu tiên match trong `decision-log.md` (ADR) lên trên.
   - Tiếp theo: `invariants.json` (rule đang enforce).
   - Tiếp theo: `specs/` (đang work-in-progress).
   - Cuối: memory + CLAUDE.md.

5. **In Report** (8-15 dòng):

```
## /recall results — query: "<keyword>"

### ADRs (.agent-toolkit/decision-log.md)
- ADR-002 line 23: ... <matched line> ...
- ADR-003 line 7: ...

### Invariants (.agent-toolkit/invariants.json)
- (no match)

### Specs (.agent-toolkit/specs/)
- <some-spec-slug>.md line 41: ...

### Memory (~/.claude/projects/.../memory/)
- feedback_python_venv.md line 3: ...

### Top-level rules
- CLAUDE.md line 12: ...

→ Tổng: 4 match across 3 nguồn.
→ Đọc full ADR: Read .agent-toolkit/decision-log.md offset <N> limit 40
```

6. **Nếu 0 match** → in "Không tìm thấy. Thử query khác hoặc verify bằng /grep
   trên codebase (codebase MCP không nằm trong /recall scope)."

## Refuse / clarify khi

- Query < 3 ký tự → từ chối.
- Query là từ tiếng Anh phổ biến (`the`, `a`, `is`) → gợi từ khóa cụ thể hơn.

## Không được làm

- KHÔNG search trong code project (đó là việc của codebase MCP / Grep tool).
- KHÔNG mở rộng query bằng synonym tự sinh — keyword exact match.
- KHÔNG modify file nào trong quá trình recall.
