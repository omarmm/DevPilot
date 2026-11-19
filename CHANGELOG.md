# Changelog

All notable DevPilot preview releases are documented here.

## [0.2.0-preview] - 2026-11-20

### Added
- New **AI Agents** tab for OpenCode CLI, Claude Code, OpenAI Codex CLI, and GitHub Copilot CLI.
- Detects installed agent commands and displays their versions.
- Installs or updates agents using vendor-published Linux installer commands after user confirmation.
- Launches an installed agent in a new terminal at a chosen directory or registered workspace.
- Installer output and status feedback in the DevPilot interface.
- Static tests for the supported agent catalog and command mapping.

### Security and behavior
- Installer source URLs and exact commands are visible before confirmation.
- Agent installers run as the current user without `sudo`.
- DevPilot does not collect provider credentials; users authenticate in each agent after launch.
- GitHub Copilot CLI requires an eligible Copilot subscription.

## [0.1.0-preview] - 2026-11-20

### Added
- Initial public project packaging and documentation.
- Guided APT package status, install, and update interface.
- Project workspace creation and registration.
- Multiple Git identity profiles and workspace assignment.
- SSH Ed25519 key generation and per-profile host aliases.
- Git conditional includes for workspace-specific identities.
- Timestamped backups for managed Git and SSH configuration changes.
- Basic GitHub Actions Python syntax check.

### Known limitations
- Per-account HTTPS credential isolation is not implemented.
- Shell prompt integration and workspace move/rename are not implemented.
- Automated behavioral tests are not included yet.
