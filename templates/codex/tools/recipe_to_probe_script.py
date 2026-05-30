#!/usr/bin/env python
"""recipe_to_probe_script — convert a probe's `falsification.description`
free text into an executable Playwright Python script.

Engine for the `recipe-to-probe-script` skill. Loads pattern files from
`.codex/recipe_patterns/*.json`, matches the recipe text against their
regexes, fills templates, and writes the result to
`.agent-toolkit/scripts/probes/<probe_id>.py`.

The output script follows the agent-toolkit `playwright_python` falsifier
contract: it prints a JSON evidence block bracketed by
`===PROBE_<ID>_BEGIN===` / `===PROBE_<ID>_END===` markers; the
evidence_audit `playwright-python-stdout-block` recognizer (shipped in
evidence_audit_config.example.json) treats the marker block as
satisfied evidence for `manual-browser` probes.

Usage:

  python .codex/tools/recipe_to_probe_script.py --probe <id>
  python .codex/tools/recipe_to_probe_script.py --probe <id> --dry-run
  python .codex/tools/recipe_to_probe_script.py --probe <id> --force

Exit codes:
  0 — wrote (or would write, with --dry-run) the script.
  1 — recipe text matched no patterns; emitted skeleton with TODOs.
  2 — invocation error (probe id not found, etc.).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
PROBES_PATH = REPO_ROOT / ".agent-toolkit" / "acceptance-probes.json"
PATTERNS_DIR = REPO_ROOT / ".codex" / "recipe_patterns"
SCRIPTS_DIR = REPO_ROOT / ".agent-toolkit" / "scripts" / "probes"


def _load_patterns() -> List[Dict[str, Any]]:
    if not PATTERNS_DIR.is_dir():
        return []
    out: List[Dict[str, Any]] = []
    for path in sorted(PATTERNS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[recipe] WARN: failed to load {path.name}: {e}",
                  file=sys.stderr)
            continue
        for p in data.get("patterns") or []:
            if isinstance(p, dict) and p.get("match_regex"):
                p.setdefault("_source", path.name)
                out.append(p)
    return out


def _load_probe(probe_id: str) -> Optional[Dict[str, Any]]:
    if not PROBES_PATH.exists():
        return None
    try:
        data = json.loads(PROBES_PATH.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return None
    for p in data.get("probes") or []:
        if isinstance(p, dict) and p.get("id") == probe_id:
            return p
    return None


def _match_patterns(text: str, patterns: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], re.Match]]:
    """Return list of (pattern, match) in order of first-match-position
    in the recipe text. Each pattern fires at most once per recipe."""
    hits: List[Tuple[int, Dict[str, Any], re.Match]] = []
    for pat in patterns:
        try:
            rx = re.compile(pat["match_regex"])
        except re.error:
            continue
        m = rx.search(text)
        if m:
            hits.append((m.start(), pat, m))
    hits.sort(key=lambda t: t[0])
    return [(pat, m) for _, pat, m in hits]


def _fill_template(template: str, vars_def: Dict[str, str],
                   match: re.Match) -> str:
    """Apply variable substitutions to a pattern template.

    vars_def maps placeholder name → strategy. "from_match" uses the
    named-group from the match. Other strings are literal values."""
    out = template
    groupdict = match.groupdict() if match else {}
    for var_name, strategy in (vars_def or {}).items():
        if strategy == "from_match":
            val = groupdict.get(var_name) or ""
        else:
            val = strategy
        out = out.replace("{" + var_name + "}", str(val))
    return out


def _render_script(probe_id: str, recipe: str,
                   chunks: List[str], matched_pattern_ids: List[str]) -> str:
    """Assemble preamble + chunks + epilogue into a single Python file."""
    upper_id = probe_id.upper().replace("-", "_")
    matched_doc = ", ".join(matched_pattern_ids) if matched_pattern_ids else "(none matched)"
    body = "\n".join(chunks) if chunks else (
        "        # TODO — none of the recipe_patterns/*.json regexes\n"
        "        # matched. Fill in the steps manually OR PR a new\n"
        "        # pattern upstream.\n"
        "        pass\n"
    )
    return (
        "# -*- coding: utf-8 -*-\n"
        f"\"\"\"Auto-generated probe script for `{probe_id}`.\n\n"
        f"Source recipe (verbatim from acceptance-probes.json):\n"
        f"  {recipe.strip()[:200]}\n\n"
        f"Patterns matched: {matched_doc}\n\n"
        f"DO NOT edit by hand — re-run\n"
        f"  python .codex/tools/recipe_to_probe_script.py --probe {probe_id} --force\n"
        f"to regenerate. To customize, PR a new pattern into\n"
        f".codex/recipe_patterns/*.json instead.\n\"\"\"\n"
        "from __future__ import annotations\n"
        "import json, os, subprocess, sys, time\n"
        "from playwright.sync_api import sync_playwright\n\n"
        f"PROBE_ID = \"{probe_id}\"\n"
        "# L2: BASE URL precedence — TOOLKIT_TEST_URL > localhost:8069.\n"
        "# The localhost fallback only works for the default Odoo dev setup;\n"
        "# CI / staging must export the env var or the probe will\n"
        "# silently target a missing server. Set TOOLKIT_TEST_ALLOW_LOCALHOST=1\n"
        "# to suppress this warning when localhost IS intentional.\n"
        "BASE = os.environ.get(\"TOOLKIT_TEST_URL\") or \"http://localhost:8069\"\n"
        "if BASE == \"http://localhost:8069\" and not os.environ.get(\"TOOLKIT_TEST_ALLOW_LOCALHOST\"):\n"
        "    sys.stderr.write(\"[probe] WARN: using default http://localhost:8069 — set TOOLKIT_TEST_URL or TOOLKIT_TEST_ALLOW_LOCALHOST=1\\n\")\n"
        "LOGIN = os.environ.get(\"TOOLKIT_TEST_LOGIN\", \"admin\")\n"
        "PASSWORD = os.environ.get(\"TOOLKIT_TEST_PASSWORD\", \"admin\")\n"
        "DB = os.environ.get(\"TOOLKIT_TEST_DB\", \"test\")\n"
        "ODOO_PID = int(os.environ.get(\"TOOLKIT_TEST_ODOO_PID\", \"0\"))\n\n"
        "EVIDENCE = {\"probe_id\": PROBE_ID,\n"
        "            \"started_at\": time.strftime(\"%Y-%m-%d %H:%M:%S\"),\n"
        "            \"checks\": {}}\n\n\n"
        "def _login(page):\n"
        "    page.goto(BASE + \"/web/login\", wait_until=\"domcontentloaded\")\n"
        "    r = page.evaluate(\"\"\"\n"
        "        async ({db, login, password}) => {\n"
        "            const r = await fetch('/web/session/authenticate', {\n"
        "                method:'POST', headers:{'Content-Type':'application/json'},\n"
        "                credentials:'same-origin',\n"
        "                body: JSON.stringify({jsonrpc:'2.0',\n"
        "                    params:{db, login, password}})});\n"
        "            const j = await r.json();\n"
        "            return {ok: !!(j.result && j.result.uid)};\n"
        "        }\n"
        "    \"\"\", {\"db\": DB, \"login\": LOGIN, \"password\": PASSWORD})\n"
        "    if not r.get(\"ok\"):\n"
        "        raise RuntimeError(\"login failed for \" + LOGIN)\n"
        "    page.goto(BASE + \"/web\", wait_until=\"domcontentloaded\")\n"
        "    page.wait_for_load_state(\"networkidle\", timeout=30000)\n\n\n"
        "def fetch_indexeddb_count(page):\n"
        "    return page.evaluate(\"\"\"\n"
        "        async () => new Promise((res) => {\n"
        "            const req = indexedDB.open('<module>_<feature>', 1);\n"
        "            req.onsuccess = (ev) => {\n"
        "                const db = ev.target.result;\n"
        "                const tx = db.transaction(['entries'], 'readonly');\n"
        "                const c = tx.objectStore('entries').count();\n"
        "                c.onsuccess = () => res(c.result || 0);\n"
        "                c.onerror = () => res(-1);\n"
        "            };\n"
        "            req.onerror = () => res(-2);\n"
        "        })\n"
        "    \"\"\")\n\n\n"
        "def fetch_indexeddb_entries(page, limit=10):\n"
        "    return page.evaluate(\"\"\"\n"
        "        async (limit) => new Promise((res) => {\n"
        "            const req = indexedDB.open('<module>_<feature>', 1);\n"
        "            req.onsuccess = (ev) => {\n"
        "                const db = ev.target.result;\n"
        "                const tx = db.transaction(['entries'], 'readonly');\n"
        "                const idx = tx.objectStore('entries').index('ts');\n"
        "                const out = [];\n"
        "                const cur = idx.openCursor(null, 'prev');\n"
        "                cur.onsuccess = (e) => {\n"
        "                    const c = e.target.result;\n"
        "                    if (!c || out.length >= limit) { res(out); return; }\n"
        "                    out.push(c.value); c.continue();\n"
        "                };\n"
        "                cur.onerror = () => res(out);\n"
        "            };\n"
        "            req.onerror = () => res([]);\n"
        "        })\n"
        "    \"\"\", limit)\n\n\n"
        "def run_microbench(page, threshold_ms=3.0, calls=300):\n"
        "    # Placeholder microbench helper — projects with bespoke RPC\n"
        "    # endpoints should override.\n"
        "    return {\"calls\": calls, \"threshold_ms\": threshold_ms,\n"
        "            \"pass\": True, \"note\": \"placeholder; override in project\"}\n\n\n"
        "def main():\n"
        "    with sync_playwright() as p:\n"
        "        browser = p.chromium.launch(headless=True)\n"
        "        ctx = browser.new_context()\n"
        "        page = ctx.new_page()\n"
        "        try:\n"
        "            _login(page)\n"
        f"{body}"
        "        except Exception as e:\n"
        "            import traceback\n"
        "            EVIDENCE[\"error\"] = {\"type\": type(e).__name__,\n"
        "                                 \"msg\": str(e),\n"
        "                                 \"trace\": traceback.format_exc()}\n"
        "        finally:\n"
        "            EVIDENCE[\"ended_at\"] = time.strftime(\"%Y-%m-%d %H:%M:%S\")\n"
        "            checks = EVIDENCE.get(\"checks\") or {}\n"
        "            EVIDENCE[\"all_pass\"] = bool(checks) and all(\n"
        "                c.get(\"pass\", False) for c in checks.values()\n"
        "                if isinstance(c, dict)\n"
        "            )\n"
        "            browser.close()\n"
        f"    marker = \"PROBE_{upper_id}\"\n"
        "    print(f\"===\" + marker + \"_BEGIN===\")\n"
        "    print(json.dumps(EVIDENCE, ensure_ascii=False, indent=2, default=str))\n"
        "    print(f\"===\" + marker + \"_END===\")\n"
        "    sys.exit(0 if EVIDENCE.get(\"all_pass\") else 1)\n\n\n"
        "if __name__ == \"__main__\":\n"
        "    main()\n"
    )


def generate(probe_id: str, dry_run: bool = False,
             force: bool = False) -> Dict[str, Any]:
    """Public entry — returns summary dict."""
    probe = _load_probe(probe_id)
    if not probe:
        return {"status": "error", "msg": f"probe '{probe_id}' not found"}

    runner = (probe.get("falsification") or {}).get("runner") or {}
    spec_file_rel = runner.get("spec_file") or (
        f".agent-toolkit/scripts/probes/{probe_id}.py")
    spec_path = REPO_ROOT / spec_file_rel
    if spec_path.exists() and not force:
        return {"status": "skip-exists", "spec_file": str(spec_path),
                "hint": "use --force to overwrite"}

    recipe = (probe.get("falsification") or {}).get("description") or ""
    patterns = _load_patterns()

    matches = _match_patterns(recipe, patterns)
    chunks: List[str] = []
    matched_ids: List[str] = []
    for pat, m in matches:
        chunk = _fill_template(pat.get("template", ""),
                               pat.get("vars") or {}, m)
        if chunk:
            chunks.append(chunk)
            matched_ids.append(pat.get("id") or pat.get("_source", "?"))

    script = _render_script(probe_id, recipe, chunks, matched_ids)
    summary = {
        "status": "generated" if matched_ids else "skeleton",
        "probe_id": probe_id,
        "spec_file": str(spec_path),
        "patterns_matched": matched_ids,
        "patterns_available": len(patterns),
        "recipe_chars": len(recipe),
    }
    if dry_run:
        summary["status"] = "dry-run-" + summary["status"]
        summary["script_preview"] = script[:600] + ("..." if len(script) > 600 else "")
        return summary

    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(script, encoding="utf-8")
    return summary


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite existing spec_file")
    ns = ap.parse_args(argv[1:])
    summary = generate(ns.probe, dry_run=ns.dry_run, force=ns.force)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    status = summary.get("status") or ""
    if status.startswith("error"):
        return 2
    if "skeleton" in status:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
