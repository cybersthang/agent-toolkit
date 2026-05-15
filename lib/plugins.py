"""Plugin hook interface (Tier 4 stub).

Lets a stack-specific module inject extra install steps without forking
the toolkit. Plugins are discovered by name listed in a preset:

    {
      "extends": "odoo-12",
      "plugins": ["my_org.my_plugin"]
    }

Each plugin module exposes one or more of these callables:

    def pre_apply(ctx: dict, target: Path) -> None:
        '''Run BEFORE pass 2 (write) of cmd_init's apply loop.
        Useful for: extra validation, pulling external data into ctx,
        creating directories that templates expect.'''

    def post_apply(ctx: dict, target: Path) -> None:
        '''Run AFTER all template files are written, BEFORE
        seed_memory / mcp configs / project config persistence.'''

    def post_install(ctx: dict, target: Path) -> None:
        '''Run after everything (write_project_config done). Use for
        side effects like creating git branches, opening editor, etc.
        Should be idempotent.'''

This is an interface stub — wire-up in setup.py is left as a small
follow-up. The goal of the stub is to lock in the contract so plugin
authors can start writing without waiting for the loader.

Example minimal plugin:

    # ~/.local/agent-toolkit-plugins/notify_slack.py
    def post_install(ctx, target):
        import requests
        requests.post(SLACK_URL, json={'text': f'installed into {target}'})
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

HookName = str
HookFn = Callable[[Dict[str, Any], Path], None]


def load_plugins(names: List[str]) -> Dict[HookName, List[HookFn]]:
    """Import every plugin module and collect its hook callables.

    Returns a dict keyed by hook name (`pre_apply`, `post_apply`,
    `post_install`) → list of callables in declaration order.
    Missing hooks are silently skipped; missing modules raise.
    """
    hooks: Dict[HookName, List[HookFn]] = {
        'pre_apply': [],
        'post_apply': [],
        'post_install': [],
    }
    for name in names:
        mod = importlib.import_module(name)
        for hook_name in hooks:
            fn: Optional[HookFn] = getattr(mod, hook_name, None)
            if callable(fn):
                hooks[hook_name].append(fn)
    return hooks


def run_hooks(hooks: Dict[HookName, List[HookFn]], hook_name: HookName,
              ctx: Dict[str, Any], target: Path) -> None:
    """Invoke every callable registered for `hook_name`. Plugin failures
    propagate so a broken plugin doesn't silently corrupt install state.
    """
    for fn in hooks.get(hook_name, []):
        fn(ctx, target)
