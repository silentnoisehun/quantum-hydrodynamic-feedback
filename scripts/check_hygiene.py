#!/usr/bin/env python3
"""Hygiene gate: fail if absolute personal paths appear in tracked files.

Why this exists
---------------
The QOI repository is public.  Four review rounds each found the same leak
family (absolute Windows paths pointing at an internal source root or a
user home directory) still present in ``docs/`` after a sanitizer commit
claimed to remove them.  The repeated root cause was that the sanitizer ran
against a working copy that was not the committed tree, and the claim was
written from a transcript instead of from ``git show --stat``.

This gate is the mechanism that makes such a regression impossible to merge
silently: it runs on every push and fails the build.

Design notes
------------
* The forbidden patterns are assembled from pieces at runtime, so the
  pattern literals in this file do not themselves match the patterns.  A
  naive raw string with four backslashes is a double-backslash in the
  regex and matches nothing real -- that bug let 15 of the 19 leaks
  through in revision 064d4c6.  ``scripts/test_check_hygiene.py`` proves
  the behaviour in both directions.
* Only *absolute* paths are forbidden.  A drive letter followed by a
  separator is a leak; a URL scheme or ordinary prose is not.
* LaTeX sources get the distinctive-root rules only.  In LaTeX a single
  letter followed by a colon and a backslash is ordinary text, so the
  generic drive-letter rule would produce false positives there.
* The scan covers every git-tracked text file, not a hand-maintained list
  of directories, so a newly added directory cannot escape the gate.
"""

import os
import re
import subprocess
import sys

# --- pattern pieces, assembled at runtime ----------------------------------
# One literal backslash character.  In a regex an escaped backslash matches
# exactly one literal backslash, which is what a real Windows path has.
_BACKSLASH = chr(92)
# A separator class: backslash or forward slash.
_SEP = '[' + re.escape(_BACKSLASH) + '/]'

# 1. Any absolute Windows path: drive letter, colon, separator.  The
#    negative lookbehind stops us matching the tail of a URL such as
#    "https://" (the 's' before the colon is excluded by the class).
PATTERN_ABSOLUTE_DRIVE = r'(?<![A-Za-z0-9_])[A-Za-z]:' + _SEP + r'(?![/])'

# 2. The personal directories that were actually leaked, matched on their
#    own so a forward-slash or mixed-separator spelling is caught too.
PATTERN_USERS_DIR = r'(?<![A-Za-z0-9_])Users' + _SEP
PATTERN_MINIMAX = r'[.]minimax'
PATTERN_KNOWN_ROOTS = (
    r'[\\/](?:codex|All_Skills|mm-target)' + _SEP
)

# Rules that apply everywhere.
PATTERNS_GENERAL = [
    ('user home directory', PATTERN_USERS_DIR),
    ('runtime directory', PATTERN_MINIMAX),
    ('internal source root', PATTERN_KNOWN_ROOTS),
]

# Additional rule for non-LaTeX sources.  In LaTeX, a single letter
# followed by a colon and a backslash is ordinary text, so applying the
# generic drive-letter rule there would flag legitimate prose.
PATTERNS_NON_LATEX = [
    ('absolute Windows path', PATTERN_ABSOLUTE_DRIVE),
]

LATEX_EXTENSIONS = {'.tex', '.bib', '.sty', '.cls', '.bbl'}

# Binary / non-text extensions that carry no readable content.
BINARY_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.pdf', '.zip', '.gz', '.exe',
    '.dll', '.so', '.dylib', '.ico', '.woff', '.woff2', '.ttf', '.bin',
    '.wasm', '.pyc', '.class', '.jar', '.mp4', '.mp3',
}


def patterns_for(path):
    """Return the (label, pattern) rules that apply to a given file."""
    extension = os.path.splitext(path)[1].lower()
    if extension in LATEX_EXTENSIONS:
        return PATTERNS_GENERAL
    return PATTERNS_GENERAL + PATTERNS_NON_LATEX


def git_tracked_files(repo_root):
    """Return the list of files tracked by git, relative to repo_root."""
    try:
        result = subprocess.run(
            ['git', 'ls-files', '-z'],
            cwd=repo_root,
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Error: cannot list git-tracked files: {exc}", file=sys.stderr)
        return None
    raw = result.stdout.decode('utf-8', errors='replace')
    return [p for p in raw.split('\0') if p]


def is_text_candidate(path):
    return os.path.splitext(path)[1].lower() not in BINARY_EXTENSIONS


def scan_file(path, root):
    """Return a list of (line_no, label, pattern, snippet) violations."""
    full = os.path.join(root, path)
    try:
        with open(full, 'r', encoding='utf-8') as handle:
            content = handle.read()
    except (UnicodeDecodeError, OSError):
        return []
    violations = []
    for label, pattern in patterns_for(path):
        for match in re.finditer(pattern, content):
            line_no = content[:match.start()].count('\n') + 1
            line_start = content.rfind('\n', 0, match.start()) + 1
            line_end = content.find('\n', match.end())
            if line_end == -1:
                line_end = len(content)
            snippet = content[line_start:line_end].strip()[:100]
            violations.append((line_no, label, pattern, snippet))
    return violations


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    files = git_tracked_files(repo_root)
    if files is None:
        return 2
    if not files:
        print("HYGIENE CHECK ERROR: no git-tracked files found", file=sys.stderr)
        return 2

    violations = []
    scanned = 0
    for path in files:
        if not is_text_candidate(path):
            continue
        scanned += 1
        for line_no, label, pattern, snippet in scan_file(path, repo_root):
            violations.append((path, line_no, label, pattern, snippet))

    if violations:
        print("HYGIENE CHECK FAILED:", file=sys.stderr)
        for path, line_no, label, pattern, snippet in violations:
            print(f"  {path}:{line_no}  [{label}]  {snippet}", file=sys.stderr)
        print(
            f"\n{len(violations)} forbidden pattern(s) in {scanned} scanned file(s).",
            file=sys.stderr,
        )
        return 1

    print(
        "HYGIENE CHECK PASSED: no absolute personal paths "
        f"in {scanned} scanned tracked file(s)"
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())