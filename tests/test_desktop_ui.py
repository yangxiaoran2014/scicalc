from __future__ import annotations

import tkinter as tk
import unittest
from types import SimpleNamespace

from scicalc.desktop import DesktopApp


class DesktopUiTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk is not available: {error}")
        self.root.withdraw()
        self.app = DesktopApp(self.root, state_path=None)
        self.root.update_idletasks()

    def tearDown(self) -> None:
        if getattr(self, "app", None) is not None:
            self.app.close()
        elif getattr(self, "root", None) is not None:
            try:
                self.root.destroy()
            except tk.TclError:
                pass

    def type_text(self, text: str) -> None:
        for char in text:
            self.app._on_keypress(SimpleNamespace(char=char, state=0))

    def test_startup_banner_and_prompt(self) -> None:
        content = self.app.console_text()
        self.assertIn("SciCalc CMD", content)
        self.assertIn("输入 help 查看命令", content)
        self.assertTrue(content.rstrip().endswith(self.app.prompt))
        self.assertEqual(self.app.get_input(), "")
        self.assertIn("RAD", self.root.title())

    def test_typing_and_submitting_an_expression(self) -> None:
        self.type_text("6*7")
        self.assertEqual(self.app.get_input(), "6*7")
        self.app.submit()
        self.root.update_idletasks()
        content = self.app.console_text()
        self.assertIn(f"{self.app.prompt}6*7", content)
        self.assertIn("= 42", content)
        self.assertEqual(self.app.get_input(), "")
        self.assertTrue(content.rstrip().endswith(self.app.prompt))

    def test_assignments_are_visible_in_variables(self) -> None:
        self.app.set_input("speed = 12 * 4")
        self.app.submit()
        self.app.set_input("vars")
        self.app.submit()
        self.root.update_idletasks()
        self.assertIn("speed = 48", self.app.console_text())

    def test_cls_clears_the_console(self) -> None:
        self.app.set_input("1+1")
        self.app.submit()
        self.app.set_input("cls")
        self.app.submit()
        self.root.update_idletasks()
        self.assertEqual(self.app.console_text().strip(), self.app.prompt)
        self.assertEqual(self.app.get_input(), "")

    def test_help_appears_above_the_current_input(self) -> None:
        self.app.set_input("1+1")
        self.app._show_help()
        self.root.update_idletasks()
        content = self.app.console_text()
        self.assertIn("SciCalc CMD 命令", content)
        self.assertIn("快捷键", content)
        self.assertEqual(self.app.get_input(), "1+1")
        self.assertTrue(content.rstrip().endswith("1+1"))

    def test_history_navigation_restores_a_draft(self) -> None:
        for expression in ("1+1", "2+2"):
            self.app.set_input(expression)
            self.app.submit()
        self.app.set_input("draft")
        self.app._history_previous()
        self.assertEqual(self.app.get_input(), "2+2")
        self.app._history_previous()
        self.assertEqual(self.app.get_input(), "1+1")
        self.app._history_next()
        self.assertEqual(self.app.get_input(), "2+2")
        self.app._history_next()
        self.assertEqual(self.app.get_input(), "draft")

    def test_tab_completion(self) -> None:
        self.app.set_input("sq")
        self.app.console.mark_set("insert", "end-1c")
        self.app._complete()
        self.assertEqual(self.app.get_input(), "sqrt(")

        self.app.set_input("hel")
        self.app.console.mark_set("insert", "end-1c")
        self.app._complete()
        self.assertEqual(self.app.get_input(), "help")

        self.app.set_input("sin")
        self.app.console.mark_set("insert", "end-1c")
        self.app._complete()
        self.assertEqual(self.app.get_input(), "sin(")

    def test_backspace_cannot_edit_the_prompt(self) -> None:
        self.app.set_input("12")
        self.app.console.mark_set("insert", "end-1c")
        self.app._backspace()
        self.assertEqual(self.app.get_input(), "1")
        self.app.console.mark_set("insert", "input_start")
        self.app._backspace()
        self.assertEqual(self.app.get_input(), "1")
        self.assertTrue(self.app.console_text().rstrip().endswith(self.app.prompt + "1"))

    def test_cancel_keeps_the_command_out_of_history(self) -> None:
        self.app.set_input("9*9")
        self.app._cancel_or_copy()
        self.root.update_idletasks()
        self.assertIn("9*9^C", self.app.console_text())
        self.assertEqual(self.app.get_input(), "")
        self.assertNotIn("9*9", self.app.session.command_history)

    def test_error_renders_source_and_caret(self) -> None:
        self.app.set_input("1/0")
        self.app.submit()
        self.root.update_idletasks()
        content = self.app.console_text()
        self.assertIn("错误: 不能除以 0", content)
        self.assertIn("^", content)

    def test_degree_change_updates_title(self) -> None:
        self.app.set_input("deg")
        self.app.submit()
        self.root.update_idletasks()
        self.assertIn("DEG", self.root.title())

    def test_f7_history_window_opens(self) -> None:
        self.app.set_input("1+1")
        self.app.submit()
        self.app._show_history_window()
        self.root.update_idletasks()
        self.assertIsNotNone(self.app._history_window)
        self.assertTrue(self.app._history_window.winfo_exists())

    def test_oversized_paste_is_rejected(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append("1" * 2_001)
        self.app._paste()
        self.root.update_idletasks()
        self.assertEqual(self.app.get_input(), "")
        self.assertIn("粘贴内容过长", self.app.console_text())


if __name__ == "__main__":
    unittest.main()
