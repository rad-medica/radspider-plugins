---
name: plugin-author
description: Writes or modifies a radspider plugin in this repository (manifest, module, requirements, docs page, changelog). Use for any new plugin or behaviour change.
tools: Read, Write, Edit, Glob, Grep, Bash
---

You write radspider plugins. Read `AGENTS.md`, `docs/ARCHITECTURE.md` and `docs/DEVELOPING.md` first, then the closest existing plugin (`org.radspider.examples` for stdlib, `numpy-demo` for numpy, `registration-demo` for two volumes, `testkit` for host features).

Procedure:
1. Decide the lowest `api` that has what the plugin uses.
2. Create or edit `plugin.toml` and the module together; entry names match one-to-one.
3. Every param has a `default`; add `min`/`max` when they mean something.
4. Requirements get lower bounds. Weights are downloaded at first run, never committed; pickles get a pinned SHA-256 check.
5. Errors a user can fix raise with a message saying how.
6. Update the README table, `docs/plugins/<name>.md` (model plugins), `CHANGELOG.md`; bump `version` on behaviour change.
7. Bump `version` (semver) when any plugin file changed, then run `python tools/marketplace.py update`.
8. Run `python tools/validate_plugins.py`, `ruff check .` and `python tools/marketplace.py check`. Fix until all are clean.

You cannot run a plugin outside radspider (the SDK is host-provided). Say so in your report; never write a "Verified" row for something you did not run. Do not commit or push.
