# PipPal Core Release Checklist

This is the authoritative release-gate checklist for PipPal Core, starting
with v0.2.5. It names every blocking gate, the evidence each gate must
produce, the waiver policy, and the release-PR contract that ties them
together.

Use this checklist for every Core release PR cut from a `release/*` branch
into `main`. The release PR must reference this file and tick the gate
boxes in [.github/PULL_REQUEST_TEMPLATE/release.md](../.github/PULL_REQUEST_TEMPLATE/release.md).

## Suite Layout

PipPal Core has two distinct test suite locations. They are separated on
purpose; do not collapse them.

| Location | Purpose | Runs where | Default invocation |
| --- | --- | --- | --- |
| `tests/` (incl. `tests/e2e/`, `tests/smoke/`, `tests/ui_smokes/`) | Headless logic + packaging + opt-in UI smokes | Every push via GitHub Actions and locally | `python -m pytest` |
| `e2e/` | Live Windows UI E2E that launches the real desktop app | Release-gate workstation only | `.\e2e\run-local.ps1` |

The headless `python -m pytest` run intentionally ignores
`tests/benchmarks`, `tests/e2e`, `tests/smoke`, and `tests/ui_smokes` via
`pytest.ini` so the default suite stays fast and deterministic. The
release-gate runners (`e2e\run-local.ps1`, `e2e\run-ui-smokes.ps1`) opt
those suites in explicitly through `PIPPAL_E2E_LIVE=1` and
`PIPPAL_UI_SMOKES=1`.

## Required Gates (non-waivable defaults)

A release PR may merge into `main` only after all three gates below have
been recorded with `status=pass` evidence. None of these gates may be
silently skipped — see [Waiver Policy](#waiver-policy) for the narrow
exception path.

### Gate 1 — Headless logic suite

- Command: `python -m pytest`
- Companion lint: `python -m ruff check .`
- Scope: every Python suite collected by `pytest.ini` (excludes the live
  and packaging suites by design — those are Gates 2/3 below).
- Pass criteria: zero failures, zero errors, ruff exits 0.
- Evidence: paste the final pytest summary line and the ruff summary
  into the release PR description, or attach the CI run URL.

### Gate 2 — Live Windows UI E2E (`e2e\run-local.ps1`)

- Command: `pwsh -NoProfile -ExecutionPolicy Bypass -File .\e2e\run-local.ps1 -SkipSetup`
- Scope: launches `reader_app.py` under an isolated `PIPPAL_DATA_DIR`,
  drives real Tk Settings + Voice Manager, synthesises a real Piper WAV,
  validates the command-server contract.
- Pass criteria documented in [LIVE_UI_E2E_RELEASE_GATE.md](LIVE_UI_E2E_RELEASE_GATE.md):
  `release-gate-summary.json` reports `status=pass`, `exit_code=0`,
  `tests>0`, `failures=0`, `errors=0`, `skipped=0`.
- Evidence directory: `.e2e\evidence\live-ui-<UTC>\` (see
  [Evidence Convention](#evidence-convention)).
- Environment assumptions to record in the release PR: Windows version,
  Edition (Core source checkout, not installed Store/MSIX build), Python
  version, Piper version surfaced by `setup.ps1`, whether
  `-SkipSetup` was used, and confirmation that no installed PipPal
  process owned the command port at start.

### Gate 3 — Foreign-app selected-text smokes (`e2e\run-ui-smokes.ps1`)

- Command: `pwsh -NoProfile -ExecutionPolicy Bypass -File .\e2e\run-ui-smokes.ps1`
- Scope: drives Notepad, Edge (webpage and built-in PDF viewer), and
  Acrobat / Adobe Reader (when installed) directly and asserts
  `pippal.clipboard_capture.capture_selection` captures the expected
  text and restores the prior clipboard. Does **not** launch the PipPal
  desktop app — this gate exclusively answers "did this release regress
  selected-text capture in the highest-value foreign apps?". Surfaces
  proven by the smokes (see `ui-smokes-summary.json:surfaces_proven`):
  Notepad happy + recovery (#62), Edge webpage happy (#62), Edge
  built-in PDF viewer happy + image-only recovery (#63), Acrobat /
  Adobe Reader happy or `unavailable` (#63).
- Pass criteria: `ui-smokes-summary.json` reports `status=pass`,
  `exit_code=0`, `tests>0`, `failures=0`, `errors=0`, `skipped=0`.
- Evidence directory: `.e2e\evidence\ui-smokes-<UTC>\` (see
  [Evidence Convention](#evidence-convention)).
- Environment assumptions to record: Notepad, Edge, and Acrobat
  executable paths and versions as printed by the per-smoke JSON
  evidence. If Acrobat is absent on the gate machine, the run is
  expected to record `acrobat_pdf_selected_text_unavailable.json`
  alongside the other smokes' evidence files.
- Waiver policy delta for PDF surfaces: an Edge PDF smoke failure is
  non-waivable (Edge ships with Windows; capture regression here
  blocks release). Acrobat unavailability is `unavailable`-waivable
  per the standard [Waiver Policy](#waiver-policy) with a follow-up
  issue against the next release. An image-only PDF returning
  non-empty text is treated as a `fail`, not an unsupported-surface
  pass — protected/scanned/image-only PDFs remain unsupported until
  OCR work lands (tracked in
  [SELECTED_TEXT_RELIABILITY.md](SELECTED_TEXT_RELIABILITY.md)).

## Evidence Convention

Every release gate that has a runner emits a self-describing evidence
directory under `.e2e\evidence\<gate>-<UTC>\`:

| File | Produced by | Reviewer use |
| --- | --- | --- |
| `pytest-*.junit.xml` | pytest `--junitxml` | machine-readable test result, CI artifact upload |
| `pytest-*.log` | runner tee | full pytest stdout/stderr |
| `release-gate-summary.json` / `ui-smokes-summary.json` | runner | status contract (`pass`/`fail`/`blocked`/`unavailable`), counts, paths |
| `release-gate-command.txt` / `ui-smokes-command.txt` | runner | exact command + environment contract used |
| per-smoke `<smoke_id>.json` (Gate 3 only) | smoke fixtures | foreign-app version, fixture path, captured text, clipboard-restoration outcome |

The release PR must either attach those evidence directories as PR
artifacts or paste the absolute paths under the release-gate machine's
checkout, along with the four-line summary excerpt that shows the
`status` and `tests`/`failures`/`errors`/`skipped` counts for each gate.

The status contract is shared across runners and is the canonical
release-gate vocabulary:

| Status | Meaning | Releasable? |
| --- | --- | --- |
| `pass` | All tests green, no honest skips. | Yes |
| `fail` | At least one test failed or errored. | No, never waivable |
| `blocked` | The harness ran but collected zero tests or honest skips were present without `-AllowUnavailable`. | No, must be re-run |
| `unavailable` | The runner was invoked with `-AllowUnavailable` and the environment legitimately cannot host the gate (e.g. headless CI runner with no desktop session). Recorded for diagnostic CI only. | Only via the [Waiver Policy](#waiver-policy) below |

## Waiver Policy

Release gates are non-waivable by default. The narrow waiver path below
exists only so a documented, transient platform limitation does not
block an otherwise green release indefinitely — it is not a shortcut.

### When a gate **may** be waived

A gate may be waived only when **all** of these conditions hold:

1. The runner emits `status=unavailable` because of a documented platform
   constraint (for example: no Windows desktop session on a hosted CI
   runner, Edge not installed on the release-gate machine), **not**
   because the gate failed.
2. A follow-up issue is filed against this repo that names the gate,
   the constraint, and the target release in which the gate will run
   green again. The waiver checkbox in the release PR links that issue.
3. The remaining non-waived gates all reported `status=pass` on the same
   release SHA.

### When a gate **must not** be waived

Waivers are explicitly forbidden in any of these cases:

- Any gate reported `status=fail` or `status=blocked`.
- Two consecutive release cuts have already waived the same gate
  (consecutive flakes are a release blocker, not a recurring waiver).
- The release PR cannot show evidence directories (or equivalent CI
  artifact URLs) for the non-waived gates.
- The gate covers a feature surface the release notes call out as new
  or fixed (you cannot ship a fix without proving the fix).

### Who signs off

A waiver requires two signatures recorded as checkboxes in the release
PR template:

- **PO sign-off** — the product owner on the release branch (e.g.
  `tigyijanos` for Core 0.2.5) acknowledges the waiver and the follow-up
  issue link.
- **Independent reviewer sign-off** — any maintainer who did not author
  the change(s) under release. The reviewer's name is recorded in the
  PR template alongside the waiver justification.

A single signer cannot waive a gate. Self-approval does not count as an
independent review.

## Release PR Contract

Every release PR uses the
[release PR template](../.github/PULL_REQUEST_TEMPLATE/release.md).
The template encodes this checklist as checkboxes so reviewers can audit
the release pass without re-reading the prose here.

The release PR description must:

- Tick the three gate checkboxes once their evidence is captured.
- Paste or link the evidence directory paths produced by each runner.
- Name the Windows version, Python version, and Piper version used on
  the release-gate machine for Gates 2 and 3.
- If any gate is waived, link the follow-up issue and record both
  signers in the waiver section.
- Reference the relevant `CHANGELOG.md` entry and confirm
  `pyproject.toml` version matches the release tag.

## Teaching Note

This is a named-gates checklist pattern. The pattern is to push every
release-blocking check behind a runner with a shared status contract
(`pass`/`fail`/`blocked`/`unavailable`) and then have one human-readable
document map the runners to product policy (when waivable, who signs).
Alternatives are tribal handoffs in chat or a single mega-runner that
fans out to every gate. The tradeoff is a small amount of doc/template
duplication, but reviewers and CI both consume the same artifacts and
the policy stays auditable in-repo.
