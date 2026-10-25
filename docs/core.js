/**
 * SciCalc web core — a dependency-free scientific expression engine.
 *
 * This module intentionally avoids `eval` and `Function`.  It is shared by the
 * GitHub Pages UI and the Node test suite.
 */

export const MAX_SOURCE_LENGTH = 1000;
export const MAX_FACTORIAL = 170;

export class CalcError extends Error {
  constructor(message, position = null) {
    super(message);
    this.name = "CalcError";
    this.message = message;
    this.position = position;
  }
}

const CHAR_MAP = {
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
  "％": "%"
};

const IDENT_START = /[\p{L}_]/u;
const IDENT_PART = /[\p{L}\p{N}_]/u;

const CONSTANTS = {
  pi: Math.PI,
  e: Math.E,
  tau: Math.PI * 2,
  phi: (1 + Math.sqrt(5)) / 2
};

const ASSIGNMENT = /^\s*([\p{L}_][\p{L}\p{N}_]*)\s*=(?!=)/u;

function normalise(source) {
  let output = "";
  for (const char of source) {
    output += CHAR_MAP[char] ?? char;
  }
  return output;
}

function token(kind, value, text, position) {
  return { kind, value, text, position };
}

export function tokenize(source) {
  const text = normalise(source);
  const tokens = [];
  let index = 0;

  while (index < text.length) {
    const char = text[index];

    if (/\s/u.test(char)) {
      index += 1;
      continue;
    }

    if (/[0-9]/u.test(char) || (char === "." && /[0-9]/u.test(text[index + 1] ?? ""))) {
      const start = index;
      while (/[0-9]/u.test(text[index] ?? "")) index += 1;

      if (text[index] === ".") {
        index += 1;
        while (/[0-9]/u.test(text[index] ?? "")) index += 1;
      }

      if (text[index] === "e" || text[index] === "E") {
        const exponentStart = index;
        let probe = index + 1;
        if (text[probe] === "+" || text[probe] === "-") probe += 1;
        if (/[0-9]/u.test(text[probe] ?? "")) {
          index = probe + 1;
          while (/[0-9]/u.test(text[index] ?? "")) index += 1;
        } else {
          index = exponentStart;
        }
      }

      const raw = text.slice(start, index);
      const value = Number(raw);
      if (!Number.isFinite(value)) {
        throw new CalcError("数字超出可表示范围", start);
      }
      tokens.push(token("number", value, raw, start));
      continue;
    }

    if (char === "π" || char === "τ" || char === "√") {
      if (char === "√") {
        tokens.push(token("sqrt", "sqrt", char, index));
      } else {
        tokens.push(token("name", char === "π" ? "pi" : "tau", char, index));
      }
      index += 1;
      continue;
    }

    if (IDENT_START.test(char)) {
      const start = index;
      index += 1;
      while (index < text.length && IDENT_PART.test(text[index])) index += 1;
      const name = text.slice(start, index);
      tokens.push(token("name", name, name, start));
      continue;
    }

    if (text.startsWith("**", index)) {
      tokens.push(token("op", "^", "**", index));
      index += 2;
      continue;
    }

    if (text.startsWith("//", index)) {
      tokens.push(token("op", "//", "//", index));
      index += 2;
      continue;
    }

    if ("+-*/%^".includes(char)) {
      tokens.push(token("op", char, char, index));
      index += 1;
      continue;
    }

    if (char === "!") {
      tokens.push(token("factorial", "!", "!", index));
      index += 1;
      continue;
    }

    if (char === "(") {
      tokens.push(token("lparen", "(", "(", index));
      index += 1;
      continue;
    }

    if (char === ")") {
      tokens.push(token("rparen", ")", ")", index));
      index += 1;
      continue;
    }

    if (char === ",") {
      tokens.push(token("comma", ",", ",", index));
      index += 1;
      continue;
    }

    throw new CalcError(`无法识别的字符 '${char}'`, index);
  }

  tokens.push(token("eof", null, "", text.length));
  return tokens;
}

class Parser {
  constructor(tokens) {
    this.tokens = tokens;
    this.index = 0;
  }

  get current() {
    return this.tokens[this.index];
  }

  get previous() {
    return this.tokens[this.index - 1];
  }

  advance() {
    const current = this.current;
    if (current.kind !== "eof") this.index += 1;
    return current;
  }

  match(kind, value = undefined) {
    const current = this.current;
    if (current.kind === kind && (value === undefined || current.value === value)) {
      this.advance();
      return current;
    }
    return null;
  }

  expect(kind, message) {
    if (this.current.kind === kind) return this.advance();
    throw new CalcError(message, this.current.position);
  }

  parse() {
    if (this.current.kind === "eof") throw new CalcError("表达式为空", this.current.position);
    const node = this.parseExpression();
    if (this.current.kind !== "eof") {
      throw new CalcError(`意外的标记 '${this.current.text}'`, this.current.position);
    }
    return node;
  }

  parseExpression() {
    let node = this.parseTerm();
    while (this.current.kind === "op" && (this.current.value === "+" || this.current.value === "-")) {
      const operator = this.advance();
      const right = this.parseTerm();
      node = { type: "binary", operator: operator.value, left: node, right, position: operator.position };
    }
    return node;
  }

  implicitMultiplicationAllowed(endKind) {
    const nextKind = this.current.kind;
    if (!["number", "name", "lparen", "sqrt"].includes(nextKind)) return false;
    if (endKind === "number") {
      return ["name", "lparen", "sqrt"].includes(nextKind);
    }
    return endKind === "name" || endKind === "rparen";
  }

  parseTerm() {
    let node = this.parseUnary();
    while (true) {
      const current = this.current;
      if (current.kind === "op" && ["*", "/", "//", "%"].includes(current.value)) {
        this.advance();
        const right = this.parseUnary();
        node = { type: "binary", operator: current.value, left: node, right, position: current.position };
        continue;
      }

      if (this.implicitMultiplicationAllowed(this.previous.kind)) {
        const position = current.position;
        const right = this.parseUnary();
        node = { type: "binary", operator: "*", left: node, right, position };
        continue;
      }
      return node;
    }
  }

  parseUnary() {
    const current = this.current;
    if (current.kind === "op" && (current.value === "+" || current.value === "-")) {
      this.advance();
      return { type: "unary", operator: current.value, operand: this.parseUnary(), position: current.position };
    }

    if (current.kind === "sqrt") {
      this.advance();
      return { type: "call", name: "sqrt", arguments: [this.parseUnary()], position: current.position };
    }

    return this.parsePower();
  }

  parsePower() {
    let node = this.parseFactorial();
    if (this.current.kind === "op" && this.current.value === "^") {
      const operator = this.advance();
      const right = this.parseUnary();
      node = { type: "binary", operator: "^", left: node, right, position: operator.position };
    }
    return node;
  }

  parseFactorial() {
    let node = this.parsePrimary();
    while (this.current.kind === "factorial") {
      const operator = this.advance();
      node = { type: "factorial", operand: node, position: operator.position };
    }
    return node;
  }

  parsePrimary() {
    const current = this.current;

    if (current.kind === "number") {
      this.advance();
      return { type: "number", value: current.value, position: current.position };
    }

    if (current.kind === "name") {
      this.advance();
      if (this.match("lparen")) {
        const args = [];
        if (this.current.kind !== "rparen") {
          while (true) {
            args.push(this.parseExpression());
            if (this.match("comma")) continue;
            break;
          }
        }
        this.expect("rparen", "函数调用缺少右括号");
        return { type: "call", name: current.value, arguments: args, position: current.position };
      }
      return { type: "name", name: current.value, position: current.position };
    }

    if (current.kind === "lparen") {
      this.advance();
      const node = this.parseExpression();
      this.expect("rparen", "缺少右括号");
      return node;
    }

    if (current.kind === "rparen") throw new CalcError("多余的右括号", current.position);
    if (current.kind === "comma") throw new CalcError("逗号只能用于函数参数之间", current.position);
    if (current.kind === "eof") throw new CalcError("表达式不完整", current.position);
    throw new CalcError(`意外的标记 '${current.text}'`, current.position);
  }
}

export function parseExpression(source) {
  if (source.length > MAX_SOURCE_LENGTH) {
    throw new CalcError(`表达式过长（最多 ${MAX_SOURCE_LENGTH} 个字符）`, MAX_SOURCE_LENGTH);
  }
  try {
    return new Parser(tokenize(source)).parse();
  } catch (error) {
    if (error instanceof RangeError) throw new CalcError("表达式嵌套过深", 0);
    throw error;
  }
}

function clampPrecision(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 12;
  return Math.max(1, Math.min(17, Math.trunc(number)));
}

export function formatNumber(value, precision = 12) {
  precision = clampPrecision(precision);
  if (typeof value !== "number" || Number.isNaN(value)) return "NaN";
  if (value === Infinity) return "∞";
  if (value === -Infinity) return "-∞";
  if (Object.is(value, -0) || value === 0) return "0";
  if (Number.isInteger(value) && Math.abs(value) < 1e16) return String(value);

  const rounded = Number(value.toPrecision(precision));
  if (rounded === 0) return "0";

  if (Math.abs(rounded) >= 1e-6 && Math.abs(rounded) < 1e16) {
    return String(rounded);
  }

  let text = rounded.toExponential(Math.max(0, precision - 1));
  text = text
    .replace(/(\.\d*?)0+e/, "$1e")
    .replace(/\.e/, "e")
    .replace(/e\+?(-?)0*(\d+)/, (_match, sign, digits) => `e${sign === "-" ? "-" : ""}${digits}`);
  return text;
}

const FUNCTIONS = new Map();

function defineFunction(name, minimum, maximum, callback) {
  FUNCTIONS.set(name, { minimum, maximum, callback });
}

function ensureNumber(value, position) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new CalcError("此处需要一个数字", position);
  }
  return value;
}

function ensureInteger(value, label, position) {
  const number = ensureNumber(value, position);
  if (!Number.isInteger(number)) throw new CalcError(`${label} 需要整数`, position);
  return number;
}

function toRadians(value, mode) {
  return mode === "deg" ? (value * Math.PI) / 180 : value;
}

function fromRadians(value, mode) {
  return mode === "deg" ? (value * 180) / Math.PI : value;
}

function finiteResult(value, position) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    throw new CalcError("数学域错误", position);
  }
  if (!Number.isFinite(value)) throw new CalcError("结果超出范围", position);
  return value;
}

function factorialValue(value, position) {
  const integer = ensureInteger(value, "阶乘", position);
  if (integer < 0) throw new CalcError("阶乘只适用于非负整数", position);
  if (integer > MAX_FACTORIAL) throw new CalcError(`阶乘的最大输入是 ${MAX_FACTORIAL}`, position);
  let result = 1;
  for (let index = 2; index <= integer; index += 1) result *= index;
  return finiteResult(result, position);
}

function powerValue(base, exponent, position) {
  if (base === 0 && exponent < 0) throw new CalcError("不能除以 0", position);
  if (!Number.isInteger(exponent) || exponent > 1000 || exponent < -1000) {
    const result = base ** exponent;
    return finiteResult(result, position);
  }
  const result = base ** exponent;
  return finiteResult(result, position);
}

function logValue(args, position) {
  let value;
  let base;
  if (args.length === 1) {
    value = args[0];
    base = 10;
  } else {
    value = args[0];
    base = args[1];
  }
  if (value <= 0) throw new CalcError("log 的真数必须为正数", position);
  if (base <= 0 || base === 1) throw new CalcError("log 的底数必须为正数且不等于 1", position);
  if (base === 10) return Math.log10(value);
  if (base === 2) return Math.log2(value);
  return Math.log(value) / Math.log(base);
}

function shiftDecimal(value, digits) {
  if (value === 0) return 0;
  const [mantissa, exponent] = value.toExponential().split("e");
  return Number(`${mantissa}e${Number(exponent) + digits}`);
}

function roundHalfCeiling(value, digits) {
  if (Number.isInteger(value) && digits >= 0) return value;
  const shifted = shiftDecimal(value, digits);
  if (!Number.isFinite(shifted)) return value;
  const rounded = Math.floor(shifted + 0.5);
  return shiftDecimal(rounded, -digits);
}

function roundValue(args, position) {
  if (args.length === 1) return roundHalfCeiling(args[0], 0);
  const digits = ensureInteger(args[1], "round 的精度", position);
  if (digits < -15 || digits > 15) throw new CalcError("round 的精度必须在 -15 到 15 之间", position);
  return roundHalfCeiling(args[0], digits);
}

defineFunction("sin", 1, 1, (args, evaluator, position) => Math.sin(toRadians(args[0], evaluator.calculator.angleMode)));
defineFunction("cos", 1, 1, (args, evaluator) => Math.cos(toRadians(args[0], evaluator.calculator.angleMode)));
defineFunction("tan", 1, 1, (args, evaluator) => Math.tan(toRadians(args[0], evaluator.calculator.angleMode)));
defineFunction("asin", 1, 1, (args, evaluator, position) => finiteResult(fromRadians(Math.asin(args[0]), evaluator.calculator.angleMode), position));
defineFunction("arcsin", 1, 1, (args, evaluator, position) => finiteResult(fromRadians(Math.asin(args[0]), evaluator.calculator.angleMode), position));
defineFunction("acos", 1, 1, (args, evaluator, position) => finiteResult(fromRadians(Math.acos(args[0]), evaluator.calculator.angleMode), position));
defineFunction("arccos", 1, 1, (args, evaluator, position) => finiteResult(fromRadians(Math.acos(args[0]), evaluator.calculator.angleMode), position));
defineFunction("atan", 1, 1, (args, evaluator) => fromRadians(Math.atan(args[0]), evaluator.calculator.angleMode));
defineFunction("arctan", 1, 1, (args, evaluator) => fromRadians(Math.atan(args[0]), evaluator.calculator.angleMode));
defineFunction("atan2", 2, 2, (args, evaluator) => fromRadians(Math.atan2(args[0], args[1]), evaluator.calculator.angleMode));
defineFunction("sinh", 1, 1, (args, _evaluator, position) => finiteResult(Math.sinh(args[0]), position));
defineFunction("cosh", 1, 1, (args, _evaluator, position) => finiteResult(Math.cosh(args[0]), position));
defineFunction("tanh", 1, 1, (args) => Math.tanh(args[0]));
defineFunction("asinh", 1, 1, (args) => Math.asinh(args[0]));
defineFunction("acosh", 1, 1, (args, _evaluator, position) => finiteResult(Math.acosh(args[0]), position));
defineFunction("atanh", 1, 1, (args, _evaluator, position) => finiteResult(Math.atanh(args[0]), position));
defineFunction("sec", 1, 1, (args, evaluator, position) => {
  const value = Math.cos(toRadians(args[0], evaluator.calculator.angleMode));
  if (value === 0) throw new CalcError("sec 在该点无定义", position);
  return finiteResult(1 / value, position);
});
defineFunction("csc", 1, 1, (args, evaluator, position) => {
  const value = Math.sin(toRadians(args[0], evaluator.calculator.angleMode));
  if (value === 0) throw new CalcError("csc 在该点无定义", position);
  return finiteResult(1 / value, position);
});
defineFunction("cot", 1, 1, (args, evaluator, position) => {
  const value = Math.tan(toRadians(args[0], evaluator.calculator.angleMode));
  if (value === 0) throw new CalcError("cot 在该点无定义", position);
  return finiteResult(1 / value, position);
});
defineFunction("sqrt", 1, 1, (args, _evaluator, position) => {
  if (args[0] < 0) throw new CalcError("sqrt 在实数范围内无定义", position);
  return Math.sqrt(args[0]);
});
defineFunction("cbrt", 1, 1, (args) => Math.cbrt(args[0]));
defineFunction("ln", 1, 1, (args, _evaluator, position) => {
  if (args[0] <= 0) throw new CalcError("ln 的定义域是正数", position);
  return Math.log(args[0]);
});
defineFunction("log", 1, 2, (args, _evaluator, position) => logValue(args, position));
defineFunction("log2", 1, 1, (args, _evaluator, position) => {
  if (args[0] <= 0) throw new CalcError("log2 的定义域是正数", position);
  return Math.log2(args[0]);
});
defineFunction("log10", 1, 1, (args, _evaluator, position) => {
  if (args[0] <= 0) throw new CalcError("log10 的定义域是正数", position);
  return Math.log10(args[0]);
});
defineFunction("exp", 1, 1, (args, _evaluator, position) => finiteResult(Math.exp(args[0]), position));
defineFunction("abs", 1, 1, (args) => Math.abs(args[0]));
defineFunction("sign", 1, 1, (args) => Math.sign(args[0]));
defineFunction("floor", 1, 1, (args) => Math.floor(args[0]));
defineFunction("ceil", 1, 1, (args) => Math.ceil(args[0]));
defineFunction("round", 1, 2, (args, _evaluator, position) => roundValue(args, position));
defineFunction("trunc", 1, 1, (args) => Math.trunc(args[0]));
defineFunction("factorial", 1, 1, (args, _evaluator, position) => factorialValue(args[0], position));
defineFunction("fact", 1, 1, (args, _evaluator, position) => factorialValue(args[0], position));
defineFunction("min", 1, null, (args) => Math.min(...args));
defineFunction("max", 1, null, (args) => Math.max(...args));
defineFunction("gcd", 2, null, (args, _evaluator, position) => {
  const values = args.map((value) => Math.abs(ensureInteger(value, "gcd", position)));
  const gcd = (a, b) => {
    while (b) [a, b] = [b, a % b];
    return a;
  };
  return values.reduce(gcd);
});
defineFunction("lcm", 2, null, (args, _evaluator, position) => {
  const values = args.map((value) => Math.abs(ensureInteger(value, "lcm", position)));
  const gcd = (a, b) => {
    while (b) [a, b] = [b, a % b];
    return a;
  };
  return values.reduce((a, b) => (a && b ? Math.abs(a * b) / gcd(a, b) : 0));
});
defineFunction("hypot", 2, null, (args) => Math.hypot(...args));
defineFunction("pow", 2, 2, (args, _evaluator, position) => powerValue(args[0], args[1], position));
defineFunction("mod", 2, 2, (args, _evaluator, position) => {
  if (args[1] === 0) throw new CalcError("不能对 0 取模", position);
  return ((args[0] % args[1]) + args[1]) % args[1];
});

class Evaluator {
  constructor(calculator) {
    this.calculator = calculator;
  }

  evaluate(node) {
    try {
      return this.visit(node);
    } catch (error) {
      if (error instanceof RangeError) throw new CalcError("表达式嵌套过深", node.position ?? 0);
      throw error;
    }
  }

  visit(node) {
    switch (node.type) {
      case "number":
        return node.value;

      case "name": {
        if (node.name === "ans") return this.calculator.ans;
        if (Object.prototype.hasOwnProperty.call(this.calculator.variables, node.name)) {
          return this.calculator.variables[node.name];
        }
        const lowered = node.name.toLowerCase();
        if (Object.prototype.hasOwnProperty.call(CONSTANTS, lowered)) return CONSTANTS[lowered];
        if (FUNCTIONS.has(lowered)) {
          throw new CalcError(`函数 '${node.name}' 需要括号，例如 ${node.name}(x)`, node.position);
        }
        throw new CalcError(`未知变量 '${node.name}'`, node.position);
      }

      case "unary": {
        const value = ensureNumber(this.visit(node.operand), node.position);
        return node.operator === "+" ? value : -value;
      }

      case "factorial":
        return factorialValue(this.visit(node.operand), node.position);

      case "binary": {
        const left = ensureNumber(this.visit(node.left), node.position);
        const right = ensureNumber(this.visit(node.right), node.position);
        let value;
        switch (node.operator) {
          case "+":
            value = left + right;
            break;
          case "-":
            value = left - right;
            break;
          case "*":
            value = left * right;
            break;
          case "/":
            if (right === 0) throw new CalcError("不能除以 0", node.position);
            value = left / right;
            break;
          case "//":
            if (right === 0) throw new CalcError("不能除以 0", node.position);
            value = Math.floor(left / right);
            break;
          case "%":
            if (right === 0) throw new CalcError("不能对 0 取模", node.position);
            value = ((left % right) + right) % right;
            break;
          case "^":
            value = powerValue(left, right, node.position);
            break;
          default:
            throw new CalcError(`不支持的运算符 '${node.operator}'`, node.position);
        }
        return finiteResult(value, node.position);
      }

      case "call": {
        const specification = FUNCTIONS.get(node.name.toLowerCase());
        if (!specification) {
          const lowered = node.name.toLowerCase();
          if (Object.prototype.hasOwnProperty.call(CONSTANTS, lowered)) {
            throw new CalcError(`'${node.name}' 是常量，不是函数`, node.position);
          }
          if (Object.prototype.hasOwnProperty.call(this.calculator.variables, node.name)) {
            throw new CalcError(`'${node.name}' 是变量，不是函数`, node.position);
          }
          throw new CalcError(`未知函数 '${node.name}'`, node.position);
        }

        const count = node.arguments.length;
        if (
          count < specification.minimum ||
          (specification.maximum !== null && count > specification.maximum)
        ) {
          let expected;
          if (specification.maximum === specification.minimum) {
            expected = String(specification.minimum);
          } else if (specification.maximum === null) {
            expected = `至少 ${specification.minimum}`;
          } else {
            expected = `${specification.minimum} 到 ${specification.maximum}`;
          }
          throw new CalcError(
            `函数 ${node.name} 需要 ${expected} 个参数，收到 ${count} 个`,
            node.position
          );
        }

        const arguments_ = node.arguments.map((argument) => ensureNumber(this.visit(argument), node.position));
        try {
          return finiteResult(specification.callback(arguments_, this, node.position), node.position);
        } catch (error) {
          if (error instanceof CalcError) throw error;
          if (error instanceof RangeError) throw new CalcError("表达式嵌套过深", node.position);
          throw new CalcError(`函数 ${node.name} 计算失败`, node.position);
        }
      }

      default:
        throw new CalcError("内部解析错误", node.position ?? 0);
    }
  }
}

export class Calculator {
  constructor({ angleMode = "rad", precision = 12 } = {}) {
    this.variables = Object.create(null);
    this.ans = 0;
    this.angleMode = angleMode === "deg" ? "deg" : "rad";
    this.precision = clampPrecision(precision);
  }

  setAngleMode(mode) {
    if (mode !== "rad" && mode !== "deg") throw new RangeError("angle mode must be rad or deg");
    this.angleMode = mode;
  }

  setPrecision(precision) {
    this.precision = clampPrecision(precision);
  }

  clear() {
    this.variables = Object.create(null);
    this.ans = 0;
  }

  evaluate(source, { record = true } = {}) {
    const original = String(source ?? "");
    if (!original.trim()) throw new CalcError("表达式为空", 0);
    if (original.length > MAX_SOURCE_LENGTH) {
      throw new CalcError(`表达式过长（最多 ${MAX_SOURCE_LENGTH} 个字符）`, MAX_SOURCE_LENGTH);
    }

    let expression = original.trim();
    let offset = original.indexOf(expression);
    let assignment = null;

    const match = expression.match(ASSIGNMENT);
    if (match) {
      assignment = match[1];
      const equalsIndex = expression.indexOf("=", match.index + match[0].length - 1);
      const afterEquals = expression.slice(equalsIndex + 1);
      const leading = (afterEquals.match(/^\s*/) ?? [""])[0].length;
      expression = afterEquals.slice(leading).trim();
      offset = original.indexOf(afterEquals) + leading;
      if (!expression) throw new CalcError("赋值号后面缺少表达式", offset);

      const lowered = assignment.toLowerCase();
      if (lowered === "ans" || Object.prototype.hasOwnProperty.call(CONSTANTS, lowered) || FUNCTIONS.has(lowered)) {
        throw new CalcError(`不能使用保留名称 '${assignment}' 作为变量名`, offset - (assignment.length + 1));
      }
    }

    let tree;
    try {
      tree = parseExpression(expression);
    } catch (error) {
      if (error instanceof CalcError && error.position !== null) error.position += offset;
      throw error;
    }

    let value;
    try {
      value = new Evaluator(this).evaluate(tree);
    } catch (error) {
      if (error instanceof CalcError && error.position !== null) error.position += offset;
      throw error;
    }

    const text = formatNumber(value, this.precision);
    if (record) {
      if (assignment) this.variables[assignment] = value;
      this.ans = value;
    }

    return {
      source: original,
      expression,
      value,
      text,
      assignment
    };
  }
}

export { CONSTANTS, FUNCTIONS };
