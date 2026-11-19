# Changelog

All notable DevPilot preview releases are documented here.

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
