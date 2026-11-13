# Security

Plugins run arbitrary Python on a workstation that may hold patient data. Treat them accordingly.

- Report a vulnerability privately to the repository owner; do not open a public issue.
- Network access in this repository is limited to first-run model downloads (Hugging Face, GitHub releases). Anything else needs a justification in the PR.
- Downloaded checkpoints that are pickles must be verified against a pinned SHA-256 before loading (`totalsegmentator` does this); plain state dicts load with `weights_only=True`.
- No patient data in git, issues, logs or test fixtures. Tests use synthetic volumes.
