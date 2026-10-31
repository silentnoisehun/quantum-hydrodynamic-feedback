# A CLI-ENERGIAK OSSZEHASONLITASA a hardcode-olt listaval
# A claude-logic `StratosField::load` a "STRA" magic-et varja:
#   [magic:u32][n:u32][viscosity:f64][psi: n*n * 16 byte]
# es a `get_mode_energies` a `hexagonal_lattice(16, 6.0)` pontokon,
# SULY NELKUL osszegezi a |psi|^2-t, majd normalizal.
import struct, math, random, json, os
from pathlib import Path

# Default to external/claude-logic/stratos.bin relative to repo root
# Override with STRATOS_BIN_PATH environment variable
BIN = os.environ.get("STRATOS_BIN_PATH") or str(
    Path(__file__).parent.parent / "external" / "claude-logic" / "stratos.bin"
)
MODE_NAMES = ["Brain","Logic","Memory","Creativity","Heart","Intuition","Focus","Empathy",
              "Analysis","Synthesis","Ethics","Play","Dream","Social","Survival","Transcendence"]

def hexagonal_lattice(n, radius):
    pos = [(0.0, 0.0)]
    rings = int(math.ceil(math.sqrt(n) * 0.8))
    ring = 1
    while len(pos) < n:
        r = radius * ring / rings
        pts = min(6 * ring, n - len(pos) + 1)
        for k in range(pts):
            if len(pos) >= n: break
            a = 2 * math.pi * k / pts
            pos.append((r * math.cos(a), r * math.sin(a)))
        ring += 1
    return pos

def load_field(path):
    with open(path, "rb") as f:
        data = f.read()
    magic = struct.unpack_from("<I", data, 0)[0]
    n = struct.unpack_from("<I", data, 4)[0]
    visc = struct.unpack_from("<d", data, 8)[0]
    psi = []
    for i in range(n * n):
        re, im = struct.unpack_from("<dd", data, 16 + i * 16)
        psi.append(complex(re, im))
    return magic, n, visc, psi

magic, n, visc, psi = load_field(BIN)
print("magic = 0x%08X (STRA = 0x53545241)  n = %d  viscosity = %.4f" % (magic, n, visc))
print("a fajl merete: %d byte (elvar: %d)" % (os.path.getsize(BIN), 16 + n*n*16))
print()
print("  A MAGIC MEGLEPETES: %s" % ("EGYEZIK -> a claude-logic StratosField olvassa" if magic == 0x53545241
                                     else "NEM EGYEZIK -> a load None-t ad, FRISS StratosField::new() keletkezik"))

def mode_energies(psi, n, well_width=1.5):
    pos = hexagonal_lattice(16, 6.0)
    dx = 20.0 / n
    out = [0.0] * 16
    for m, (mx, my) in enumerate(pos):
        for j in range(n):
            for i in range(n):
                x = (i - n / 2.0) * dx
                y = (j - n / 2.0) * dx
                r2 = (x - mx) ** 2 + (y - my) ** 2
                if r2 < 4.0 * well_width * well_width:
                    out[m] += abs(psi[j * n + i]) ** 2
    tot = sum(out)
    if tot > 1e-10:
        out = [e / tot for e in out]
    return out

E = mode_energies(psi, n)
print()
print("  A STRATOS.BIN-BOL SZAMITOTT 16 MOD ENERGIA:")
for i, e in enumerate(E):
    print("    %2d %-16s E=%.8f" % (i, MODE_NAMES[i], e))

HARD = [
    0.09620959036827400, 0.07677600000000000, 0.08902975000000000, 0.09443425000000000,
    0.08851945000000000, 0.08038322000000000, 0.07562627000000000, 0.02933872000000000,
    0.03608653000000000, 0.05413618000000000, 0.05810160000000000, 0.06105229000000000,
    0.04328244000000000, 0.03946274000000000, 0.04136071000000000, 0.03620027197138900,
]
print()
print("  OSSZEHASONLITAS a hardcode-olt listaval:")
for i in range(16):
    print("    %-16s stratos.bin=%.8f  hardcode=%.8f  diff=%+.2e" % (
        MODE_NAMES[i], E[i], HARD[i], E[i]-HARD[i]))
print()
print("  max |diff| = %.3e" % max(abs(E[i]-HARD[i]) for i in range(16)))

def depolarized(p, c):
    return c * p + (1.0 - c) / 2.0

def sample(rng, p, shots):
    mu = p * shots
    sigma = math.sqrt(max(p * (1.0 - p) * shots, 1e-12))
    n_ = int(round(rng.gauss(mu, sigma)))
    return max(0, min(shots, n_))

def accuracy(energies, c, trials=20000, seed=20261026):
    rng = random.Random(seed)
    classical = max(range(16), key=lambda i: energies[i])
    hits = 0
    for _ in range(trials):
        counts = [sample(rng, depolarized(p, c), 1024) for p in energies]
        if max(range(16), key=lambda i: counts[i]) == classical:
            hits += 1
    return hits / trials

print()
print("  PONTOSSAG a ket energialistaval (1024 shot, 20 000 trial):")
for c in (1.0, 0.949, 0.877):
    a = accuracy(E, c)
    b = accuracy(HARD, c)
    print("    c=%.3f   stratos.bin: %.4f    hardcode: %.4f" % (c, a, b))
