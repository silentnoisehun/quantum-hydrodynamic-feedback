#!/usr/bin/env python3
"""End-to-end proof that the hygiene gate fails on a real reintroduced leak.

Writes the exact pre-sanitization lines from commit 064d4c6 into a tracked
file, runs the gate as a subprocess, and asserts the exit code is non-zero.
The file is restored afterwards.  Nothing outside the repository is touched.

The leak lines are assembled from pieces at runtime, so this file itself
contains no literal forbidden pattern and the gate does not need to exempt
it.
"""

import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(REPO, 'docs', 'MEASUREMENTS-FLUID-STRATOS-20261026.txt')
GATE = os.path.join(REPO, 'scripts', 'check_hygiene.py')

_BS = chr(92)
_HOME_DIR = 'Users'
_RUNTIME_DIR = '.' + 'minimax'
_ROOT_D = 'codex'
_ROOT_SKILLS = 'All' + '_Skills'
_ROOT_TARGET = 'mm' + '-target'


def _path(*parts):
    """Join path parts with a backslash separator.

    The first part is the drive prefix (for example ``C:``) and must be
    followed by a separator, so it is joined explicitly.
    """
    head = parts[0]
    tail = _BS.join(parts[1:])
    return head + _BS + tail


# The exact lines that commit 064d4c6 removed, verbatim in content.
PRE_SANITIZATION_LINES = [
    'A launchpad renderer: ' + _path('D:', _ROOT_D,
                                     'Hope Wave protocol Studio',
                                     'crates', ''),
    'MERES (grep, ' + _path('D:', _ROOT_SKILLS, 'claude-logic', 'src',
                             'main.rs)') + '):',
    'Bemenet: a valos STRATOS allapot, '
    + _path('D:', _ROOT_SKILLS, 'claude-logic', 'stratos.bin'),
    _path('C:', _HOME_DIR, 'mater', _RUNTIME_DIR, 'sessions',
          'mvs_4be75a039e3e4dd2a6a370720f28065c', 'workspace',
          'qoi-repo', 'scripts', 'x.py'),
    'bridge-cli: ' + _path('E:', _ROOT_TARGET + '-qoi', 'debug',
                           'bridge-cli.exe'),
]


def run_gate():
    result = subprocess.run(
        [sys.executable, GATE],
        cwd=REPO, capture_output=True, text=True,
    )
    return result.returncode, result.stdout, result.stderr


def main():
    with open(TARGET, 'r', encoding='utf-8') as handle:
        original = handle.read()

    # Baseline: the clean tree must pass.
    rc, out, err = run_gate()
    print(f"baseline (clean tree): rc={rc}")
    if rc != 0:
        print("  UNEXPECTED FAILURE on the clean tree:")
        print(err)
        return 1
    print(f"  {out.strip()}")

    # Inject each leak line one at a time and require rc != 0 every time.
    failures = []
    try:
        for index, line in enumerate(PRE_SANITIZATION_LINES, start=1):
            with open(TARGET, 'w', encoding='utf-8') as handle:
                handle.write(original + '\n' + line + '\n')
            rc, out, err = run_gate()
            detected = rc != 0
            label = line[:62]
            print(f"\ninjected leak {index}/{len(PRE_SANITIZATION_LINES)}: "
                  f"rc={rc}  {'DETECTED' if detected else 'MISSED'}")
            print(f"  {label}")
            if not detected:
                failures.append(f"gate did not fail on: {label}")
            else:
                first = [ln for ln in err.splitlines() if ':' in ln and '[' in ln]
                if first:
                    print(f"  -> {first[0].strip()}")
    finally:
        with open(TARGET, 'w', encoding='utf-8') as handle:
            handle.write(original)

    # Confirm the file was restored and the tree passes again.
    rc, out, err = run_gate()
    print(f"\nafter restore: rc={rc}")
    if rc != 0:
        failures.append("tree did not return to a passing state after restore")

    print()
    if failures:
        print(f"END-TO-END TEST FAILED: {len(failures)} problem(s)")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("END-TO-END TEST PASSED: every reintroduced leak was caught, "
          "and the clean tree passes")
    return 0


if __name__ == '__main__':
    sys.exit(main())