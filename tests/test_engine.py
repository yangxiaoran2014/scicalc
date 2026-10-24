from __future__ import annotations

import math
import unittest

from scicalc.engine import CalcError, Calculator, format_number


class CalculatorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.calculator = Calculator()

    def value(self, expression: str):
        return self.calculator.evaluate(expression).value

    def test_arithmetic_precedence(self) -> None:
        self.assertEqual(self.value("1 + 2 * 3"), 7)
        self.assertEqual(self.value("(1 + 2) * 3"), 9)
        self.assertEqual(self.value("10 / 4"), 2.5)
        self.assertEqual(self.value("10 // 4"), 2)
        self.assertEqual(self.value("10 % 4"), 2)

    def test_power_is_right_associative_and_binds_before_unary(self) -> None:
        self.assertEqual(self.value("2^3^2"), 512)
        self.assertEqual(self.value("-2^2"), -4)
        self.assertEqual(self.value("(-2)^2"), 4)
        self.assertEqual(self.value("2^-3"), 0.125)
        self.assertEqual(self.value("2**8"), 256)

    def test_implicit_multiplication(self) -> None:
        self.assertAlmostEqual(self.value("2pi"), 2 * math.pi)
        self.assertEqual(self.value("3(4 + 1)"), 15)
        self.assertEqual(self.value("(2 + 1)(4 + 1)"), 15)
        self.assertEqual(self.value("2√9"), 6)
        self.assertAlmostEqual(self.value("2 sin(pi / 2)"), 2)

    def test_functions_and_constants(self) -> None:
        self.assertAlmostEqual(self.value("sin(pi / 2)"), 1)
        self.assertAlmostEqual(self.value("cos(0)"), 1)
        self.assertAlmostEqual(self.value("sqrt(81)"), 9)
        self.assertAlmostEqual(self.value("cbrt(-27)"), -3)
        self.assertEqual(self.value("log(1000)"), 3)
        self.assertEqual(self.value("log(8, 2)"), 3)
        self.assertAlmostEqual(self.value("ln(e)"), 1)
        self.assertEqual(self.value("5!"), 120)
        self.assertEqual(self.value("fact(5)"), 120)
        self.assertEqual(self.value("max(1, 5, 3)"), 5)
        self.assertEqual(self.value("gcd(24, 36)"), 12)
        self.assertEqual(self.value("lcm(6, 8)"), 24)
        self.assertEqual(self.value("round(2.6)"), 3)

    def test_degree_mode(self) -> None:
        self.calculator.set_angle_mode("deg")
        self.assertAlmostEqual(self.value("sin(30)"), 0.5)
        self.assertAlmostEqual(self.value("asin(0.5)"), 30.0)
        self.assertEqual(self.value("atan2(1, 1)"), 45.0)

    def test_variables_and_ans(self) -> None:
        self.assertEqual(self.value("x = 2^10"), 1024)
        self.assertEqual(self.value("x / 4"), 256)
        self.assertEqual(self.value("ans + 1"), 257)
        self.assertEqual(self.calculator.variables["x"], 1024)

    def test_unicode_input(self) -> None:
        self.assertEqual(self.value("10 × 3 ÷ 2 − 1"), 14)
        self.assertAlmostEqual(self.value("π"), math.pi)
        self.assertAlmostEqual(self.value("√(16)"), 4)

    def test_formatting(self) -> None:
        self.assertEqual(format_number(0.1 + 0.2), "0.3")
        self.assertEqual(format_number(1 / 3), "0.333333333333")
        self.assertEqual(format_number(1.0), "1")
        self.assertEqual(format_number(-0.0), "0")
        self.assertEqual(format_number(10**20), "1e20")
        self.assertEqual(format_number(math.pi, 5), "3.1416")

    def test_division_by_zero(self) -> None:
        with self.assertRaisesRegex(CalcError, "不能除以 0"):
            self.value("1 / 0")
        with self.assertRaisesRegex(CalcError, "不能对 0 取模"):
            self.value("1 % 0")

    def test_domain_errors(self) -> None:
        with self.assertRaisesRegex(CalcError, "sqrt"):
            self.value("sqrt(-1)")
        with self.assertRaisesRegex(CalcError, "ln"):
            self.value("ln(0)")
        with self.assertRaisesRegex(CalcError, "阶乘"):
            self.value("(-1)!")

    def test_syntax_errors_include_positions(self) -> None:
        with self.assertRaises(CalcError) as raised:
            self.value("1.2.3")
        self.assertIsNotNone(raised.exception.position)
        with self.assertRaisesRegex(CalcError, "缺少右括号"):
            self.value("(1 + 2")
        with self.assertRaisesRegex(CalcError, "未知变量"):
            self.value("nope + 1")
        with self.assertRaisesRegex(CalcError, "未知函数"):
            self.value("frobnicate(3)")

    def test_reserved_names_cannot_be_assigned(self) -> None:
        for name in ("pi", "sin", "ans"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(CalcError, "保留名称"):
                    self.value(f"{name} = 1")

    def test_guard_limits(self) -> None:
        with self.assertRaisesRegex(CalcError, "指数过大"):
            self.value("2^10001")
        with self.assertRaisesRegex(CalcError, "阶乘的最大输入"):
            self.value("1001!")
        with self.assertRaisesRegex(CalcError, "过长"):
            self.value("1+" * 1001 + "1")

    def test_history_recording(self) -> None:
        self.calculator.evaluate("2 + 2")
        self.calculator.evaluate("x = 3")
        self.assertEqual(len(self.calculator.history), 2)
        self.assertEqual(self.calculator.history[0].text, "4")
        self.assertEqual(self.calculator.history[1].assignment, "x")
        self.calculator.clear()
        self.assertEqual(self.calculator.history, [])
        self.assertEqual(self.calculator.variables, {})
        self.assertEqual(self.calculator.ans, 0)


if __name__ == "__main__":
    unittest.main()
