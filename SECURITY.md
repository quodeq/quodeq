# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in quodeq, please report it responsibly.

**Do NOT open a public issue.**

Instead, email: quodeq.ai@gmail.com

We will acknowledge receipt within 48 hours and provide a timeline for a fix.

## Supported Versions

| Version | Supported |
| ------- | --------- |
| latest  | Yes       |

## Verifying a release

Every release is built by GitHub Actions in this repository, and each file it
produces carries a signed [build provenance attestation](https://docs.github.com/en/actions/security-guides/using-artifact-attestations-to-establish-provenance-for-builds).
Verifying one proves the file was built from this repository by the named
workflow, and has not been changed since. You need the [GitHub CLI](https://cli.github.com/)
(`gh`), version 2.49 or later.

Replace `1.2.3` below with the version you downloaded.

### Desktop apps (DMG and Windows zip)

Download the app and `SHA256SUMS` from the [release page](https://github.com/quodeq/quodeq/releases)
into one folder, then check the digests. Run the check from that folder; it
reports a missing file for whichever platform you did not download, which you
can ignore.

```bash
shasum -a 256 -c SHA256SUMS
```

Then confirm where the file came from:

```bash
gh attestation verify Quodeq-1.2.3-macOS.dmg \
  --repo quodeq/quodeq \
  --signer-workflow quodeq/quodeq/.github/workflows/build-dmg.yml
```

On Windows, use `Quodeq-1.2.3-Windows.zip` in the same command, and
`Get-FileHash Quodeq-1.2.3-Windows.zip -Algorithm SHA256` in place of `shasum`
to compare against the line in `SHA256SUMS`.

`SHA256SUMS` is itself attested, so it can be checked the same way.

The desktop apps are not yet signed by Apple or by an Authenticode certificate,
so macOS Gatekeeper and Windows SmartScreen will still warn on first launch.
The checks above are how to confirm the download is genuine until they are.

### Python package (PyPI)

The wheel and sdist are uploaded to PyPI through trusted publishing, with
[PEP 740](https://peps.python.org/pep-0740/) attestations shown on the
[PyPI project page](https://pypi.org/project/quodeq/#files). To check a
downloaded wheel against the GitHub attestation:

```bash
pip download quodeq==1.2.3 --no-deps --only-binary :all: -d quodeq-dist
gh attestation verify quodeq-dist/quodeq-1.2.3-py3-none-any.whl \
  --repo quodeq/quodeq \
  --signer-workflow quodeq/quodeq/.github/workflows/publish.yml
```

### Software bill of materials

Each release attaches two CycloneDX SBOMs: `quodeq-1.2.3-python.cdx.json` for
the locked Python dependencies and `quodeq-1.2.3-ui.cdx.json` for the npm
packages bundled into the web UI. Both are covered by provenance attestations,
and the Python SBOM is also attested against the wheel and sdist:

```bash
gh attestation verify quodeq-dist/quodeq-1.2.3-py3-none-any.whl \
  --repo quodeq/quodeq \
  --predicate-type https://cyclonedx.org/bom
```

Releases before the one that introduced these checks do not have attestations,
checksums or SBOMs.
