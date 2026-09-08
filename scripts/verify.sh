#!/usr/bin/env bash
# Invoke directly; the shebang fixes the interpreter regardless of interactive shell.
set -uo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." || exit 1
failed=0
not_run=0
passed=0
skipped=0

run_check() {
    local name=$1 code
    shift
    printf '\nRUN: %s\n' "$name"
    "$@"
    code=$?
    case "$code" in
        0) printf 'PASSED: %s (exit %s)\n' "$name" "$code"; passed=$((passed + 1)) ;;
        # Heuristic: a checked program can itself legitimately exit 126/127.
        # Always fail the gate, but report these separately as execution failures.
        126|127) printf 'NOT RUN (did-not-run): %s (exit %s)\n' "$name" "$code"; not_run=$((not_run + 1)) ;;
        *) printf 'FAILED: %s (exit %s)\n' "$name" "$code"; failed=$((failed + 1)) ;;
    esac
}

run_check 'ShellCheck' shellcheck install.sh tests/test-install.sh scripts/check_plugin_root.sh scripts/verify.sh
run_check 'Installer syntax' bash -n install.sh
run_check 'Verification script syntax' bash -n scripts/verify.sh
run_check 'Skill validation' python3 scripts/validate_skill.py
export PYTHONDONTWRITEBYTECODE=1
run_check 'Python tests' python3 -m unittest discover -s tests -p 'test_*.py'
run_check 'Bash installer tests' bash tests/test-install.sh
run_check 'Plugin root' scripts/check_plugin_root.sh
run_check 'Version sync' python3 scripts/check_version_sync.py
run_check 'Claude plugin validation' claude plugin validate . --strict

if command -v pwsh >/dev/null 2>&1; then
    run_check 'PowerShell installer tests' pwsh tests/test-install.ps1
elif [[ ${OS:-} == Windows_NT ]]; then
    run_check 'PowerShell installer tests' pwsh tests/test-install.ps1
else
    printf '\nSKIPPED: PowerShell installer tests (pwsh absent; optional off Windows; exit n/a)\n'
    skipped=$((skipped + 1))
fi

printf '\nSUMMARY: %s passed, %s failed, %s did-not-run, %s optional skipped\n' "$passed" "$failed" "$not_run" "$skipped"
if (( failed > 0 || not_run > 0 )); then
    printf 'GATE FAILED\n'
    exit 1
fi
printf 'GATE PASSED\n'
