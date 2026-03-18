# Release Checklist

## 1. Prepare

- [ ] Decide version number (major / minor / patch)
- [ ] Update version in `pyproject.toml`
- [ ] Update version in `package.json` (if applicable)
- [ ] Search for any other hardcoded version strings and update them

## 2. Create release branch

```bash
git checkout develop
git pull
git checkout -b release/vX.Y.Z
```

## 3. Create PR

- [ ] Create PR from `release/vX.Y.Z` → `develop`
- [ ] Review changes, run tests
- [ ] Merge PR

## 4. Publish

Once the release branch is merged into `develop`:

- [ ] Publish new Python package (`uv publish` or PyPI workflow)
- [ ] Build and update the macOS DMG (QuodeqBar)
- [ ] Create a new tag and GitHub release:

```bash
git checkout develop
git pull
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
gh release create vX.Y.Z --title "vX.Y.Z" --generate-notes
```

- [ ] Attach DMG to the GitHub release
