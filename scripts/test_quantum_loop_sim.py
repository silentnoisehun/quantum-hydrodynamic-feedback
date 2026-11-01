"""Regresszios teszt a kvantum csatorna konvencioira.

A hardver a Rust bridge-cli-t hasznalta a dekódolásra
(`crates/quantum-bridge/src/lib.rs:365`):
    A = 2*arccos(sqrt(P(q0=0)))
Ha a Python szimuláció más konvenciót követ, akkor a CPU "kvantum" ág
más rendszert szimulál, mint amit a hardveren futott — és az összehasonlítás
nem azt méri, amit állít.

A tesztek a HARDVERBŐL származó bizonyítékhoz kötik a konvenciót:
a nyers `counts_raw` fájlokat visszafejtik, és a rögzített
`decoded_raw` értékekkel egyeztetik.

Futtatás:  python scripts/test_quantum_loop_sim.py
Kilépési kód 0 = minden teszt zöld.
"""

import glob
import json
import math
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(REPO, "measurement_raw")
sys.path.insert(0, os.path.join(REPO, "scripts"))

import quantum_loop_sim as q  # noqa: E402

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print(f"  OK    {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILURES.append(name)


def test_channels_are_lossless():
    """Zaj nelkuli csatorna: mindhárom parameter veszteségmentesen visszatér."""
    worst_a = worst_f = worst_phi = 0.0
    grid = np.linspace(0.0, 1.0, 21)
    for A in grid:
        for f in np.linspace(0.0, 15.0, 16):
            for phi in grid[::2]:
                a2, f2, p2 = q.quantum_shot_exact(float(A), float(f), float(phi))
                worst_a = max(worst_a, abs(a2 - A))
                worst_f = max(worst_f, abs(f2 - f))
                worst_phi = max(worst_phi, abs(p2 - phi))
    check("the amplitude channel is lossless", worst_a < 1e-9,
          f"(max error {worst_a:.3e})")
    check("the frequency channel is lossless", worst_f < 1e-9,
          f"(max error {worst_f:.3e})")
    check("the phase channel is lossless", worst_phi < 1e-9,
          f"(max error {worst_phi:.3e})")


def test_amplitude_decode_uses_p_q0_zero():
    """A bridge-cli konvencioja: A = 2*arccos(sqrt(P(q0=0)))."""
    counts = {"0": 700, "1": 300}
    p_q0_zero = 0.7
    decoded = q.decode_amplitude(p_q0_zero)
    expected = 2.0 * math.acos(math.sqrt(p_q0_zero))
    check("decode_amplitude follows the bridge convention",
          abs(decoded - expected) < 1e-12)
    # a RY(pi*A) kormany -> P(q0=0) = cos^2(A_kod/2)
    for a_kod in (0.3, 1.0, 2.0, 3.0):
        p0 = math.cos(a_kod / 2.0) ** 2
        back = q.decode_amplitude(p0)
        check(f"amplitude roundtrip at {a_kod}",
              abs(back - a_kod) < 1e-9, f"(got {back:.12f})")


def test_decode_matches_the_recorded_hardware():
    """A hardveres nyers fajjlok visszafejtése reprodukálja a rögzített értékeket.

    Ez a konvenció HARDVER BIZONYÍTÉKA: ha a Python a másik konvenciót
    követné, a két eltérés 2 nagyságrend lenne.
    """
    paths = sorted(glob.glob(os.path.join(RAW, "loop_*_iter*.json")))
    if not paths:
        check("the recorded hardware files are present", False,
              "(no loop_*_iter*.json found)")
        return
    worst_a = worst_f = worst_phi = 0.0
    n = 0
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            d = json.load(handle)
        counts = d["counts_raw"]

        def p_zero(two_qubits):
            total = sum(two_qubits.values())
            width = 2 if two_qubits is counts["frequency"] else 1
            hits = 0
            for key, value in two_qubits.items():
                bits = format(int(key, 2), f"0{width}b")
                if bits[-1] == "0":
                    hits += value
            return hits / total

        a_back = q.decode_amplitude(p_zero(counts["amplitude"]))
        f_back = q.decode_frequency(1.0 - p_zero(counts["frequency"]))
        phi_back = q.decode_phase(1.0 - p_zero(counts["phase"]))
        worst_a = max(worst_a, abs(a_back - d["decoded_raw"]["A"]))
        worst_f = max(worst_f, abs(f_back - d["decoded_raw"]["f"]))
        worst_phi = max(worst_phi, abs(phi_back - d["decoded_raw"]["phi"]))
        n += 1
    check(f"the recorded amplitude decodes ({n} files)", worst_a < 1e-9,
          f"(max error {worst_a:.3e})")
    check(f"the recorded frequency decodes ({n} files)", worst_f < 1e-9,
          f"(max error {worst_f:.3e})")
    check(f"the recorded phase decodes ({n} files)", worst_phi < 1e-9,
          f"(max error {worst_phi:.3e})")


def test_classical_equals_the_noiseless_channel():
    """A zajmentes kvantum csatorna a klasszikus kontrollal azonos.

    Ha ez igaz, akkor a "kvantum vs klasszikus" különbség NEM a csatorna
    strukturájából jön, hanem kizárólag a mérési zajból.
    """
    seed = q.SEED
    iters = 20
    classical = q.run_loop_channel(lambda A, f, phi: (A, f, phi),
                                    iters=iters, seed=seed)
    exact = q.run_loop_channel(q.quantum_shot_exact, iters=iters, seed=seed)
    check("the noiseless channel equals the classical control", classical == exact,
          f"\n        classical: {classical}\n        exact    : {exact}")


def test_noise_models_stay_in_bounds():
    """A zajmodellek a merési hatarokon belul maradnak."""
    for model, lo, hi in ((q.NOISE_SYMMETRIC, 0.5 * (1 - q.C_BELL), 1.0),
                          (q.NOISE_FLOOR, q.HW_PROB_FLOOR, q.HW_PROB_CEILING)):
        for p in (0.0, 0.25, 0.5, 0.75, 1.0):
            eff = q.effective_prob(p, q.C_BELL, model)
            if not (lo - 1e-12 <= eff <= hi + 1e-12):
                check(f"the {model} noise model stays in bounds", False,
                      f"(p={p} -> {eff})")
                return
    check("the noise models stay in bounds", True)


def main():
    print("=" * 74)
    print("A kvantum csatorna regresszios tesztjei")
    print("=" * 74)
    print()
    test_channels_are_lossless()
    print()
    test_amplitude_decode_uses_p_q0_zero()
    print()
    test_decode_matches_the_recorded_hardware()
    print()
    test_classical_equals_the_noiseless_channel()
    print()
    test_noise_models_stay_in_bounds()
    print()
    print("=" * 74)
    if FAILURES:
        print(f"{len(FAILURES)} TESZT ELBUKOTT: {', '.join(FAILURES)}")
        return 1
    print("MINDEN TESZT ZOLD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
