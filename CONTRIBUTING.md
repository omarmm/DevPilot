# Contributing to DevPilot

Thanks for your interest in contributing.

## Before you start

- Search existing issues before opening a new one.
- For substantial changes, open an issue first to discuss the scope and approach.
- Keep pull requests focused and explain the user-facing impact.

## Development environment

DevPilot targets Linux desktop environments and currently uses Python and Tkinter. On Linux Mint / Ubuntu, install the required system packages with:

```bash
sudo apt update
sudo apt install -y python3 python3-tk policykit-1 git openssh-client
```

Run the app as a regular user:

```bash
python3 linux_work_setup.py
```

Do not run it with `sudo` during normal use.

## Pull request checklist

- [ ] Explain the problem and the proposed change.
- [ ] Keep the diff focused; avoid unrelated refactoring.
- [ ] Run `python -m py_compile linux_work_setup.py`.
- [ ] Update the README or changelog when behavior or user instructions change.
- [ ] Never include private keys, access tokens, passwords, personal configuration files, or backup archives.

## Reporting bugs

Include your Linux distribution, desktop environment, Python version, reproduction steps, and relevant sanitized logs. Remove secrets and personal data before sharing logs.
