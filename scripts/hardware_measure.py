#!/usr/bin/env python3
"""
A VALÓDI HARDVERES MÉRÉS — a Quantum Organic Intelligence kvantumhídja.

Ez a script a mérési pipeline-t ellenőrzi és a hardver-minőséget méri:

  1. a bit-sorrend-ellenőrzés (a mérés előfeltétele)
  2. a Bell-referencia → a HARDVER-MINŐSÉG (c) mérése
  3. a 16 mód argmax kvantum-mérése → a pontosság a klasszikus argmaxhoz képest
  4. az (A, f, φ) kódolás → mérés → dekódolás ellenőrzése

HASZNÁLAT
---------
    # pipeline-ellenőrzés IDEÁLIS szimulátoron (token NEM kell)
    python scripts/hardware_measure.py --local

    # valódi QPU
    python scripts/hardware_measure.py --backend ibm_fez --shots 1024

    # a 16 módos argmax-pontosság 50 futással
    python scripts/hardware_measure.py --mode-trials 50 --shots 1024

A KULCS: az `IBM_QUANTUM_API_TOKEN` környezetváltozóban (SOSE a
parancssorban, SOSE fájlba írva).

A nyers mérési adatok a `measurement_raw/` mappába kerülnek — ez
verziókövetve (lásd a .gitignore).
"""
import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

# ── a scs_quantum elérhetősége ──────────────────────────────────────────
def _load_scs():
    """A scs_quantum modulok betöltése: telepített csomag, majd SCS_QUANTUM_PATH."""
    try:
        from scs_quantum import tkr_measure, tkr_ibm
        return tkr_measure, tkr_ibm
    except ImportError:
        pass
    p = os.environ.get("SCS_QUANTUM_PATH")
    if not p:
        # Default to relative path from repo root for portability
        repo_root = Path(__file__).parent.parent
        p = str(repo_root / "external" / "scs-quantum" / "python")
    if os.path.isdir(p):
        sys.path.insert(0, p)
        import tkr_measure, tkr_ibm
        return tkr_measure, tkr_ibm
    raise SystemExit(
        "A scs_quantum nem elérhető. Telepítsd: pip install scs-quantum[qpu]\n"
        "vagy állítsd a SCS_QUANTUM_PATH környezetváltozót a python/ mappára."
    )


tkr_measure, tkr_ibm = _load_scs()

Gate = tkr_measure.Gate
CircuitSpec = tkr_measure.CircuitSpec

# ── a mért 16 mód energiái (a STRATOS folyadékból) ───────────────────────
# Brain 0,09620959 · Creativity 0,09443425 · … (a részletek a docs/-ben)
MODE_NAMES = [
    "Brain", "Logic", "Memory", "Creativity", "Heart", "Intuition", "Focus", "Empathy",
    "Analysis", "Synthesis", "Ethics", "Play", "Dream", "Social", "Survival", "Transcendence",
]
MODE_ENERGIES = [
    0.09620959036827400, 0.07677600000000000, 0.08902975000000000, 0.09443425000000000,
    0.08851945000000000, 0.08038322000000000, 0.07562627000000000, 0.02933872000000000,
    0.03608653000000000, 0.05413618000000000, 0.05810160000000000, 0.06105229000000000,
    0.04328244000000000, 0.03946274000000000, 0.04136071000000000, 0.03620027197138900,
]


# ── a kódolás (a hardver-igazolt séma) ─────────────────────────────────
def encode_amplitude(a: float) -> CircuitSpec:
    """1 qubit, RY(A): P(q0=1) = sin²(A/2)"""
    return CircuitSpec(qubits=1, gates=[Gate.with_param("RY", [0], a)])


def encode_frequency(f: float) -> CircuitSpec:
    """2 qubit, RY(2πf) a q1-en + CNOT: P(q0=1) = sin²(πf)"""
    return CircuitSpec(
        qubits=2,
        gates=[
            Gate.with_param("RY", [1], 2.0 * math.pi * f),
            Gate.new("CNOT", [1, 0]),
        ],
    )


def encode_phase(phi: float) -> CircuitSpec:
    """2 qubit, RY(φ) a q1-en + CNOT: P(q0=1) = sin²(φ/2)"""
    return CircuitSpec(
        qubits=2,
        gates=[
            Gate.with_param("RY", [1], phi),
            Gate.new("CNOT", [1, 0]),
        ],
    )


def encode_mode_energies(energies) -> CircuitSpec:
    """A 16 mód: minden qubit a saját energiáját hordozza.

    θ = 2·arcsin(√E) → P(q=1) = E.
    """
    gates = []
    for i, e in enumerate(energies):
        theta = 2.0 * math.asin(math.sqrt(max(0.0, min(1.0, e))))
        gates.append(Gate.with_param("RY", [i], theta))
    return CircuitSpec(qubits=len(energies), gates=gates)


# ── a dekódolás ────────────────────────────────────────────────────────
def _p_q0_one(counts) -> float:
    """P(q0=1) a 2 bites kulcsokból: a q0=1 esetek aránya."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    hits = 0
    for key, n in counts.items():
        if _bits(key, 2)[0] == "1":
            hits += n
    return hits / total


def _p_q0_zero(counts) -> float:
    """P(q0=0) a 2 bites kulcsokból."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    zeros = 0
    for key, n in counts.items():
        if _bits(key, 2)[0] == "0":
            zeros += n
    return zeros / total


def decode_phase(p_q0_one: float) -> float:
    """φ = 2·arcsin(√P(q0=1))"""
    return 2.0 * math.asin(math.sqrt(max(0.0, min(1.0, p_q0_one))))


def decode_frequency(p_q0_one: float) -> float:
    """f = arcsin(√P(q0=1))/π"""
    return math.asin(math.sqrt(max(0.0, min(1.0, p_q0_one)))) / math.pi


def decode_amplitude(p_q0_zero: float) -> float:
    """A = 2·arccos(√P(q0=0))"""
    return 2.0 * math.acos(math.sqrt(max(0.0, min(1.0, p_q0_zero))))


# ── a mérés futtatása ──────────────────────────────────────────────────
def to_qiskit(spec, QuantumCircuit):
    """A `CircuitSpec` → Qiskit áramkör, a Qiskit 2.x paramétersorrendjével.

    🧬 A QISKIT 2.x VÁLTOZÁS: a forgó kapuknál a paraméter megy először
    (`qc.ry(θ, qubit)`), nem a kvantumindex. Az 1.x-es sorrend
    (`qc.ry(qubit, θ)`) a 2.x-ben `CircuitError`-t dob. A kétkvantumos
    kapuknál (`cx(control, target)`) a sorrend változatlan.

    🧬 A BIT-SORREND: a klasszikus regiszter 0. bitje a jobb oldali
    karakter, tehát a `bits[0]` a q0. A `counts` kulcsformátuma kétféle
    lehet: a szimulátor a sima bináris formát adja ("00"), a QPU a
    "0x0" formátumot — a `_bits()` normalizálja mindkettőt.
    """
    TWO_QUBIT = {"CX", "CNOT", "CZ", "SWAP", "ISWAP"}
    qc = QuantumCircuit(spec.qubits, spec.qubits)
    for g in spec.gates:
        if g.gate_type in TWO_QUBIT:
            if len(g.qubits) != 2:
                raise ValueError(
                    f"{g.gate_type} két kvantumot kér, {len(g.qubits)} megadva")
            gate = {"CX": "cx", "CNOT": "cx", "CZ": "cz",
                    "SWAP": "swap"}.get(g.gate_type, g.gate_type.lower())
            getattr(qc, gate)(int(g.qubits[0]), int(g.qubits[1]))
        else:
            gate = {"H": "h", "X": "x", "Y": "y", "Z": "z",
                    "RY": "ry", "RZ": "rz"}.get(g.gate_type, g.gate_type)
            for q in g.qubits:
                if g.params:
                    getattr(qc, gate)(g.params[0], int(q))
                else:
                    getattr(qc, gate)(int(q))
    qc.measure(range(spec.qubits), range(spec.qubits))
    return qc


def _bits(key, n):
    """A counts kulcs → a bitek listája, a q0 elöl (a jobb oldali bit)."""
    k = str(key).replace(" ", "").replace("0x", "").replace("0X", "")
    if not k:
        return ["0"] * n
    k = k.zfill(n)
    return list(reversed(k))


def run_spec(runner, spec: CircuitSpec, shots: int, label: str):
    """Egy áramkör beküldése és a counts visszajátszása.

    A transzpilálást és a sampler primitívet a scs_quantum `tkr_ibm`
    implementációja végzi; a spec → Qiskit konverzió itt, a 2.x
    paramétersorrend szerint.

    🧬 A MÉRÉS IDŐZÍTÉSE (2026-11-01): a visszatérés a QPU-időt és a
    falióra-időt is tartalmazza, a nyers fájl pedig elmenti őket.
    Ennek oka: a 16 módos mérés 3σ-hoz ~481 jobból álló kampánya
    (492 000 lövés / 1024), és hogy a kampány a kvótába fér-e, azt a
    JOBONKÉNTI QPU-IDŐ dönti el. A 2 kvubitos hurkóramkör mért ideje
    (3,00 mp/iter, 4 tömörített áramkörrel) nem extrapolálható egy 16
    kvubitos áramkörre. A mérés a maga dolga: mérjük, ne tippeljünk.
    """
    qc = to_qiskit(spec, runner.QuantumCircuit)
    t0 = time.time()
    if runner.local:
        job = runner.backend.run([qc], shots=shots)
        counts = job.result()[0].data.c.get_counts()
        job_id = "local_statevector"
        backend_name = "statevector (ideális, helyi)"
    else:
        from qiskit_ibm_runtime import SamplerV2
        tq = runner._transpile(qc, runner.backend, optimization_level=1, seed_transpiler=42)
        job = SamplerV2(mode=runner.backend).run([(tq,)], shots=shots)
        job_id = job.job_id()
        backend_name = getattr(runner.backend, "name", "unknown")
        counts = job.result()[0].data.c.get_counts()
    wall = time.time() - t0
    qpu = 0.0
    try:
        qpu = float(job.usage())
    except Exception:
        try:
            qpu = float((job.metrics() or {}).get("run_time", 0.0) or 0.0)
        except Exception:
            qpu = 0.0
    return counts, job_id, backend_name, qpu, wall


def save_raw(label, counts, job_id, backend_name, shots, extra=None,
             qpu_seconds=None, wall_seconds=None):
    """A nyers mérési adat mentése (audit trail) — NEM verziókövetve."""
    raw_dir = Path("measurement_raw")
    raw_dir.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = raw_dir / f"{label}_{shots}s_{job_id}_{ts}.json"
    data = {
        "label": label,
        "job_id": job_id,
        "backend": backend_name,
        "shots": shots,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "counts_raw": {str(k): int(v) for k, v in counts.items()},
    }
    # 🧬 A MÉRÉS IDŐZÍTÉSE (2026-11-01): a nyers fájl hordozza a QPU-időt
    # és a falióra-időt is, hogy a kvóta-kérdés mértből legyen eldönthető.
    if qpu_seconds is not None:
        data["qpu_seconds"] = qpu_seconds
    if wall_seconds is not None:
        data["wall_seconds"] = wall_seconds
    if extra:
        data.update(extra)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    print(f"  nyers adat: {path}")
    return path


# ── a három mérés ──────────────────────────────────────────────────────
def measure_hardware_fidelity(runner, shots: int):
    """A Bell-referencia mérése → a hardver-minőség (c).

    A Bell-állapot (|00⟩+|11⟩)/√2 esetén az egyensúly P(00)+P(11) a
    mért fidelitás. Ez az a paraméter, amit a szimuláció `c`-ként használ.
    """
    spec = tkr_measure.ref_bell(2)
    counts, job_id, backend_name, qpu, wall = run_spec(runner, spec, shots, "bell")
    total = sum(counts.values())
    bal = 0
    for key, n in counts.items():
        b = _bits(key, 2)
        # a Bell-allapot a |00> es |11> felre kerul: mindketto bit egyezik
        if b[0] == b[1]:
            bal += n
    fidelity = bal / total if total else 0.0
    save_raw("bell", counts, job_id, backend_name, shots,
             {"fidelity": fidelity, "counts_normalized": {str(k): int(v) for k, v in counts.items()}},
             qpu, wall)
    return fidelity, counts, job_id, backend_name


def measure_mode_argmax(runner, shots: int, trials: int):
    """A 16 mód argmaxának kvantum-mérése, a klasszikus argmaxhoz képest.

    Minden futás egy 16 qubit-es áramkör 1024 lövéssel; a nyertes a
    a legtöbb q=1 találatot kapott mód. A klasszikus referencia az
    energiamaximum.
    """
    classical_idx = max(range(16), key=lambda i: MODE_ENERGIES[i])
    spec = encode_mode_energies(MODE_ENERGIES)
    correct = 0
    winners = {}
    for t in range(trials):
        counts, job_id, backend_name, qpu, wall = run_spec(runner, spec, shots, "modes")
        # minden qubit q=1 találatainak száma
        hits = [0] * 16
        total = 0
        for key, n in counts.items():
            b = _bits(key, 16)
            total += n
            for i, ch in enumerate(b):
                if ch == "1":
                    hits[i] += n
        best = max(range(16), key=lambda i: hits[i])
        winners[best] = winners.get(best, 0) + 1
        if best == classical_idx:
            correct += 1
        if t == 0:
            save_raw("modes", counts, job_id, backend_name, shots,
                     {"hits": hits, "classical_idx": classical_idx, "quantum_idx": best},
                     qpu, wall)
        print(f"  futás {t+1}/{trials}: nyertes #{best} ({MODE_NAMES[best]}), "
              f"klasszikus #{classical_idx} ({MODE_NAMES[classical_idx]})")
    accuracy = correct / trials if trials else 0.0
    return accuracy, winners, classical_idx


def measure_wavepacket(runner, shots: int):
    """Az (A, f, φ) kódolás → mérés → dekódolás ellenőrzése."""
    a_true, f_true, phi_true = 1.0, 0.25, 1.0
    results = {}
    for name, spec, decoder, true_val in [
        ("A", encode_amplitude(a_true), lambda c: decode_amplitude(_p_q0_zero(c)), a_true),
        ("f", encode_frequency(f_true), lambda c: decode_frequency(_p_q0_one(c)), f_true),
        ("phi", encode_phase(phi_true), lambda c: decode_phase(_p_q0_one(c)), phi_true),
    ]:
        counts, job_id, backend_name, qpu, wall = run_spec(runner, spec, shots, f"wave_{name}")
        got = decoder(counts)
        results[name] = {"true": true_val, "decoded": got, "error": got - true_val}
        save_raw(f"wave_{name}", counts, job_id, backend_name, shots, results[name], qpu, wall)
        print(f"  {name}: beküldött {true_val:.4f} → vissza {got:.4f} "
              f"(hiba {got - true_val:+.4f})")
    return results


# ── a fő ───────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="A valós hardveres mérés")
    ap.add_argument("--local", action="store_true",
                    help="ideális helyi szimulátor (token nélkül) — NEM QPU-bizonyíték")
    ap.add_argument("--backend", default=None, help="a backend neve (pl. ibm_brisbane)")
    ap.add_argument("--shots", type=int, default=1024)
    ap.add_argument("--mode-trials", type=int, default=10,
                    help="a 16 módos argmax-mérés futásainak száma")
    ap.add_argument("--skip-modes", action="store_true")
    args = ap.parse_args()

    print("=" * 72)
    print("QUANTUM ORGANIC INTELLIGENCE — hardveres mérés")
    print("=" * 72)
    if args.local:
        print("!!  IDEÁLIS HELYI SZIMULÁTOR. Ez a KÓD PIPELINE-ellenőrzése,")
        print("!!  nem QPU-validáció. A hardverről semmit nem állít.")
        print()

    runner = tkr_ibm.IbmRunner(backend_name=args.backend, shots=args.shots, local=args.local)
    print(f"backend: {runner.backend_label}")
    print()

    # 1. a bit-sorrend-ellenőrzés — a mérés előfeltétele
    print("[1/3] bit-sorrend-ellenőrzés")
    if not tkr_measure.bit_order_selfcheck():
        print("  SIKERTELEN — a mérés elutasítva, mert az eredménye félrevezető lenne.")
        return 2
    print("  OK")
    print()

    # 2. a hardver-minőség
    print("[2/3] a hardver-minőség (Bell-referencia)")
    fidelity, _, _, _ = measure_hardware_fidelity(runner, args.shots)
    print(f"  egyensúly (P(00)+P(11)) = {fidelity * 100:.2f}%")
    print(f"  → a szimulációban használandó c = {fidelity:.4f}")
    print()

    # 3. a 16 mód argmax + a hullámcsomag
    print("[3/3] a kvantumhíd mérése")
    wave = measure_wavepacket(runner, args.shots)
    print()
    if not args.skip_modes:
        print(f"  a 16 mód argmax — {args.mode_trials} futás, {args.shots} lövés")
        acc, winners, classical = measure_mode_argmax(runner, args.shots, args.mode_trials)
        print(f"  pontosság (a klasszikus #{classical} nyert {acc * 100:.1f}%-ban): {acc * 100:.2f}%")
        print("  a nyertesek megoszlása:")
        for idx, n in sorted(winners.items(), key=lambda kv: -kv[1]):
            print(f"    #{idx:02d} {MODE_NAMES[idx]:<16} {n}x")
        print()
        print("  A DÖNTÉS:")
        if acc < 1.0:
            print("   A kvantum-út a mért hardverrel NEM nyert a klasszikus argmax ellen.")
            print("   Ennek oka a mért energiák 1,85%-os különbsége (0,137σ @1024 lövés).")
        else:
            print("   A kvantum-út megelőzte a klasszikus argmaxot.")

    print()
    print("=" * 72)
    print(f"ÖSSZEFOGLALÓ: fidelity={fidelity:.4f}, "
          f"A-hiba={wave['A']['error']:+.4f}, f-hiba={wave['f']['error']:+.4f}, "
          f"phi-hiba={wave['phi']['error']:+.4f}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
