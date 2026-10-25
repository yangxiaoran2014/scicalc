"""Expression parsing and evaluation for SciCalc.

The evaluator is intentionally self-contained: it never calls ``eval`` and
only exposes a fixed set of mathematical functions and constants.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR, localcontext
from typing import Any, Callable, Sequence

MAX_SOURCE_LENGTH = 2_000
MAX_FACTORIAL = 1_000
MAX_INTEGER_EXPONENT = 10_000
MAX_RESULT_BITS = 100_000

# Characters that appear in copy-pasted expressions are normalised before
# tokenisation.  The mapping is one-to-one wherever possible so error columns
# continue to point at the right place in the user's input.
_CHAR_MAP = str.maketrans(
    {
        "×": "*",
        "·": "*",
        "⋅": "*",
        "÷": "/",
        "−": "-",
        "–": "-",
        "—": "-",
        "（": "(",
        "）": ")",
        "，": ",",
        "＋": "+",
        "－": "-",
        "＊": "*",
        "／": "/",
        "＾": "^",
        "！": "!",
        "％": "%",
    }
)

_ASSIGNMENT_RE = re.compile(r"^\s*([^\W\d]\w*)\s*=(?!=)\s*(.+?)\s*$", re.UNICODE)


class CalcError(Exception):
    """A user-facing calculation error.

    ``position`` is a zero-based offset into the full source line, when known.
    """

    def __init__(self, message: str, position: int | None = None):
        super().__init__(message)
        self.message = message
        self.position = position


@dataclass(frozen=True)
class Token:
    kind: str
    value: Any
    text: str
    position: int


def _token(kind: str, value: Any, text: str, position: int) -> Token:
    return Token(kind, value, text, position)


def tokenize(source: str) -> list[Token]:
    """Turn an expression into a small, explicit token stream."""

    text = source.translate(_CHAR_MAP)
    tokens: list[Token] = []
    index = 0
    length = len(text)

    while index < length:
        char = text[index]

        if char.isspace():
            index += 1
            continue

        if char.isdigit() or (char == "." and index + 1 < length and text[index + 1].isdigit()):
            start = index

            while index < length and text[index].isdigit():
                index += 1

            if index < length and text[index] == ".":
                index += 1
                while index < length and text[index].isdigit():
                    index += 1

            if index < length and text[index] in "eE":
                exponent_start = index
                probe = index + 1
                if probe < length and text[probe] in "+-":
                    probe += 1
                if probe < length and text[probe].isdigit():
                    index = probe
                    while index < length and text[index].isdigit():
                        index += 1
                else:
                    # ``2e`` is treated as implicit multiplication (2 * e).
                    index = exponent_start

            raw = text[start:index]
            try:
                value: int | float = float(raw) if ("." in raw or "e" in raw.lower()) else int(raw)
            except ValueError:
                raise CalcError(f"无效的数字 '{raw}'", start) from None

            if isinstance(value, float) and not math.isfinite(value):
                raise CalcError("数字超出可表示范围", start)

            tokens.append(_token("number", value, raw, start))
            continue

        if char in ("π", "τ", "√"):
            value = {"π": "pi", "τ": "tau", "√": "sqrt"}[char]
            tokens.append(_token("name" if char != "√" else "sqrt", value, char, index))
            index += 1
            continue

        if char.isalpha() or char == "_":
            start = index
            index += 1
            while index < length and (text[index].isalnum() or text[index] == "_"):
                index += 1
            name = text[start:index]
            tokens.append(_token("name", name, name, start))
            continue

        if text.startswith("**", index):
            tokens.append(_token("op", "^", "**", index))
            index += 2
            continue

        if text.startswith("//", index):
            tokens.append(_token("op", "//", "//", index))
            index += 2
            continue

        if char in "+-*/%^":
            tokens.append(_token("op", char, char, index))
            index += 1
            continue

        if char == "!":
            tokens.append(_token("factorial", "!", "!", index))
            index += 1
            continue

        if char == "(":
            tokens.append(_token("lparen", "(", "(", index))
            index += 1
            continue

        if char == ")":
            tokens.append(_token("rparen", ")", ")", index))
            index += 1
            continue

        if char == ",":
            tokens.append(_token("comma", ",", ",", index))
            index += 1
            continue

        raise CalcError(f"无法识别的字符 '{char}'", index)

    tokens.append(_token("eof", None, "", length))
    return tokens


# ---------------------------------------------------------------------------
# AST nodes


@dataclass(frozen=True)
class NumberNode:
    value: int | float
    position: int


@dataclass(frozen=True)
class UnaryNode:
    operator: str
    operand: Any
    position: int


@dataclass(frozen=True)
class BinaryNode:
    operator: str
    left: Any
    right: Any
    position: int


@dataclass(frozen=True)
class FactorialNode:
    operand: Any
    position: int


@dataclass(frozen=True)
class NameNode:
    name: str
    position: int


@dataclass(frozen=True)
class CallNode:
    name: str
    arguments: tuple[Any, ...]
    position: int


class Parser:
    """Recursive-descent parser with scientific-calculator precedence."""

    def __init__(self, tokens: Sequence[Token]):
        self.tokens = tokens
        self.index = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    @property
    def previous(self) -> Token:
        return self.tokens[self.index - 1]

    def advance(self) -> Token:
        token = self.current
        if token.kind != "eof":
            self.index += 1
        return token

    def match(self, kind: str, value: Any = None) -> Token | None:
        token = self.current
        if token.kind == kind and (value is None or token.value == value):
            self.advance()
            return token
        return None

    def expect(self, kind: str, message: str) -> Token:
        token = self.current
        if token.kind == kind:
            return self.advance()
        raise CalcError(message, token.position)

    def parse(self) -> Any:
        if self.current.kind == "eof":
            raise CalcError("表达式为空", self.current.position)
        node = self.parse_expression()
        if self.current.kind != "eof":
            token = self.current
            raise CalcError(f"意外的标记 '{token.text}'", token.position)
        return node

    def parse_expression(self) -> Any:
        node = self.parse_term()
        while self.current.kind == "op" and self.current.value in ("+", "-"):
            operator = self.advance()
            right = self.parse_term()
            node = BinaryNode(operator.value, node, right, operator.position)
        return node

    def _implicit_multiplication_allowed(self, end_kind: str) -> bool:
        next_kind = self.current.kind
        if next_kind not in ("number", "name", "lparen", "sqrt"):
            return False
        if end_kind == "number":
            # Reject malformed numbers such as ``1.2.3`` while keeping ``2pi``.
            return next_kind in ("name", "lparen", "sqrt")
        return end_kind in ("name", "rparen")

    def parse_term(self) -> Any:
        node = self.parse_unary()
        while True:
            token = self.current
            if token.kind == "op" and token.value in ("*", "/", "//", "%"):
                self.advance()
                right = self.parse_unary()
                node = BinaryNode(token.value, node, right, token.position)
                continue

            if self._implicit_multiplication_allowed(self.previous.kind):
                multiplication_position = token.position
                right = self.parse_unary()
                node = BinaryNode("*", node, right, multiplication_position)
                continue

            return node

    def parse_unary(self) -> Any:
        token = self.current
        if token.kind == "op" and token.value in ("+", "-"):
            self.advance()
            operand = self.parse_unary()
            return UnaryNode(token.value, operand, token.position)

        if token.kind == "sqrt":
            self.advance()
            operand = self.parse_unary()
            return CallNode("sqrt", (operand,), token.position)

        return self.parse_power()

    def parse_power(self) -> Any:
        node = self.parse_factorial()
        if self.current.kind == "op" and self.current.value == "^":
            operator = self.advance()
            right = self.parse_unary()
            node = BinaryNode("^", node, right, operator.position)
        return node

    def parse_factorial(self) -> Any:
        node = self.parse_primary()
        while self.current.kind == "factorial":
            token = self.advance()
            node = FactorialNode(node, token.position)
        return node

    def parse_primary(self) -> Any:
        token = self.current

        if token.kind == "number":
            self.advance()
            return NumberNode(token.value, token.position)

        if token.kind == "name":
            self.advance()
            if self.match("lparen"):
                arguments: list[Any] = []
                if self.current.kind != "rparen":
                    while True:
                        arguments.append(self.parse_expression())
                        if self.match("comma"):
                            continue
                        break
                self.expect("rparen", "函数调用缺少右括号")
                return CallNode(token.value, tuple(arguments), token.position)
            return NameNode(token.value, token.position)

        if token.kind == "lparen":
            self.advance()
            node = self.parse_expression()
            self.expect("rparen", "缺少右括号")
            return node

        if token.kind == "rparen":
            raise CalcError("多余的右括号", token.position)
        if token.kind == "comma":
            raise CalcError("逗号只能用于函数参数之间", token.position)
        if token.kind == "eof":
            raise CalcError("表达式不完整", token.position)
        raise CalcError(f"意外的标记 '{token.text}'", token.position)


def parse_expression(source: str) -> Any:
    if len(source) > MAX_SOURCE_LENGTH:
        raise CalcError(f"表达式过长（最多 {MAX_SOURCE_LENGTH} 个字符）", MAX_SOURCE_LENGTH)
    tokens = tokenize(source)
    try:
        return Parser(tokens).parse()
    except RecursionError:
        raise CalcError("表达式嵌套过深", 0) from None


# ---------------------------------------------------------------------------
# Evaluation


_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "phi": (1 + math.sqrt(5)) / 2,
}


_LOG10_2 = 0.3010299956639812


def _decimal_digit_count(value: int) -> int:
    """Count decimal digits without converting a huge integer to a string.

    Python 3.11+ limits ``str()`` on integers to 4300 digits by default, but
    the calculator allows larger intermediate results.  The bit length gives
    an estimate that is corrected with one or two exact powers of ten.
    """

    if value == 0:
        return 1
    digits = int((value.bit_length() - 1) * _LOG10_2) + 1
    power = 10**digits
    while value >= power:
        digits += 1
        power *= 10
    while value < power // 10:
        digits -= 1
        power //= 10
    return digits


def _format_big_integer(value: int, precision: int) -> str:
    sign = "-" if value < 0 else ""
    magnitude = abs(value)
    digits = _decimal_digit_count(magnitude)
    exponent = digits - 1
    keep = min(precision, digits)

    # At most ``precision`` (<= 17) digits; this conversion is always safe.
    if keep >= digits:
        return f"{sign}{magnitude}"

    scale = 10 ** (digits - keep)
    leading, remainder = divmod(magnitude, scale)
    if remainder * 2 >= scale:
        leading += 1
        if leading >= 10**keep:
            exponent += 1
            leading //= 10

    significant = str(leading).ljust(keep, "0").rstrip("0") or "0"
    if len(significant) == 1:
        mantissa = significant
    else:
        mantissa = significant[0] + "." + significant[1:]
    return f"{sign}{mantissa}e{exponent}"


def format_number(value: int | float, precision: int = 12) -> str:
    """Format a result without scientific noise for ordinary values."""

    precision = max(1, min(17, precision))

    if isinstance(value, int):
        if abs(value) < 10**16:
            return str(value)
        return _format_big_integer(value, precision)

    if isinstance(value, float):
        if not math.isfinite(value):
            return "∞" if value > 0 else "-∞"
        if value == 0:
            return "0"
        if value.is_integer() and abs(value) < 1e16:
            return str(int(value))
        text = format(value, f".{precision}g")
        text = re.sub(r"e([+-])0*(\d+)", lambda match: "e" + ("" if match.group(1) == "+" else "-") + match.group(2), text)
        if text.startswith("-0e"):
            text = text[1:]
        return text

    return str(value)


def _as_number(value: Any, position: int) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalcError("此处需要一个数字", position)
    if isinstance(value, float) and not math.isfinite(value):
        raise CalcError("数字超出可表示范围", position)
    return value


def _as_integer(value: Any, name: str, position: int) -> int:
    number = _as_number(value, position)
    if isinstance(number, float):
        if not number.is_integer():
            raise CalcError(f"{name} 需要整数", position)
        number = int(number)
    return int(number)


def _to_radians(value: int | float, angle_mode: str) -> float:
    number = float(value)
    return math.radians(number) if angle_mode == "deg" else number


def _from_radians(value: float, angle_mode: str) -> float:
    return math.degrees(value) if angle_mode == "deg" else value


@dataclass(frozen=True)
class FunctionSpec:
    minimum: int
    maximum: int | None
    callback: Callable[["_Evaluator", Sequence[int | float], int], int | float]


class _Evaluator:
    def __init__(self, calculator: "Calculator"):
        self.calculator = calculator

    def evaluate(self, node: Any) -> int | float:
        try:
            return self._evaluate(node)
        except RecursionError:
            raise CalcError("表达式嵌套过深", getattr(node, "position", 0)) from None

    def _evaluate(self, node: Any) -> int | float:
        if isinstance(node, NumberNode):
            return node.value

        if isinstance(node, NameNode):
            name = node.name
            if name == "ans":
                return self.calculator.ans
            if name in self.calculator.variables:
                return self.calculator.variables[name]
            lowered = name.lower()
            if lowered in _CONSTANTS:
                return _CONSTANTS[lowered]
            if lowered in FUNCTIONS:
                raise CalcError(f"函数 '{name}' 需要括号，例如 {name}(x)", node.position)
            raise CalcError(f"未知变量 '{name}'", node.position)

        if isinstance(node, UnaryNode):
            value = _as_number(self._evaluate(node.operand), node.position)
            return value if node.operator == "+" else -value

        if isinstance(node, FactorialNode):
            value = _as_integer(self._evaluate(node.operand), "阶乘", node.position)
            if value < 0:
                raise CalcError("阶乘只适用于非负整数", node.position)
            if value > MAX_FACTORIAL:
                raise CalcError(f"阶乘的最大输入是 {MAX_FACTORIAL}", node.position)
            return math.factorial(value)

        if isinstance(node, BinaryNode):
            left = _as_number(self._evaluate(node.left), node.position)
            right = _as_number(self._evaluate(node.right), node.position)
            try:
                if node.operator == "+":
                    value = left + right
                elif node.operator == "-":
                    value = left - right
                elif node.operator == "*":
                    value = left * right
                elif node.operator == "/":
                    if right == 0:
                        raise CalcError("不能除以 0", node.position)
                    value = left / right
                elif node.operator == "//":
                    if right == 0:
                        raise CalcError("不能除以 0", node.position)
                    if isinstance(left, int) and isinstance(right, int):
                        value = left // right
                    else:
                        # Python's float // corrects for representation error,
                        # so 1 // 0.1 is 9.  Use the same floor(left / right)
                        # rule as the web engine and ordinary calculators.
                        value = math.floor(left / right)
                elif node.operator == "%":
                    if right == 0:
                        raise CalcError("不能对 0 取模", node.position)
                    value = left % right
                elif node.operator == "^":
                    value = _power(left, right, node.position)
                else:
                    raise CalcError(f"不支持的运算符 '{node.operator}'", node.position)
            except CalcError:
                raise
            except ZeroDivisionError:
                raise CalcError("不能除以 0", node.position) from None
            except OverflowError:
                raise CalcError("结果超出范围", node.position) from None
            except ValueError:
                raise CalcError("数学域错误", node.position) from None

            return _check_result(value, node.position)

        if isinstance(node, CallNode):
            specification = FUNCTIONS.get(node.name.lower())
            if specification is None:
                lowered = node.name.lower()
                if lowered in _CONSTANTS:
                    raise CalcError(f"'{node.name}' 是常量，不是函数", node.position)
                if node.name in self.calculator.variables:
                    raise CalcError(f"'{node.name}' 是变量，不是函数", node.position)
                raise CalcError(f"未知函数 '{node.name}'", node.position)

            count = len(node.arguments)
            if count < specification.minimum or (
                specification.maximum is not None and count > specification.maximum
            ):
                if specification.maximum == specification.minimum:
                    expected = f"{specification.minimum}"
                elif specification.maximum is None:
                    expected = f"至少 {specification.minimum}"
                else:
                    expected = f"{specification.minimum} 到 {specification.maximum}"
                raise CalcError(
                    f"函数 {node.name} 需要 {expected} 个参数，收到 {count} 个",
                    node.position,
                )

            arguments = [
                _as_number(self._evaluate(argument), node.position) for argument in node.arguments
            ]
            try:
                value = specification.callback(self, arguments, node.position)
            except CalcError:
                raise
            except ZeroDivisionError:
                raise CalcError("不能除以 0", node.position) from None
            except OverflowError:
                raise CalcError("结果超出范围", node.position) from None
            except ValueError:
                raise CalcError(f"函数 {node.name} 在实数范围内无定义", node.position) from None
            return _check_result(value, node.position)

        raise CalcError("内部解析错误", getattr(node, "position", 0))


def _check_result(value: Any, position: int) -> int | float:
    if isinstance(value, complex):
        raise CalcError("暂不支持复数结果", position)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalcError("计算结果不是数字", position)
    if isinstance(value, float) and not math.isfinite(value):
        raise CalcError("结果超出范围", position)
    if isinstance(value, int) and value.bit_length() > MAX_RESULT_BITS:
        raise CalcError("结果过大", position)
    return value


def _power(left: int | float, right: int | float, position: int) -> int | float:
    if isinstance(left, int) and isinstance(right, int):
        if right > MAX_INTEGER_EXPONENT:
            raise CalcError(f"指数过大（最大 {MAX_INTEGER_EXPONENT}）", position)
        if right > 0 and left not in (0, 1, -1):
            estimated_bits = max(1, abs(left).bit_length()) * right
            if estimated_bits > MAX_RESULT_BITS:
                raise CalcError("结果过大", position)
        if right < 0 and left == 0:
            raise CalcError("不能除以 0", position)

    try:
        return left**right
    except ZeroDivisionError:
        raise CalcError("不能除以 0", position) from None
    except OverflowError:
        raise CalcError("结果超出范围", position) from None
    except ValueError:
        raise CalcError("幂运算的输入无效", position) from None


# ---------------------------------------------------------------------------
# Built-in scientific functions


def _require_integer_arguments(name: str, arguments: Sequence[int | float], position: int) -> list[int]:
    values: list[int] = []
    for argument in arguments:
        if isinstance(argument, float):
            if not argument.is_integer():
                raise CalcError(f"{name} 需要整数参数", position)
            argument = int(argument)
        values.append(int(argument))
    return values


def _fn_sin(evaluator: _Evaluator, args: Sequence[int | float], position: int) -> float:
    return math.sin(_to_radians(args[0], evaluator.calculator.angle_mode))


def _fn_cos(evaluator: _Evaluator, args: Sequence[int | float], position: int) -> float:
    return math.cos(_to_radians(args[0], evaluator.calculator.angle_mode))


def _fn_tan(evaluator: _Evaluator, args: Sequence[int | float], position: int) -> float:
    return math.tan(_to_radians(args[0], evaluator.calculator.angle_mode))


def _fn_asin(evaluator: _Evaluator, args: Sequence[int | float], position: int) -> float:
    return _from_radians(math.asin(args[0]), evaluator.calculator.angle_mode)


def _fn_acos(evaluator: _Evaluator, args: Sequence[int | float], position: int) -> float:
    return _from_radians(math.acos(args[0]), evaluator.calculator.angle_mode)


def _fn_atan(evaluator: _Evaluator, args: Sequence[int | float], position: int) -> float:
    return _from_radians(math.atan(args[0]), evaluator.calculator.angle_mode)


def _fn_atan2(evaluator: _Evaluator, args: Sequence[int | float], position: int) -> float:
    return _from_radians(math.atan2(args[0], args[1]), evaluator.calculator.angle_mode)


def _fn_sec(evaluator: _Evaluator, args: Sequence[int | float], position: int) -> float:
    cosine = math.cos(_to_radians(args[0], evaluator.calculator.angle_mode))
    if cosine == 0:
        raise CalcError("sec 在该点无定义", position)
    return 1 / cosine


def _fn_csc(evaluator: _Evaluator, args: Sequence[int | float], position: int) -> float:
    sine = math.sin(_to_radians(args[0], evaluator.calculator.angle_mode))
    if sine == 0:
        raise CalcError("csc 在该点无定义", position)
    return 1 / sine


def _fn_cot(evaluator: _Evaluator, args: Sequence[int | float], position: int) -> float:
    tangent = math.tan(_to_radians(args[0], evaluator.calculator.angle_mode))
    if tangent == 0:
        raise CalcError("cot 在该点无定义", position)
    return 1 / tangent


def _fn_sqrt(arguments: Sequence[int | float], position: int) -> int | float:
    value = arguments[0]
    if value < 0:
        raise CalcError("sqrt 在实数范围内无定义", position)

    # math.sqrt converts its argument to float, so a large integer such as
    # 10**600 overflows even though its square root (10**300) is representable.
    if isinstance(value, int) and value.bit_length() > 1023:
        root = math.isqrt(value)
        if root * root == value:
            return root
        try:
            return math.exp(math.log(value) / 2)
        except OverflowError:
            raise CalcError("sqrt 的结果超出范围", position) from None

    return math.sqrt(value)


def _fn_cbrt(arguments: Sequence[int | float], position: int) -> float:
    value = arguments[0]
    if value == 0:
        return 0.0

    magnitude = abs(value)
    if isinstance(value, int) and magnitude.bit_length() > 1023:
        try:
            root = math.exp(math.log(magnitude) / 3)
        except OverflowError:
            raise CalcError("cbrt 的结果超出范围", position) from None
    else:
        root = magnitude ** (1 / 3)
    # Do not pass a huge int to math.copysign: it would convert it to float.
    return -root if value < 0 else root


def _fn_ln(arguments: Sequence[int | float], position: int) -> float:
    if arguments[0] <= 0:
        raise CalcError("ln 的定义域是正数", position)
    return math.log(arguments[0])


def _fn_log(arguments: Sequence[int | float], position: int) -> float:
    if len(arguments) == 1:
        base = 10
        value = arguments[0]
    else:
        value = arguments[0]
        base = arguments[1]
    if value <= 0:
        raise CalcError("log 的真数必须为正数", position)
    if base <= 0 or base == 1:
        raise CalcError("log 的底数必须为正数且不等于 1", position)
    if base == 10:
        return math.log10(value)
    if base == 2:
        return math.log2(value)
    return math.log(value, base)


def _fn_log2(arguments: Sequence[int | float], position: int) -> float:
    if arguments[0] <= 0:
        raise CalcError("log2 的定义域是正数", position)
    return math.log2(arguments[0])


def _fn_log10(arguments: Sequence[int | float], position: int) -> float:
    if arguments[0] <= 0:
        raise CalcError("log10 的定义域是正数", position)
    return math.log10(arguments[0])


def _round_half_ceiling(value: int | float, digits: int) -> int | float:
    """Match JavaScript's ``Math.round`` (ties go toward positive infinity).

    Decimal string shifting avoids binary floating-point surprises such as
    ``1.005 * 100 == 100.49999999999999``.
    """

    if isinstance(value, int):
        if digits >= 0:
            return value
        factor = 10 ** (-digits)
        quotient, remainder = divmod(value, factor)
        if remainder * 2 >= factor:
            quotient += 1
        return quotient * factor

    if value == 0:
        return 0

    if value.is_integer():
        if digits > 0:
            return value
        if abs(value) < 1e16:
            return int(value)

    with localcontext() as context:
        context.prec = max(40, abs(digits) + 30)
        shifted = Decimal(str(value)).scaleb(digits)
        floored = shifted.to_integral_value(rounding=ROUND_FLOOR)
        if shifted - floored >= Decimal("0.5"):
            floored += 1
        result = floored.scaleb(-digits)

    return int(result) if digits <= 0 else float(result)


def _fn_round(arguments: Sequence[int | float], position: int) -> int | float:
    if len(arguments) == 1:
        return _round_half_ceiling(arguments[0], 0)
    digits = _as_integer(arguments[1], "round 的精度", position)
    if digits < -15 or digits > 15:
        raise CalcError("round 的精度必须在 -15 到 15 之间", position)
    return _round_half_ceiling(arguments[0], digits)


def _fn_factorial(arguments: Sequence[int | float], position: int) -> int:
    value = _as_integer(arguments[0], "阶乘", position)
    if value < 0:
        raise CalcError("阶乘只适用于非负整数", position)
    if value > MAX_FACTORIAL:
        raise CalcError(f"阶乘的最大输入是 {MAX_FACTORIAL}", position)
    return math.factorial(value)


def _fn_gcd(arguments: Sequence[int | float], position: int) -> int:
    values = _require_integer_arguments("gcd", arguments, position)
    return math.gcd(*values)


def _fn_lcm(arguments: Sequence[int | float], position: int) -> int:
    values = _require_integer_arguments("lcm", arguments, position)
    return math.lcm(*values)


def _fn_min(arguments: Sequence[int | float], position: int) -> int | float:
    return min(arguments)


def _fn_max(arguments: Sequence[int | float], position: int) -> int | float:
    return max(arguments)


def _fn_pow(evaluator: _Evaluator, arguments: Sequence[int | float], position: int) -> int | float:
    return _power(arguments[0], arguments[1], position)


def _fn_mod(arguments: Sequence[int | float], position: int) -> int | float:
    if arguments[1] == 0:
        raise CalcError("不能对 0 取模", position)
    return arguments[0] % arguments[1]


FUNCTIONS: dict[str, FunctionSpec] = {
    "sin": FunctionSpec(1, 1, _fn_sin),
    "cos": FunctionSpec(1, 1, _fn_cos),
    "tan": FunctionSpec(1, 1, _fn_tan),
    "sec": FunctionSpec(1, 1, _fn_sec),
    "csc": FunctionSpec(1, 1, _fn_csc),
    "cot": FunctionSpec(1, 1, _fn_cot),
    "asin": FunctionSpec(1, 1, _fn_asin),
    "arcsin": FunctionSpec(1, 1, _fn_asin),
    "acos": FunctionSpec(1, 1, _fn_acos),
    "arccos": FunctionSpec(1, 1, _fn_acos),
    "atan": FunctionSpec(1, 1, _fn_atan),
    "arctan": FunctionSpec(1, 1, _fn_atan),
    "atan2": FunctionSpec(2, 2, _fn_atan2),
    "sinh": FunctionSpec(1, 1, lambda _e, a, _p: math.sinh(a[0])),
    "cosh": FunctionSpec(1, 1, lambda _e, a, _p: math.cosh(a[0])),
    "tanh": FunctionSpec(1, 1, lambda _e, a, _p: math.tanh(a[0])),
    "asinh": FunctionSpec(1, 1, lambda _e, a, _p: math.asinh(a[0])),
    "acosh": FunctionSpec(1, 1, lambda _e, a, _p: math.acosh(a[0])),
    "atanh": FunctionSpec(1, 1, lambda _e, a, _p: math.atanh(a[0])),
    "sqrt": FunctionSpec(1, 1, lambda _e, a, p: _fn_sqrt(a, p)),
    "cbrt": FunctionSpec(1, 1, lambda _e, a, p: _fn_cbrt(a, p)),
    "exp": FunctionSpec(1, 1, lambda _e, a, _p: math.exp(a[0])),
    "ln": FunctionSpec(1, 1, lambda _e, a, p: _fn_ln(a, p)),
    "log": FunctionSpec(1, 2, lambda _e, a, p: _fn_log(a, p)),
    "log2": FunctionSpec(1, 1, lambda _e, a, p: _fn_log2(a, p)),
    "log10": FunctionSpec(1, 1, lambda _e, a, p: _fn_log10(a, p)),
    "abs": FunctionSpec(1, 1, lambda _e, a, _p: abs(a[0])),
    "sign": FunctionSpec(1, 1, lambda _e, a, _p: (a[0] > 0) - (a[0] < 0)),
    "floor": FunctionSpec(1, 1, lambda _e, a, _p: math.floor(a[0])),
    "ceil": FunctionSpec(1, 1, lambda _e, a, _p: math.ceil(a[0])),
    "round": FunctionSpec(1, 2, lambda _e, a, p: _fn_round(a, p)),
    "trunc": FunctionSpec(1, 1, lambda _e, a, _p: math.trunc(a[0])),
    "factorial": FunctionSpec(1, 1, lambda _e, a, p: _fn_factorial(a, p)),
    "fact": FunctionSpec(1, 1, lambda _e, a, p: _fn_factorial(a, p)),
    "min": FunctionSpec(1, None, lambda _e, a, p: _fn_min(a, p)),
    "max": FunctionSpec(1, None, lambda _e, a, p: _fn_max(a, p)),
    "gcd": FunctionSpec(2, None, lambda _e, a, p: _fn_gcd(a, p)),
    "lcm": FunctionSpec(2, None, lambda _e, a, p: _fn_lcm(a, p)),
    "hypot": FunctionSpec(2, None, lambda _e, a, _p: math.hypot(*a)),
    "pow": FunctionSpec(2, 2, lambda _e, a, p: _fn_pow(_e, a, p)),
    "mod": FunctionSpec(2, 2, lambda _e, a, p: _fn_mod(a, p)),
}


# ---------------------------------------------------------------------------
# Public engine API


@dataclass(frozen=True)
class HistoryEntry:
    source: str
    text: str
    assignment: str | None = None


@dataclass(frozen=True)
class CalcResult:
    source: str
    value: int | float
    text: str
    assignment: str | None = None

    @property
    def output(self) -> str:
        if self.assignment:
            return f"{self.assignment} = {self.text}"
        return self.text


class Calculator:
    """Stateful calculator session used by the REPL and library users."""

    def __init__(self, angle_mode: str = "rad", precision: int = 12):
        self.variables: dict[str, int | float] = {}
        self.history: list[HistoryEntry] = []
        self.ans: int | float = 0
        self._angle_mode = "rad"
        self._precision = 12
        self.set_angle_mode(angle_mode)
        self.set_precision(precision)

    @property
    def angle_mode(self) -> str:
        return self._angle_mode

    @property
    def precision(self) -> int:
        return self._precision

    def set_angle_mode(self, mode: str) -> None:
        if mode not in ("rad", "deg"):
            raise ValueError("angle mode must be 'rad' or 'deg'")
        self._angle_mode = mode

    def set_precision(self, precision: int) -> None:
        if not 1 <= precision <= 17:
            raise ValueError("precision must be between 1 and 17")
        self._precision = precision

    def clear(self) -> None:
        self.variables.clear()
        self.history.clear()
        self.ans = 0

    def evaluate(self, source: str, *, record: bool = True) -> CalcResult:
        source = source.strip()
        if not source:
            raise CalcError("表达式为空", 0)
        if len(source) > MAX_SOURCE_LENGTH:
            raise CalcError(f"表达式过长（最多 {MAX_SOURCE_LENGTH} 个字符）", MAX_SOURCE_LENGTH)

        assignment: str | None = None
        expression = source
        offset = 0
        match = _ASSIGNMENT_RE.match(source)
        if match:
            assignment = match.group(1)
            expression = match.group(2)
            offset = match.start(2)
            lowered = assignment.lower()
            if lowered == "ans" or lowered in _CONSTANTS or lowered in FUNCTIONS:
                raise CalcError(f"不能使用保留名称 '{assignment}' 作为变量名", match.start(1))

        try:
            tree = parse_expression(expression)
        except CalcError as error:
            if error.position is not None:
                error.position += offset
            raise

        try:
            value = _Evaluator(self).evaluate(tree)
        except CalcError as error:
            if error.position is not None:
                error.position += offset
            raise

        text = format_number(value, self.precision)

        if record:
            if assignment is not None:
                self.variables[assignment] = value
            self.ans = value
            self.history.append(HistoryEntry(source, text, assignment))

        return CalcResult(source, value, text, assignment)
