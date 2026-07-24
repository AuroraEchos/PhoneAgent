# GitHub Release Guide

PhoneAgent releases use semantic version tags and a tag-triggered GitHub Actions workflow.

## Validate locally

Update the package version, changelog, release notes, website version text, and
`CITATION.cff`, then run:

```bash
uv lock --check
uv sync --extra dev
bash scripts/release_check.sh
```

Install the generated wheel in a clean environment and verify both command-line entry
points before publishing.

## Publish the release commit

Push the validated release commit to `main` and wait for CI and Pages to pass:

```bash
git push origin main
```

## Create the tag and GitHub Release

For example, to publish `v0.1.1`:

```bash
git tag -a v0.1.1 -m "PhoneAgent v0.1.1"
git push origin v0.1.1
```

The `Release` workflow verifies that the tag matches the package version, runs lint and
tests, builds the wheel and source distribution, generates `SHA256SUMS.txt`, and creates the
GitHub Release using `RELEASE_NOTES_v0.1.1.md`.

## Enable GitHub Pages

Open **Settings → Pages**, select **GitHub Actions** as the source, and run the
`Deploy GitHub Pages` workflow. The project site is configured for:

```text
https://auroraechos.github.io/PhoneAgent/
```
