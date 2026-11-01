# =============================================================================
# ⚠️ ELAVULT SOLVER — KIZÁRÓLAG REPRODUKCIÓS CÉLOKBRA ⚠️
# =============================================================================
# Ez a fájl a commit a72ead4 állapotának pontos másolata
# (scripts/quantum_loop_sim.py a72ead4 commitban).
#
# 🧬 MIÉRT VAN: a 2026-10-27-i hardveres hurok-futások EZZEL a solverrel
# futottak. A replay-regressziós teszt (scripts/replay_hardware_log.py)
# a naplózott mode_argmax-ot ennek a solverrel reprodukálja, és
# ellenőrzi, hogy a JAVÍTOTT solverrel NEM reprodukálható — vagyis
# hogy a hardveres futások a javítás ELŐTTI kóddal készültek.
#
# 🧬 A KÉT SOLVER KÖZÖTTI KÜLÖNBSÉG (a 2026-10-31-es javítás):
#   1. a kinetikus lépés: itt `ifft2(psi * KPH)` (előre transforms NÉLKÜL),
#      a javítottban `ifft2(fft2(psi) * KPH)` — a helyes 2D FFT
#   2. a csillapítás: itt globális `DECAY = exp(-gamma*dt)` skalár,
#      a javítottban lokális `exp(-gamma*dt*|psi|^2)`
#      (a globális skalárt a lépés végi normalizálás kivenné, tehát
#      matematikailag no-op lenne)
#
# 🧬 EZT A SOLVERT NEM SZABAD ÚJ MÉRÉSRE HASZNÁLNI. A javított változat:
#   scripts/quantum_loop_sim.py
# =============================================================================

# A KVANTUM-KLASSZIKUS HUROK SZIMULACIOJA
# =============================================================
# A protokoll, ahogy MATE leirta:
#   1. GPE novel -> (A, f, phi)
#   2. QPU: 3 circuit (A, f, phi), 10 shot
#   3. decode -> (A', f', phi')  [zajos]
#   4. GPE 50-100 lepes: a zajt "betereli" egy attraktorba
#   5. ujra mer -> vissza 2.
#
# A CEL: a hurok 16 mod argmax-sorozata mutat-e STRUKTURALT MINTAT,
#        a klasszikus (kvantumzaj nelkuli) kontrollhoz kepest.
#
# AZ ELEJES GPE: valodi 2D FFT (numpy ifft2), a gpe.rs K/2 -> V -> K/2
#               szerkezetevel. A gpe.rs FAZIS-ROTACIOJA (dead) kontrollkent.
# HARDVER: a mert Bell-egyensuly c (0.877-0.993) -> p_eff = c*p + (1-c)*0.5
# ==================================================================
import numpy as np, math, json, os, sys
from math import comb, sin, sqrt, asin, acos, pi

N       = 32
DOMAIN  = 20.0
DT      = 0.005
G       = -1.0
TRAP    = 0.1
DAMPING = 0.002
HBAR    = 1.0
MASS    = 1.0
WELL_DEPTH = 2.0
WELL_SIGMA = 3.0

ITERS   = 1000
GPE_STEPS = 50
SHOTS   = 10
C_BELL  = 0.949          # a 'jellemzo' Bell-egyensuly (87,7-99,3% tartomany)
SEED    = 20261026

rng = np.random.default_rng(SEED)

# ------------------------------------------------------------------
# A GPE — a gpe.rs verbatim portja, DE valodi 2D FFT-vel a kinetikus lepesben
# ------------------------------------------------------------------
def genome_positions(n):
    center = n / 2.0
    radius = n / 4.0
    pos = [(center, center)]
    for k in range(6):
        a = 2 * pi * k / 6
        pos.append((center + radius*0.5*math.cos(a), center + radius*0.5*math.sin(a)))
    for k in range(9):
        a = 2 * pi * k / 9
        pos.append((center + radius*math.cos(a), center + radius*math.sin(a)))
    return pos

MODES = genome_positions(N)

# A 16 mód neve (a hardveres hurok a nevüket is kiírja)
MODE_NAMES = [
    "Brain", "Logic", "Memory", "Creativity", "Heart", "Intuition", "Focus", "Empathy",
    "Analysis", "Synthesis", "Ethics", "Play", "Dream", "Social", "Survival", "Transcendence",
]

def create_potential(n):
    pot = np.zeros((n, n))
    center = n / 2.0
    for i in range(n):
        for j in range(n):
            dx = (i - center) / center
            dy = (j - center) / center
            v = 0.5 * TRAP * TRAP * (dx*dx + dy*dy)
            for (mx, my) in MODES:
                d2 = (i-mx)**2 + (j-my)**2
                v += -WELL_DEPTH * math.exp(-d2 / (2.0*WELL_SIGMA**2))
            pot[i, j] = v
    return pot

def k_grid(n):
    dk = 2.0 * pi / DOMAIN
    k = np.array([i*dk if i <= n//2 else (i-n)*dk for i in range(n)])
    return k

K1 = k_grid(N)
KX, KY = np.meshgrid(K1, K1, indexing="ij")
K2 = KX**2 + KY**2
# gpe.rs: a kinetikus felresz a K/2-re: exp(-i*dt*hbar*k2/(4*mass))
KPH = np.exp(-1j * DT * HBAR * K2 / (4.0*MASS))
KPH_DEAD = np.exp(-1j * DT * HBAR * K2 / (4.0*MASS))   # a dead kod: index-tér, nem k-tér

POT = create_potential(N)
DX = DOMAIN / N
DECAY = math.exp(-DAMPING * DT)

def init_psi(n, seed):
    r = np.random.default_rng(seed)
    c = n / 2.0
    sigma = n / 6.0
    i = np.arange(n)[:, None]; j = np.arange(n)[None, :]
    x = (i - c)/c * DOMAIN/2.0
    y = (j - c)/c * DOMAIN/2.0
    gauss = np.exp(-(x*x + y*y) / (2.0*sigma*sigma/(c*c)))
    psi = (r.uniform(-0.1, 0.1, (n, n)) + 1j*r.uniform(-0.1, 0.1, (n, n))) * gauss
    return normalize(psi)

def normalize(psi):
    ns = (np.abs(psi)**2).sum() * DX * DX
    if ns < 1e-10: return psi
    return psi / math.sqrt(ns)

def gpe_step(psi, live=True):
    """K/2 -> V -> K/2 split-step, valodi 2D FFT-vel (live=True) vagy
       a gpe.rs dead fazis-rotaciojaval (live=False)."""
    if live:
        psi = np.fft.ifft2(psi * KPH)
    else:
        # a gpe.rs dead kod: a fazis-rotacio a RACsINDEX-térben (nem k-térben)
        psi = psi * np.exp(-1j * DT * HBAR * K2 / (4.0*MASS))
    dens = np.abs(psi)**2
    v = POT + G * dens
    psi = psi * np.exp(-1j * DT * v / HBAR) * DECAY
    if live:
        psi = np.fft.ifft2(psi * KPH)
    else:
        psi = psi * np.exp(-1j * DT * HBAR * K2 / (4.0*MASS))
    return normalize(psi)

def mode_energies(psi):
    """hope-cli/src/fluid_stratos/mod.rs:202-232 verbatim (radius=5, sigma=3)"""
    dens = np.abs(psi)**2
    out = np.zeros(16)
    for m, (px, py) in enumerate(MODES):
        ii = np.arange(N)[:, None]; jj = np.arange(N)[None, :]
        d = np.hypot(ii - px, jj - py)
        mask = d < 5.0
        w = np.exp(-(d*d)/(2.0*9.0)) * mask
        out[m] = (dens * w).sum()
    return out

def coherence(psi):
    """gpe.rs:179-201 verbatim"""
    dens = np.abs(psi)**2
    mx = dens.max(); mean = dens.mean()
    if mean < 1e-10: return 0.0
    return math.tanh((mx/mean)/15.0)

# ------------------------------------------------------------------
# A GPE -> (A, f, phi) KINYERES
# A GPE hexagonalis 16 modjabol:
#   A    : a dominancia (max E) a maximumhoz kepest -> [0,1]
#   f    : az energiákkal sulyozott atlagos MOD-INDEX / 16 -> [0,1]
#   phi  : az energiákkal sulyozott atlagos HEXAGONALIS SZOG / 2pi -> [0,1]
# Majd a KODOLASI TARTOMANYBA:
#   A_kod = pi * A      -> P(q0=1) = sin^2(A_kod/2)
#   f_kod = 0.5 * f     -> P(q0=1) = sin^2(pi*f_kod)   [dekodalas [0,0.5]]
#   ph_kod = pi * phi   -> P(q0=1) = sin^2(ph_kod/2)
# ------------------------------------------------------------------
MODE_ANGLES = np.array([math.atan2(my - N/2.0, mx - N/2.0) % (2*pi) for (mx, my) in MODES])
MODE_RADII = np.array([math.hypot(mx - N/2.0, my - N/2.0) for (mx, my) in MODES])
RMAX = MODE_RADII.max()

def extract(psi):
    E = mode_energies(psi)
    s = E.sum()
    if s < 1e-12: return 0.0, 0.0, 0.0, E
    p = E / s
    A = p.max()
    f = float((p * np.arange(16)).sum())
    ang = np.exp(1j * MODE_ANGLES)
    c = (p * ang).sum()
    phi = (math.atan2(c.imag, c.real) % (2*pi)) / (2*pi)
    return A, f, phi, E

# ------------------------------------------------------------------
# A KVANTUM LOKES — 3 circuit, 10 shot, hardver-minoseg c
# ------------------------------------------------------------------
def q_measure(p_true):
    """A hardver c-vel gyengul: p_eff = c*p_true + (1-c)*0.5.
       10 loves -> k darab talalat -> P = k/10"""
    p_eff = C_BELL * p_true + (1 - C_BELL) * 0.5
    k = rng.binomial(SHOTS, p_eff)
    return k / SHOTS

def decode_phase(p):     return 2.0 * asin(sqrt(min(max(p, 0.0), 1.0)))
def decode_amplitude(p0):return 2.0 * acos(sqrt(min(max(p0, 0.0), 1.0)))
def decode_frequency(p1):return asin(sqrt(min(max(p1, 0.0), 1.0))) / pi

def quantum_shot(A, f, phi):
    """A 3 hardver-meres, 10 lovesel, a c-minoseggel"""
    # A: RY(A_kod) -> P(q0=0) = cos^2(A_kod/2)
    A_kod = pi * A
    p0_true = math.cos(A_kod/2.0)**2
    A_back = decode_amplitude(1.0 - q_measure(p0_true))
    # f: RY(2*pi*f_kod) + CNOT -> P(q0=1) = sin^2(pi*f_kod)
    f_kod = 0.5 * f
    f_back = decode_frequency(q_measure(math.sin(pi*f_kod)**2))
    # phi: RY(phi_kod) + CNOT -> P(q0=1) = sin^2(phi_kod/2)
    ph_kod = pi * phi
    ph_back = decode_phase(q_measure(math.sin(ph_kod/2.0)**2))
    return A_back/pi, f_back/0.5, ph_back/pi

def excite(psi, A, f, phi):
    """A dekodolt (A, f, phi) visszatoltese a folyadékba:
       a 16 mod kozul a (f, phi) koordinatahoz legkozelebbi modo gerjesztese A erosseggel"""
    target_ang = phi * 2 * pi
    target_rad = f * RMAX
    d = np.hypot(MODE_ANGLES - target_ang, (MODE_RADII - target_rad) * 0.6)
    d = np.minimum(d, 2*pi - np.minimum(d, 2*pi))
    m = int(np.argmin(d))
    mx, my = MODES[m]
    ii = np.arange(N)[:, None]; jj = np.arange(N)[None, :]
    r2 = (ii-mx)**2 + (jj-my)**2
    psi = psi + np.exp(-r2/(2.0*1.5**2)) * (A * 2.0)
    return normalize(psi)

# ------------------------------------------------------------------
# A HUROK
# ------------------------------------------------------------------
def run_loop(mode, live=True, seed=SEED):
    """mode: 'quantum' | 'classical' (kvantumzaj nelkul) | 'dead' (gpe.rs halott)"""
    r = np.random.default_rng(seed)
    global rng
    old_rng = rng
    rng = r
    psi = init_psi(N, seed)
    seq = []; coh = []; params = []
    for it in range(ITERS):
        A, f, phi, E = extract(psi)
        if mode == "quantum":
            A2, f2, ph2 = quantum_shot(A, f, phi)
        else:
            A2, f2, ph2 = A, f, phi       # a klasszikus kontroll: a GPE folytatodik
        psi = excite(psi, A2, f2, ph2)
        for _ in range(GPE_STEPS):
            psi = gpe_step(psi, live=live)
        seq.append(int(np.argmax(mode_energies(psi))))
        coh.append(coherence(psi))
        params.append((A, f, phi))
    rng = old_rng
    return seq, coh, params

def stats(seq, label):
    n = len(seq)
    hist = np.bincount(seq, minlength=16)
    # a marginalis elosztas entrópiaja
    p = hist / n
    nz = p[p > 0]
    H = -(nz * np.log(nz)).sum()
    Hmax = math.log(16)
    # az atmeneti matrix (kovetkezo allapot)
    T = np.zeros((16, 16))
    for a, b in zip(seq, seq[1:]):
        T[a, b] += 1
    tr = T.sum(axis=1, keepdims=True)
    tr[tr == 0] = 1
    P = T / tr
    # az "atmeneti entrópia" (a sorok entrópiajanak sulya)
    rowH = []
    for i in range(16):
        if tr[i, 0] == 0: continue
        pi_ = P[i][P[i] > 0]
        rowH.append(-(pi_*np.log(pi_)).sum())
    mH = float(np.mean(rowH)) if rowH else 0.0
    # a valtozok szama (hany allapotban volt atmenet)
    active = int((tr[:, 0] > 0).sum())
    # a legutolso 500: a stabilizacio utani allapot
    tail = seq[-500:]
    thist = np.bincount(tail, minlength=16)
    tp = thist / len(tail)
    tnz = tp[tp > 0]
    tH = -(tnz*np.log(tnz)).sum()
    print("  %-22s hisztogram: %s" % (label, " ".join("%d" % h for h in hist)))
    print("  %-22s marginalis H/Hmax = %.4f  |  atmeneti H (sor) = %.4f / %.4f" % (label, H/Hmax, mH, math.log(16)))
    print("  %-22s aktiv atmeneti allapot = %d/16  |  utolso 500: H/Hmax = %.4f, max modos gyakorisag = %.1f%%" % (
        label, active, tH/Hmax, 100*tp.max()))
    return {"hist": hist.tolist(), "H_Hmax": float(H/Hmax), "mH": mH, "active": active,
            "tail_H": float(tH/Hmax), "tail_max": float(tp.max())}



def main():
    """A 4 ágas szimuláció futtatása (a szkript közvetlen futtatásakor)."""
    print("=" * 78)
    print("A KVANTUM-KLASSZIKUS HUROK SZIMULACIOJA")
    print("=" * 78)
    print("  N=%d  ITERS=%d  GPE_STEPS=%d  SHOTS=%d  C_BELL=%.3f" % (N, ITERS, GPE_STEPS, SHOTS, C_BELL))
    print("  a GPE: valodi 2D FFT (numpy) | a hardver: c=%.3f Bell-egyensuly" % C_BELL)
    print()

    results = {}
    print("-" * 78)
    print("AG 1: KVANTUM-HUROK (a MATE-protokoll, 3 meres x 10 loves)")
    print("-" * 78)
    seq_q, coh_q, par_q = run_loop("quantum", live=True, seed=SEED)
    results["quantum"] = stats(seq_q, "quantum")
    results["quantum"]["coh_mean"] = float(np.mean(coh_q))
    results["quantum"]["coh_min"] = float(np.min(coh_q))
    results["quantum"]["coh_max"] = float(np.max(coh_q))

    print()
    print("-" * 78)
    print("AG 2: KLASSZIKUS KONTROLL (azonos GPE, kvantumzaj NELKUL)")
    print("-" * 78)
    seq_c, coh_c, par_c = run_loop("classical", live=True, seed=SEED+1)
    results["classical"] = stats(seq_c, "classical")
    results["classical"]["coh_mean"] = float(np.mean(coh_c))

    print()
    print("-" * 78)
    print("AG 3: NULL-MODELL (uniform random 16 mod)")
    print("-" * 78)
    r = np.random.default_rng(SEED+2)
    seq_u = r.integers(0, 16, ITERS).tolist()
    results["uniform"] = stats(seq_u, "uniform")

    print()
    print("-" * 78)
    print("AG 4: A DEAD GPE (a gpe.rs FAZIS-ROTACIOJA, ahogy ma van)")
    print("-" * 78)
    seq_d, coh_d, par_d = run_loop("dead", live=False, seed=SEED+3)
    results["dead"] = stats(seq_d, "dead")
    results["dead"]["coh_mean"] = float(np.mean(coh_d))

    print()
    print("=" * 78)
    print("EREDMENY")
    print("=" * 78)
    q = results["quantum"]; c = results["classical"]; u = results["uniform"]; d = results["dead"]
    print("  marginalis H/Hmax   quantum=%.4f  classical=%.4f  uniform=%.4f  dead=%.4f" % (
        q["H_Hmax"], c["H_Hmax"], u["H_Hmax"], d["H_Hmax"]))
    print("  atmeneti H          quantum=%.4f  classical=%.4f  uniform=%.4f  dead=%.4f" % (
        q["mH"], c["mH"], u["mH"], d["mH"]))
    print("  aktiv atmeneti mod  quantum=%d/16   classical=%d/16   dead=%d/16" % (
        q["active"], c["active"], d["active"]))
    print()
    print("  KOHERENCIA (C):")
    print("    quantum   mean=%.4f  min=%.4f  max=%.4f" % (q["coh_mean"], q["coh_min"], q["coh_max"]))
    print("    classical mean=%.4f" % c["coh_mean"])
    print("    dead      mean=%.4f" % d["coh_mean"])
    print()
    print("  A KUZEPS: a quantum es a classical kozott a kulonbseg?")
    print("    hisztogram kulonbseg (TV distance) = %.4f" % (
        0.5*np.abs(np.array(q["hist"]) - np.array(c["hist"])).sum()/ITERS))
    print()
    print("  A KVANTUM PARAMETEREK (az elso 5 iteracio):")
    for i in range(5):
        A, f, phi = par_q[i]
        print("    iter %d: A=%.4f f=%.4f phi=%.4f  -> argmax mod = %d" % (i, A, f, phi, seq_q[i]))

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "quantum-loop-results.json")
    with open(out_path, "w") as fh:
        json.dump({"results": results,
                   "seq_quantum": seq_q, "seq_classical": seq_c, "seq_dead": seq_d,
                   "coh_quantum": coh_q, "coh_classical": coh_c}, fh, indent=1)
    print()
    print("  kiirva: quantum-loop-results.json")



if __name__ == "__main__":
    main()
