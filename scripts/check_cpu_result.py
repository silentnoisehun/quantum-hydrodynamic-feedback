#!/usr/bin/env python3
"""Compare the regenerated CPU measurement with the committed one.

Why this exists
---------------
The measurement job in CI regenerates ``measurement_cpu/quantum-loop-results.json``
and compares it with the committed version.  The first version of that gate
was a plain ``git diff --exit-code``, i.e. a byte-identity requirement.

That gate was wrong, and it was proved wrong by the CI itself on
2026-11-01 (run 41300523065): the file differed on the Linux runner while
the Windows run of the same commit was byte identical.  The measured cause
is the floating point noise of the coherence values:

  coh_min   0.398488036528213   vs  0.3984880365281942
  coh_mean  0.9292912247944051  vs  0.929291224794398
  coh_mean  0.9999997415307316  vs  0.9999997415307497

a relative difference of about 1e-13 to 1e-14.  The mode sequences, the
histograms and every metric derived from them were IDENTICAL - the
simulation's decisions are not close to a tie.  Measured over the 1000
iterations: the smallest decision margin (top1 - top2 mode energy) is
1.43e-4 in the quantum branch and 7.84e-4 in the classical branch, i.e.
eleven orders of magnitude above the platform noise.  The physics is
portable; the last bit of a float is not.

What this gate requires therefore
---------------------------------
* Integers (the mode sequences, the histograms, the integer metrics) must
  be EXACTLY equal.  A changed mode sequence is a changed measurement and
  must fail the build.
* Floats must be equal within a relative tolerance of 1e-9.  The observed
  cross-platform deviation is 1.1e-13, so this leaves four orders of
  magnitude of head room, and it is still four orders of magnitude below
  the precision the paper quotes (1e-4).

``scripts/test_check_cpu_result.py`` proves that this gate fires: it
injects a changed mode sequence, a changed histogram and an out-of-
tolerance float, and asserts a non-zero exit for each.

Usage
-----
    python scripts/check_cpu_result.py [path]
    python scripts/check_cpu_result.py --committed <file> --regenerated <file>

Without arguments the committed version is read from git (HEAD) and the
regenerated one from the working tree.
"""

import json
import os
import subprocess
import sys

DEFAULT_PATH = "measurement_cpu/quantum-loop-results.json"
RTOL = 1e-9


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_float(value):
    return isinstance(value, float)


def compare(committed, regenerated, rtol=RTOL, path="<root>", problems=None, stats=None):
    """Compare two parsed JSON structures.

    Integers must match exactly, floats within the relative tolerance.
    Returns a list of human readable problems (empty when the two agree).
    """
    if problems is None:
        problems = []
    if stats is None:
        stats = {"ints": 0, "floats": 0, "max_rel": 0.0}

    if type(committed) is not type(regenerated) and not (
        _is_int(committed) and _is_float(regenerated)
    ) and not (_is_float(committed) and _is_int(regenerated)):
        problems.append("%s: type differs (%s vs %s)" % (path, type(committed).__name__,
                                                         type(regenerated).__name__))
        return problems

    if isinstance(committed, dict):
        missing = sorted(set(committed) - set(regenerated))
        extra = sorted(set(regenerated) - set(committed))
        for key in missing:
            problems.append("%s.%s: missing in the regenerated file" % (path, key))
        for key in extra:
            problems.append("%s.%s: unexpected key in the regenerated file" % (path, key))
        for key in sorted(set(committed) & set(regenerated)):
            compare(committed[key], regenerated[key], rtol, "%s.%s" % (path, key), problems, stats)
        return problems

    if isinstance(committed, list):
        if len(committed) != len(regenerated):
            problems.append("%s: length differs (%d vs %d)" % (path, len(committed), len(regenerated)))
            return problems
        for i, (a, b) in enumerate(zip(committed, regenerated)):
            compare(a, b, rtol, "%s[%d]" % (path, i), problems, stats)
        return problems

    if _is_int(committed) and _is_int(regenerated):
        stats["ints"] += 1
        if committed != regenerated:
            problems.append("%s: %d != %d (integers must match exactly)" % (path, committed, regenerated))
        return problems

    if _is_float(committed) and _is_float(regenerated):
        stats["floats"] += 1
        scale = max(1.0, abs(committed), abs(regenerated))
        rel = abs(committed - regenerated) / scale
        if rel > stats["max_rel"]:
            stats["max_rel"] = rel
        if rel > rtol:
            problems.append("%s: %.17g != %.17g (relative difference %.3e > %.0e)"
                            % (path, committed, regenerated, rel, rtol))
        return problems

    if committed != regenerated:
        problems.append("%s: %r != %r" % (path, committed, regenerated))
    return problems


def git_committed_version(repo_root, path):
    """Return the committed (HEAD) content of path as a string."""
    result = subprocess.run(
        ["git", "show", "HEAD:%s" % path],
        cwd=repo_root, capture_output=True, check=True,
    )
    return result.stdout.decode("utf-8")


def main(argv):
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = DEFAULT_PATH
    committed_file = None
    regenerated_file = None

    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg == "--committed":
            committed_file = argv[i + 1]; i += 2
        elif arg == "--regenerated":
            regenerated_file = argv[i + 1]; i += 2
        elif arg.startswith("-"):
            print("unknown option: %s" % arg, file=sys.stderr)
            return 2
        else:
            path = arg; i += 1

    try:
        if committed_file:
            with open(committed_file, "r", encoding="utf-8") as handle:
                committed_text = handle.read()
        else:
            committed_text = git_committed_version(repo_root, path)
        if regenerated_file:
            with open(regenerated_file, "r", encoding="utf-8") as handle:
                regenerated_text = handle.read()
        else:
            with open(os.path.join(repo_root, path), "r", encoding="utf-8") as handle:
                regenerated_text = handle.read()
    except (OSError, subprocess.CalledProcessError) as exc:
        print("ERROR: cannot read the measurement files: %s" % exc, file=sys.stderr)
        return 2

    try:
        committed = json.loads(committed_text)
        regenerated = json.loads(regenerated_text)
    except json.JSONDecodeError as exc:
        print("ERROR: invalid JSON: %s" % exc, file=sys.stderr)
        return 2

    problems = []
    stats = {"ints": 0, "floats": 0, "max_rel": 0.0}
    compare(committed, regenerated, RTOL, path, problems, stats)

    print("compared %d integers (exact) and %d floats (relative tolerance %.0e)"
          % (stats["ints"], stats["floats"], RTOL))
    print("largest relative float difference: %.3e" % stats["max_rel"])

    if problems:
        print("CPU RESULT CHECK FAILED: %d problem(s)" % len(problems), file=sys.stderr)
        for problem in problems[:40]:
            print("  %s" % problem, file=sys.stderr)
        if len(problems) > 40:
            print("  ... and %d more" % (len(problems) - 40), file=sys.stderr)
        return 1

    print("CPU RESULT CHECK PASSED: the regenerated measurement matches the committed one")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
