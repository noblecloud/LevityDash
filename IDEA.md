<!--
Hermes agent entry point. Hermes reads this file as its project "idea" when a
workspace is created; nothing else in the repo consumes it. Other agents have
their own front doors — CLAUDE.md (Claude Code) and AGENTS.md (OpenCode /
DeepSeek) — and those two are the fuller, authoritative ones. Keep this short
and orienting; put anything load-bearing in CLAUDE.md and AGENTS.md so every
agent sees it, and keep those two roughly in sync.
-->

Desktop-native multi-source weather dashboard (Qt/PySide6, QGraphicsScene),
in daily use. Three folders, because they move together:

- Code/LevityDash — the app. Contains qolkit (generic utils) <- statekit
  (declarative state + YAML persistence, Qt-free) <- LevityDash. Dependency
  direction is strict; never import Qt or LevityDash from the lower two.
- Code/WeatherUnits — sibling library every displayed value is formatted
  through. LevityDash path-depends on it in develop mode, so changes here
  immediately affect the dashboard.
- Library/Application Support/LevityDash — the LIVE config: real dashboards
  (.levity YAML), plugin settings, API keys, cached observations. Editing or
  overwriting anything here affects the running app.

Read CLAUDE.md first — it covers architecture, run/test commands, and hard-won
gotchas (macOS Bluetooth/TCC, cross-thread Qt timers, StateProperty encoders,
CategoryItem source-vs-identity). docs/tasks/ holds handoff briefs for work
picked up in fresh sessions.

Current focus: dashboard design/layout iteration, plus a backlog of open bugs
tracked in docs/tasks/.

Also, it would be a good idea to familiarize yourself with the README and the docs in the /docs directory
