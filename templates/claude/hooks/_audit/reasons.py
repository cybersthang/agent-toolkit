"""Block-reason formatters for evidence_audit Stop hook."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .progress_checks import ALL_PROGRESS_CHECKS


def format_pass_block_reason(
    text: str,
    matched_probes: List[Dict[str, Any]],
    fallback_used: bool,
    required_prefixes: Tuple[str, ...],
) -> str:
    sample = (text[:280].rstrip() + "…") if len(text) > 280 else text.strip()
    lines = [
        "[evidence-audit] PASS/DONE/VERIFIED claim detected — nhưng turn này KHÔNG có "
        "tool call MCP nào chạy verification trên real data.",
        "",
        "Agent Vibe failure pattern: 'báo pass' không kèm chạy thật → dev sẽ phải re-test "
        "tay và phát hiện lỗi. Toolkit ép verify cơ học trước khi cho phép chốt.",
        "",
    ]
    if matched_probes:
        lines.append("Probe contract activated:")
        for p in matched_probes:
            ev = p.get("evidence") or {}
            required = ev.get("required_tools") or []
            falsi = (p.get("falsification") or {}).get("description") or ""
            lines.append(
                f"  - {p.get('id', '?')} ({p.get('severity', 'blocker')}): "
                f"{p.get('description', '')}"
            )
            lines.append(f"      Required tools (≥{ev.get('min_calls', 1)}): {', '.join(required)}")
            if falsi:
                lines.append(f"      Falsification recipe: {falsi}")
            if p.get("rationale"):
                lines.append(f"      Lý do: {p['rationale']}")
    if fallback_used:
        lines.append(
            f"Generic fallback (no per-feature probe matched): cần ≥1 tool call "
            f"mở đầu bằng một trong {list(required_prefixes)}."
        )

    lines += [
        "",
        "Cách unblock:",
        "1. Chạy MCP verification (e.g. `mcp__realdata_test__run_module_test` / "
        "`eval_orm_expression` / `compare_with_expected`) trên real data, rồi report "
        "kết quả raw (số / fingerprint) trước khi claim PASS.",
        "2. Cho claim hành vi vật lý (BLOCK / async / timing), CHẠY THÊM falsification "
        "probe — ví dụ inject `time.sleep(N)` vào suspected blocking call rồi đo "
        "downstream wait phải tăng N±0.1s; nếu không tăng → claim BLOCK sai.",
        "3. Nếu thật sự không thể chạy probe (DB down / probe N/A), thêm dòng "
        "`probe-skip: <probe-id-or-all> <reason>` vào response (single-shot, audit ghi lại).",
        "4. Hoặc gắn `[assumption]` cho từng claim chưa verify để hạ tone từ FACT xuống GUESS.",
        "",
        "Trích response:",
        f"---\n{sample}\n---",
    ]
    return "\n".join(lines)


def format_progress_block_reason(violations: List[str], skipped: List[str]) -> str:
    lines = [
        "[evidence-audit] Hallucinated-progress detected — response làm claim "
        "về tiến độ/hành động mà transcript không backup.",
        "",
        f"{len(violations)} category(ies) vi phạm:",
    ]
    for v in violations:
        lines.append(f"  - {v}")
    if skipped:
        lines.append("")
        lines.append(f"Đã skip qua progress-skip: {', '.join(skipped)}")
    lines += [
        "",
        "Cách unblock:",
        "1. Sửa response — bỏ claim sai (vd. xoá past-tense nếu chưa Edit), hoặc "
        "thực sự gọi tool tương ứng rồi viết lại.",
        "2. Bypass single-shot: thêm dòng `progress-skip: <category|all> <reason>` "
        "vào response. Categories: " + ", ".join(ALL_PROGRESS_CHECKS) + ".",
        "3. [assumption] tag KHÔNG exempt progress claim — past-tense và success "
        "claim là factual, không phải opinion.",
    ]
    return "\n".join(lines)


def format_generic_claim_reason(text: str, claims: List[str]) -> str:
    sample = (text[:280].rstrip() + "…") if len(text) > 280 else text.strip()
    return (
        "[evidence-audit] Response vừa rồi có claim nhưng KHÔNG đi kèm bất kỳ "
        "tool call inspect nào trong turn này (không Read/Grep/Glob/MCP search/"
        "psql). Trước khi chốt, hoặc:\n\n"
        f"1. Chạy MCP / Read / Grep để verify các claim ({len(claims)} pattern "
        "khớp: " + ", ".join(c for c in claims[:5]) + ").\n"
        "2. Hoặc nếu không thể verify, sửa response gắn nhãn `[assumption]` "
        "hoặc `[chưa verify]` cho từng claim chưa có chứng cứ — rõ ràng với "
        "user là phỏng đoán, không phải fact.\n\n"
        "Trích response cần kiểm tra:\n"
        f"---\n{sample}\n---\n\n"
        "Bỏ qua audit cho turn này: thêm dòng `evidence-audit: skip` vào "
        "response (chỉ dùng khi claim hiển nhiên vô hại như format/style)."
    )
