"""A kvantum-visszacsatolas KONTROLL-OSSZEHASONLITASA.

A KERDES: felel-e a kvantum csatorna a modvaltasert?

A VALASZ ADATOKBOL, NEM ALLITASBOL. Minden ag ugyanazt a hurkot futtatja
(ugyanazzal a solverrel, ugyanazzal a kezdeti allapottal), es csak a
visszacsatolas kulonbozik:

  classical            nincs csatorna, nincs zaj — a KONTROLL
  exact                a teljes kvantum csatorna, de ZAJ NELKULI meressel
  noise_10shot_*       10 loves, a MATE-protokoll
  noise_1024shot_*     1024 loves, ahogy a hardver futott
  hardware_residual    a hardveres nyers fajlok RÖGZÍTETT visszacsatolasai
  hardware_permuted    ugyanazok a visszacsatolasok, >=200 permutalva

A DÖNTÉST EGY KÉRDÉS DÖNT EL: a klasszikus kontroll (egyetlen determinisztikus
pont) a zajos agak 5-95%-os SAVJAN BELUL VAN-E?

  - ha igen: a mod-mintazat nem a kvantum csatornatol kulonbozik, hanem a
    meresi zajtol; a kvantum-visszacsatolas nem felelös a modvaltasert
  - ha nem: a kontroll kivallik a zajsavbol, es a zajos csatorna tenyleges
    hatasa van a mod-mintazatra

A HARDVERES FUTASOK HOL VANNAK a savban? A hardver a LEGACY solverrel futott
(2026-10-27, a javitas elott) — ezert a hardver a legacy solver savjaba
kerul, hogy a comparison apples-to-apples legyen. A javított solver savja
is ki van szamitva: az azt mutatja, mi lett volna a javitott koduval.

Futtatás:  python scripts/control_comparison.py
Kimenet:   measurement_cpu/control_comparison.json
           docs/MEASUREMENTS-CPU-CONTROLS.txt
Kilépési kód 0 = a belső összefüggések rendben.
"""

import argparse
import json
import math
import os
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(REPO, "measurement_raw")
sys.path.insert(0, os.path.join(REPO, "scripts"))

import quantum_loop_sim as q          # noqa: E402
import replay_hardware_log as R       # noqa: E402

# ── a hardveres futások ────────────────────────────────────────────────
# A visszacsatolas modja futasonkent a scripts/replay_hardware_log.py-bol
# (a 68 iteracios futas a c-vel torzitastlanitott dekódolast toltotte
# vissza, a ket 20 iteracios a nyerset).
HARDWARE_RUNS = [
    {"prefix": "20261027T010656Z", "length": 20, "feedback": "raw"},
    {"prefix": "20261027T015558Z", "length": 20, "feedback": "raw"},
    {"prefix": "20261027T003737Z", "length": 68, "feedback": "corrected"},
]

# A hardveres futasok hossza — a CPU-futások is EZEKKEL a hosszakkal futnak,
# hogy a statisztikak osszehasonlithatoak legyenek.
LENGTHS = [20, 68]

# A két kör. "fixed_init": a kezdeti állapot fix, a zaj seedje váltakozik
# (ez a fő sáv). "varying_init": a kezdeti állapot is váltakozik — ez
# ellenőrzi, hogy az eredmény nem egy kezdeti állapot mellékterméke.
ROUNDS = ["fixed_init", "varying_init"]

# 🧬 A c MERT ERTEKE, nem feltetelezett: a 111 rogzitett `c_live` ertek
# medianja a nyers fajlokbol. A szimulacio sajat C_BELL=0.949 erteke a
# median felett van, de a mert tartomanyon belul van.
C_MEASURED_MEDIAN = 0.934570

# A zajos agak.
NOISE_ARMS = [
    {"id": "noise_10shot_symmetric", "shots": 10,
     "model": q.NOISE_SYMMETRIC},
    {"id": "noise_1024shot_symmetric", "shots": 1024,
     "model": q.NOISE_SYMMETRIC},
    {"id": "noise_10shot_floor", "shots": 10, "model": q.NOISE_FLOOR},
    {"id": "noise_1024shot_floor", "shots": 1024, "model": q.NOISE_FLOOR},
]

# A CLASSICAL es az EXACT ag determinisztikus (nincs zajuk), ezert minden
# kezdeti allapotban egy-egy futasuk van.
DET_ARMS = [{"id": "classical", "kind": "classical"},
            {"id": "exact", "kind": "exact"}]

# A visszacsatolasra kerulo parameterek tartomanyai.
# A reziduum (hardware_residual) negativ is lehet, ezert szelesabb tartomany.
A_RANGE = (-1.0, 1.0)         # a visszacsatolt A / reziduum A
F_RANGE = (-15.0, 15.0)       # a visszacsatolt f / reziduum f (mod-index)
PHI_RANGE = (-1.0, 1.0)       # a visszacsatolt phi / reziduum phi


def clip(value, bounds):
    return min(max(value, bounds[0]), bounds[1])


# ── a solver betoltes ──────────────────────────────────────────────────
_LEGACY = None


def legacy_solver():
    global _LEGACY
    if _LEGACY is None:
        _LEGACY = R.load_legacy()
    return _LEGACY


def solver_by_name(name):
    return q if name == "current" else legacy_solver()


# ── a hardveres visszacsatolasok ───────────────────────────────────────
_FEEDBACK_CACHE = {}


def recorded_feedback(prefix, feedback_mode, solver_name):
    """A hardveres futas ROGZITETT visszacsatolasai a folyadek szamara
    (mostantol: hardware_recorded_replay).

    A nyers `counts_raw`-okat visszafejtjuk (a replay ugyanigy csinalja),
    majd a hardver skalajara helyezzuk:
      A   -> a_fb / pi            [0, 1]
      f   -> f_fb / 0.5 * scale   [0, 15]
      phi -> ph_fb / pi           [0, 1]

    A `scale` a solver f-visszacsatolasanak skaalaja: a legacy solverben
    `f_fb / 0.5` (a mode-index helyett [0,1] — ez volt a hiba), a javitottban
    `f_fb / 0.5 * 15` (a tenyleges mode-index).

    🧬 A `_rescaled` utagas: a JAVITOTT f-skalat hasznalja, fuggetlenul a
    solvertol. Ez a dontoeso arm: ugyanaz a ROGZITETT hardveres visszacsatolas,
    csak a helyes skalan — igy megvalaszolhato, hogy a hardveres mod-mintazat
    a f-skala hibaja miatt volt-e kivagyes, vagy a kvantum csatorna hatasa.
    """
    key = (prefix, feedback_mode, solver_name)
    if key in _FEEDBACK_CACHE:
        return _FEEDBACK_CACHE[key]
    rescaled = feedback_mode.endswith("_rescaled")
    base_mode = (feedback_mode[:-len("_rescaled")] if rescaled
                 else feedback_mode)
    if rescaled:
        scale = q.F_MODE_INDEX_MAX
    else:
        scale = 1.0 if solver_name == "legacy" else q.F_MODE_INDEX_MAX
    out = []
    for _, data in R.load_run(prefix):
        a_raw, f_raw, ph_raw, a_cor, f_cor, ph_cor = R.decode_from_counts(
            data["counts_raw"], data.get("c_live"))
        if base_mode == "raw":
            a_fb, f_fb, ph_fb = a_raw, f_raw, ph_raw
        else:
            a_fb, f_fb, ph_fb = a_cor, f_cor, ph_cor
        out.append((
            clip(a_fb / math.pi, A_RANGE),
            clip(f_fb / q.F_DECODE_MAX * scale, F_RANGE),
            clip(ph_fb / math.pi, PHI_RANGE),
        ))
    _FEEDBACK_CACHE[key] = out
    return out


_TRUE_RESIDUAL_CACHE = {}


def true_residual_feedback(prefix, solver_name):
    """A VALODI reziduum: iteracionkent `decoded_raw - ideal` a javitott
    f-skalan, a javitott solverrel.

    Az `ideal` ertekek a nyers fajlok `ideal` mezojeibol jonnek (ez az, amit
    a QPU-nak elkuldunk: A es phi egyforman, f pedig `encoded.f % 0.5`).
    A 68 iteracios futasban nincs `ideal` mezo, ott az `encoded`-bol
    szarmazik: ideal.A = encoded.A, ideal.f = encoded.f % 0.5,
    ideal.phi = encoded.phi.
    A `decoded_raw` a mertes ertek a QPU-tol.

    A reziduum a javitott f-skalan (mode-index tartomany [0,15]):
      A_residual    = (decoded_raw.A - ideal.A) / pi           -> [0, 1]
      f_residual    = (decoded_raw.f - ideal.f) * 30           -> [0, 15]
                    (mivel f [0, 0.5]-on van, denormalizalas * 15/0.5 = 30)
      phi_residual  = (decoded_raw.phi - ideal.phi) / pi       -> [0, 1]

    Ez az ARM valaszolja meg: ha a QPU-zaj helyes kodolassal/skalaval
    szamit-e. A korabbi `hardware_residual` (most
    `hardware_recorded_replay`) csak a rogzitett dekodolt ertekeket
    jatszotta vissza, ami nem ugyanaz.
    """
    key = (prefix, solver_name)
    if key in _TRUE_RESIDUAL_CACHE:
        return _TRUE_RESIDUAL_CACHE[key]
    out = []
    for _, data in R.load_run(prefix):
        # az ideal ertekek: ha van `ideal` mezo, azt hasznaljuk,
        # kulonben az `encoded`-bol szarmazik
        if "ideal" in data:
            ideal = data["ideal"]
        else:
            enc = data["encoded"]
            ideal = {
                "A": enc["A"],
                "f": enc["f"] % 0.5,  # a 2-qubit dekodolas csak [0, 0.5]-on egyertelmu
                "phi": enc["phi"],
            }
        decoded_raw = data["decoded_raw"]

        a_residual = (decoded_raw["A"] - ideal["A"]) / math.pi
        f_residual = (decoded_raw["f"] - ideal["f"]) * 30.0  # 15/0.5 = 30
        ph_residual = (decoded_raw["phi"] - ideal["phi"]) / math.pi

        out.append((
            clip(a_residual, A_RANGE),
            clip(f_residual, F_RANGE),
            clip(ph_residual, PHI_RANGE),
        ))
    _TRUE_RESIDUAL_CACHE[key] = out
    return out


# ── egy futas ──────────────────────────────────────────────────────────
def run_task(task):
    """Egy hurok-futas. A feladat egy tuple, hogy a ProcessPoolExecutor
    pickelhessen (a Windows-on a spawn miatt a modul szintjen kell lennie)."""
    (kind, arm_id, shots, model, iters, init_seed, noise_seed,
     solver_name, prefix, feedback_mode, permute, round_name) = task

    solver = solver_by_name(solver_name)

    if kind == "classical":
        seq = q.run_loop_channel(lambda A, f, phi: (A, f, phi),
                                  iters=iters, seed=init_seed, solver=solver)
    elif kind == "exact":
        seq = q.run_loop_channel(q.quantum_shot_exact, iters=iters,
                                  seed=init_seed, solver=solver)
    elif kind == "noise":
        rng = np.random.default_rng(noise_seed)

        def channel(A, f, phi, rng=rng, shots=shots, model=model):
            return q.quantum_shot(A, f, phi, rng=rng, shots=shots,
                                  c=C_MEASURED_MEDIAN, model=model)

        seq = q.run_loop_channel(channel, iters=iters, seed=init_seed,
                                  solver=solver)
    elif kind == "hardware":
        if feedback_mode == "true_residual":
            feedback = list(true_residual_feedback(prefix, solver_name))
        else:
            feedback = list(recorded_feedback(prefix, feedback_mode, solver_name))
        if permute:
            order = np.random.default_rng(noise_seed).permutation(len(feedback))
            feedback = [feedback[i] for i in order]
        seq = q.run_loop_channel(None, iters=iters, seed=init_seed,
                                  solver=solver, feedback_list=feedback)
    else:
        raise ValueError(f"ismeretlen ag: {kind}")

    return (kind, arm_id, iters, init_seed, noise_seed, solver_name,
            prefix or "", round_name, q.metrics(seq), seq)


# ── a feladat-lista ────────────────────────────────────────────────────
def build_tasks(seeds, init_seeds, solvers, init_noise_seeds):
    """Minden futas determinisztikus: a seed-ek explicit, a sorrend nem
    szamit, mert az eredmenyeket rendezes utan irjuk ki.

    KET KOR:
      "fixed_init"    a kezdeti allapot FIX (a hardver seedje), a zaj seedje
                      varyal — ez a fo sav, >=200 futas per zajos ag
      "varying_init"  a kezdeti allapot IS varyal (>=30 db) — ez azt
                      ellenorzi, hogy az eredmeny nem egy kezdeti allapot
                      mellekvedoje
    """
    tasks = []
    for solver_name in solvers:
        for iters in LENGTHS:
            # ── 1. kör: a kezdeti allapot FIX, a zaj seedje varyal ──
            for arm in DET_ARMS:
                tasks.append((arm["kind"], arm["id"], 0, None, iters,
                              q.SEED, 0, solver_name, None, None, False,
                              "fixed_init"))
            for arm in NOISE_ARMS:
                for s in range(seeds):
                    tasks.append(("noise", arm["id"], arm["shots"], arm["model"],
                                  iters, q.SEED, s, solver_name, None, None,
                                  False, "fixed_init"))
            for hw in HARDWARE_RUNS:
                if hw["length"] != iters:
                    continue
                # A regi hardware_residual -> most hardware_recorded_replay
                tasks.append(("hardware", f"hardware_recorded_replay_{hw['prefix']}",
                              0, None, iters, q.SEED, 0, solver_name,
                              hw["prefix"], hw["feedback"], False, "fixed_init"))
                # Az UJ hardware_residual: valodi reziduum a javitott solverrel
                if solver_name == "current":
                    tasks.append(("hardware", f"hardware_residual_{hw['prefix']}",
                                  0, None, iters, q.SEED, 0, solver_name,
                                  hw["prefix"], "true_residual", False, "fixed_init"))
                tasks.append(("hardware", f"hardware_rescaled_{hw['prefix']}",
                              0, None, iters, q.SEED, 0, solver_name,
                              hw["prefix"], hw["feedback"] + "_rescaled", False,
                              "fixed_init"))
                for s in range(seeds):
                    tasks.append(("hardware", f"hardware_permuted_{hw['prefix']}",
                                  0, None, iters, q.SEED, s, solver_name,
                                  hw["prefix"], hw["feedback"], True, "fixed_init"))
            # ── 2. kör: a kezdeti allapot is varyal ──
            for j in range(init_seeds):
                init_seed = q.SEED + 1000 + j
                for arm in DET_ARMS:
                    tasks.append((arm["kind"], arm["id"], 0, None, iters,
                                  init_seed, init_seed, solver_name, None,
                                  None, False, "varying_init"))
                for arm in NOISE_ARMS:
                    for s in range(init_noise_seeds):
                        tasks.append(("noise", arm["id"], arm["shots"],
                                      arm["model"], iters, init_seed,
                                      init_seed * 1000 + s, solver_name,
                                      None, None, False, "varying_init"))
                for hw in HARDWARE_RUNS:
                    if hw["length"] != iters:
                        continue
                    tasks.append(("hardware",
                                  f"hardware_recorded_replay_{hw['prefix']}", 0, None,
                                  iters, init_seed, init_seed, solver_name,
                                  hw["prefix"], hw["feedback"], False,
                                  "varying_init"))
                    if solver_name == "current":
                        tasks.append(("hardware",
                                      f"hardware_residual_{hw['prefix']}", 0, None,
                                      iters, init_seed, init_seed, solver_name,
                                      hw["prefix"], "true_residual", False,
                                      "varying_init"))
                    tasks.append(("hardware",
                                  f"hardware_rescaled_{hw['prefix']}", 0, None,
                                  iters, init_seed, init_seed, solver_name,
                                  hw["prefix"], hw["feedback"] + "_rescaled",
                                  False, "varying_init"))
                    for s in range(init_noise_seeds):
                        tasks.append(("hardware",
                                      f"hardware_permuted_{hw['prefix']}",
                                      0, None, iters, init_seed,
                                      init_seed * 1000 + s, solver_name,
                                      hw["prefix"], hw["feedback"], True,
                                      "varying_init"))
    return tasks


# ── a statisztika ──────────────────────────────────────────────────────
METRIC_KEYS = ("distinct_modes", "brain_ratio", "H_Hmax", "transient_H")


def band(values):
    """A median es az 5-95%-os sav."""
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return None
    return {
        "n": n,
        "median": float(statistics.median(ordered)),
        "p5": float(ordered[int(0.05 * (n - 1))]),
        "p95": float(ordered[int(0.95 * (n - 1))]),
        "min": float(ordered[0]),
        "max": float(ordered[-1]),
        "mean": float(statistics.fmean(ordered)),
    }


def percentile_of(value, distribution):
    """A hardveres futas merőszamanak helye a CPU-ag sávjában (százalék).

    100 * (a legfeljebb ennyi futas, amelynek a mérőszáma <= a hardveré)
    / osszes futas
    """
    if not distribution:
        return None
    below = sum(1 for v in distribution if v <= value)
    return 100.0 * below / len(distribution)


def tv_distance(hist_a, hist_b):
    """A ket hisztogram teljes variacios távolsaga."""
    a = np.asarray(hist_a, dtype=float)
    b = np.asarray(hist_b, dtype=float)
    total = a.sum()
    if total == 0:
        return 0.0
    return float(0.5 * np.abs(a / total - b / total).sum())


# ── a hardveres futasok mod-sorozatai ──────────────────────────────────
def hardware_mode_sequences():
    """A hardveres futasok mod-sorozata a LEGACY solverrel (az, ami
    ténylegesen futott) es a JAVITOTT solverrel (amit a replay ad)."""
    out = {}
    for hw in HARDWARE_RUNS:
        entries = R.load_run(hw["prefix"])
        for solver_name, f_mode in (("legacy", "legacy"), ("current", "current")):
            modes = R.replay(entries, solver_by_name(solver_name), f_mode,
                             hw["feedback"], R.RUN_SEED[hw["prefix"]])
            out[(hw["prefix"], solver_name)] = modes
    return out


# ── a jelentés ─────────────────────────────────────────────────────────
def fmt_band(b, digits=4):
    if b is None:
        return "nincs adat"
    if b["median"] == int(b["median"]) and b["p5"] == int(b["p5"]):
        return ("%d  [%d, %d]" % (b["median"], b["p5"], b["p95"]))
    return ("%.4f  [%.4f, %.4f]" % (b["median"], b["p5"], b["p95"]))


def write_report(path, payload, params):
    hw_seq = payload["hardware"]
    lines = []
    add = lines.append

    add("=" * 78)
    add("A KVANTUM-VISSZACSATOLAS KONTROLL-OSSZEHASONLITASA (CPU)")
    add("=" * 78)
    add("")
    add("GENERALVA: scripts/control_comparison.py")
    add("A CEL: a modvaltas felelose-e a kvantum csatornanak, vagy a meresi")
    add("zajnak? A valasz a kontroll savjan belul van-e, nem az allitasbol jon.")
    add("")
    add("PARAMETEREK")
    add("  solver            : a javitott (scripts/quantum_loop_sim.py) es a")
    add("                      legacy (a72ead4, a hardver ezzel futott)")
    add("  hurok-hossz       : %s iteracio (a hardveres futasok hossza)" %
        ", ".join(str(x) for x in LENGTHS))
    add("  zaj seed/db       : %d (1. kor), kezdeti allapot: %d db x %d zaj "
        "seed (2. kor)" % (params["seeds"], params["init_seeds"],
                           params["init_noise_seeds"]))
    add("  c (zaj agak)      : %.6f  -- a 111 rogzitett c_live ertek medianja" %
        C_MEASURED_MEDIAN)
    add("  kulcs              : %s" % params["key"])
    add("")
    add("AGAK")
    add("  classical                nincs csatorna, nincs zaj (a KONTROLL)")
    add("  exact                    a teljes kvantum csatorna, ZAJ NELKULI meressel")
    add("  noise_10shot_*           10 loves, a MATE-protokoll")
    add("  noise_1024shot_*         1024 loves, ahogy a hardver futott")
    add("  hardware_recorded_replay a hardveres nyers fajlok ROGZITETT visszacsatolasai")
    add("  hardware_residual        a VALODI reziduum: decoded_raw - ideal a javitott f-skalan")
    add("  hardware_rescaled        ugyanaz a rogzitett visszacsatolas, de a JAVITOTT f-skalan (a dontest arm)")
    add("  hardware_permuted        ugyanazok a visszacsatolasok, %d permutalva" %
        params["seeds"])
    add("")

    for solver_name in payload["parameters"]["solvers"]:
        title = ("A JAVITOTT SOLVERREL" if solver_name == "current"
                 else "A LEGACY SOLVERREL (a hardver ezzel futott)")
        add("=" * 78)
        add(title)
        add("=" * 78)
        for iters in LENGTHS:
            for rnd in ROUNDS:
                add("")
                add("-- %d iteracio, %s kor --" % (iters, rnd))
                add("  %-38s %-22s %-22s %-22s %-22s" % (
                    "ag", "lattogatott modok", "Brain-aran", "H/Hmax",
                    "atmeneti H"))
                arms = payload["arms"][solver_name][str(iters)][rnd]
                order = ([a["id"] for a in DET_ARMS]
                         + [a["id"] for a in NOISE_ARMS]
                         + [f"hardware_recorded_replay_{hw['prefix']}"
                            for hw in HARDWARE_RUNS if hw["length"] == iters]
                         + [f"hardware_residual_{hw['prefix']}"
                            for hw in HARDWARE_RUNS if hw["length"] == iters]
                         + [f"hardware_rescaled_{hw['prefix']}"
                            for hw in HARDWARE_RUNS if hw["length"] == iters]
                         + [f"hardware_permuted_{hw['prefix']}"
                            for hw in HARDWARE_RUNS if hw["length"] == iters])
                for arm_id in order:
                    entry = arms.get(arm_id)
                    if not entry:
                        continue
                    m = entry["metrics"]
                    add("  %-38s %-22s %-22s %-22s %-22s" % (
                        arm_id,
                        fmt_band(m["distinct_modes"], 0),
                        fmt_band(m["brain_ratio"]),
                        fmt_band(m["H_Hmax"]),
                        fmt_band(m["transient_H"])))
                add("")
                add("  A klasszikus kontroll a zajos agak savjan belul van?")
                control = arms.get("classical")
                if control:
                    for arm in NOISE_ARMS:
                        noisy = arms.get(arm["id"])
                        if not noisy:
                            continue
                        for key in METRIC_KEYS:
                            cval = control["metrics"][key]["median"]
                            band_v = noisy["metrics"][key]
                            inside = band_v["p5"] <= cval <= band_v["p95"]
                            add("    %-30s %-14s kontroll=%-10.4f "
                                "sav=[%.4f, %.4f]  %s"
                                % (arm["id"], key, cval, band_v["p5"],
                                   band_v["p95"],
                                   "Benne" if inside else "KIVUL"))
                add("")

    add("=" * 78)
    add("A HARDVERES FUTASOK HELYE A SAVBAN")
    add("=" * 78)
    add("")
    add("A hardver a LEGACY solverrel futott, ezert a legacy savba kerul.")
    add("A 'szazalek' a hardver merőszamanak helye a CPU-ag savjaban.")
    add("")
    for hw in HARDWARE_RUNS:
        prefix = hw["prefix"]
        add("  %s  (%d iteracio, %s visszacsatolas)" % (
            prefix, hw["length"], hw["feedback"]))
        for solver_name in payload["parameters"]["solvers"]:
            key = f"{prefix}|{solver_name}"
            if key not in hw_seq:
                continue
            m = hw_seq[key]["metrics"]
            add("    %s solver:" % solver_name)
            add("      lattogatott modok = %d | Brain-aran = %.4f | "
                "H/Hmax = %.4f | atmeneti H = %.4f"
                % (m["distinct_modes"], m["brain_ratio"], m["H_Hmax"],
                   m["transient_H"]))
            placement = hw_seq[key]["percentile"]
            for rnd in ROUNDS:
                if rnd not in placement:
                    continue
                add("      %s kor:" % rnd)
                for arm_id, per_metric in sorted(placement[rnd].items()):
                    add("        %-38s %s" % (arm_id, "  ".join(
                        "%s=%.1f%%" % (k, per_metric[k]) for k in METRIC_KEYS)))
        add("")

    add("=" * 78)
    add("KOVETKEZTETES")
    add("=" * 78)
    add("")
    for line in payload["conclusion"]:
        add("  " + line)
    add("")
    add("A nyers adatok: measurement_cpu/control_comparison.json")
    add("")

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


# ── a verifikacio ──────────────────────────────────────────────────────
def verify(payload):
    """A beallitott json belso osszefuggeseinek ellenorzese."""
    problems = []
    for solver_name, by_length in payload["arms"].items():
        for length, by_round in by_length.items():
            for rnd, arms in by_round.items():
                for arm_id, entry in arms.items():
                    for key, band_v in entry["metrics"].items():
                        if band_v is None:
                            continue
                        if not (band_v["min"] <= band_v["p5"]
                                <= band_v["median"]
                                <= band_v["p95"] <= band_v["max"]):
                            problems.append(
                                f"{solver_name}/{length}/{rnd}/{arm_id}/{key}: "
                                f"a sav nem rendezett")
                # a classical ag determinisztikus AZONOS kezdeti allapottal
                entry = arms.get("classical")
                if entry:
                    by_init = {}
                    for row in entry["runs"]:
                        by_init.setdefault(row["init_seed"], []).append(row)
                    for init_seed, rows in by_init.items():
                        for key in METRIC_KEYS:
                            values = {row[key] for row in rows}
                            if len(values) > 1:
                                problems.append(
                                    f"{solver_name}/{length}/{rnd}/classical/"
                                    f"{key}: a determinisztikus ag nem "
                                    f"determinisztikus (init_seed={init_seed})")
                # az exact agnak azonosnak kell lennie a classical aggal
                exact = arms.get("exact")
                if entry and exact:
                    for key in METRIC_KEYS:
                        cval = entry["metrics"][key]["median"]
                        eval_ = exact["metrics"][key]["median"]
                        if abs(cval - eval_) > 1e-12:
                            problems.append(
                                f"{solver_name}/{length}/{rnd}/exact/{key}: a "
                                f"zajmentes csatorna nem egyezik a klasszikus "
                                f"kontrollal ({eval_} != {cval})")
    # a hardveres futasok savon belul-e
    for key, hw in payload["hardware"].items():
        for rnd, placement in hw["percentile"].items():
            for arm_id, per_metric in placement.items():
                for metric, pct in per_metric.items():
                    if pct is None:
                        continue
                    if not (0.0 <= pct <= 100.0):
                        problems.append(f"{key}/{rnd}/{arm_id}/{metric}: a "
                                        f"szazalek kívül esik 0-100 kozott")
    return problems


# ── a fo ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="A kvantum-visszacsatolas kontroll-osszehasonlítása")
    parser.add_argument("--seeds", type=int, default=200,
                        help="zaj seed/db per zajos ag (>= 200)")
    parser.add_argument("--init-seeds", type=int, default=30,
                        help="a valtozo kezdeti allapot db szama (>= 30)")
    parser.add_argument("--init-noise-seeds", type=int, default=6,
                        help="zaj seed/db ketto korben, kezdeti allapotonkent")
    parser.add_argument("--workers", type=int, default=0,
                        help="processz szam (0 = ossszes mag)")
    parser.add_argument("--out-dir", default=None,
                        help="a json kimenet konyvtara")
    parser.add_argument("--report", default=None,
                        help="a szoveges jelentés konyvtara")
    parser.add_argument("--verify", default=None,
                        help="a beallitott json ellenorzése (nem futtat)")
    parser.add_argument("--no-legacy", action="store_true",
                        help="csak a javitott solverrel (a gyorsabb smoke)")
    args = parser.parse_args()

    if args.verify:
        with open(args.verify, encoding="utf-8") as handle:
            payload = json.load(handle)
        problems = verify(payload)
        if problems:
            print("AZ ELLENORZES NEM TELJESUL:")
            for item in problems:
                print(f"  - {item}")
            return 1
        print("AZ ELLENORZES TELJESUL: a beallitott json belso "
              "osszefugesei rendben")
        return 0

    out_dir = args.out_dir or os.path.join(REPO, "measurement_cpu")
    report_dir = args.report or os.path.join(REPO, "docs")
    os.makedirs(out_dir, exist_ok=True)

    solvers = ["current"] if args.no_legacy else ["current", "legacy"]
    tasks = build_tasks(args.seeds, args.init_seeds, solvers,
                        args.init_noise_seeds)
    workers = args.workers or max(1, (os.cpu_count() or 2) - 2)

    print("=" * 78)
    print("A KVANTUM-VISSZACSATOLAS KONTROLL-OSSZEHASONLITASA")
    print("=" * 78)
    print(f"  futasok szama : {len(tasks)}")
    print(f"  processzek    : {workers}")
    print(f"  solver        : {', '.join(solvers)}")
    print(f"  zaj seed/db   : {args.seeds} | valtozo kezdeti allapot: "
          f"{args.init_seeds} (x{args.init_noise_seeds} zaj seed)")
    print()

    results = []
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for i, item in enumerate(pool.map(run_task, tasks, chunksize=8)):
                results.append(item)
                if (i + 1) % 200 == 0:
                    print(f"  ... {i + 1}/{len(tasks)}")
    else:
        for i, task in enumerate(tasks):
            results.append(run_task(task))
            if (i + 1) % 200 == 0:
                print(f"  ... {i + 1}/{len(tasks)}")

    # ── a rendezes (a determinizmus miatt) ──
    results.sort(key=lambda item: (item[5], item[2], item[7], item[0],
                                   item[1], item[3], item[4]))

    # ── a referencia hisztogram (a klasszikus kontroll) ──
    reference = {}
    for kind, arm_id, iters, init_seed, noise_seed, solver_name, prefix, rnd, m, seq in results:
        if kind == "classical":
            reference[(solver_name, iters, init_seed)] = m["hist"]

    # ── az armok osszefogasa ──
    arms = {}
    for solver_name in solvers:
        arms[solver_name] = {}
        for iters in LENGTHS:
            arms[solver_name][str(iters)] = {}
            for rnd in ROUNDS:
                arms[solver_name][str(iters)][rnd] = {}

    runs_by_arm = {}
    hist_by_arm = {}
    for kind, arm_id, iters, init_seed, noise_seed, solver_name, prefix, rnd, m, seq in results:
        ref = reference.get((solver_name, iters, init_seed))
        row = {
            "kind": kind,
            "init_seed": init_seed,
            "noise_seed": noise_seed,
            "prefix": prefix,
            "distinct_modes": m["distinct_modes"],
            "brain_ratio": m["brain_ratio"],
            "H_Hmax": m["H_Hmax"],
            "transient_H": m["transient_H"],
            "tv_to_classical": (tv_distance(m["hist"], ref)
                                if ref is not None else None),
        }
        runs_by_arm.setdefault((solver_name, iters, rnd, arm_id), []).append(row)
        hist_by_arm.setdefault((solver_name, iters, rnd, arm_id), []).append(m["hist"])

    for (solver_name, iters, rnd, arm_id), rows in runs_by_arm.items():
        hists = hist_by_arm.get((solver_name, iters, rnd, arm_id), [])
        mean_hist = ([float(x) for x in np.mean(np.array(hists), axis=0)]
                     if hists else [0.0] * 16)
        entry = {
            "count": len(rows),
            "metrics": {
                key: band([row[key] for row in rows]) for key in METRIC_KEYS
            },
            "tv_to_classical": band([row["tv_to_classical"] for row in rows
                                     if row["tv_to_classical"] is not None]),
            "mean_histogram": mean_hist,
            "runs": rows,
        }
        arms[solver_name][str(iters)][rnd][arm_id] = entry

    # ── a hardveres futasok mod-sorozatai es helyuk ──
    hw_sequences = hardware_mode_sequences()
    hardware = {}
    for hw in HARDWARE_RUNS:
        prefix = hw["prefix"]
        for solver_name in solvers:
            modes = hw_sequences[(prefix, solver_name)]
            m = q.metrics(modes)
            placement = {}
            for rnd in ROUNDS:
                for arm_id, entry in arms[solver_name][str(hw["length"])][rnd].items():
                    per_metric = {}
                    for key in METRIC_KEYS:
                        values = [row[key] for row in entry["runs"]]
                        per_metric[key] = percentile_of(m[key], values)
                    placement.setdefault(rnd, {})[arm_id] = per_metric
            hardware[f"{prefix}|{solver_name}"] = {
                "prefix": prefix,
                "length": hw["length"],
                "feedback": hw["feedback"],
                "solver": solver_name,
                "mode_sequence": modes,
                "metrics": m,
                "percentile": placement,
            }

    # ── a dontetest ──
    conclusion = []
    for solver_name in solvers:
        for iters in LENGTHS:
            for rnd in ROUNDS:
                arms_here = arms[solver_name][str(iters)][rnd]
                control = arms_here.get("classical")
                if not control:
                    continue
                inside_all = True
                for arm in NOISE_ARMS:
                    noisy = arms_here.get(arm["id"])
                    if not noisy:
                        continue
                    for key in METRIC_KEYS:
                        cval = control["metrics"][key]["median"]
                        band_v = noisy["metrics"][key]
                        if not (band_v["p5"] <= cval <= band_v["p95"]):
                            inside_all = False
                conclusion.append(
                    f"{solver_name} solver, {iters} iteracio, {rnd} kor: a "
                    f"klasszikus kontroll "
                    f"{'a zajos agak savjan BELUL van' if inside_all else 'a zajos agak savjan KIVUL van'}")

    # ── hardveres reziduum arm ertekelese a QPU-RUN-DECISION-RULE.txt szerint ──
    # M1 = distinct_modes, M2 = brain_ratio
    # A hardveres reziduum a zajsavon KIVUL van, ha legalabb az egyik metrika
    # (M1 vagy M2) KIVUL esik a zajos agak 5-95% savjan.
    # A szabaly szerint: ha a hardver a zajsavon BELUL van -> NEM inditunk uj QPU futast.
    for solver_name in solvers:
        if solver_name != "current":
            continue  # a valodi reziduum csak a javitott solverrel van szamitva
        for iters in LENGTHS:
            for rnd in ROUNDS:
                arms_here = arms[solver_name][str(iters)][rnd]
                # Megtalaljuk a hardveres reziduum agakat
                hw_residual_arms = [aid for aid in arms_here.keys() if aid.startswith("hardware_residual_")]
                for hw_arm in hw_residual_arms:
                    hw_m = arms_here[hw_arm]["metrics"]
                    hw_distinct = hw_m["distinct_modes"]["median"]
                    hw_brain = hw_m["brain_ratio"]["median"]
                    
                    # Ellenorizzuk minden zaj ag ellen
                    outside_any = False
                    for arm in NOISE_ARMS:
                        noisy = arms_here.get(arm["id"])
                        if not noisy:
                            continue
                        # M1: distinct_modes
                        d_band = (noisy["metrics"]["distinct_modes"]["p5"], noisy["metrics"]["distinct_modes"]["p95"])
                        d_out = hw_distinct < d_band[0] or hw_distinct > d_band[1]
                        # M2: brain_ratio
                        b_band = (noisy["metrics"]["brain_ratio"]["p5"], noisy["metrics"]["brain_ratio"]["p95"])
                        b_out = hw_brain < b_band[0] or hw_brain > b_band[1]
                        
                        if d_out or b_out:
                            outside_any = True
                    
                    if outside_any:
                        conclusion.append(
                            f"HARDVERES REZIDUUM ({hw_arm}, {iters} iter, {rnd}): "
                            f"M1(distinct={hw_distinct}) vagy M2(brain={hw_brain:.4f}) "
                            f"KIVUL esik a zajos agak savjan -> "
                            f"SZABALY: uj QPU futas INDOKOLT")
                    else:
                        conclusion.append(
                            f"HARDVERES REZIDUUM ({hw_arm}, {iters} iter, {rnd}): "
                            f"M1(distinct={hw_distinct}) es M2(brain={hw_brain:.4f}) "
                            f"BELUL van a zajos agak savjan -> "
                            f"SZABALY: uj QPU futas NEM indokolt")

    payload = {
        "generated_by": "scripts/control_comparison.py",
        "parameters": {
            "seeds": args.seeds,
            "init_seeds": args.init_seeds,
            "init_noise_seeds": args.init_noise_seeds,
            "rounds": ROUNDS,
            "lengths": LENGTHS,
            "solvers": solvers,
            "c_measured_median": C_MEASURED_MEDIAN,
            "gpe_steps": q.GPE_STEPS,
            "base_seed": q.SEED,
            "runs": len(results),
        },
        "arms": arms,
        "hardware": hardware,
        "conclusion": conclusion,
    }

    json_path = os.path.join(out_dir, "control_comparison.json")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, ensure_ascii=False, sort_keys=True)
    print(f"  kiirva: {os.path.relpath(json_path, REPO)}")

    report_path = os.path.join(report_dir, "MEASUREMENTS-CPU-CONTROLS.txt")
    write_report(report_path, payload, {
        "seeds": args.seeds,
        "init_seeds": args.init_seeds,
        "init_noise_seeds": args.init_noise_seeds,
        "key": "a classical kontroll benne van-e a zajos agak 5-95% savjan",
    })
    print(f"  kiirva: {os.path.relpath(report_path, REPO)}")

    problems = verify(payload)
    if problems:
        print()
        print("AZ ELLENORZES NEM TELJESUL:")
        for item in problems:
            print(f"  - {item}")
        return 1
    print()
    for line in conclusion:
        print("  " + line)
    print()
    print("AZ ELLENORZES TELJESUL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
