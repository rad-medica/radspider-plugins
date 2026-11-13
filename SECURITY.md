# Security

Plugins run arbitrary Python on a workstation that may hold patient data. Treat them accordingly.

- Report a vulnerability privately to the repository owner; do not open a public issue.
- Network access in this repository is limited to first-run model downloads (Hugging Face, GitHub releases). Anything else needs a justification in the PR.
- Downloaded checkpoints that are pickles must be verified against a pinned SHA-256 before loading (`totalsegmentator` does this); plain state dicts load with `weights_only=True`.
- Plugin requirements are plain pip requirements (name, extras, version specifiers, markers). `validate_plugins.py` rejects `-r`, `-e`, `--index-url`, `--extra-index-url`, `--find-links`, URLs and local paths: pip runs those lines on the user's machine, and an extra index is a supply-chain hole.
- No patient data in git, issues, logs or test fixtures. Tests use synthetic volumes.

## Token for the marketplace

This repository is private, so a client (radspider's marketplace window) reads the index and downloads packages with a token. Use a **fine-grained personal access token**, never a classic one (the classic `repo` scope also writes to every private repository the user reaches).

Create it:

1. GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token.
2. Resource owner: `rad-medica`. If it is not offered, an organisation owner must allow fine-grained tokens in the organisation's settings; some organisations also require an owner to approve each token before it works.
3. Repository access: *Only select repositories* → `rad-medica/radspider-plugins`. Nothing else.
4. Permissions → Repository permissions → **Contents: Read-only**. Everything else stays *No access* (Metadata: read-only is added automatically).
5. Expiration: the shortest the team can live with (90 days at most). Copy the token once; paste it into radspider's connect window. radspider keeps it in the system keyring, not in a file.

Who gets access: people who may install the plugins, and only those. A token cannot reach more than its owner can, so access is granted by adding the person to the repository (read role), not by sharing a token. Do not share one token between people: one token per person, so a leaver's token can be revoked alone.

Rotate: before the expiry (or at once if a token may have leaked) create a new token as above, replace it in radspider (disconnect, connect), then delete the old one under Developer settings. A client that gets `401` has an expired or revoked token; `404` means the token has no access to the repository.
