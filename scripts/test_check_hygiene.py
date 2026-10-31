#!/usr/bin/env python3
"""Self-test for the hygiene gate.

The gate in ``check_hygiene.py`` exists to stop a regression that happened
four times in this repository.  A gate that does not fire is worse than no
gate at all, because it creates a false sense of security -- which is
exactly what revision 064d4c6 shipped: an over-escaped regex that caught
only 4 of the 19 leak lines.

This test therefore verifies both directions:

  1. every leak family that was actually removed from ``docs/`` is detected;
  2. benign strings (URLs, LaTeX prose, ratios) are not flagged.

The leak strings below are assembled from pieces at runtime, so this file
itself contains no literal forbidden pattern and the gate does not need to
exempt it.

Run:  python scripts/test_check_hygiene.py
Exit code 0 = the gate behaves as intended.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_hygiene as gate  # noqa: E402


# One literal backslash, and the pieces of the paths that must be caught.
# Assembling them here keeps this file itself clean.
_BS = chr(92)
_FS = chr(47)
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


# The leak families, verbatim in spirit, that were removed from docs/ in
# commit 064d4c6 plus the variants a future edit could introduce.
LEAK_CASES = [
    ('session workspace path',
     _path('C:', _HOME_DIR, 'mater', _RUNTIME_DIR, 'sessions', 'mvs_abc',
           'workspace', 'qoi-repo', 'scripts', 'x.py')),
    ('internal source root D drive',
     'ugyanitt: ' + _path('D:', _ROOT_D, 'quantum-lab', '')),
    ('internal source root, skills folder',
     'MERES (grep, ' + _path('D:', _ROOT_SKILLS, 'claude-logic', 'src',
                              'main.rs)') + '):'),
    ('cargo target directory',
     'bridge-cli: ' + _path('E:', _ROOT_TARGET + '-qoi', 'debug',
                            'bridge-cli.exe')),
    ('forward-slash user home',
     'C:' + _FS + _HOME_DIR + _FS + 'mater' + _FS + _RUNTIME_DIR + _FS
     + 'sessions' + _FS + 'x'),
    ('forward-slash internal root',
     'ugyanitt: D:' + _FS + _ROOT_D + _FS + 'quantum-lab' + _FS),
    ('bare internal root',
     'path D:' + _BS + _ROOT_D),    ('bare runtime directory name',
     'runtime ' + _RUNTIME_DIR + ' sessions'),
    ('bare user home directory',
     _HOME_DIR + _BS + 'mater' + _BS + 'x'),
    ('mixed separators',
     'D:' + _BS + _ROOT_D + '/quantum-lab'),]


# Strings that must NOT be flagged.  These appear in ordinary LaTeX, in
# URLs, and in measurement prose.
BENIGN_CASES = [
    ('https URL', 'https://github.com/silentnoisehun/quantum-organic-intelligence'),
    ('http URL', 'http://example.org/path'),
    ('ftp URL', 'ftp://files.example.org/x'),
    ('DOI', 'doi:10.1145/3712345.3712346'),
    ('DOI in URL', 'https://doi.org/10.1145/3597503'),
    ('measured ratio', 'ratio A:1.0000 -> 0.9922'),
    ('paper section marker', 'see Section 3: the method'),
    ('measurement ratio prose', 'the ratio 4.3e+03x (79x)'),
    ('author email', 'materobi86@gmail.com'),
    ('plain word users', 'the users of the system'),
    ('plain word codex', 'the codex of the manuscript'),
]


def detected(text, extension='.txt'):
    """Return the labels of the patterns that fire on text."""
    labels = []
    for label, pattern in gate.patterns_for('sample' + extension):
        if re.search(pattern, text):
            labels.append(label)
    return labels


def main():
    failures = []

    print("=" * 74)
    print("PART 1 -- every leak family must be DETECTED")
    print("=" * 74)
    for label, sample in LEAK_CASES:
        hits = detected(sample)
        if hits:
            print(f"  DETECTED  {label}")
            print(f"            by: {hits}")
        else:
            print(f"  MISSED    {label}")
            failures.append(f"leak family not detected: {label}")

    print()
    print("=" * 74)
    print("PART 2 -- benign strings must NOT be flagged")
    print("=" * 74)
    for label, sample in BENIGN_CASES:
        hits = detected(sample)
        if hits:
            print(f"  FALSE POSITIVE  {label}  -> {hits}")
            failures.append(f"false positive on benign case: {label}")
        else:
            print(f"  OK             {label}")

    print()
    print("=" * 74)
    print("PART 3 -- LaTeX sources use the narrower rule set")
    print("=" * 74)
    latex_leak = 'D:' + _BS + _ROOT_D + _BS + 'quantum-lab'
    latex_hits = detected(latex_leak, '.tex')
    if latex_hits:
        print(f"  DETECTED  internal root in a .tex file  -> {latex_hits}")
    else:
        print("  MISSED    internal root in a .tex file")
        failures.append("latex source: internal root not detected")
    latex_benign = detected(
        _BS + 'newcommand{' + _BS + 'x}{A:' + _BS + 'B}', '.tex')
    if latex_benign:
        print(f"  FALSE POSITIVE  latex command with colon -> {latex_benign}")
        failures.append("latex source: false positive on a drive-letter colon")
    else:
        print("  OK             latex command with a drive-letter colon is clean")

    print()
    print("=" * 74)
    if failures:
        print(f"SELF-TEST FAILED: {len(failures)} problem(s)")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(
        f"SELF-TEST PASSED: {len(LEAK_CASES)} leak families detected, "
        f"{len(BENIGN_CASES)} benign strings clean"
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())