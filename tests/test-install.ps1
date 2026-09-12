$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$installer = Join-Path $repo "install.ps1"
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("claude-dev-install-" + [guid]::NewGuid())
$passCount = 0

function Assert-Path([string]$Path) {
    if (-not (Test-Path $Path)) { throw "Missing path: $Path" }
}
function Assert-Absent([string]$Path) {
    if (Test-Path $Path) { throw "Unexpected path: $Path" }
}
function Pass([string]$Name) {
    $script:passCount++
    Write-Host "PASS: $Name"
}
function Skip([string]$Name, [string]$Reason) {
    Write-Host "SKIP: $Name ($Reason)"
}
# Builds a scratch PATH carrying delegating shims for the named tools
# (skipping any not found), so a test can prove "X is unavailable" while
# every other tool stays fully functional. Shims - not copies of the
# resolved executable - are used deliberately: Git for Windows' git.exe
# depends on sibling directories at its real install location (its own
# usr/bin, mingw64/bin, libexec/git-core), so relocating just the .exe
# breaks it outright rather than merely hiding it, which would make a
# test relying on git actually working misreport that breakage as
# whatever guard it meant to exercise.
function New-ScratchPathWithout([string]$Destination, [string[]]$ToolNames) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    foreach ($toolName in $ToolNames) {
        $toolCmd = Get-Command $toolName -ErrorAction SilentlyContinue
        if (-not ($toolCmd -and $toolCmd.Source -and (Test-Path $toolCmd.Source -PathType Leaf))) {
            continue
        }
        $realPath = $toolCmd.Source
        if ($IsWindows) {
            $shimPath = Join-Path $Destination "$toolName.cmd"
            if (-not (Test-Path $shimPath)) {
                Set-Content -LiteralPath $shimPath -Encoding ASCII -Value @(
                    "@echo off"
                    "`"$realPath`" %*"
                    "exit /b %errorlevel%"
                )
            }
        }
        else {
            $shimPath = Join-Path $Destination $toolName
            if (-not (Test-Path $shimPath)) {
                Set-Content -LiteralPath $shimPath -Encoding ASCII -Value @(
                    "#!/bin/sh"
                    "exec `"$realPath`" `"`$@`""
                )
                & chmod +x $shimPath
            }
        }
    }
}
# Proves the scratch PATH's git shim actually runs a real git command
# against $RepoPath, not just that Get-Command finds it. Gates any test
# that genuinely invokes git during the install (as opposed to tests
# where git's absence is itself the point, which never reach a real git
# invocation): if construction is broken on some platform, the test must
# skip with a stated reason rather than misreport the breakage as the
# guard under test.
function Test-ScratchGitWorks([string]$ScratchPath, [string]$RepoPath) {
    $originalPath = $env:PATH
    try {
        $env:PATH = $ScratchPath
        $gitCmd = Get-Command git -ErrorAction SilentlyContinue
        if (-not $gitCmd) { return $false }
        & $gitCmd.Source -C $RepoPath rev-parse --show-prefix *> $null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
    finally {
        $env:PATH = $originalPath
    }
}

try {
    New-Item -ItemType Directory -Path $testRoot | Out-Null

    $fresh = Join-Path $testRoot "fresh config"
    & $installer -ConfigDir $fresh -Lang en | Out-Null
    Assert-Path (Join-Path $fresh "skills\dev\SKILL.md")
    Assert-Path (Join-Path $fresh "skills\dev\phases\external-review.md")
    Assert-Path (Join-Path $fresh "skills\dev\phases\phase5.md")
    Assert-Path (Join-Path $fresh "skills\dev\scripts\inspect_external_reviews.py")
    Assert-Path (Join-Path $fresh "skills\dev\scripts\detect_execution_backend.py")
    Assert-Path (Join-Path $fresh "skills\dev\backends\contract.md")
    Assert-Path (Join-Path $fresh "skills\dev\backends\claude-native.md")
    Assert-Path (Join-Path $fresh "skills\dev\backends\traycer.md")
    Assert-Path (Join-Path $fresh "skills\dev\agents\report-back.md")
    Assert-Path (Join-Path $fresh "skills\dev\agents\reviewer.md")
    Assert-Path (Join-Path $fresh "skills\dev\templates\DEV_STATE_TEMPLATE.md")
    Pass "fresh install with path spaces"

    $dry = Join-Path $testRoot "dry run"
    & $installer -ConfigDir $dry -DryRun | Out-Null
    Assert-Absent $dry
    Pass "dry run is non-mutating"

    $invalid = Join-Path $testRoot "invalid language"
    $rejected = $false
    try { & $installer -ConfigDir $invalid -Lang zh | Out-Null } catch { $rejected = $true }
    if (-not $rejected) { throw "Chinese install unexpectedly succeeded" }
    Assert-Absent $invalid
    Pass "unsupported language rejected before mutation"

    $legacy = Join-Path $testRoot "legacy config"
    New-Item -ItemType Directory -Force -Path (Join-Path $legacy "commands\dev") | Out-Null
    Set-Content -Path (Join-Path $legacy "commands\dev.md") -Value "legacy entry"
    Set-Content -Path (Join-Path $legacy "commands\dev\phase.md") -Value "legacy phase"
    & $installer -ConfigDir $legacy | Out-Null
    Assert-Path (Join-Path $legacy "skills\dev\SKILL.md")
    Assert-Absent (Join-Path $legacy "commands\dev.md")
    Assert-Absent (Join-Path $legacy "commands\dev")
    $legacyBackup = Get-ChildItem (Join-Path $legacy "backups\dev") -Filter dev.md -File -Recurse | Select-Object -First 1
    if (-not $legacyBackup) { throw "Legacy backup missing" }
    Pass "legacy migration and backup"

    $rollback = Join-Path $testRoot "rollback config"
    New-Item -ItemType Directory -Force -Path (Join-Path $rollback "skills\dev") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $rollback "commands\dev") | Out-Null
    Set-Content -Path (Join-Path $rollback "skills\dev\old.txt") -Value "old skill"
    Set-Content -Path (Join-Path $rollback "commands\dev.md") -Value "legacy entry"
    Set-Content -Path (Join-Path $rollback "commands\dev\old-phase.md") -Value "legacy phase"
    $env:DEV_INSTALL_FAIL_AT = "after-backup"
    $failed = $false
    try { & $installer -ConfigDir $rollback | Out-Null } catch { $failed = $true }
    Remove-Item Env:DEV_INSTALL_FAIL_AT -ErrorAction SilentlyContinue
    if (-not $failed) { throw "Injected failure unexpectedly succeeded" }
    Assert-Path (Join-Path $rollback "skills\dev\old.txt")
    Assert-Path (Join-Path $rollback "commands\dev.md")
    Assert-Path (Join-Path $rollback "commands\dev\old-phase.md")
    Pass "rollback after backup"

    # Dirty checkout: uncommitted edits to tracked files and ignored/untracked
    # files under skills/dev must not ship (Issue #44).
    $dirtySource = Join-Path $testRoot "dirty-source"
    New-Item -ItemType Directory -Force -Path $dirtySource | Out-Null
    Copy-Item (Join-Path $repo "*") $dirtySource -Recurse -Force
    Add-Content -Path (Join-Path $dirtySource "skills\dev\SKILL.md") -Value "`n<!-- local edit: must not ship -->"
    New-Item -ItemType Directory -Force -Path (Join-Path $dirtySource "skills\dev\scripts\__pycache__") | Out-Null
    Set-Content -Path (Join-Path $dirtySource "skills\dev\scripts\__pycache__\x.pyc") -Value "compiled"
    $dirtyTarget = Join-Path $testRoot "dirty target"
    & (Join-Path $dirtySource "install.ps1") -ConfigDir $dirtyTarget -Lang en | Out-Null
    Assert-Path (Join-Path $dirtyTarget "skills\dev\SKILL.md")
    if (Select-String -Path (Join-Path $dirtyTarget "skills\dev\SKILL.md") -Pattern "local edit: must not ship" -Quiet) {
        throw "Uncommitted edit to a tracked file shipped in the install"
    }
    Assert-Absent (Join-Path $dirtyTarget "skills\dev\scripts\__pycache__")
    Pass "dirty checkout excludes uncommitted edits and ignored files"

    # No .git source: falls back to the working-tree copy and reports tarball
    # provenance instead of a commit (Issue #44, ADR-007 tarball/libexec case).
    $nogitSource = Join-Path $testRoot "nogit-source"
    New-Item -ItemType Directory -Force -Path $nogitSource | Out-Null
    Copy-Item (Join-Path $repo "*") $nogitSource -Recurse -Force
    Remove-Item (Join-Path $nogitSource ".git") -Recurse -Force -ErrorAction SilentlyContinue
    $nogitTarget = Join-Path $testRoot "nogit target"
    # 6>&1 merges the Information stream (what Write-Host writes to) into the
    # success stream so the provenance line below can be captured.
    $nogitOutput = & (Join-Path $nogitSource "install.ps1") -ConfigDir $nogitTarget -Lang en 6>&1
    Assert-Path (Join-Path $nogitTarget "skills\dev\SKILL.md")
    if (-not ($nogitOutput -match "Installed from: no git metadata \(tarball install\)")) {
        throw "No-.git install did not report tarball provenance"
    }
    Pass "no-.git source installs via the copy path with tarball provenance"

    # A source with no .git of its own, sitting underneath an unrelated git
    # checkout, must not be misclassified as that ancestor's repo: it has to
    # install via the copy path too, not attempt (and fail) a git archive of
    # the ancestor's unrelated tree (Issue #44 follow-up).
    $nestedParent = Join-Path $testRoot "nested-parent"
    New-Item -ItemType Directory -Force -Path (Join-Path $nestedParent "nested") | Out-Null
    & git init --quiet -- $nestedParent
    # -c user.name/user.email keep this fixture hermetic: a CI runner with
    # no git identity configured (no ~/.gitconfig, no GECOS full name)
    # otherwise fails this commit with "Please tell me who you are."
    & git -c user.name=test -c user.email=test@example.com `
        -C $nestedParent commit --quiet --allow-empty -m "unrelated ancestor root commit"
    $nestedRepo = Join-Path $nestedParent "nested\repo"
    Copy-Item $repo $nestedRepo -Recurse -Force
    Remove-Item (Join-Path $nestedRepo ".git") -Recurse -Force -ErrorAction SilentlyContinue
    $nestedTarget = Join-Path $testRoot "nested target"
    $nestedOutput = & (Join-Path $nestedRepo "install.ps1") -ConfigDir $nestedTarget -Lang en 6>&1
    Assert-Path (Join-Path $nestedTarget "skills\dev\SKILL.md")
    if (-not ($nestedOutput -match "Installed from: no git metadata \(tarball install\)")) {
        throw "Nested no-own-.git install did not report tarball provenance"
    }
    Pass "nested source with no own .git installs via the copy path"

    # A source with its own .git but no git binary on PATH must abort with
    # an actionable error and install nothing — never silently fall back
    # to the copy path, which would ship possibly-dirty working-tree
    # content while looking, from the outside, exactly like the safe case
    # (Issue #44 follow-up).
    $noGitBin = Join-Path $testRoot "fakebin-no-git"
    New-ScratchPathWithout -Destination $noGitBin -ToolNames @("python3", "python", "rtk", "tar")
    $noGitTarget = Join-Path $testRoot "no-git-bin target"
    $originalPath = $env:PATH
    $noGitError = $null
    try {
        $env:PATH = $noGitBin
        & $installer -ConfigDir $noGitTarget -Lang en 2>$null | Out-Null
    }
    catch {
        $noGitError = $_.Exception.Message
    }
    finally {
        $env:PATH = $originalPath
    }
    if (-not $noGitError) { throw "Install unexpectedly succeeded with git unavailable in a git checkout" }
    if ($noGitError -notmatch "git is required to stage it safely from git content") {
        throw "Unexpected error text for git-unavailable abort: $noGitError"
    }
    Assert-Absent $noGitTarget
    Pass "git checkout with git binary unavailable aborts and installs nothing"

    # A genuine git checkout with tar unavailable must abort with an
    # actionable error and install nothing, rather than silently falling
    # back to the working-tree copy while still claiming git provenance
    # (Issue #44 follow-up). Only git/python3/rtk are carried into the
    # scratch PATH; tar is deliberately left out. Unlike the git-missing
    # test above, this one genuinely invokes git during the install (the
    # tar guard is only reached once git-checkout validation succeeds), so
    # it self-checks the shimmed git actually works before asserting
    # anything - a platform where shimming can't preserve a working git
    # (observed on windows-latest when the shim relocated the executable
    # instead of delegating to it) skips with a stated reason rather than
    # asserting the wrong error.
    $noTarBin = Join-Path $testRoot "fakebin-no-tar"
    New-ScratchPathWithout -Destination $noTarBin -ToolNames @("git", "python3", "python", "rtk")
    if (-not (Test-ScratchGitWorks -ScratchPath $noTarBin -RepoPath $repo)) {
        Skip "git checkout with tar unavailable aborts and installs nothing" "could not construct a working git shim on this platform"
    }
    else {
        $noTarTarget = Join-Path $testRoot "no-tar target"
        $originalPath = $env:PATH
        $noTarError = $null
        try {
            $env:PATH = $noTarBin
            & $installer -ConfigDir $noTarTarget -Lang en 2>$null | Out-Null
        }
        catch {
            $noTarError = $_.Exception.Message
        }
        finally {
            $env:PATH = $originalPath
        }
        if (-not $noTarError) { throw "Install unexpectedly succeeded with tar unavailable in a git checkout" }
        $expectedNoTarError = "This is a git checkout of the Skill, but tar is required to stage it safely from git content. Install tar, or install from a release tarball instead."
        if ($noTarError -ne $expectedNoTarError) {
            throw "Unexpected error text for tar-unavailable abort: $noTarError"
        }
        Assert-Absent $noTarTarget
        Pass "git checkout with tar unavailable aborts and installs nothing"
    }

    # The converse of the exclusion case above: an uncommitted *deletion* of
    # a required tracked file must not block installing the perfectly valid
    # committed tree. Preflight has to validate what will actually be
    # installed (the committed content at HEAD), not the mutable working
    # tree (Issue #44 follow-up).
    $dirtyDeletionSource = Join-Path $testRoot "dirty-deletion-source"
    New-Item -ItemType Directory -Force -Path $dirtyDeletionSource | Out-Null
    Copy-Item (Join-Path $repo "*") $dirtyDeletionSource -Recurse -Force
    Remove-Item (Join-Path $dirtyDeletionSource "skills\dev\phases\phase5.md")
    $dirtyDeletionTarget = Join-Path $testRoot "dirty-deletion target"
    & (Join-Path $dirtyDeletionSource "install.ps1") -ConfigDir $dirtyDeletionTarget -Lang en | Out-Null
    Assert-Path (Join-Path $dirtyDeletionTarget "skills\dev\phases\phase5.md")
    Pass "uncommitted deletion of a tracked file does not block installing the committed tree"

    # The other side of that fix: a file *actually* missing from the
    # committed tree (removed and committed, not just deleted on disk) must
    # still be caught by preflight in git mode, before any mutation - the
    # fix above must not have quietly turned preflight validation off for
    # git checkouts.
    $committedBrokenSource = Join-Path $testRoot "committed-broken-source"
    & git clone --quiet -- $repo $committedBrokenSource
    & git -c user.name=test -c user.email=test@example.com `
        -C $committedBrokenSource rm --quiet -- skills/dev/phases/phase5.md
    & git -c user.name=test -c user.email=test@example.com `
        -C $committedBrokenSource commit --quiet -m "remove a required file"
    $committedBrokenTarget = Join-Path $testRoot "committed-broken target"
    $committedBrokenFailed = $false
    try { & (Join-Path $committedBrokenSource "install.ps1") -ConfigDir $committedBrokenTarget -Lang en | Out-Null }
    catch { $committedBrokenFailed = $true }
    if (-not $committedBrokenFailed) { throw "Install with a required file missing from the committed tree unexpectedly succeeded" }
    Assert-Absent $committedBrokenTarget
    Pass "a required file missing from the committed tree is still rejected before mutation"

    # Clean checkout: the install reports the staged commit (Issue #44).
    $cleanTarget = Join-Path $testRoot "clean target"
    $cleanOutput = & $installer -ConfigDir $cleanTarget -Lang en 6>&1
    $expectedCommit = (& git -C $repo rev-parse HEAD).Trim()
    if (-not ($cleanOutput -match "Installed from commit $expectedCommit")) {
        throw "Clean checkout install did not report the staged commit"
    }
    Pass "clean checkout install reports commit provenance"

    # Static guard against the provenance race regressing: the archive call
    # must pin the commit already captured and validated (installCommit),
    # not re-resolve HEAD at staging time, which would reopen a window
    # where a concurrent commit could make the archived content disagree
    # with the commit the install reports (Issue #44 follow-up).
    $installerSource = Get-Content -Raw -LiteralPath $installer
    if ($installerSource -match [regex]::Escape('"archive", "-o", $archiveFile, "HEAD"')) {
        throw "install.ps1 archives HEAD directly instead of the captured installCommit"
    }
    if ($installerSource -notmatch [regex]::Escape('"archive", "-o", $archiveFile, $installCommit')) {
        throw "install.ps1 does not archive the captured installCommit"
    }
    Pass "install.ps1 archives the captured commit, not HEAD, at staging time"

    # GIT_DIR/GIT_WORK_TREE/GIT_COMMON_DIR inherited from the caller's
    # environment override git's repository discovery entirely, so without
    # neutralizing them a perfectly valid own-.git checkout could silently
    # validate, archive, and install a completely different repository's
    # committed tree while reporting *its* commit (Issue #44 follow-up).
    # GIT_COMMON_DIR is the linked-worktree analog of GIT_DIR; poisoning it
    # alongside the other two is defense in depth even though it did not
    # independently redirect this worktree-less checkout. Point all three
    # at a disposable repo carrying a planted marker file and confirm the
    # real source's own tree and commit are what actually gets installed.
    $envHijackAlt = Join-Path $testRoot "env-hijack-alt"
    New-Item -ItemType Directory -Force -Path $envHijackAlt | Out-Null
    Copy-Item (Join-Path $repo "skills") $envHijackAlt -Recurse -Force
    & git init --quiet -- $envHijackAlt
    Set-Content -Path (Join-Path $envHijackAlt "skills\dev\ENV_HIJACK_MARKER.txt") -Value "planted by an unrelated repo; must never ship"
    & git -C $envHijackAlt add -A
    & git -c user.name=test -c user.email=test@example.com `
        -C $envHijackAlt commit --quiet -m "alt repo commit carrying a planted marker"
    $envHijackTarget = Join-Path $testRoot "env-hijack target"
    $expectedRealCommit = (& git -C $repo rev-parse HEAD).Trim()
    $originalGitDir = $env:GIT_DIR
    $originalGitWorkTree = $env:GIT_WORK_TREE
    $originalGitCommonDir = $env:GIT_COMMON_DIR
    try {
        $env:GIT_DIR = Join-Path $envHijackAlt ".git"
        $env:GIT_WORK_TREE = $envHijackAlt
        $env:GIT_COMMON_DIR = Join-Path $envHijackAlt ".git"
        $envHijackOutput = & $installer -ConfigDir $envHijackTarget -Lang en 6>&1
    }
    finally {
        if ($null -ne $originalGitDir) { $env:GIT_DIR = $originalGitDir } else { Remove-Item Env:GIT_DIR -ErrorAction SilentlyContinue }
        if ($null -ne $originalGitWorkTree) { $env:GIT_WORK_TREE = $originalGitWorkTree } else { Remove-Item Env:GIT_WORK_TREE -ErrorAction SilentlyContinue }
        if ($null -ne $originalGitCommonDir) { $env:GIT_COMMON_DIR = $originalGitCommonDir } else { Remove-Item Env:GIT_COMMON_DIR -ErrorAction SilentlyContinue }
    }
    Assert-Path (Join-Path $envHijackTarget "skills\dev\SKILL.md")
    Assert-Absent (Join-Path $envHijackTarget "skills\dev\ENV_HIJACK_MARKER.txt")
    if (-not ($envHijackOutput -match "Installed from commit $expectedRealCommit")) {
        throw "Install reported the wrong commit under an inherited GIT_DIR/GIT_WORK_TREE/GIT_COMMON_DIR"
    }
    Pass "inherited GIT_DIR/GIT_WORK_TREE/GIT_COMMON_DIR cannot redirect install to another repository"

    # The fix for the hijack above must clean only the CHILD git process's
    # environment, never this process's own: install.ps1 runs via `&` in
    # this same runspace (not as its own process), so an earlier version
    # that removed these variables from $env: for "this process" mutated
    # the CALLER's session too, permanently - proven by this exact probe,
    # which survived even a -DryRun (Issue #44 follow-up). Set sentinel
    # values, run a dry run, and confirm all five are unchanged afterward.
    $sentinelVars = [ordered]@{
        GIT_DIR              = "sentinel-gitdir"
        GIT_WORK_TREE        = "sentinel-worktree"
        GIT_INDEX_FILE       = "sentinel-indexfile"
        GIT_OBJECT_DIRECTORY = "sentinel-objdir"
        GIT_COMMON_DIR       = "sentinel-commondir"
    }
    $originalSentinelValues = @{}
    foreach ($varName in $sentinelVars.Keys) {
        $originalSentinelValues[$varName] = [Environment]::GetEnvironmentVariable($varName, "Process")
        Set-Item "Env:$varName" $sentinelVars[$varName]
    }
    try {
        $sentinelDryTarget = Join-Path $testRoot "sentinel-dry-run"
        & $installer -ConfigDir $sentinelDryTarget -Lang en -DryRun | Out-Null
        foreach ($varName in $sentinelVars.Keys) {
            $currentValue = [Environment]::GetEnvironmentVariable($varName, "Process")
            if ($currentValue -ne $sentinelVars[$varName]) {
                throw "install.ps1 mutated the caller's `$varName during -DryRun (expected '$($sentinelVars[$varName])', got '$currentValue')"
            }
        }
    }
    finally {
        foreach ($varName in $sentinelVars.Keys) {
            if ($null -ne $originalSentinelValues[$varName]) {
                Set-Item "Env:$varName" $originalSentinelValues[$varName]
            }
            else {
                Remove-Item "Env:$varName" -ErrorAction SilentlyContinue
            }
        }
    }
    Pass "sentinel GIT_* env vars survive a -DryRun install unchanged in the caller's session"

    Write-Host "All $passCount PowerShell installer tests passed."
}
finally {
    Remove-Item Env:DEV_INSTALL_FAIL_AT -ErrorAction SilentlyContinue
    if (Test-Path $testRoot) { Remove-Item $testRoot -Recurse -Force }
}
