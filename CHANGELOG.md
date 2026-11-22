# Changelog

All notable changes to SciCalc are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use
[Semantic Versioning](https://semver.org/).

## [1.2.0] - 2026-11-22

### Added

- Web live result preview while typing, debounced and non-recording.
- Web precision selector (1–17 significant digits) with local persistence.
- Web history search and per-variable delete buttons, plus a `del x` command.
- Desktop status bar with angle, precision, variable/history counts, and
  shortcut hints.
- Desktop F2 variable manager, `Ctrl+Shift+C` copy-result shortcut, and
  `Ctrl++` / `Ctrl+-` / `Ctrl+0` font zoom.
- `del <variable>` / `unset <variable>` and `history clear` commands in the
  CLI, desktop session, and web UI.
- Bounded calculation history (500 entries) to keep long sessions small.

### Changed

- Version bumped to 1.2.0.
- Desktop command help and README updated for the new shortcuts and commands.

## [1.1.1] - 2026-10-25

### Changed

- Version bumped to 1.1.1 for the bug-fix Windows release.

### Fixed

- Large integer results no longer crash number formatting on Python 3.11+.
- `sqrt` and `cbrt` handle large integer inputs without an unnecessary float
  overflow.
- The CLI accepts attached precision values such as `-p5`.
- `round` now uses the same decimal half-ceiling rule in the Python and web
  engines.
- Float floor division (`//`) matches the web engine, so `1 // 0.1` is `10`.
- Documented the different factorial limits of the desktop/CLI and web builds.

## [1.1.0] - 2026-10-25

### Added

- **SciCalc CMD** Windows desktop application with a command-prompt UI.
- Persistent input history, angle unit, precision, and window geometry under
  `%APPDATA%\SciCalcCMD\state.json`.
- Command history navigation (`↑` / `↓`), F7 history picker, Tab completion,
  F1 help, and terminal-style clipboard shortcuts.
- Dark native Windows title bar, custom icon, and a slim dark scrollbar.
- Standalone, console-free Windows executable built with PyInstaller.
- `scicalc-desktop` GUI entry point, `.pyw` launcher, and double-click `.cmd`
  launcher.
- Desktop command/session tests and Tkinter UI tests.
- "Windows" download link on the web calculator.

### Changed

- Version bumped to 1.1.0.
- README expanded with desktop installation, commands, shortcuts, packaging,
  security, and project structure documentation.
- Removed stale CI references from the README.

### Fixed

- Desktop `cls` correctly replaces the console with a single fresh prompt.
- Desktop editing keys cannot alter the prompt or scrollback.
- Oversized clipboard input is rejected instead of silently truncated.

## [1.0.0] - 2026-10-24

### Added

- Safe, zero-dependency Python CLI scientific calculator with REPL, one-shot
  execution, and pipeline input.
- Browser calculator with responsive dark/light UI and local history.
- Shared expression syntax: scientific functions, constants, implicit
  multiplication, variables, `ans`, and angle modes.
- Python and Node.js test suites.
- GitHub Pages deployment from `docs/`.

[1.2.0]: https://github.com/yangxiaoran2014/scicalc/releases/tag/v1.2.0
[1.1.1]: https://github.com/yangxiaoran2014/scicalc/releases/tag/v1.1.1
[1.1.0]: https://github.com/yangxiaoran2014/scicalc/releases/tag/v1.1.0
[1.0.0]: https://github.com/yangxiaoran2014/scicalc/releases/tag/v1.0.0
