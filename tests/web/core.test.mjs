import test from "node:test";
import assert from "node:assert/strict";

import { CalcError, Calculator, formatNumber } from "../../docs/core.js";

function evaluate(expression, options = {}) {
  const calculator = new Calculator(options);
  return calculator.evaluate(expression);
}

test("arithmetic precedence", () => {
  assert.equal(evaluate("1 + 2 * 3").value, 7);
  assert.equal(evaluate("(1 + 2) * 3").value, 9);
  assert.equal(evaluate("10 // 4").value, 2);
  assert.equal(evaluate("10 % 4").value, 2);
  assert.equal(evaluate("1 // 0.1").value, 10);
  assert.equal(evaluate("3 // 0.1").value, 30);
  assert.equal(evaluate("-3 // 0.1").value, -30);
});

test("power is right-associative and binds before unary", () => {
  assert.equal(evaluate("2^3^2").value, 512);
  assert.equal(evaluate("-2^2").value, -4);
  assert.equal(evaluate("(-2)^2").value, 4);
  assert.equal(evaluate("2^-3").value, 0.125);
  assert.equal(evaluate("2**8").value, 256);
});

test("implicit multiplication", () => {
  assert.equal(evaluate("3(4 + 1)").value, 15);
  assert.equal(evaluate("(2 + 1)(4 + 1)").value, 15);
  assert.equal(evaluate("2√9").value, 6);
  assert.ok(Math.abs(evaluate("2π").value - Math.PI * 2) < 1e-12);
});

test("scientific functions", () => {
  assert.ok(Math.abs(evaluate("sin(pi/2)").value - 1) < 1e-12);
  assert.equal(evaluate("log(1000)").value, 3);
  assert.equal(evaluate("log(8, 2)").value, 3);
  assert.equal(evaluate("5!").value, 120);
  assert.equal(evaluate("sqrt(16) + cbrt(27)").value, 7);
  assert.equal(evaluate("max(1, 5, 3)").value, 5);
  assert.equal(evaluate("gcd(24, 36)").value, 12);
  assert.equal(evaluate("lcm(6, 8)").value, 24);
});

test("rounding uses decimal half-ceiling", () => {
  assert.equal(evaluate("round(2.5)").value, 3);
  assert.equal(evaluate("round(3.5)").value, 4);
  assert.equal(evaluate("round(-2.5)").value, -2);
  assert.equal(evaluate("round(1.005, 2)").value, 1.01);
  assert.equal(evaluate("round(2.675, 2)").value, 2.68);
  assert.equal(evaluate("round(125, -1)").value, 130);
  assert.equal(evaluate("round(-125, -1)").value, -120);
});

test("degree mode", () => {
  assert.ok(Math.abs(evaluate("sin(30)", { angleMode: "deg" }).value - 0.5) < 1e-12);
  assert.ok(Math.abs(evaluate("asin(0.5)", { angleMode: "deg" }).value - 30) < 1e-10);
});

test("variables and ans", () => {
  const calculator = new Calculator();
  assert.equal(calculator.evaluate("x = 2^10").value, 1024);
  assert.equal(calculator.evaluate("x / 4").value, 256);
  assert.equal(calculator.evaluate("ans + 1").value, 257);
  assert.equal(calculator.variables.x, 1024);
});

test("unicode input", () => {
  assert.equal(evaluate("10 × 3 ÷ 2 − 1").value, 14);
  assert.ok(Math.abs(evaluate("π").value - Math.PI) < 1e-12);
  assert.equal(evaluate("√(16)").value, 4);
});

test("formatting numbers", () => {
  assert.equal(formatNumber(0.1 + 0.2), "0.3");
  assert.equal(formatNumber(1 / 3), "0.333333333333");
  assert.equal(formatNumber(1.0), "1");
  assert.equal(formatNumber(-0), "0");
  assert.equal(formatNumber(1e20), "1e20");
  assert.equal(formatNumber(1e-9), "1e-9");
  assert.equal(formatNumber(Math.PI, 5), "3.1416");
});

test("division by zero and modulo zero", () => {
  assert.throws(() => evaluate("1/0"), (error) => error instanceof CalcError && error.message.includes("不能除以 0"));
  assert.throws(() => evaluate("1%0"), (error) => error instanceof CalcError && error.message.includes("取模"));
});

test("domain errors", () => {
  assert.throws(() => evaluate("sqrt(-1)"), /sqrt/);
  assert.throws(() => evaluate("ln(0)"), /ln/);
  assert.throws(() => evaluate("(-1)!"), /阶乘/);
});

test("syntax errors include positions", () => {
  assert.throws(
    () => evaluate("1.2.3"),
    (error) => error instanceof CalcError && Number.isInteger(error.position)
  );
  assert.throws(() => evaluate("(1 + 2"), /缺少右括号/);
  assert.throws(() => evaluate("missing + 1"), /未知变量/);
  assert.throws(() => evaluate("2 3"), /意外的标记/);
});

test("reserved names cannot be assigned", () => {
  for (const name of ["pi", "sin", "ans"]) {
    assert.throws(() => evaluate(`${name} = 1`), /保留名称/);
  }
});

test("recording can be disabled", () => {
  const calculator = new Calculator();
  calculator.evaluate("1+1");
  const preview = calculator.evaluate("x = 9", { record: false });
  assert.equal(preview.value, 9);
  assert.equal(calculator.ans, 2);
  assert.equal(calculator.variables.x, undefined);
});

test("long input is rejected", () => {
  assert.throws(() => evaluate("1".repeat(1001)), /过长/);
});
