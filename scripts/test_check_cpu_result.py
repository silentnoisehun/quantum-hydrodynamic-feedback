#!/usr/bin/env python3
"""Prove that the CPU result gate fires, and that it does not cry wolf.

The gate (``scripts/check_cpu_result.py``) replaced a byte-identity
``git diff`` that the CI itself proved wrong on 2026-11-01: the file
differed on the Linux runner by about 1e-13 in the coherence floats, while
every mode sequence and histogram was identical.

A gate that stops firing gives false confidence, so this test asserts both
directions:

* the real violations must be caught (a changed mode sequence, a changed
  histogram, a changed integer metric, a float outside the tolerance, a
  changed key set, a changed length);
* the benign cases must stay clean (an identical file, and a float
  perturbed at the platform noise level of 1e-13).

Run: python scripts/test_check_cpu_result.py
"""

import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GATE = os.path.join(HERE, "check_cpu_result.py")
sys.path.insert(0, HERE)

import check_cpu_result  # noqa: E402


def sample():
    """A small structure with the same shape as the real measurement file."""
    return {
        "results": {
            "quantum": {
                "hist": [874, 25, 0, 8, 21, 0, 15, 30, 0, 0, 0, 0, 0, 0, 0, 0],
                "H_Hmax": 0.21982885397603688,
                "mH": 0.414348495225926,
                "active": 16,
                "tail_H": 0.21705829823531503,
                "tail_max": 0.874,
                "distinct_modes": 9,
                "brain_ratio": 0.874,
                "n": 1000,
                "coh_mean": 0.9924862204696897,
                "coh_min": 0.398488036528213,
                "coh_max": 0.9999999999996595,
            }
        },
        "seq_quantum": [0] * 874 + [1] * 25 + [3] * 8 + [4] * 21 + [6] * 15 + [7] * 30,
        "seq_classical": [0] * 949 + [2] * 51,
        "seq_dead": [0] * 1000,
        "coh_quantum": [0.6126353055832283, 0.9990097808637142, 0.7074618287291923],
    }


def run_gate(committed, regenerated):
    """Run the gate as a subprocess; return the exit code."""
    tmp = tempfile.mkdtemp(prefix="qoi_gate_test_")
    cpath = os.path.join(tmp, "committed.json")
    rpath = os.path.join(tmp, "regenerated.json")
    with open(cpath, "w", encoding="utf-8") as handle:
        json.dump(committed, handle, indent=1)
    with open(rpath, "w", encoding="utf-8") as handle:
        json.dump(regenerated, handle, indent=1)
    proc = subprocess.run(
        [sys.executable, GATE, "--committed", cpath, "--regenerated", rpath],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, proc.stdout + proc.stderr


def perturb(value, relative):
    return value * (1.0 + relative)


failures = []


def expect(label, committed, regenerated, wanted_rc):
    rc, out = run_gate(committed, regenerated)
    ok = (rc == wanted_rc)
    print("  [%s] %-52s rc=%d (expected %d)" % ("OK " if ok else "FAIL", label, rc, wanted_rc))
    if not ok:
        failures.append(label)
        print("      " + out.strip().replace("\n", "\n      "))
    return out


print("=== benign cases must stay clean ===")
base = sample()
expect("identical file", base, copy.deepcopy(base), 0)

noise = copy.deepcopy(base)
noise["results"]["quantum"]["coh_min"] = perturb(noise["results"]["quantum"]["coh_min"], 1.1e-13)
noise["results"]["quantum"]["coh_mean"] = perturb(noise["results"]["quantum"]["coh_mean"], 7.6e-15)
noise["results"]["quantum"]["coh_max"] = perturb(noise["results"]["quantum"]["coh_max"], 1.8e-14)
noise["coh_quantum"] = [perturb(v, 6.6e-14) for v in noise["coh_quantum"]]
expect("platform float noise (1e-13 relative)", base, noise, 0)

print()
print("=== real violations must be caught ===")

bad = copy.deepcopy(base)
bad["seq_quantum"][100] = 9
expect("one changed mode in seq_quantum", base, bad, 1)

bad = copy.deepcopy(base)
bad["seq_classical"][3] = 11
expect("one changed mode in seq_classical", base, bad, 1)

bad = copy.deepcopy(base)
bad["results"]["quantum"]["hist"][2] = 1
expect("changed histogram entry", base, bad, 1)

bad = copy.deepcopy(base)
bad["results"]["quantum"]["distinct_modes"] = 8
expect("changed integer metric (distinct_modes)", base, bad, 1)

bad = copy.deepcopy(base)
bad["results"]["quantum"]["H_Hmax"] = perturb(bad["results"]["quantum"]["H_Hmax"], 1e-6)
expect("float outside the tolerance (1e-6 relative)", base, bad, 1)

bad = copy.deepcopy(base)
del bad["results"]["quantum"]["tail_max"]
expect("removed key", base, bad, 1)

bad = copy.deepcopy(base)
bad["extra_key"] = 1
expect("unexpected key", base, bad, 1)

bad = copy.deepcopy(base)
bad["seq_quantum"] = bad["seq_quantum"][:-1]
expect("changed sequence length", base, bad, 1)

print()
print("=== the real committed measurement file must pass against itself ===")
real = os.path.join(REPO, "measurement_cpu", "quantum-loop-results.json")
if os.path.exists(real):
    with open(real, "r", encoding="utf-8") as handle:
        parsed = json.load(handle)
    expect("the committed file compared with itself", parsed, copy.deepcopy(parsed), 0)
else:
    print("  (skipped: %s is not present)" % real)

print()
if failures:
    print("SELF-TEST FAILED: %d case(s): %s" % (len(failures), ", ".join(failures)))
    sys.exit(1)
print("SELF-TEST PASSED: the gate catches every injected violation and stays clean on the benign ones")
sys.exit(0)
