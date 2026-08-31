# Releasing

The plugin marketplace entry pins a release tag (ADR-003), so **the plugin does
not resolve until that tag exists and is pushed**. Cutting a release is
therefore a required step, not an optional one.

## Version sites

One version, five places — four repository fields plus the git tag. The four
repository fields are updated together in the release commit; the tag is created
afterwards, from that commit.

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

   `claude plugin tag` refuses to run on a dirty worktree, and `--force`
   defeats the check rather than satisfying it. Commit or clean first.

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
   real one is untouched.

   The marketplace entry uses an `https://` `url` source specifically so this
   works without a GitHub SSH key (ADR-003). Verify on a machine where
   `ssh -T git@github.com` fails, if you have one — that is the configuration
   the `url` source exists to support.

   ```bash
   CLAUDE_CONFIG_DIR=/tmp/dev-skill-release-check \
     claude plugin marketplace add KHAEntertainment/claude-dev-skill
   CLAUDE_CONFIG_DIR=/tmp/dev-skill-release-check \
     claude plugin install dev-skill@khaentertainment-dev-skill
   ```

   This is the step that catches an unresolvable pin, and the only step that
   exercises the transport real users hit. Do not skip it — manifest validation
   passing proves neither that the pinned ref exists nor that it can be fetched.

   It can only be run **after** the tag is pushed. Before that, both the
   `owner/repo` shorthand and the explicit HTTPS URL fail on the missing
   manifest, which is expected and tells you nothing about the release.

## What CI enforces for you

`.github/workflows/ci.yml` runs the full Verification Gate on every pull request
and every push to `main`, so most of step 2 is checked automatically. In
particular the packaging job extracts `git archive HEAD` and runs
`scripts/validate_skill.py` against the **extracted archive**, not just the
working tree — so a broken `export-ignore` rule that would ship a defective
source tarball fails CI rather than surfacing later as a broken `brew install`.

What CI cannot do is step 5. The tag does not exist when CI runs, so verifying
that the published plugin actually installs remains a manual post-tag step.

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

Update the four repository fields in a single commit, land it, then create the
tag from that commit — the tag is the fifth site and by definition cannot be
inside the commit it points at. Then repeat from step 1.

`CHANGELOG.custom.md` also records the version as a release-lifecycle heading.
It is not a plugin-resolution source, so it is not in the table above, but it
should be updated in the same release commit. `skills/dev/SKILL.md`
keeps its `+upstream.<sha>` suffix, updated only when an upstream merge changes
the base commit — see [UPSTREAM.md](../UPSTREAM.md).
