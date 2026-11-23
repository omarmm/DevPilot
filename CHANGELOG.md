## 0.3.4-preview

- Add MySQL account setup for local GUI database clients.
- Use privileged socket authentication without changing root credentials or saving passwords.
- Default to one-database privileges; make local-admin privileges an explicit choice.

# Changelog

All notable DevPilot preview releases are documented here.

## Unreleased

### Fixed
- Desktop and application-menu launchers now use a stable per-user installed copy instead of the source checkout path, avoiding stale working-directory errors after the repository is moved.
- GitHub CLI installation now runs in the background with a visible indeterminate progress indicator and completion/error feedback.
- Git profile rows now display per-account GitHub CLI authentication status and can be refreshed from the UI.

### Fixed
- Desktop shortcut creation now always creates the XDG Desktop directory when needed, writes a directly executable `DevPilot.desktop` launcher with an explicit working directory, and provides a manual **Create Desktop Shortcut** action with the resulting paths.

### Added
- Added a **Set up HTTPS authentication** action for HTTPS Git profiles. It launches GitHub CLI's browser/device sign-in, configures Git's credential helper, and verifies the authenticated GitHub username matches the selected profile without collecting passwords or tokens.

### Fixed
- Applying a Git profile now detects the repository from which DevPilot was launched and writes the selected commit author name and email to that repository's local Git configuration.
- Added a project-folder picker for cases where DevPilot was launched outside the target repository.
- Verifies the resulting local Git identity and backs up the target repository's `.git/config` before changing it; restores the saved file if applying or verification fails.

## [0.3.0-preview] - 2026-11-20

### Added
- Dedicated **Database Servers** tab for MySQL, MariaDB, PostgreSQL, and Redis.
- APT package installation and upgrade actions for database servers.
- Systemd service status, start, stop, restart, enable-at-boot, and disable-at-boot controls.
- Detection of manually launched database server processes, including PID, port, data directory, and socket when available.
- Default-port and MySQL/MariaDB conflict checks before installation or service start.
- Automated tests for server catalog conflicts and unmanaged process detection.

### Safety
- Unmanaged database processes are displayed read-only; DevPilot does not stop or alter them.
- Package/service actions require explicit confirmation and privileged authorization.
- Existing client tools remain separate from server packages.


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
