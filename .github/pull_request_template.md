## What and why

<!-- One paragraph. Which plugin(s), what changes for the user. -->

## Checklist

- [ ] `python tools/validate_plugins.py` and `ruff check .` pass
- [ ] Plugin `version` bumped and `CHANGELOG.md` line added (behaviour change)
- [ ] `docs/plugins/<name>.md` and README table updated (if the summary, params or limits changed)
- [ ] No weights, data, secrets or patient data added
- [ ] Downloaded pickles are checked against a pinned SHA-256

## What I ran, and on what

<!-- Becomes the "Verified" row. State plugin, radspider version, OS, data (synthetic / real), result. Say what you did NOT run. -->
