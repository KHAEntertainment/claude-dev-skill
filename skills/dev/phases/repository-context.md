# Repository & Account Context — canonical procedure

One canonical procedure, referenced by every phase and agent prompt that
touches a Git push or a GitHub read/mutation. Do not redefine this logic
independently in another prompt file; reference this one.

`.dev.json` at the worktree root records confirmed, nonsecret project intent.
It never holds a token, password, private key, or credential-bearing URL.
`skills/dev/scripts/dev_config.py` owns its schema, validation, and creation.
`skills/dev/scripts/resolve_repository.py` owns comparing that intent against
what a checkout and its authentication would actually do — and **loads
`.dev.json` itself**: every invocation below fails closed on a missing,
invalid, or tracked config, regardless of which other flags are passed.

```json
{
  "version": 1,
  "github": {
    "host": "github.com",
    "account": "your-account",
    "pushRepository": "your-account/project",
    "pullRequestRepository": "your-account/project",
    "pushRemote": "origin"
  }
}
```

## First invocation (run before any GitHub mutation, Phase 0)

1. Locate the worktree root (`git rev-parse --show-toplevel`, or the
   explicitly selected project root before Git exists). Do not search parent
   directories for another project's `.dev.json`.
2. Run `dev_config.py status`. Its `status` field decides the next step:
   - `tracked` — `/.dev.json` is committed in this repository. **Stop.**
     A repository-supplied file is never trusted as user-confirmed intent.
     Ask the user for a focused decision before doing anything else.
   - `invalid` — a file exists but fails schema validation. **Stop.** Report
     the `reason`. Never rewrite or discard the file to make it valid.
   - `not_ignored` — the file is valid and untracked, but not yet covered by
     the repository-local exclude file. Run `dev_config.py create`'s exclusion
     step (`ensure_excluded`) before treating it as ready, then re-check status.
   - `valid` — reuse it. Do not ask the user to reconfirm values that already
     agree with observed reality.
   - `missing` — continue to step 3.
3. For `missing` on an existing checkout: collect candidate remotes, every
   effective push URL, GitHub repository metadata, and available account
   evidence with read-only calls only. Remote names, fork metadata, and the
   active CLI account are candidates, not confirmed intent.
   - If the repository is a fork (or the user states a work-type preference),
     present the two supported presets and their resulting destinations:

     | Preset | Git pushes | Plugin task issues | PRs |
     | --- | --- | --- | --- |
     | Independent fork | user's fork | user's fork | user's fork |
     | Upstream contributor | user's fork | user's fork | explicitly confirmed upstream |

     Never infer contributor mode merely because GitHub reports a parent.
     When contributor mode is selected, confirm the actual upstream target
     explicitly. A preset initializes the explicit fields; do not persist a
     separate `workType` field that could disagree with them.
4. Present one compact setup proposal — account, push/task-issue repository,
   push remote, and PR repository — and ask for confirmation or a correction
   together. Reuse an explicit choice the user already supplied instead of
   asking again.
5. Verify the selected values against available repository/authentication
   facts (see "Pre-write verification" below run once, read-only). An
   unresolved identity/destination mismatch on an existing checkout stops
   setup; do not stamp a guessed configuration as established.
6. Run `dev_config.py create` with the confirmed values. It refuses to
   overwrite an existing file; if another setup process created one
   meanwhile, read and compare instead of replacing it.
7. Confirm the file is excluded (`dev_config.py` runs `ensure_excluded`
   automatically on create) before staging any project files. A file already
   tracked by the project requires the same focused user decision as step 2;
   never untrack or overwrite it automatically.

### A genuinely new project (no remote yet)

No remote or repository may exist on the first invocation. Confirm the
intended name/owner/account, verify the available GitHub account, and save
those confirmed values at the selected project root with `dev_config.py
create`. Explicitly report that remote and Git-transport checks are pending —
file existence never makes a push ready. If the user has not chosen a name or
usable account yet, leave setup incomplete rather than inventing one; finish
it before the first GitHub write. Phase 2's bootstrap step is responsible for
the actual repository creation; before that write, check the CLI account
(`resolve_repository.py --mode check-gh-account --account <github.account>`)
and create using the full confirmed `<account>/<project-name>`, never a bare
project name. After creation/clone, re-run this procedure to verify the
actual remote, repository, and Git identity before any push. If bootstrap
creates a different local root, move the confirmed file there explicitly and
exclude it before any staging.

## Worktrees

When preparing a worker/QA/reviewer worktree, the lead copies the confirmed
local file into the new worktree before launch, after verifying the
source/worker Git common-directory relationship. Do not overwrite a
differing worker config — if one already exists and disagrees, report it
rather than replacing it. This avoids a new setup interview per worker while
preserving the same target intent. A worker or resumed session that finds no
config in an unrelated clone triggers first-use setup, not a silent copy from
elsewhere.

## Pre-write verification (run immediately before every push and every GitHub mutation)

Never reuse a verdict from before a config, credential, branch, or remote
change — recheck immediately before the write, using the same remote/target
and refspec the write will use. `resolve_repository.py` always loads and
requires a valid `.dev.json` for both forms below; there is no way to bypass
that by omitting a flag.

### Before a Git push

```bash
resolve_repository.py --repo-dir <worktree> --operation push \
  --assigned-branch <ledger-assigned branch>
```

- Loads `.dev.json`, resolves the actual effective push remote and **every
  one of its push URLs** (fetch URLs are separate context and never block —
  a fork that fetches upstream while pushing to itself is a supported shape,
  not a mismatch), and requires them to match `github.pushRepository` and
  `github.pushRemote`.
- Confirms the current checkout is actually on `--assigned-branch`, then runs
  `git push --dry-run` for the exact validated remote and refspec. This is
  the one non-offline check in the module: it never advances a ref, but it is
  real evidence the push will reach the intended destination, not only that
  the URLs look right.
- Exit 0 with `status: "ready"` means push. Use the printed
  `effective_push_remote` (or `--print-push-remote`) as the remote argument —
  never a value read from a rejected verdict, and never a bare `git push`
  that lets Git's own default choose:
  ```bash
  remote="$(resolve_repository.py --repo-dir <worktree> --operation push \
    --assigned-branch <branch> --print-push-remote)" || exit 1
  git push "$remote" "<branch>:refs/heads/<branch>"
  ```
- Exit 2 means stop — no fallback, no default selection. `gh_default` and
  `notes` in the JSON output are informational only: an unrelated `gh repo
  set-default` disagreeing with the target does **not** block.

### Before a PR or Issue operation

```bash
resolve_repository.py --repo-dir <worktree> --operation pr \
  --target <the literal OWNER/REPO you are about to pass to gh>
```

This has nothing to do with git push URLs — a PR/Issue is a literal `--repo`
argument, so the check is simply "does that argument match confirmed
intent". Use `--operation pr` (target must equal `pullRequestRepository`) for
PR create/read/review/merge, or `--operation issue` (target must equal
`pushRepository` by default) for a plugin-created Issue. For an operation on
an **explicitly assigned existing Issue** whose own qualified repository
identity is expected to differ (already confirmed via the ledger, not
re-derived here), add `--allow-target-override`. Every `ready` result here
also verifies the actual `gh` CLI login
(`resolve_repository.py --mode check-gh-account`) against `github.account`
before you may treat the operation as safe — two accounts can both have
access to a repository, so a correct Git credential does not establish which
account `gh` will use.

Use the confirmed target explicitly in the command: `gh <cmd> --repo
<owner/repo>` where accepted, the explicit REST/GraphQL endpoint path or
repository identity for `gh api`, and the positional repository for `gh repo
create`. Never rely on a cwd-derived `{owner}`/`{repo}` placeholder or an
inherited `gh` default. Reference an Issue in another repository as `Closes
OWNER/REPO#N` (or its URL), never a bare `#N`.

**Run this check before the first command that touches the repository at
all** — including an early read like posting an understanding-confirmation
comment on an Issue, not only the final write. A check run only immediately
before the last command in a sequence leaves every earlier command in that
sequence unscoped.

### Authentication support boundary

| Transport | Supported verification |
| --- | --- |
| Ordinary HTTPS with an existing credential helper | `resolve_repository.py --mode check-https-account --url <exact push URL> --account <github.account>` — `git credential fill` for the exact URL/context, checked in-process only |
| Standard OpenSSH, including host aliases | `resolve_repository.py --mode check-ssh-account --host <alias or host> --account <github.account>` — resolves the alias via `ssh -G` to confirm it points at GitHub, then probes the **original alias** (never the resolved hostname) so the alias's own port/identity/user apply exactly as a real push would; requires GitHub's documented greeting and exit status **1** |
| GitHub CLI / API mutation | `resolve_repository.py --mode check-gh-account --account <github.account>` — `gh api user`, never `gh auth status` alone |

`verified` is the only status that establishes an account; `incomplete` with
`unsupported_transport_auth`, `identity_unavailable`, or `account_mismatch`
all stop the write. Commit authorship, a URL username, and `gh auth status`
alone never establish this — they are not accepted as substitutes.

Anything else — `GIT_SSH_COMMAND`/`GIT_SSH`/`core.sshCommand`/`ssh.variant`
overrides, an HTTP auth override matched the way Git itself matches it
(`git config --get-urlmatch http.extraHeader <url>`, not a literal key), an
askpass fallback (`GIT_ASKPASS`/`SSH_ASKPASS` or `core.askPass`), or an
unreadable/unexpected probe response — returns `unsupported_transport_auth`
or `identity_unavailable` rather than probing a different, lower-precedence
source. Never run credential `approve`/`reject`, persist a new credential,
switch accounts, or accept a new SSH host key automatically. A
credential-helper secret is captured only inside the helper process; it is
never printed, logged, or written to a temp file or the ledger.

This narrows stale-state exposure within the supported workflow; it is not an
atomic guarantee against a concurrent hostile change.
