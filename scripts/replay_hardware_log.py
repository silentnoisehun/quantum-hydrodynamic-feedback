"""Replay a hardveres hurok-futásnak a CPU-n, és derítse ki, melyik
solver adja vissza a naplózott mode_argmax-ot.

A HARDVERES FUTÁSOKAT NEM FUTTATJUK ÚJRA (ebben a munkamenőben nincs
QPU-futtatás). A visszajátszás a NYERS FÁJLOKBAN tárolt counts-okat
használja: a hurok minden lépéséhez a mért counts-okat visszafejtjük,
így a hardver eredménye determinisztikus inputként érkezik. Az egyetlen
változó a SOLVER és az ahhoz tartozó `f`-kezelés.

Ez bizonyítja vagy cáfolja azt az állítást, hogy a 2026-10-27-i
hardveres futások a 2026-10-31-es solver-javítás ELŐTTI kóddal
készültek.

Futtatás:  python scripts/replay_hardware_log.py
Kilépési kód 0 = a replay konzisztens a naplóval.
"""

import glob
import importlib.util
import json
import math
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(REPO, "measurement_raw")
sys.path.insert(0, os.path.join(REPO, "scripts"))

import quantum_loop_sim as current  # noqa: E402

# A két hardveres futás, amelynek a nyers fájljaiban VAN mode_argmax.
RUNS_WITH_ARGMAX = ["20261027T010656Z", "20261027T015558Z"]
# A 68 iterációs futás: az iterációs fájlokban nincs mode_argmax.
RUN_WITHOUT_ARGMAX = "20261027T003737Z"
# 🧬 A 2026-11-02-i 100 iterációs futás: a nyers fájljaiban VAN mode_argmax
# (a hardveres script ma már kiírja), tehát a fenti listába kerül.
RUN_20261102 = "20261102T120704Z"
RUNS_WITH_ARGMAX.append(RUN_20261102)

# 🧬 MELYIK SOLVER VISSZAADJA A NAPLÓT? (futasonkent) — ez a gate maga.
# A 2026-10-27-i futasok a LEGACY solverrel keszultek (a javitas ELOTT), ezert
# a legacy solvernek pontosan vissza kell adnia a naplót, a javitottnak NEM.
# A 2026-11-02-i futas a JAVITOTT solverrel keszult (a javitott
# quantum_loop_hardware.py script), ezert pont az ellenkezo igaz: a javitott
# solver adja vissza pontosan a naplót, a legacy nem.
RUN_SOLVER_THAT_MUST_MATCH = {
    "20261027T010656Z": "legacy",
    "20261027T015558Z": "legacy",
    "20261027T003737Z": "legacy",
    RUN_20261102: "current",
}

# A visszacsatolás módja futásonként. A 68 iterációs futás a C-VEL
# torzítástlanított dekódolást töltötte vissza (docs/MEASUREMENTS-HARDWARE
# 2. szekció); a két 20 iterációs futás a NYERS-t.
# 🧬 A 68 iterációs nyers fájlokban nincs `feedback` mező — ezt a
# dokumentációból kell tudni.
RUN_FEEDBACK = {
    "20261027T003155Z": "raw",
    "20261027T003737Z": "corrected",
    "20261027T010656Z": "raw",
    "20261027T015558Z": "raw",
    RUN_20261102: "raw",
}

# A seed futásonként. 🧬 EZEK NEM FIKCIÓK: a mérésből határozták meg.
# Az első iteráció kódolt (A, f, phi) értékei az init_psi(seed) + extract()
# függvényei, tehát a seed-re egyértelműen megfelelnek. A mérés:
#   20261027T003155Z -> 20261026
#   20261027T003737Z -> 20261026
#   20261027T010656Z -> 20261026
#   20261027T015558Z -> 20261027
# A három "20261026"-os futás a LEGACY solverrel illeszkedik — a javított
# solverrel egyik sem, ami önmagában is bizonyítja, hogy a javítás előtti
# kóddal futottak.
RUN_SEED = {
    "20261027T003155Z": 20261026,
    "20261027T003737Z": 20261026,
    "20261027T010656Z": 20261026,
    "20261027T015558Z": 20261027,
    RUN_20261102: 20261026,
}

# A RUNLOG fájl futásonként — a naplózott mode_argmax második forrása.
RUNLOG_FOR_RUN = {
    "20261027T003737Z": "RUNLOG-LOOP-68IT-20261027.txt",
    "20261027T010656Z": "RUNLOG-LOOP-20IT-RAW-20261027.txt",
    "20261027T015558Z": None,  # a második 20 iterációs futásnak nincs saját RUNLOG-ja
}

# A hardveres hurok paraméterei (a RUNLOG-okból).
GPE_STEPS = 50


def load_legacy():
    path = os.path.join(REPO, "scripts", "legacy",
                        "quantum_loop_sim_a72ead4.py")
    spec = importlib.util.spec_from_file_location("legacy_sim", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_run(prefix):
    """A futás iterációs fájljai, index szerint rendezve."""
    entries = []
    for path in sorted(glob.glob(os.path.join(RAW, f"loop_{prefix}_iter*.json"))):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        index = int(os.path.basename(path).split("_iter")[1][:4])
        entries.append((index, data))
    entries.sort(key=lambda item: item[0])
    return entries


def logged_modes_from_runlog(runlog_name, count):
    """A naplózott mód-sor a RUNLOG fájlból.

    A 68 iterációs futásnak nincs `mode_argmax` a nyers fájlokban, de a
    RUNLOG minden iterációra kiírja a nyertes módot. Ez a forrás.
    """
    path = os.path.join(REPO, "docs", runlog_name)
    modes = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if "mód #" not in line:
                continue
            tail = line.split("mód #", 1)[1]
            number = ""
            for ch in tail:
                if ch.isdigit():
                    number += ch
                else:
                    break
            if number:
                modes.append(int(number))
    if len(modes) != count:
        raise ValueError(
            f"{runlog_name}: {len(modes)} módot találtam, {count} kell")
    return modes


def _p_q0_one(counts):
    """P(q0=1) a counts-ból.

    🧬 A BIT-REND: a q0 a bit-STRING JOBB OLDALI karaktere. A counts
    kulcsai ("00", "01", "10", "11") a qiskit-formátumúak, ahol a
    bal oldali a magasabb sorszámú kvantum. A bridge-cli hexa-vá alakít
    ("01" -> 0x1), és a Rust `p_of_q0_one` a 0x1 + 0x3-at számolja —
    vagyis a bit-string jobb oldali karakterét tekinti q0-nak.

    Ellenőrzés: a 20261027T010656Z első iterációjának frequency counts-ja
    {"00": 562, "11": 420, "10": 31, "01": 11} -> P(q0=1) = 431/1024,
    f = 0.2247149596, ami a rögzített decoded_raw.f értékkel egyezik.
    """
    total = sum(counts.values())
    hits = 0
    for key, n in counts.items():
        bits = format(int(key, 2), "02b")
        if bits[-1] == "1":  # a q0 a jobb oldali bit
            hits += n
    return hits / total if total else 0.0


def _p_q0_zero(counts):
    """P(q0=0) a counts-ból (két kvantum)."""
    total = sum(counts.values())
    hits = 0
    for key, n in counts.items():
        bits = format(int(key, 2), "02b")
        if bits[-1] == "0":
            hits += n
    return hits / total if total else 0.0


def _p_q0_zero_1qubit(counts):
    """P(q0=0) EGY qubit esetén.

    🧬 AZ AMPLITÚDÓ-CSATORNA EGYQUBITES: a kulcs "0" vagy "1", nem
    két bites bináris szám. A két bites formázás minden 1-es kulcsot
    "01"-re bontana, így a q0 mindig 0 lenne -> a dekódolás mindig
    A = π (a maximum) lenne.
    """
    total = sum(counts.values())
    hits = 0
    for key, n in counts.items():
        bits = format(int(key, 2), "01b")
        if bits[-1] == "0":
            hits += n
    return hits / total if total else 0.0


def decode_from_counts(counts, c_parity):
    """A bridge-cli decode-wave viselkedése a nyers counts-okon.

    Visszaadja: (A_nyers, f_nyers, phi_nyers, A_corr, f_corr, phi_corr),
    ahol a `corr` a szimmetrikus c-korrekcióval torzítástlanított érték
    (a `--correct` ág). A `--correct` a mérés szerint RONT, ezért a hurok
    alapból a nyers értéket tölti vissza.
    """
    a_counts = counts["amplitude"]
    f_counts = counts["frequency"]
    p_counts = counts["phase"]

    p_a0 = _p_q0_zero_1qubit(a_counts)
    p_f1 = _p_q0_one(f_counts)
    p_p1 = _p_q0_one(p_counts)

    def unbias(p, c):
        if c <= 0.0:
            return 0.5
        return min(max((p - (1.0 - c) * 0.5) / c, 0.0), 1.0)

    a_raw = 2.0 * math.acos(math.sqrt(min(max(p_a0, 0.0), 1.0)))
    f_raw = math.asin(math.sqrt(min(max(p_f1, 0.0), 1.0))) / math.pi
    ph_raw = 2.0 * math.asin(math.sqrt(min(max(p_p1, 0.0), 1.0)))

    c = c_parity if c_parity else 1.0
    a_cor = 2.0 * math.acos(math.sqrt(unbias(p_a0, c)))
    f_cor = math.asin(math.sqrt(unbias(p_f1, c))) / math.pi
    ph_cor = 2.0 * math.asin(math.sqrt(unbias(p_p1, c)))

    return a_raw, f_raw, ph_raw, a_cor, f_cor, ph_cor


def replay(entries, solver, f_mode, feedback_mode, seed, anchor_every=5):
    """A hurok újrajátszása.

    `f_mode`:
      "legacy" — a 2026-10-27-i kód: a dekódolt f-et `f / 0.5` értékkel
                 adja vissza a folyadékba (a mode-index helyett [0,1])
      "current" — a javított kód: `f / 0.5 * 15`, vagyis a mode-index
                  tartományban adja vissza

    `feedback_mode`: "raw" vagy "corrected" — melyik dekódolás került
    vissza a folyadékba az adott futásban.

    🧬 AZ ÉLŐ `c` VISZI AZ ANCHOROK KÖZÖTT (a visszajátszás kulcsa):
    a hardveres hurokban a `c` csak az anchor-iterációkon frissül
    (`it % anchor_every == 0`), a többi iteráció a LEGUTÓBBI anchor c-jét
    viszi tovább. A nyers fájl `c_live` mezője ezt már tartalmazza, de a
    visszajátszásnak is ugyanígy kell kezelnie.
    """
    psi = solver.init_psi(solver.N, seed)
    modes = []
    for _, data in entries:
        # 🧬 AZ ÉLŐ `c` A FÁJLBAN JÖN: a hardveres hurok a `c`-t csak az
        # anchor-iterációkon frissíti, és a nyers fájl `c_live` mezője
        # MÁR a legutóbbi anchor értékét tartalmazza (a 68 iterációs
        # futásban: 0.9268 öt iteráción át, majd 0.9170, és így tovább).
        a_raw, f_raw, ph_raw, a_cor, f_cor, ph_cor = decode_from_counts(
            data["counts_raw"], data.get("c_live"))

        if feedback_mode == "raw":
            a_fb, f_fb, ph_fb = a_raw, f_raw, ph_raw
        else:
            a_fb, f_fb, ph_fb = a_cor, f_cor, ph_cor

        if f_mode == "legacy":
            f_arg = f_fb / 0.5
        else:
            f_arg = f_fb / 0.5 * solver.F_MODE_INDEX_MAX

        psi = solver.excite(psi, a_fb / math.pi, f_arg, ph_fb / math.pi)
        for _ in range(GPE_STEPS):
            psi = solver.gpe_step(psi, live=True)
        modes.append(int(np.argmax(solver.mode_energies(psi))))
    return modes


def main():
    print("=" * 76)
    print("REPLAY — melyik solver adja vissza a naplózott mode_argmax-ot?")
    print("=" * 76)
    print()

    legacy = load_legacy()
    print("legacy solver : scripts/legacy/quantum_loop_sim_a72ead4.py")
    print("current solver: scripts/quantum_loop_sim.py")
    print()
    outcomes = {}
    for prefix in RUNS_WITH_ARGMAX:
        entries = load_run(prefix)
        if not entries:
            print(f"run {prefix}: nincs iterációs fájl")
            continue
        logged = [d.get("mode_argmax") for _, d in entries]
        # a RUNLOG ugyanazt a sort tartalmazza — a két forrásnak egyeznie
        # kell, különben a replay célpontja nem egyértelmű
        runlog_name = RUNLOG_FOR_RUN.get(prefix)
        if runlog_name:
            from_runlog = logged_modes_from_runlog(runlog_name, len(entries))
            same = from_runlog == logged
            feedback_modes = sorted({d.get("feedback") for _, d in entries})
            print(f"run {prefix}: {len(entries)} iteráció, feedback={feedback_modes}")
            print(f"  a nyers fájlok és a RUNLOG egyezik: {same}")
            if not same:
                print(f"    nyers : {logged}")
                print(f"    runlog: {from_runlog}")
        else:
            print(f"run {prefix}: {len(entries)} iteráció, "
                  f"(nincs külön RUNLOG ehhez a futáshoz)")
        print(f"  naplózott : {logged}")

        for label, solver, f_mode in (
            ("legacy  (a72ead4)", legacy, "legacy"),
            ("current (javított)", current, "current"),
        ):
            modes = replay(entries, solver, f_mode, RUN_FEEDBACK[prefix],
                           RUN_SEED[prefix])
            hits = sum(1 for a, b in zip(modes, logged) if a == b)
            total = len(logged)
            outcomes[(prefix, label)] = (hits, total)
            print(f"  {label:20}: {hits}/{total} egyezés "
                  f"({100.0 * hits / total:.1f}%)")
            if hits != total:
                mismatches = [(i, logged[i], modes[i])
                              for i in range(total) if modes[i] != logged[i]]
                print(f"      eltérések (iter, napló, replay): {mismatches[:10]}")
        print()

    # ── a 68 iterációs futás: a napló a RUNLOG-ból jön ──────────────────
    entries = load_run(RUN_WITHOUT_ARGMAX)
    print(f"run {RUN_WITHOUT_ARGMAX}: {len(entries)} iteráció")
    has_argmax = sum(1 for _, d in entries if d.get("mode_argmax") is not None)
    has_ideal = sum(1 for _, d in entries if d.get("ideal") is not None)
    has_counts = sum(1 for _, d in entries if d.get("counts_raw") is not None)
    print(f"  mode_argmax a nyers fájlokban: {has_argmax}/{len(entries)}")
    print(f"  ideal a nyers fájlokban:        {has_ideal}/{len(entries)}")
    print(f"  counts_raw a nyers fájlokban:   {has_counts}/{len(entries)}")
    print("  -> a naplózott mode_argmax a RUNLOG-ból olvasandó ki:")
    print("     docs/RUNLOG-LOOP-68IT-20261027.txt")
    print()

    logged68 = logged_modes_from_runlog("RUNLOG-LOOP-68IT-20261027.txt",
                                         len(entries))
    print(f"  a RUNLOG-ból {len(logged68)} naplózott mód")
    legacy_modes = None
    for label, solver, f_mode in (
        ("legacy  (a72ead4)", legacy, "legacy"),
        ("current (javított)", current, "current"),
    ):
        modes = replay(entries, solver, f_mode,
                       RUN_FEEDBACK[RUN_WITHOUT_ARGMAX],
                       RUN_SEED[RUN_WITHOUT_ARGMAX])
        if label.startswith("legacy"):
            legacy_modes = modes
        hits = sum(1 for a, b in zip(modes, logged68) if a == b)
        total = len(logged68)
        outcomes[(RUN_WITHOUT_ARGMAX, label)] = (hits, total)
        print(f"  {label:20}: {hits}/{total} egyezés "
              f"({100.0 * hits / total:.1f}%)")
        if hits != total:
            mismatches = [(i, logged68[i], modes[i])
                          for i in range(total) if modes[i] != logged68[i]]
            print(f"      eltérések (iter, napló, replay): {mismatches[:12]}")
    print()

    # 🧬 A HIÁNYZÓ loop_summary: a 68 iterációs futásnak nincs
    # loop_summary fájlja a nyers adatok között. A replay-ból most
    # előállítjuk — ÚJ fájlnévvel, a nyers fájlokat NEM módosítva.
    if legacy_modes is not None:
        summary = {
            "run": RUN_WITHOUT_ARGMAX,
            "generated_by": "scripts/replay_hardware_log.py",
            "generated_note": (
                "A 68 iteracios futasnak nem volt loop_summary fajlja. Ez "
                "a replay a legacy solverrel allitja elo a mode_argmax "
                "sort, a RUNLOG-bol ellenorizve."),
            "solver": "legacy (a72ead4)",
            "feedback": RUN_FEEDBACK[RUN_WITHOUT_ARGMAX],
            "seed": RUN_SEED[RUN_WITHOUT_ARGMAX],
            "iterations": len(entries),
            "mode_argmax": legacy_modes,
            "mode_histogram": [
                legacy_modes.count(i) for i in range(16)
            ],
            "distinct_modes": len(set(legacy_modes)),
        }
        out_path = os.path.join(
            RAW, f"loop_summary_{RUN_WITHOUT_ARGMAX}_replay.json")
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=1, ensure_ascii=False)
        print(f"  a 68 iterációs futás loop_summary-je előállítva:")
        print(f"    {os.path.relpath(out_path, REPO)}")
        print(f"    a mode_argmax sor megegyezik a RUNLOG-gal: "
              f"{legacy_modes == logged68}")
        print(f"    a meglátott módok száma: {summary['distinct_modes']}/16")
        print()

    print("=" * 76)
    print("ÖSSZESÍTÉS")
    print("=" * 76)
    failures = []
    for (prefix, label), (hits, total) in outcomes.items():
        flag = ""
        # 🧬 A CI-FELTÉTEL FUTASONKENT: az a solver, amivel a futas KESZULT,
        # pontosan vissza kell adja a naplót, a masik nem. A 2026-10-27-i
        # futasok a LEGACY solverrel keszultek (a javitas elott), a
        # 2026-11-02-i futas a JAVITOTTAL.
        expected = RUN_SOLVER_THAT_MUST_MATCH.get(prefix)
        is_expected = (
            (label.startswith("legacy") and expected == "legacy")
            or (label.startswith("current") and expected == "current")
        )
        if is_expected:
            if hits == total:
                flag = "  <- TELJES (a varakozo solver)"
            else:
                failures.append(
                    f"{prefix}: a {label} solver csak {hits}/{total}-at adja "
                    f"vissza, pedig a futas ezzel keszult")
                flag = "  <- HIBA"
        else:
            # a masik solvernek NEM szabad visszaadnia a naplót:
            # ez bizonyítja, hogy a futás a másik kóddal készült
            if hits == total:
                failures.append(
                    f"{prefix}: a {label} solver is visszaadja a naplót "
                    f"({hits}/{total}) — ez ellentmond a dokumentált állításnak")
            else:
                flag = f"  <- eltér ({100.0 * hits / total:.0f}%), ahogy várható"
        print(f"  {prefix}  {label:20}: {hits}/{total}{flag}")
    print()
    if failures:
        print("  A REPLAY-FELTÉTEL NEM TELJESÜL:")
        for item in failures:
            print(f"    - {item}")
        return 1
    print("  IGAZOLT: minden futas a hozzá rendelt solverrel készült")
    print("  (a legacy solver a három 2026-10-27-i futást pontosan visszaadja,")
    print("  a javított a 2026-11-02-i futást; a másik solver egyiket sem).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
