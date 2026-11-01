#!/usr/bin/env python3
"""
A KVANTUM-KLASSZIKUS HUROK VALÓDI HARDVEREN — a háromrétegű protokoll.

🧬 A HÁROM RÉTEG (és miért kell mindhárom):

1. MIKRO-KÖTEGELÉS (circuit arraying)
   Az iteráció három kódoló áramköre (A, f, φ) EGY jobban megy, és
   minden `--anchor-every` iterációban a Bell-anchor is ugyanabban a
   jobban van. Így a három paraméter hajszálpontosan ugyanabban a
   kalibrációs ablakban mérődik, és a sor-várakozás is csak egyszer
   történik iterációnként.

2. KOLOKÁCIÓ (Qiskit Runtime Session)
   A session a QPU-t fenntartja a hurok idejére, így az iterációk
   között nem kell újra sorba állni. A mért várakozási idő a
   `--no-session` móddal összehasonlítható.

3. ÉLŐ FIDELITY ANCHOR
   A Bell-anchorból mért `c` (a hardver-minőség) minden anchor
   iterációban frissül, és a dekódolásba az ÉLŐ érték megy. A
   dekódolás a Rust `bridge-cli`-n fut, így a matematika egyetlen
   forrásból jön. A `c` a mért valószínűséget TORZÍTÁSTLANÍTJA
   (`unbias_probability`), nem újra torzítja — a hardver zaja már
   benne van a mérésben.

A KULCS az `IBM_QUANTUM_API_TOKEN` környezetváltozóban.

HASZNÁLAT
---------
    python scripts/quantum_loop_hardware.py --backend ibm_fez --iterations 20
"""
import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

import quantum_loop_sim as fluid  # noqa: E402  (a GPE motor, driver nélkül)


# ── a Rust bridge-cli (a dekódolás egyetlen forrása) ───────────────────
def resolve_bridge_cli(explicit=None):
    """A bridge-cli bináris útja; hiányzik → buildeljük."""
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise SystemExit(f"a bridge-cli nem létezik: {p}")
        return p
    target = Path(os.environ.get("CARGO_TARGET_DIR", REPO / "crates" / "quantum-bridge" / "target"))
    exe = target / "debug" / ("bridge-cli.exe" if os.name == "nt" else "bridge-cli")
    if not exe.exists():
        print("a bridge-cli nincs buildelve — buildeljük...")
        subprocess.run(
            ["cargo", "build", "--manifest-path",
             str(REPO / "crates" / "quantum-bridge" / "Cargo.toml"), "--bin", "bridge-cli"],
            check=True,
        )
    if not exe.exists():
        raise SystemExit(f"a bridge-cli build után sem létezik: {exe}")
    return exe


def call_cli(cli, args):
    """A bridge-cli hívása → a stdout sor."""
    out = subprocess.run([str(cli)] + args, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise RuntimeError(f"bridge-cli hiba: {out.stderr.strip()}")
    return out.stdout.strip()


# ── az áramkörek ──────────────────────────────────────────────────────
def build_circuits(qc, a_kod, f_kod, phi_kod, with_anchor):
    """A három kódoló áramkör + a Bell-anchor.

    A: 1 qubit, RY(A) → P(q0=1) = sin²(A/2)
    f: 2 qubit, RY(2πf) a q1-en + CNOT(1→0) → P(q0=1) = sin²(πf)
    φ: 2 qubit, RY(φ) a q1-en + CNOT(1→0) → P(q0=1) = sin²(φ/2)
    anchor: H(0) + CNOT(0→1) → (|00⟩+|11⟩)/√2
    """
    circs = []

    c = qc.QuantumCircuit(1, 1)
    c.ry(a_kod, 0)
    c.measure([0], [0])
    circs.append(c)

    c = qc.QuantumCircuit(2, 2)
    c.ry(2.0 * math.pi * f_kod, 1)
    c.cx(1, 0)
    c.measure([0, 1], [0, 1])
    circs.append(c)

    c = qc.QuantumCircuit(2, 2)
    c.ry(phi_kod, 1)
    c.cx(1, 0)
    c.measure([0, 1], [0, 1])
    circs.append(c)

    if with_anchor:
        c = qc.QuantumCircuit(2, 2)
        c.h(0)
        c.cx(0, 1)
        c.measure([0, 1], [0, 1])
        circs.append(c)
    return circs


def counts_to_cli(counts, nqubits):
    """A Qiskit counts → a bridge-cli formátum: bináris kulcsok.

    A Qiskit a hex formát adja ("0x3"), amit binárissá alakítunk
    ("11"), hogy a kulcs egyértelmű legyen. A bitek sorrendje a
    Qiskit-konvenció: a jobb oldali bit a q0.
    """
    parts = []
    for key, value in counts.items():
        k = str(key).replace(" ", "")
        if k.lower().startswith("0x"):
            n = int(k, 16)
        else:
            n = int(k, 2)
        bits = format(n, "0%db" % nqubits)
        parts.append(f"{bits}:{int(value)}")
    return ",".join(parts)


# ── a hurok ────────────────────────────────────────────────────────────
def run_hardware_loop(args, cli, qc, service, backend, sampler, raw_dir, tag):
    """A valódi hardveres hurok. Visszaadja az iterációs naplót."""
    psi = fluid.init_psi(fluid.N, args.seed)
    log = []
    c_live = None
    total_qpu = 0.0
    total_wall = 0.0

    for it in range(args.iterations):
        a, f, phi, energies = fluid.extract(psi)
        a_kod = math.pi * a
        # 🧬 A `f` NORMALIZÁLÁS (2026-11-01, T1): az `extract()` az f-et a
        # MOD-INDEX sulyozott átlagaként adja ([0,15]), de a ketkvantumos
        # frekvenciadekodolas CSAK [0,0.5]-on egyertelmu (sin^2 periodikus).
        # A hardveres nyers fajlokban a f_kod 1.24-3.81 volt (111/111
        # iteracioban > 0.5) -> MINDEN iteracioban osszzehajtott. A javitas:
        # a kodolas elott normalizalunk, a visszafejtes visszaszoroz.
        f_kod = fluid.normalize_f(f)
        ph_kod = math.pi * phi

        with_anchor = (it % args.anchor_every == 0) or (it == args.iterations - 1)
        circs = build_circuits(qc, a_kod, f_kod, ph_kod, with_anchor)
        isa = qc.transpile(circs, backend, optimization_level=1, seed_transpiler=42)

        t0 = time.time()
        job = sampler.run([(c,) for c in isa], shots=args.shots)
        # 🧬 A HATÁRIDŐ KELL: ha a kontó kvótája elfogyott, a platform
        # ELFOGADJA a jobot, de az SOOSEM fut le — a `result()` végtelenül
        # blokkolna. A timeout ez helyett hibát dob. A zsúfolt sorban is
        # ez a védelem: a job nem indult el a határidőn belül.
        try:
            result = job.result(timeout=args.job_timeout)
        except Exception as exc:
            if type(exc).__name__ != "RuntimeJobTimeoutError":
                raise
            try:
                job.cancel()
            except Exception:
                pass
            raise SystemExit(
                f"\nA JOB NEM INDULT EL {args.job_timeout:.0f} MPEN BELÜL "
                f"(job {job.job_id()}).\n"
                f"  a backend: {getattr(backend, 'name', '?')} — a sor túl zsúfolt.\n"
                f"  a kvótából nem fogyott semmi (a várakozás nem számít bele).\n"
                "  a szabad backend vagy a sessionos (dedicated) csomag ezt megoldja."
            )
        wall = time.time() - t0

        qpu = 0.0
        try:
            qpu = float(job.usage())
        except Exception:
            try:
                m = job.metrics()
                qpu = float(m.get("run_time", 0.0) or 0.0)
            except Exception:
                qpu = 0.0
        total_qpu += qpu
        total_wall += wall

        counts_list = [r.data.c.get_counts() for r in result]
        job_id = job.job_id()

        # a horgony: a Bell-egyensúly → az ÉLŐ c
        anchor_counts = None
        if with_anchor:
            anchor_counts = counts_list[-1]
            c_live = float(call_cli(cli, ["bell-fidelity", "--counts",
                                          counts_to_cli(anchor_counts, 2)]))
            counts_list = counts_list[:-1]

        # a dekódolás a Rust bridge-cli-jével, az ÉLŐ c-vel
        out = call_cli(cli, [
            "decode-wave",
            "--amplitude-counts", counts_to_cli(counts_list[0], 1),
            "--frequency-counts", counts_to_cli(counts_list[1], 2),
            "--phase-counts", counts_to_cli(counts_list[2], 2),
            "--fidelity", f"{c_live:.10f}",
            "--correct",
        ])
        a_raw, f_raw, ph_raw, a_cor, f_cor, ph_cor = [float(x) for x in out.split()]

        # a hibaméret bázisa: az IDEÁLIS visszafejtett érték (a CLI-ből).
        # 🧬 Az `f` csatorna modul 1 szerint összefügg, ezért a nyers kódolt
        # érték nem jó bázis — az, amit az ideális áramkör visszaad.
        ideal_out = call_cli(cli, [
            "ideal-wave",
            "--amplitude", f"{a_kod:.10f}",
            "--frequency", f"{f_kod:.10f}",
            "--phase", f"{ph_kod:.10f}",
        ])
        a_ideal, f_ideal, ph_ideal = [float(x) for x in ideal_out.split()]

        # visszatöltés a folyadékba — a választott visszacsatolás szerint
        if args.feedback == "raw":
            a_fb, f_fb, ph_fb = a_raw, f_raw, ph_raw
        else:
            a_fb, f_fb, ph_fb = a_cor, f_cor, ph_cor
        psi = fluid.excite(psi, a_fb / math.pi,
                           f_fb / fluid.F_DECODE_MAX * fluid.F_MODE_INDEX_MAX,
                           ph_fb / math.pi)
        for _ in range(args.gpe_steps):
            psi = fluid.gpe_step(psi, live=True)

        mode = int(fluid.np.argmax(fluid.mode_energies(psi)))
        entry = {
            "iteration": it,
            "job_id": job_id,
            "anchor": with_anchor,
            "feedback": args.feedback,
            "c_live": c_live,
            "qpu_seconds": qpu,
            "wall_seconds": wall,
            "encoded": {"A": a_kod, "f": f_kod, "phi": ph_kod},
            "ideal": {"A": a_ideal, "f": f_ideal, "phi": ph_ideal},
            "decoded_raw": {"A": a_raw, "f": f_raw, "phi": ph_raw},
            "decoded_corrected": {"A": a_cor, "f": f_cor, "phi": ph_cor},
            "error_raw": {"A": a_raw - a_ideal, "f": f_raw - f_ideal, "phi": ph_raw - ph_ideal},
            "error_corrected": {"A": a_cor - a_ideal, "f": f_cor - f_ideal,
                                "phi": ph_cor - ph_ideal},
            "mode_argmax": mode,
            "mode_name": fluid.MODE_NAMES[mode] if hasattr(fluid, "MODE_NAMES") else str(mode),
            "coherence": fluid.coherence(psi),
            "counts": {
                "amplitude": {str(k): int(v) for k, v in counts_list[0].items()},
                "frequency": {str(k): int(v) for k, v in counts_list[1].items()},
                "phase": {str(k): int(v) for k, v in counts_list[2].items()},
            },
        }
        if anchor_counts is not None:
            entry["counts"]["anchor"] = {str(k): int(v) for k, v in anchor_counts.items()}
        if args.save_state:
            # 🧬 A FOLYADÉKÁLLAPOT: a nyers fájl így önmagában elegendő ahhoz,
            # hogy a mód-energiákat és a koherenciát újraszámítsuk — a
            # mérési eredmény teljesen visszakövethető a nyers adattal.
            entry["psi_real"] = [[round(float(v), 6) for v in row] for row in psi.real]
            entry["psi_imag"] = [[round(float(v), 6) for v in row] for row in psi.imag]
        log.append(entry)

        raw_path = raw_dir / f"loop_{tag}_iter{it:04d}_{job_id}.json"
        with open(raw_path, "w", encoding="utf-8") as fh:
            json.dump({
                "iteration": it,
                "job_id": job_id,
                "backend": getattr(backend, "name", "unknown"),
                "shots": args.shots,
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "qpu_seconds": qpu,
                "wall_seconds": wall,
                "c_live": c_live,
                "counts_raw": entry["counts"],
                "encoded": entry["encoded"],
                "ideal": entry["ideal"],
                "decoded_raw": entry["decoded_raw"],
                "decoded_corrected": entry["decoded_corrected"],
                "mode_argmax": entry["mode_argmax"],
                "coherence": entry["coherence"],
                "feedback": args.feedback,
            }, fh, indent=1)

        print(f"  iter {it+1}/{args.iterations} | anchor={with_anchor} c={c_live:.4f} | "
              f"qpu={qpu:.2f}s várakozás={wall:.1f}s | "
              f"dA={a_cor - a_ideal:+.4f} df={f_cor - f_ideal:+.4f} dphi={ph_cor - ph_ideal:+.4f} | "
              f"mód #{mode}")

    return log, total_qpu, total_wall


def run_classical_branch(args):
    """A klasszikus kontroll: azonos GPE, kvantumzaj nélkül."""
    psi = fluid.init_psi(fluid.N, args.seed + 1)
    seq = []
    for _ in range(args.iterations):
        a, f, phi, _ = fluid.extract(psi)
        psi = fluid.excite(psi, a, f, phi)
        for _ in range(args.gpe_steps):
            psi = fluid.gpe_step(psi, live=True)
        seq.append(int(fluid.np.argmax(fluid.mode_energies(psi))))
    return seq


# ── a fő ───────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="A kvantum-klasszikus hurok valódi hardveren")
    ap.add_argument("--backend", default="ibm_fez")
    ap.add_argument("--iterations", type=int, default=20)
    ap.add_argument("--shots", type=int, default=1024)
    ap.add_argument("--anchor-every", type=int, default=5)
    ap.add_argument("--gpe-steps", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20261026)
    ap.add_argument("--no-session", action="store_true", help="session nélkül (a várakozás mérésére)")
    ap.add_argument("--bridge-bin", default=None)
    ap.add_argument("--classical-control", action="store_true")
    ap.add_argument("--feedback", choices=["corrected", "raw"], default="corrected",
                    help="melyik dekódolás kerül vissza a folyadékba: a nyers vagy "
                         "az élő c-vel torzítástlanított érték")
    ap.add_argument("--no-save-state", dest="save_state", action="store_false",
                    help="ne mentsük a folyadékállapotot a nyers fájlba")
    ap.add_argument("--token-file", default=None,
                    help="JSON fájl az IBM kulccsal ({\"apikey\": ...}) — "
                         "a kulcs nem kerül a parancssorba")
    ap.add_argument("--job-timeout", type=float, default=900.0,
                    help="a job eredményének várakozási határa mp-ben")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    token = os.environ.get("IBM_QUANTUM_API_TOKEN") or os.environ.get("QISKIT_IBM_TOKEN")
    if args.token_file:
        # 🧬 A KULCS FÁJLBÓL: a három IBM kulcs három KÜLÖN instance
        # (külön kvótával), ezért párhuzamosan futtathatók. A kulcs soha
        # nem kerül a parancssorba.
        with open(args.token_file, encoding="utf-8") as fh:
            token = json.load(fh)["apikey"]
    if not token:
        raise SystemExit("az IBM_QUANTUM_API_TOKEN környezetváltozó nincs beállítva")

    import qiskit
    from qiskit import QuantumCircuit, transpile
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2, Session

    cli = resolve_bridge_cli(args.bridge_bin)
    print(f"bridge-cli: {cli}")

    service = QiskitRuntimeService(channel="ibm_quantum_platform", token=token)
    backend = service.backend(args.backend)
    print(f"backend: {backend.name} ({backend.num_qubits} qubit)")

    out_dir = Path(args.out_dir) if args.out_dir else REPO / "measurement_raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir
    tag = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

    print()
    print("=" * 78)
    print(f"A KVANTUM-KLASSZIKUS HUROK VALÓDI HARDVEREN — {args.backend}")
    print(f"  iteráció={args.iterations} lövés={args.shots} anchor-minden={args.anchor_every} "
          f"GPE-lépés={args.gpe_steps} session={not args.no_session}")
    print("=" * 78)

    usage_before = service.usage()
    # 🧬 A KVÓTA-ELLENŐRZÉS BEKÜLDÉS ELŐTT: ha elfogyott a keret, a
    # platform fogadja a jobot, de az sosem fut le. Ezt meg kell állítani
    # itt, nem egy beragadt `result()`-ban.
    if usage_before.get("usage_limit_reached"):
        raise SystemExit(
            "A KONTÓ KVÓTÁJA ELFYOGOTT — a jobok soha nem futnának le.\n"
            f"  instance : {usage_before.get('instance_id')}\n"
            f"  fogyott  : {usage_before.get('usage_consumed_seconds')} mp "
            f"(limit {usage_before.get('usage_limit_seconds')} mp)\n"
            "  másik kulcsot vagy másik plan instance-t kell használni."
        )
    print(f"kvóta előtte: {usage_before.get('usage_remaining_seconds')} mp "
          f"(limit {usage_before.get('usage_limit_seconds')} mp)")

    session_ctx = None
    session_error = None
    session_active = False
    if not args.no_session:
        try:
            session_ctx = Session(backend=backend)
            session_ctx.__enter__()
            session_active = True
            print("session megnyitva — a QPU fenntartva a hurok idejére")
        except Exception as exc:  # noqa: BLE001 — a csomag szabálya dönt
            # 🧬 AZ OPEN CSOMAG NEM ENGED SESSIONT ("not authorized to run a
            # session when using the open plan"). Ilyenkor job-módban futunk:
            # minden iteráció külön sorba áll. A várakozást MÉRJÜK, ne
            # tippeljük.
            print(f"! a session nem elérhető ezen a csomagon: {type(exc).__name__}")
            print("  → job mód: minden iteráció külön sorba áll. A várakozást mérjük.")
            session_error = f"{type(exc).__name__}: {exc}"
            session_ctx = None
    try:
        sampler = SamplerV2(mode=session_ctx if session_ctx is not None else backend)
        log, total_qpu, total_wall = run_hardware_loop(
            args, cli, qiskit, service, backend, sampler, raw_dir, tag)
    finally:
        if session_ctx is not None:
            session_ctx.__exit__(None, None, None)

    usage_after = service.usage()
    print()
    print("=" * 78)
    print("AZ ITERÁCIÓK ÖSSZESÍTÉSE")
    print("=" * 78)
    print(f"  QPU-idő összesen : {total_qpu:.3f} mp")
    print(f"  falióra-idő      : {total_wall:.1f} mp (átlag {total_wall / max(1, args.iterations):.1f} mp/iter)")
    print(f"  kvóta maradt     : {usage_after.get('usage_remaining_seconds')} mp")
    print(f"  kvóta fogyás     : {usage_before.get('usage_remaining_seconds', 0) - usage_after.get('usage_remaining_seconds', 0):.1f} mp")

    print()
    print("  A DEKÓDOLÁS PONTOSSÁGA (a hibaméret bázisa az ideális visszafejtés):")
    for key, label in (("A", "A"), ("f", "f"), ("phi", "φ")):
        raw = [abs(e["error_raw"][key]) for e in log]
        cor = [abs(e["error_corrected"][key]) for e in log]
        print(f"    {label}: nyers       átlag {sum(raw) / len(raw):.5f}  max {max(raw):.5f}")
        print(f"    {label}: torzítástlan átlag {sum(cor) / len(cor):.5f}  max {max(cor):.5f}")
    cs = [e["c_live"] for e in log if e["c_live"] is not None]
    if cs:
        print(f"  az élő c: min {min(cs):.4f} max {max(cs):.4f} (a mért Bell-egyensúly)")

    modes = [e["mode_argmax"] for e in log]
    print(f"  a mód-argmax sor: {modes}")

    if args.classical_control:
        seq = run_classical_branch(args)
        print(f"  a klasszikus kontroll argmax sora: {seq}")

    summary = {
        "backend": backend.name,
        "iterations": args.iterations,
        "shots": args.shots,
        "anchor_every": args.anchor_every,
        "gpe_steps": args.gpe_steps,
        "feedback": args.feedback,
        # A KÉRT mód és a TÉNYLEGESEN használt mód különbsége: az open
        # csomag nem enged sessiont, ezért a kérés job-módra esik vissza.
        # A "session" mező a régi (téves) jelentését tartalmazta: ez a
        # felhasználó szándéka volt, nem a tényleges futásmód.
        "session_requested": not args.no_session,
        "session_active": session_active,
        "session_error": session_error,
        "execution_mode": "session" if session_active else "job",
        "total_qpu_seconds": total_qpu,
        "total_wall_seconds": total_wall,
        "usage_before": usage_before,
        "usage_after": usage_after,
        "log": log,
    }
    summary_path = out_dir / f"loop_summary_{tag}.json"
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    print()
    print(f"  az összefoglaló: {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
