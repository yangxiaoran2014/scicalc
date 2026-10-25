# Changelog

All notable changes to SciCalc are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use
[Semantic Versioning](https://semver.org/).

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

[1.1.0]: https://github.com/yangxiaoran2014/scicalc/releases/tag/v1.1.0
[1.0.0]: https://github.com/yangxiaoran2014/scicalc/releases/tag/v1.0.0
