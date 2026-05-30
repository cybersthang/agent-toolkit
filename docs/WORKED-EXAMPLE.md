# Worked example — log + classify user requests / ví dụ thực tế

**DEV's ask** (verbatim, paraphrased):

> "Log toàn bộ request của user được cấu hình. Với mỗi request, đo
>  dung lượng (request size + response size), thời gian phản hồi
>  (server-side processing time), và tốc độ mạng user (network
>  round-trip). Mục tiêu: phân biệt user chậm là do **server-side**
>  (response chậm) hay **client-side network** (latency cao)."
>
> *"Log every request of configured users. For each request, measure
>  payload size, server response time, and user network round-trip. Goal:
>  classify slowness as server-side (slow response) or client-side
>  (slow network)."*

This is a **classifier feature** — emits a tag (`server_slow` /
`network_slow` / `ok`) per request. The full DEV flow:

```
DEV: /plan log user requests + classify slowness as server vs network

    → Agent reads codebase (controllers, HTTP layer), drafts spec at
      .agent-toolkit/specs/<branch>/log-request-slowness/log-request-slowness.md
      with 8 sections + acceptance_evals skeleton, sets
      feature_kind: classification + eval_status: draft. STOPs.
      (Agent đọc codebase, draft spec, dừng — KHÔNG implement.)

DEV: /clarify log-request-slowness

    → Agent asks 1 question per turn (5-layer self-resolve first):
       Q1: Which network metric? options (a) TCP RTT (b) browser
           PerformanceObserver paint timing (c) custom beacon — Recommended (a)
       Q2: Threshold for "network slow" vs "server slow"?
           options (a) RTT > 300ms AND server_time < 100ms → network_slow
                   (b) server_time > 500ms regardless of RTT → server_slow
                   (c) ratio-based — Recommended (a) + (b) compound
       Q3 (only if needed): which users are "configured"? → from ir.config_parameter? per-group?
    → DEV answers each, agent refines spec inline + acceptance_evals get
      concrete probes:
        - us1-payload-recorded: postgres SELECT request_log WHERE user_id IN (...)
        - us2-server-tag-correct: real-data-proof Recipe 1 — inject
          sleep(2s) into handler → server_time should rise by ~2s → tag = server_slow
        - us3-network-tag-correct: real-data-proof Recipe 13 — leave server
          fast, simulate user network via Playwright route().continue_({delay: 500})
          → RTT should rise, server_time unchanged → tag = network_slow
    → Agent smoke-tests 1 probe (postgres connect + sample query) → OK.
    → Agent auto-fires /tasks log-request-slowness, emits tasks.md
      (e.g. T1 add request_log model, T2 hook BaseRequest dispatch,
      T3 compute classification, T4 expose via /web/log_metrics endpoint),
      STOPs for DEV review.
      (Agent test thử 1 probe, sinh tasks.md, dừng cho DEV review.)

DEV: (reads tasks.md, OK) /implement log-request-slowness

    → Agent auto-chains:
        /analyze → 7 checks PASS → READY
        autonomy ON
        T1 (model) → PASS · T2 (hook) → PASS · T3 (classify) → PASS · T4 (endpoint) → PASS
        /verify:
          - us1: 10 000 rows logged for 3 configured users — ✅ PASS
          - us2: sleep(2s) injected into handler, server_time delta = +2.1s,
                 tag flipped baseline=ok → perturbed=server_slow — ✅ CONSISTENT
          - us3: Playwright network delay 500ms, RTT delta = +480ms,
                 server_time unchanged, tag flipped ok → network_slow — ✅ CONSISTENT
          - Real-Data Proof Report attached (Distribution table + Falsification table)
          - verify_lint.py hook ran — all evals covered, Real-Data Proof
            section present → exit 0
        autonomy auto-OFF
        Spec status → verified
    → ✅ Implement done — DEV reads Verify Report, merges.
```

**Why this matters / Tại sao đáng học:**

- The classifier tag (`server_slow` / `network_slow`) is proven on
  REAL data via perturbation — not just "looks right by eyeball".
  Sleep-injection forces server-side latency; Playwright network
  delay forces client-side latency. Tag flip must match the
  perturbation direction — that's falsification, not assertion.
- *Tag (`server_slow` / `network_slow`) được chứng minh trên dữ liệu
  thật bằng perturbation — không phải "nhìn thấy đúng". Inject sleep
  ép server chậm; Playwright delay ép network chậm. Tag phải flip
  theo perturbation — đó là falsification, không phải assertion.*
- See [`real-data-proof/SKILL.md`](../templates/cursor/skills/_common/real-data-proof/SKILL.md)
  + [worked example for BLOCK/ASYNC pattern](../templates/cursor/skills/_common/real-data-proof/references/block-async-worked-example.md)
  for the canonical 4-step contract.
