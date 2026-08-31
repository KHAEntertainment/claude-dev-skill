# Releasing

The plugin marketplace entry pins a release tag (ADR-003), so **the plugin does
not resolve until that tag exists and is pushed**. Cutting a release is
therefore a required step, not an optional one.

## Version sites

One version, four places. They must agree before a tag is cut.

| Site | Form | Example |
|---|---|---|
| `skills/dev/SKILL.md` frontmatter `version:` | semver + build metadata | `2.0.0+upstream.3e87db0` |
| `.claude-plugin/plugin.json` `version` | plain semver | `2.0.0` |
| `.claude-plugin/marketplace.json` plugin entry `version` | plain semver | `2.0.0` |
| `.claude-plugin/marketplace.json` plugin entry `source.ref` | `v` + semver | `v2.0.0` |
| git tag | `v` + semver | `v2.0.0` |

The Skill value carries `+upstream.<sha>` build metadata that the manifests do
not. They are **not** byte-identical — they share the same core version, the
part before `+`. Comparison must strip build metadata.

## Tag scheme

Plain `vX.Y.Z`, starting at `v2.0.0` (ADR-004). Note that `claude plugin tag`
generates a *different* form — `dev-skill--v2.0.0` — which this project does not
use, because a plain `vX.Y.Z` tag also serves the Homebrew formula's source
tarball URL (`refs/tags/vX.Y.Z.tar.gz`, ADR-007). One tag serves both channels.

`claude plugin tag --dry-run .` is still useful as a *validation* step: it
reports whether `plugin.json` and the marketplace entry agree on name and
version. Ignore the tag name it proposes; do not let it create the tag.

## Procedure

1. **Land the content.** Every PR for the release is merged to `main`.

2. **Verify agreement.** From a clean checkout of `main`:

   ```bash
   python3 scripts/validate_skill.py
   PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
   bash tests/test-install.sh
   claude plugin validate . --strict
   claude plugin tag --dry-run .        # validation only; ignore the proposed tag name
   ```

   `claude plugin tag` refuses to run on a dirty worktree. Commit or clean
   first — do not reach for `--force`, which defeats the check.

3. **Tag and push.**

   ```bash
   git checkout main && git pull --ff-only
   git tag -a v2.0.0 -m "dev-skill 2.0.0"
   git push origin refs/tags/v2.0.0
   ```

   Cut the tag from `main` only. `master` mirrors upstream and carries
   upstream's `v1.x` tags; releasing from it would be wrong.

4. **Verify the tag resolves.**

   ```bash
   git ls-remote --tags origin | grep v2.0.0
   ```

5. **Verify the advertised install actually works**, in a scratch config so the
   real one is untouched:

   ```bash
   CLAUDE_CONFIG_DIR=/tmp/dev-skill-release-check \
     claude plugin marketplace add KHAEntertainment/claude-dev-skill
   CLAUDE_CONFIG_DIR=/tmp/dev-skill-release-check \
     claude plugin install dev-skill@khaentertainment-dev-skill
   ```

   This is the step that catches an unresolvable pin. Do not skip it — manifest
   validation passing does not prove the pinned ref exists.

## Never move a released tag

The marketplace pins `ref` only, not a commit `sha`, so a moved tag silently
changes what existing users receive. Treat a pushed release tag as immutable. If
a release is wrong, cut a new patch version.

Pinning `sha` alongside `ref` would make this mechanically impossible rather
than merely forbidden. It was deliberately deferred: it requires editing the
commit SHA into the manifest *after* the commit exists, which is a
chicken-and-egg step better handled by release automation. Revisit when CI
computes it (Issue #6).

## Next release

Bump all five sites in one commit, then repeat from step 1. `skills/dev/SKILL.md`
keeps its `+upstream.<sha>` suffix, updated only when an upstream merge changes
the base commit — see [UPSTREAM.md](../UPSTREAM.md).
