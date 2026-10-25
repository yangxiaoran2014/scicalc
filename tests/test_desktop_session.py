from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scicalc.desktop_session import (
    MAX_HISTORY,
    Action,
    DesktopSession,
    load_app_state,
    save_app_state,
)


def rendered(outcome) -> str:
    return "\n".join(line.text for line in outcome.lines)


class DesktopSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = DesktopSession()

    def test_arithmetic_and_scientific_expressions(self) -> None:
        self.assertIn("= 3", rendered(self.session.submit("1 + 2")))
        self.assertIn("= 5", rendered(self.session.submit("sin(pi / 2) + sqrt(16)")))
        self.assertEqual(self.session.calculator.ans, 5)

    def test_large_integer_result(self) -> None:
        self.assertIn("= 1e5000", rendered(self.session.submit("10^5000")))
        self.assertIn("= 1.61915507072e5135", rendered(self.session.submit("1000! * 1000!")))

    def test_assignment_and_variables(self) -> None:
        result = self.session.submit("x = 2^10")
        self.assertIn("x = 1024", rendered(result))
        self.assertIn("= 256", rendered(self.session.submit("x / 4")))
        variables = rendered(self.session.submit("vars"))
        self.assertIn("x = 1024", variables)
        self.assertIn("ans = 256", variables)

    def test_degrees_and_precision(self) -> None:
        self.assertIn("DEG", rendered(self.session.submit("deg")))
        self.assertEqual(self.session.angle_mode, "deg")
        self.assertIn("= 0.5", rendered(self.session.submit("sin(30)")))
        self.assertIn("设为 5", rendered(self.session.submit("precision 5")))
        self.assertEqual(self.session.precision, 5)
        self.assertIn("0.33333", rendered(self.session.submit("1/3")))
        self.session.submit("rad")
        self.assertEqual(self.session.angle_mode, "rad")

    def test_invalid_precision(self) -> None:
        for value in ("0", "18", "high", ""):
            with self.subTest(value=value):
                command = "precision" + (f" {value}" if value else "")
                result = self.session.submit(command)
                self.assertIn("错误", rendered(result))
        self.assertEqual(self.session.precision, 12)

    def test_calculation_history(self) -> None:
        self.session.submit("1 + 1")
        self.session.submit("3 * 4")
        result = rendered(self.session.submit("history 1"))
        self.assertIn("3 * 4", result)
        self.assertIn("12", result)
        self.assertNotIn("1 + 1", result)
        self.assertIn("暂无", rendered(DesktopSession().submit("history")))

    def test_mode_and_about(self) -> None:
        self.session.submit("x = 1")
        mode = rendered(self.session.submit("mode"))
        self.assertIn("RAD", mode)
        self.assertIn("有效数字", mode)
        about = rendered(self.session.submit("about"))
        self.assertIn("SciCalc CMD", about)
        self.assertIn("github.com/yangxiaoran2014/scicalc", about)

    def test_help_aliases_and_colon_commands(self) -> None:
        for command in ("help", "?", ":help", "h"):
            with self.subTest(command=command):
                self.assertIn("SciCalc CMD 命令", rendered(self.session.submit(command)))

    def test_clear_screen_and_exit_actions(self) -> None:
        self.assertEqual(self.session.submit("cls").action, Action.CLEAR_SCREEN)
        self.assertEqual(self.session.submit(":clear").action, Action.CLEAR_SCREEN)
        exit_result = self.session.submit("quit")
        self.assertEqual(exit_result.action, Action.EXIT)
        self.assertIn("再见", rendered(exit_result))

    def test_reset_clears_calculator_state_only(self) -> None:
        self.session.submit("x = 1")
        self.session.submit("2 + 2")
        self.assertIn("已清空", rendered(self.session.submit("reset")))
        self.assertEqual(self.session.calculator.variables, {})
        self.assertEqual(self.session.calculator.history, [])
        self.assertGreater(len(self.session.command_history), 0)

    def test_errors_include_source_and_caret(self) -> None:
        result = rendered(self.session.submit("1 / 0"))
        self.assertIn("不能除以 0", result)
        self.assertIn("1 / 0", result)
        self.assertIn("^", result)

        unknown = rendered(self.session.submit(":missing"))
        self.assertIn("未知命令", unknown)
        self.assertIn("^", unknown)

    def test_empty_input_does_nothing(self) -> None:
        outcome = self.session.submit("   ")
        self.assertEqual(outcome.lines, ())
        self.assertEqual(outcome.action, Action.NONE)
        self.assertEqual(self.session.command_history, [])

    def test_command_history_is_bounded(self) -> None:
        for index in range(MAX_HISTORY + 25):
            self.session.submit(f"{index}+0")
        self.assertEqual(len(self.session.command_history), MAX_HISTORY)
        self.assertEqual(self.session.command_history[0], "25+0")
        self.assertEqual(self.session.command_history[-1], f"{MAX_HISTORY + 24}+0")


class AppStateTests(unittest.TestCase):
    def test_state_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "state.json"
            session = DesktopSession(angle_mode="deg", precision=7, history=["1+1", "help"])
            self.assertTrue(save_app_state(path, session, "900x600+100+100"))
            state = load_app_state(path)
            self.assertEqual(state.angle_mode, "deg")
            self.assertEqual(state.precision, 7)
            self.assertEqual(state.history, ("1+1", "help"))
            self.assertEqual(state.geometry, "900x600+100+100")

    def test_corrupt_state_falls_back_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            for content in (
                "{not json",
                "[]",
                json.dumps({"angle_mode": "grad", "precision": 99, "history": "nope"}),
                json.dumps({"history": [1, "", " 2+2 ", {"x": 1}]}),
            ):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    state = load_app_state(path)
                    self.assertEqual(state.angle_mode, "rad")
                    self.assertEqual(state.precision, 12)
                    self.assertIsNone(state.geometry)
                    if content.startswith('{"history"'):
                        self.assertEqual(state.history, ("2+2",))

    def test_missing_and_disabled_state(self) -> None:
        state = load_app_state(Path("does-not-exist") / "state.json")
        self.assertEqual(state.history, ())
        self.assertFalse(save_app_state(None, DesktopSession(), None))

    def test_history_is_capped_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(
                json.dumps({"history": [f"{index}+0" for index in range(MAX_HISTORY + 30)]}),
                encoding="utf-8",
            )
            state = load_app_state(path)
            self.assertEqual(len(state.history), MAX_HISTORY)
            self.assertEqual(state.history[0], "30+0")


if __name__ == "__main__":
    unittest.main()
