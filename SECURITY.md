# Security Policy

## Reporting a vulnerability

Please do **not** open a public issue for security problems.

- Preferred: GitHub private vulnerability reporting on this repository.
- Alternative: email **vlad@sterngold.nl** with a description and reproduction steps.

You will get a response within 7 days. Confirmed issues are fixed on `main`.
There is no bounty program.

## Supported versions

Only the latest `main` receives security fixes.

## Local credential storage

This skill stores Google browser cookies and localStorage under `data/`.
The directory is gitignored and the scripts set owner-only permissions for
state files on platforms that support POSIX modes. Treat `data/` as sensitive:
do not sync it, commit it, paste it into issues, or share it with another user.

Use a dedicated Google account for NotebookLM automation if your notebooks
contain client, financial, medical, or private personal material.

