"""G6 v0.11.0 — telemetry export tests.

Exporter reads ring-buffer state files + writes append-only JSONL.
High-water dedup ensures running it twice doesn't duplicate events.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLKIT_ROOT / 'templates' / 'codex' / 'tools'))

import hook_telemetry_export as hte  # noqa: E402


def _seed_fire_log(workspace: Path, events: list) -> None:
    d = workspace / '.agent-toolkit'
    d.mkdir(parents=True, exist_ok=True)
    (d / '.hook_fire_log.json').write_text(
        json.dumps({'events': events}), encoding='utf-8'
    )


def _seed_crash_log(workspace: Path, events: list) -> None:
    d = workspace / '.agent-toolkit'
    d.mkdir(parents=True, exist_ok=True)
    (d / '.hook_crash_log.json').write_text(
        json.dumps({'events': events}), encoding='utf-8'
    )


class TestExport:

    def test_no_events_no_files_created(self, tmp_path: Path):
        summary = hte.export(tmp_path)
        assert summary['new_events'] == 0
        assert summary['wrote_jsonl'] == 0
        assert not (tmp_path / '.agent-toolkit' / 'telemetry').exists()

    def test_exports_fire_events_to_jsonl(self, tmp_path: Path):
        now = int(time.time())
        _seed_fire_log(tmp_path, [
            {'ts': now - 100, 'hook': 'invariant_guard.py', 'verdict': 'allow'},
            {'ts': now - 50, 'hook': 'evidence_audit.py', 'verdict': 'block'},
        ])
        summary = hte.export(tmp_path)
        assert summary['new_events'] == 2
        assert summary['wrote_jsonl'] == 2
        # File should exist + contain 2 JSONL lines.
        jsonl_path = Path(summary['jsonl_path'])
        assert jsonl_path.exists()
        lines = [l for l in jsonl_path.read_text(encoding='utf-8').splitlines() if l]
        assert len(lines) == 2
        # Each line parses to a dict with enrichment fields.
        for line in lines:
            evt = json.loads(line)
            assert '_source' in evt
            assert '_host' in evt
            assert '_workspace' in evt
            assert evt['_source'] in ('fire', 'crash')

    def test_second_run_dedups_via_high_water(self, tmp_path: Path):
        now = int(time.time())
        _seed_fire_log(tmp_path, [
            {'ts': now - 100, 'hook': 'h1', 'verdict': 'allow'},
        ])
        first = hte.export(tmp_path)
        assert first['wrote_jsonl'] == 1

        # Second run with same events → nothing new, no write.
        second = hte.export(tmp_path)
        assert second['new_events'] == 0
        assert second['wrote_jsonl'] == 0

        # Add a new event AFTER high water → only that one exports.
        _seed_fire_log(tmp_path, [
            {'ts': now - 100, 'hook': 'h1', 'verdict': 'allow'},
            {'ts': now - 10, 'hook': 'h2', 'verdict': 'block'},
        ])
        third = hte.export(tmp_path)
        assert third['new_events'] == 1
        assert third['wrote_jsonl'] == 1

    def test_dry_run_does_not_write(self, tmp_path: Path):
        now = int(time.time())
        _seed_fire_log(tmp_path, [
            {'ts': now - 50, 'hook': 'h', 'verdict': 'allow'},
        ])
        summary = hte.export(tmp_path, dry_run=True)
        assert summary['new_events'] == 1
        assert summary['wrote_jsonl'] == 0
        assert not (tmp_path / '.agent-toolkit' / 'telemetry').exists()
        # High-water NOT advanced on dry-run → next real run sees the same events.
        real = hte.export(tmp_path)
        assert real['new_events'] == 1

    def test_combines_fire_and_crash_events(self, tmp_path: Path):
        now = int(time.time())
        _seed_fire_log(tmp_path, [
            {'ts': now - 30, 'hook': 'h1', 'verdict': 'allow'},
        ])
        _seed_crash_log(tmp_path, [
            {'ts': now - 20, 'hook': 'h2', 'exc_type': 'KeyError',
             'exc_msg': 'foo', 'traceback_tail': ''},
        ])
        summary = hte.export(tmp_path)
        assert summary['fire_total'] == 1
        assert summary['crash_total'] == 1
        assert summary['new_events'] == 2

        jsonl_path = Path(summary['jsonl_path'])
        lines = [l for l in jsonl_path.read_text(encoding='utf-8').splitlines() if l]
        sources = sorted(json.loads(l)['_source'] for l in lines)
        assert sources == ['crash', 'fire']

    def test_explicit_since_overrides_high_water(self, tmp_path: Path):
        now = int(time.time())
        _seed_fire_log(tmp_path, [
            {'ts': now - 200, 'hook': 'h1', 'verdict': 'allow'},
            {'ts': now - 100, 'hook': 'h2', 'verdict': 'allow'},
            {'ts': now - 50, 'hook': 'h3', 'verdict': 'allow'},
        ])
        # Explicit since = now - 120 → only h2 and h3 export.
        summary = hte.export(tmp_path, since=now - 120)
        assert summary['new_events'] == 2

    def test_parse_since_arg(self):
        # Relative formats.
        now_seconds = int(time.time())
        s_1h = hte._parse_since('1h')
        # 1h ago: should be roughly now - 3600. Allow 5s clock skew.
        assert abs((now_seconds - s_1h) - 3600) < 5
        # Epoch seconds passthrough.
        assert hte._parse_since('1000000000') == 1000000000
        # 'now' → current time.
        s_now = hte._parse_since('now')
        assert abs(s_now - now_seconds) < 5

    def test_otlp_stub_counts_without_network(self, tmp_path: Path, capsys):
        """--otlp-url runs the stub adapter (prints, no network)."""
        now = int(time.time())
        _seed_fire_log(tmp_path, [
            {'ts': now - 10, 'hook': 'h', 'verdict': 'allow'},
        ])
        summary = hte.export(tmp_path, otlp_url='https://otel.example/v1/logs')
        assert summary['wrote_otlp'] == 1
        captured = capsys.readouterr()
        assert 'otlp-stub' in captured.err

    def test_main_cli_smoke(self, tmp_path: Path):
        now = int(time.time())
        _seed_fire_log(tmp_path, [
            {'ts': now - 10, 'hook': 'h', 'verdict': 'allow'},
        ])
        # Run via main() — exercises argparse + summary print.
        rv = hte.main([
            '--workspace', str(tmp_path),
            '--quiet',
        ])
        assert rv == 0
