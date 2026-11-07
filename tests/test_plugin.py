"""Registration matches plugin.yaml, versions agree, and the tool schema is provider-safe."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import teach_commands  # noqa: E402
from shapes import validate_draw_payload  # noqa: E402
from teach import SCHEMA  # noqa: E402


def manifest_list(key: str) -> list[str]:
    """Read a top-level YAML list from plugin.yaml without a YAML dependency."""
    lines = (ROOT / "plugin.yaml").read_text(encoding="utf-8").splitlines()
    out, inside = [], False
    for line in lines:
        if re.match(rf"^{re.escape(key)}:\s*$", line):
            inside = True
            continue
        if inside:
            item = re.match(r"^\s+-\s+(.+?)\s*$", line)
            if item:
                out.append(item.group(1))
            elif line.strip():
                break
    return out


def manifest_scalar(key: str) -> str:
    text = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", text, re.M)
    return match.group(1).strip("'\"") if match else ""


def load_package():
    spec = importlib.util.spec_from_file_location(
        "hud_teach_under_test", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeContext:
    def __init__(self) -> None:
        self.tools: dict[str, dict] = {}
        self.hooks: dict[str, object] = {}
        self.skills: dict[str, Path] = {}
        self.commands: dict[str, dict] = {}
        self.cli: dict[str, dict] = {}

    def register_tool(self, name, toolset, schema, handler, **kwargs):
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler, **kwargs}

    def register_hook(self, name, fn, **_kwargs):
        self.hooks[name] = fn

    def register_skill(self, name, path, **_kwargs):
        self.skills[name] = Path(path)

    def register_command(self, name, handler, description="", args_hint="", **_kwargs):
        self.commands[name] = {"handler": handler, "description": description, "args_hint": args_hint}

    def register_cli_command(self, name, help, setup_fn, handler_fn=None, **_kwargs):
        self.cli[name] = {"setup_fn": setup_fn, "handler_fn": handler_fn}


class RegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ctx = FakeContext()
        load_package().register(cls.ctx)

    def test_tools_match_manifest(self) -> None:
        self.assertEqual(sorted(self.ctx.tools), sorted(manifest_list("provides_tools")))

    def test_hooks_match_manifest(self) -> None:
        self.assertEqual(sorted(self.ctx.hooks), sorted(manifest_list("provides_hooks")))
        self.assertEqual(manifest_list("hooks"), manifest_list("provides_hooks"))

    def test_marks_survive_the_turn(self) -> None:
        self.assertNotIn("on_session_end", self.ctx.hooks)
        self.assertIn("on_session_finalize", self.ctx.hooks)

    def test_skill_registered(self) -> None:
        self.assertIn("hud-teach", self.ctx.skills)
        self.assertTrue(self.ctx.skills["hud-teach"].is_file())

    def test_slash_and_cli_commands(self) -> None:
        self.assertIn("teach", self.ctx.commands)
        self.assertIn("hud-teach", self.ctx.cli)
        usage = self.ctx.commands["teach"]["handler"]("")
        self.assertIn("/teach", usage)

    def test_handler_forwards_lesson_args(self) -> None:
        handler = self.ctx.tools["teach_screen"]["handler"]
        data = json.loads(handler({"action": "draw", "steps": ["a"], "current_step": 5}))
        self.assertFalse(data["ok"])

    def test_cli_parser(self) -> None:
        import argparse

        parser = argparse.ArgumentParser()
        self.ctx.cli["hud-teach"]["setup_fn"](parser)
        args = parser.parse_args(["demo", "Chess"])
        self.assertEqual((args.hud_teach_command, args.target), ("demo", "Chess"))


class ConsistencyTests(unittest.TestCase):
    def test_versions_agree(self) -> None:
        version = manifest_scalar("version")
        self.assertTrue(re.fullmatch(r"\d+\.\d+\.\d+", version), version)
        dashboard = json.loads((ROOT / "dashboard" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(dashboard["version"], version)
        skill = (ROOT / "skills" / "hud-teach" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(f"version: {version}", skill)
        self.assertIn(f"## {version}", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))

    def test_schema_arrays_have_items(self) -> None:
        def walk(node, path):
            if isinstance(node, dict):
                if node.get("type") == "array":
                    self.assertIn("items", node, f"{path} is an array without items")
                for key, value in node.items():
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    walk(value, f"{path}[{i}]")

        walk(SCHEMA["parameters"], "parameters")

    def test_demo_shapes_fit_any_capture(self) -> None:
        for w, h in ((1280, 800), (800, 1280), (320, 200), (1280, 120)):
            self.assertIsNone(validate_draw_payload(teach_commands.demo_shapes(w, h), w, h), (w, h))


if __name__ == "__main__":
    unittest.main()
