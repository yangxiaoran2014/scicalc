# SciCalc

一个同时提供 **命令行** 和 **网页** 两种形态的科学计算器。零第三方运行时依赖，安全解析表达式，不使用 `eval`。

<p align="center">
  <img src="docs/preview.png" alt="SciCalc 网页版桌面界面" width="780">
</p>

<p align="center">
  <img src="docs/preview-mobile.png" alt="SciCalc 网页版手机界面" width="230">
</p>

- **CLI**：交互式 REPL、单次执行、管道输入、变量、历史记录、角度制切换。
- **Web**：纯前端科学计算器，支持键盘输入、函数快捷键、历史、变量和浅色/深色主题。
- **共享能力**：三角函数、反三角函数、双曲函数、对数、指数、阶乘、隐式乘法、`ans` 与自定义变量。

在线体验：[https://yangxiaoran2014.github.io/scicalc/](https://yangxiaoran2014.github.io/scicalc/)

## 功能一览

| 能力 | CLI | Web |
| --- | :---: | :---: |
| 四则运算、幂、整除、取模、阶乘 | ✅ | ✅ |
| `sin/cos/tan`、反三角、双曲函数 | ✅ | ✅ |
| `ln/log/log2/log10`、`sqrt/cbrt/exp` | ✅ | ✅ |
| 角度制 / 弧度制 | ✅ | ✅ |
| 隐式乘法 `2π`、`3(4+1)` | ✅ | ✅ |
| 变量 `x = ...`、`ans` | ✅ | ✅ |
| 历史记录 | ✅ | ✅ 本地持久化 |
| 管道 / 脚本输入 | ✅ | — |
| 无网络、无账号、无追踪 | ✅ | ✅ |

## 命令行使用

需要 Python 3.10 或更高版本。

```bash
git clone https://github.com/yangxiaoran2014/scicalc.git
cd scicalc
python -m scicalc
```

也可以安装为命令：

```bash
python -m pip install .
scicalc
```

### 单次执行

```console
$ python -m scicalc "sin(pi / 2) + sqrt(16)"
5

$ python -m scicalc --degrees "sin(30) + asin(0.5)"
30.5

$ python -m scicalc -p 5 "1 / 3"
0.33333
```

表达式包含空格时建议加引号。以负号开头的表达式也可以直接写：

```bash
python -m scicalc -2^2 + 10
# 6
```

### 交互模式

```console
$ python -m scicalc
SciCalc 1.0.0
科学计算器  ·  RAD  ·  12 位有效数字
输入 :help 查看命令，:quit 退出。

sci[rad]> sin(pi / 2)
  = 1
sci[rad]> x = 2^10
  x = 1024
sci[rad]> x / 4
  = 256
sci[rad]> :deg
角度单位已切换为 DEG。
sci[deg]> sin(30)
  = 0.5
```

内置命令：

| 命令 | 说明 |
| --- | --- |
| `:help`, `:h` | 显示帮助 |
| `:quit`, `:q` | 退出 |
| `:clear` | 清除变量和历史 |
| `:vars`, `:v` | 查看变量 |
| `:history [n]` | 查看最近记录 |
| `:deg`, `:rad` | 切换角度单位 |
| `:precision N` | 设置有效数字（1–17） |
| `:mode` | 查看当前模式 |

### 管道与脚本

```bash
printf '2^10\nsqrt(81)\nx = 5\nx * 2\n' | python -m scicalc
```

每行一条表达式或命令；`#` 后可作为注释。遇到错误时会继续处理剩余行，并以非零状态码退出。

## 表达式语法

```text
+  -  *  /  //  %  ^  !  ( )
sin cos tan sec csc cot
asin acos atan atan2  (arcsin / arccos / arctan 也可)
sinh cosh tanh asinh acosh atanh
ln log log2 log10 exp
sqrt cbrt abs sign floor ceil round trunc
factorial fact min max gcd lcm hypot pow mod
pi π  e  tau τ  phi  ans
```

- `log(x)` 为常用对数，`log(x, b)` 可指定底数。
- 幂运算从右向左结合：`2^3^2 = 512`。
- 支持隐式乘法：`2π`、`3(4+1)`、`2sqrt(9)`、`2√9`。
- 赋值语法：`x = 2^10`，之后可使用 `x` 和 `ans`。
- 整数阶乘上限为 1000；CLI 支持大整数显示为科学计数法。
- 复数不在支持范围内。

## 网页版

网页源码在 [`docs/`](docs/) 中，完全静态，可直接由 GitHub Pages 托管，也可以本地预览：

```bash
python -m http.server 8000 --directory docs
# 打开 http://localhost:8000
```

网页计算引擎位于 [`docs/core.js`](docs/core.js)，与 UI 解耦并有独立的 Node.js 测试。它同样是手写解析器，不使用 `eval`。

## 测试

Python：

```bash
python -m unittest discover -s tests -v
```

网页引擎（Node.js 22+）：

```bash
node --test tests/web/core.test.mjs
```

## 项目结构

```text
.
├── scicalc/            # CLI 与计算引擎
│   ├── cli.py
│   ├── engine.py
│   └── __main__.py
├── docs/               # GitHub Pages 静态站点
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   └── core.js
├── tests/              # Python 测试 + 网页核心测试
├── .github/workflows/  # CI
├── pyproject.toml
└── README.md
```

## 安全说明

表达式由专用词法分析器和递归下降解析器处理，只接受数字、运算符、固定函数和常量。没有使用 Python `eval` 或 JavaScript `eval`/`Function`，网页端不会上传输入内容，所有计算都在浏览器本地完成。

## License

[MIT](LICENSE)
