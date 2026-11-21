# DevPilot

**Your Linux development environment, under control.**

DevPilot is a lightweight desktop utility for setting up and managing a Linux developer workstation. It brings development package management, project workspaces, multiple Git identities, SSH key profiles, safe configuration backups, and terminal AI coding agents into one guided interface.

> **Current status:** Early development / preview (`0.3.1-preview`). Features and configuration behavior may change.

## Features

### Development Setup
- Organizes common developer tools into practical package groups.
- Detects whether packages are installed, missing, or have updates available.
- Installs missing packages or updates selected packages through APT and `pkexec`.

### Database Servers
The dedicated **Database Servers** tab manages common local server packages and their system services:

| Server | APT package | Default service | Default port |
|---|---|---|---:|
| MySQL | `mysql-server` | `mysql` | 3306 |
| MariaDB | `mariadb-server` | `mariadb` | 3306 |
| PostgreSQL | `postgresql` | `postgresql` | 5432 |
| Redis | `redis-server` | `redis-server` | 6379 |

- Detects package installation state, installed/candidate version, service activity, and whether the service is enabled at boot.
- Installs or upgrades the selected APT server package after confirmation.
- Starts, stops, restarts, enables, or disables APT/systemd-managed services after confirmation.
- Detects manually launched database processes that do not have an APT/systemd service entry, and displays their PID, port, data directory, and socket when available.
- Treats unmanaged processes as read-only. DevPilot does not stop, restart, import, move, or delete their data.
- Checks for known default-port conflicts before installing or starting another server. MySQL and MariaDB are treated as conflicting default-port alternatives.

**Important:** Installing a system database server is different from installing a database client. The **Development Setup** tab still provides client tools for connecting to servers. Installing a server may create a system-managed data directory and start a service; back up existing databases before changing server packages or migrating data. A manually launched server using a temporary data directory remains temporary until you deliberately migrate it to a persistent setup.

### Project Workspaces
- Uses a configurable workspace root (default: `~/Projects`).
- Creates new workspace directories or registers existing directories.
- Assigns a Git profile to a workspace.
- Stores workspace metadata in the user's local configuration.

### Git Accounts & SSH
- Stores multiple Git identity profiles with separate commit names and email addresses.
- Supports SSH or HTTPS as the selected authentication mode.
- Generates a separate Ed25519 SSH key for an SSH profile without overwriting an existing key.
- Creates distinct SSH host aliases for different accounts.
- Applies Git conditional includes so repositories under a workspace can inherit its assigned commit identity.

### AI Agents
The **AI Agents** tab manages four terminal coding agents:

| Agent | Command | What DevPilot provides |
|---|---|---|
| OpenCode CLI | `opencode` | Install/update, detect version, launch in a project folder |
| Claude Code | `claude` | Install/update, detect version, launch in a project folder |
| OpenAI Codex CLI | `codex` | Install/update, detect version, launch in a project folder |
| GitHub Copilot CLI | `copilot` | Install/update, detect version, launch in a project folder |

- Uses each vendor's official Linux installer command.
- Shows the installer source and exact command and asks for confirmation before running it.
- Runs the installer as the current user; DevPilot does not use `sudo` for AI-agent installation.
- Lets you choose a launch directory or use a registered workspace.
- Opens the selected agent in a new terminal window and displays installer output in the app.

**Important:** The install action downloads and executes the installer script published by the selected vendor. Review the displayed source and command before confirming. Installing a CLI does not include a subscription, API credits, or provider authentication. Sign in from the agent's terminal after installation. GitHub Copilot CLI requires an eligible Copilot subscription.

Official agent documentation:
- [OpenCode](https://opencode.ai/docs/)
- [Claude Code](https://code.claude.com/docs/en/getting-started)
- [OpenAI Codex CLI](https://learn.chatgpt.com/docs/cli)
- [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli)

### Backup & Recovery
- Creates timestamped backups before applying managed Git and SSH configuration.
- Preserves unmanaged content in Git and SSH configuration files.
- Uses clearly marked managed sections.
- Does not copy private SSH keys into backups.

## Requirements

- Linux Mint 22.x, Ubuntu 24.04, or a compatible Debian-based distribution.
- Python 3.12 or later.
- Tkinter.
- APT and `pkexec` for package installation.
- Git and OpenSSH client for Git/SSH features.
- `curl` for AI-agent installers.
- A supported terminal emulator (such as the system's `x-terminal-emulator`, GNOME Terminal, Xfce Terminal, Konsole, Kitty, or Alacritty) to launch agents.

Install system dependencies on Linux Mint / Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-tk policykit-1 git openssh-client curl
```

## Quick start

```bash
git clone https://github.com/omarmm/DevPilot.git
cd DevPilot
python3 linux_work_setup.py
```

On first launch, DevPilot automatically creates an application-menu entry and, when your desktop environment exposes a Desktop folder, a `DevPilot.desktop` shortcut there. You can then launch it with a double-click (some desktop environments may ask you to mark the shortcut as trusted once). The launcher points to the current script location, so keep the repository folder in place.

**Run DevPilot as your regular user, not with `sudo`.** It requests elevated privileges only for APT package operations through `pkexec`.

## Git account setup

1. Open **Git Accounts & SSH**.
2. Select **Add Git account** and enter a profile label, commit author name, commit email, hosting domain, username, and authentication mode.
3. For SSH profiles, select the profile and choose **Generate SSH key**.
4. Add the generated `.pub` public key to the matching GitHub or GitLab account. Never share the private key.
5. Open **Project Workspaces**, select a workspace, and choose **Assign Git profile…**.
6. Return to **Git Accounts & SSH** and select **Apply Git / SSH Configuration**. When DevPilot was launched from inside a Git repository, it detects that repository and asks which profile to apply.
7. When DevPilot was not launched from the project folder, select **Apply to project folder…**, choose the repository directory, and select the Git profile. DevPilot writes and verifies repository-local `user.name` and `user.email`; you do not need to edit Git configuration in a terminal.
8. To apply all saved workspace-to-profile assignments through Git conditional includes and update SSH aliases, use **Apply assigned profiles** in the **Project Workspaces** tab. Use the generated SSH host alias in SSH remotes. For example:

```bash
git remote set-url origin git@github-work:OWNER/REPOSITORY.git
```

Replace `github-work`, `OWNER`, and `REPOSITORY` with the values for your profile and repository.

### Authentication notes

- Git conditional includes configure commit identity (author name and email); they do not authenticate to the hosting provider.
- SSH authentication requires adding the generated public key to the corresponding hosting account and using the profile's SSH host alias in the remote URL.
- HTTPS profile metadata does not contain passwords or tokens. Automatic per-account HTTPS credential isolation is **not implemented** in this preview; configure a secure Git credential manager on your system.
- Repository-local Git settings can override inherited settings. DevPilot does not rewrite repository-local configuration.

## Configuration and safety

To preserve compatibility with the earlier Linux Work Setup preview, DevPilot currently stores its application configuration under:

```text
~/.config/linux-work-setup/
```

Backups are stored under:

```text
~/.local/share/linux-work-setup/backups/
```

Before applying managed Git or SSH configuration, DevPilot creates a backup. It updates only its marked sections in `~/.gitconfig` and `~/.ssh/config`; existing content outside those sections is preserved. If managed markers are inconsistent, the operation stops rather than replacing the file.

Private SSH keys are not included in DevPilot backups. Keep your own secure backup of private keys when required.

## Current limitations

- HTTPS multi-account credential isolation is not automated.
- Bash and Zsh prompt integration is not included.
- Workspace move and rename workflows are not included.
- A graphical diagnostics and configuration-conflict review screen is still planned.
- Package availability depends on the configured APT repositories and Linux distribution.
- GUI flows that run external installers require an interactive desktop session.
- Automated installer integration tests are not included yet; CI checks syntax and the static agent catalog.

## Roadmap

- [x] Development package setup and status detection
- [x] Workspace creation and registration
- [x] Multiple Git identity profiles
- [x] Workspace-to-Git-profile assignment
- [x] SSH key generation and host aliases
- [x] Git conditional includes
- [x] Timestamped backups before managed configuration changes
- [x] AI Agents tab for install/update, status detection, and terminal launch
- [x] Database Servers tab for APT installation, systemd lifecycle, and unmanaged process detection
- [ ] Secure per-account HTTPS credential integration
- [ ] Bash and Zsh workspace prompt integration
- [ ] Workspace move/rename with collision preview
- [ ] Diagnostics and configuration repair workflow
- [ ] Automated UI and installer integration test suite
- [ ] Packaged release for easier installation

## Project structure

```text
DevPilot/
├── .github/
│   └── workflows/
│       └── ci.yml
├── docs/
│   └── images/
├── tests/
│   ├── test_ai_agent_catalog.py
│   └── test_database_servers.py
├── linux_work_setup.py
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
└── SECURITY.md
```

The preview is intentionally lightweight and is currently distributed as a single Python application file. The legacy script filename and configuration directory are retained for compatibility during this preview release.

## Contributing

Bug reports, feature suggestions, and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before contributing. Never commit private keys, access tokens, passwords, personal configuration files, or backup archives.

## Security

Please read [SECURITY.md](SECURITY.md) for responsible vulnerability reporting guidance.

## License

No license has been selected yet. Until a license file is added, all rights are reserved by the copyright holder; reuse, redistribution, and modification are not automatically granted.

---

<p align="center">Made for developers who want a cleaner, safer, more organized Linux workstation.</p>
