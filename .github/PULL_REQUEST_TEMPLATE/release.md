<!--
PipPal Core release PR template.

Use this template for any PR that merges a `release/*` branch into `main`.
For non-release PRs, do not pick this template — submit a plain PR.

Pick this template by appending `?template=release.md` to the PR-create
URL, or by running:

  gh pr create --base main --template release.md

The authoritative gate definitions live in
docs/RELEASE_CHECKLIST.md. Keep the boxes below in sync with that doc.
-->

## Release summary

- Version: `0.X.Y`
- Release branch: `release/0.X.Y`
- Release-gate machine (Windows version, Python version, Piper version):

## Required gates

Tick a box only after attaching or linking the evidence for that gate.
See [docs/RELEASE_CHECKLIST.md](../docs/RELEASE_CHECKLIST.md) for the
full contract; see [docs/LIVE_UI_E2E_RELEASE_GATE.md](../docs/LIVE_UI_E2E_RELEASE_GATE.md)
for the Gate 2 reviewer rule.

- [ ] **Gate 1 — Headless logic suite**: `python -m pytest` green, `python -m ruff check .` green.
  - pytest summary line:
  - ruff summary line:
- [ ] **Gate 2 — Live Windows UI E2E**: `e2e\run-local.ps1` reported `status=pass`.
  - Evidence dir (`.e2e\evidence\live-ui-<UTC>\`):
  - `release-gate-summary.json` excerpt (`status`, `tests`, `failures`, `errors`, `skipped`):
  - Confirmation no installed PipPal process owned the command port at start: yes / no
- [ ] **Gate 3 — Foreign-app selected-text smokes**: `e2e\run-ui-smokes.ps1` reported `status=pass`.
  - Evidence dir (`.e2e\evidence\ui-smokes-<UTC>\`):
  - `ui-smokes-summary.json` excerpt (`status`, `tests`, `failures`, `errors`, `skipped`):
  - Notepad and Edge versions captured by per-smoke JSON evidence:

## Release notes and version bumps

- [ ] `CHANGELOG.md` has an entry for this version.
- [ ] `pyproject.toml` version matches the release tag.
- [ ] `README.md` "Status" line references the correct release.

## Waivers (only if a gate cannot run green)

The default is no waivers. Fill this section only if a gate reported
`status=unavailable` for a documented platform reason **and** the
[Waiver Policy](../docs/RELEASE_CHECKLIST.md#waiver-policy) conditions
are satisfied.

- Gate being waived:
- Reason it is `unavailable` (not `fail` / `blocked`):
- Follow-up issue tracking the constraint (must link a filed issue):
- Has this gate been waived in the previous release? (If yes, this
  release **cannot** waive it again — re-run instead.)

Both signatures are required for a waiver. A single signer cannot waive
a gate; self-approval does not count as independent review.

- [ ] PO sign-off (name):
- [ ] Independent reviewer sign-off (name, must not be the author):

## Linked issues

- Closes #
