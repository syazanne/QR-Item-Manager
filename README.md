# QR-Item-Manager

QR-based item management and a separate manual/support prototype.

This repository contains two project branches:

- [project-1-item-manager](https://github.com/syazanne/QR-Item-Manager/tree/project-1-item-manager): QR-based item management system.
- [project-2-ai-prototype](https://github.com/syazanne/QR-Item-Manager/tree/project-2-ai-prototype): AI-assisted manual/support prototype.

The `main` branch contains this general introduction. Open a project branch for
its application code, requirements, and setup instructions.

## Branch overview

| Branch | Purpose |
| --- | --- |
| `main` | General repository introduction. |
| `project-1-item-manager` | Working item manager with editable records, QR scanning, custom fields, printable labels, and Backup & Restore. |
| `project-2-ai-prototype` | Experimental manual/support project. The current code provides manual keyword search; AI integration remains future work. |

An additional `project-2-ai-assistant` branch is retained for reference. It is not
one of the two project entry points above.

## Start with Project 1

```bash
git clone --branch project-1-item-manager https://github.com/syazanne/QR-Item-Manager.git
cd QR-Item-Manager
```

Follow that branch's [README](https://github.com/syazanne/QR-Item-Manager/blob/project-1-item-manager/README.md)
for installation and its [user guide](https://github.com/syazanne/QR-Item-Manager/blob/project-1-item-manager/docs/USER_GUIDE.md)
for field setup, records, QR labels, scanning, and backups.

## Explore Project 2

Use a separate folder when trying the prototype:

```bash
git clone --branch project-2-ai-prototype https://github.com/syazanne/QR-Item-Manager.git QR-Item-Manager-AI
cd QR-Item-Manager-AI
```

Read the prototype's [README](https://github.com/syazanne/QR-Item-Manager/blob/project-2-ai-prototype/README.md)
and install its own requirements. The two projects have different application
code and database schemas; keep their local data in separate folders.
