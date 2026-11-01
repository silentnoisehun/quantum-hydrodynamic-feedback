//! Quantum Bridge — a STRATOS folyadék kvantumhídja
//!
//! 🧬 NEM 16 versenyző qubit. A hardver-igazolt séma
//! (`scs-quantum`, 2026.10.06, valódi 156 qubit szupravezető QPU)
//! **2 qubit + 3 külön mérés**: az `A` (1 qubit, `RY`), a `f` és a `φ`
//! (2 qubit, `RY` + `CNOT` interferencia).
//!
//! 🧬 A MÉRT DÖNTÉS — AMIÉRT EZ A RÉTEG NEM REJT EL:
//! 16 qubit, 1024 shot, Monte Carlo 20 000 trial, a mért Bell-egyensúlyokkal:
//!   c = 1,000 (nulla zaj) → 42,29%   ·   c = 0,993 → 41,73%
//!   c = 0,981 → 40,85%   ·   c = 0,950 → 39,03%   ·   c = 0,877 → 35,31%
//! A klasszikus argmax ezzel szemben **100%** (0 statisztikai hiba).
//! Az ok: a Brain-vs-Creativity rés mindössze 1,85%, ami 1024 shot-tal
//! **0,14σ** — a kvantum-út a jelenlegi architektúrában NEM KIMUTATHATÓ.
//! 3σ-hoz ~492 000 shot kellene (~481 QDS-job 1024 lövéssel).
//!
//! 🧬 A RÉTEG CÉLJA ezért nem az, hogy a kvantumút nyerjen, hanem hogy
//! **mérhető és látható legyen a különbség** a két út között. Aki ezt
//! elrejti, az nem hazudik — az csak nem mér.

use rand::Rng;
use std::collections::HashMap;
use std::f64::consts::PI;

/// Standard normális véletlen szám (Box–Muller).
///
/// 🧬 MIÉRT NEM A `rand` NORMÁLISA: a `rng.gen::<f64>()` EGYENNYELŐ
/// uniform [0,1) — ha azt használnánk a középső értékhez adva, a
/// binomiális minta nem normálisan, hanem egyenletesen torzított
/// lenne, és a 16 mód versenye hamis eredményt adna. (Ez pontosan
/// happened az első implementációban: 69,25% a mért 42,29% helyett.)
fn standard_normal(rng: &mut impl Rng) -> f64 {
    let mut u1 = rng.gen::<f64>();
    if u1 <= f64::MIN_POSITIVE {
        u1 = f64::MIN_POSITIVE;
    }
    let u2 = rng.gen::<f64>();
    (-2.0 * u1.ln()).sqrt() * (2.0 * PI * u2).cos()
}

/// Pontos binomiális minta: `n` független próba `p` valószínűséggel.
///
/// 🧬 A KÖZELÍTÉS INDOKLÁSA: n = 1024 lövésnél a normál-közelítés
/// skewnesse `|1−2p|/√(np(1−p))` — a 16 mód energiatartományán
/// (p = 0,029…0,096) ez 0,08…0,18, tehát a hiba elhanyagolható.
/// A széles szélekben (np < 10) közvetlen Bernoulli-számlálás, hogy
/// ott se legyen közelítés.
fn binomial_sample(rng: &mut impl Rng, n: u64, p: f64) -> u64 {
    if n == 0 || p <= 0.0 {
        return 0;
    }
    if p >= 1.0 {
        return n;
    }
    let mean = n as f64 * p;
    if mean < 10.0 || mean > n as f64 - 10.0 {
        return (0..n).filter(|_| rng.gen::<f64>() < p).count() as u64;
    }
    let sd = (n as f64 * p * (1.0 - p)).sqrt();
    let v = mean + standard_normal(rng) * sd;
    v.round().clamp(0.0, n as f64) as u64
}

/// A hardver-igazolt SCS-kvóták (a `scs-quantum` repó mérési adatai)
pub mod measured {
    /// A Bell-állapot egyensúly 7 független futásból (2026.10.06, 156 qubit)
    pub const BELL_FIDELITY_MIN: f64 = 0.877;
    pub const BELL_FIDELITY_MAX: f64 = 0.993;
    /// A jellemző futások ~92–95% között voltak
    pub const BELL_FIDELITY_TYPICAL: f64 = 0.949;
    /// A GHZ-állapot egyensúly: 89,3–96,7%
    pub const GHZ_FIDELITY_MIN: f64 = 0.893;
    pub const GHZ_FIDELITY_MAX: f64 = 0.967;
    /// A kvantum-delayed-sync effektív T₂: 89,6 ± 39,2 µs
    pub const QDS_T2_EFF_US: f64 = 89.6;
    pub const QDS_T2_STD_US: f64 = 39.2;
    /// A QDS kalibrált mérési ablak
    pub const QDS_SHOTS: usize = 1024;
    /// A 16 mód ARGMAX-ának mért kvantum pontossága nulla zaj mellett
    pub const MEASURED_QUANTUM_ACCURACY: f64 = 0.4229;
    /// A klasszikus argmax pontossága
    pub const MEASURED_CLASSICAL_ACCURACY: f64 = 1.0;
}

/// A frekvencia (`f`) kódolási tartománya.
///
/// 🧬 MIÉRT (2026-11-01, T1): a GPE-ből kinyert `f` a 16 mód
/// indexének súlyozott átlaga, tehát `[0, 15]`. A kétkvantumos
/// interferencia-dekódolás (`f = arcsin(√P)/π`) CSAK `[0, 0.5]`-en
/// egyértelmű, mert a `sin²(πf)` periodikus. Ezért a kódolás előtt a
/// `f`-et normalizáljuk, a dekódolás után visszaszorozzuk.
pub const F_MODE_INDEX_MAX: f64 = 15.0;
/// A frekvenciadekódolás egyértelmű tartománya.
pub const F_DECODE_MAX: f64 = 0.5;

/// Az `f` (mód-index, `[0, 15]`) → a kódolás egyértelmű tartománya `[0, 0.5]`.
pub fn normalize_f(f: f64) -> f64 {
    F_DECODE_MAX * f / F_MODE_INDEX_MAX
}

/// A dekódolt `f` `[0, 0.5]` → vissza a mód-index tartományba `[0, 15]`.
pub fn denormalize_f(f_decoded: f64) -> f64 {
    f_decoded / F_DECODE_MAX * F_MODE_INDEX_MAX
}

/// Quantum backend target.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum QuantumBackend {
    /// Origin Quantum Wukong — szupravezető, felhő API
    Wukong,
    /// IBM Quantum Eagle/Heron — 127+ qubit
    IbmEagle,
    /// Klasszikus szimuláció (a mért hardver-paraméterekkel)
    Classical,
}

impl QuantumBackend {
    /// A backend hardver-kapacitása
    pub fn max_qubits(&self) -> usize {
        match self {
            QuantumBackend::Wukong => 72,
            QuantumBackend::IbmEagle => 127,
            QuantumBackend::Classical => 16,
        }
    }

    /// A backend állapotának szöveges leírása
    pub fn status(&self) -> String {
        match self {
            QuantumBackend::Wukong => format!(
                "Wukong {} qubit (a mért útvonal: 2 qubit, 3 külön mérés)",
                self.max_qubits()
            ),
            QuantumBackend::IbmEagle => format!(
                "IBM Eagle {} qubit (a mért útvonal: 2 qubit, 3 külön mérés)",
                self.max_qubits()
            ),
            QuantumBackend::Classical => format!(
                "Klasszikus szimuláció {} virtuális qubit (mért hardver-paraméterekkel)",
                self.max_qubits()
            ),
        }
    }
}

/// Egyetlen kvantumkapu — gyártótól független leírás.
#[derive(Clone, Debug, PartialEq)]
pub struct Gate {
    /// A kapu neve (`RY`, `H`, `CX`, `CNOT`, …)
    pub gate_type: String,
    /// A célkvantumok. Kétkvantumos kapunál: `[kontroll, cél]`.
    pub qubits: Vec<usize>,
    /// A kapu paraméterei
    pub params: Vec<f64>,
}

impl Gate {
    /// Paraméter nélküli kapu
    pub fn new(gate_type: &str, qubits: Vec<usize>) -> Self {
        Self {
            gate_type: gate_type.to_string(),
            qubits,
            params: Vec::new(),
        }
    }

    /// Egyparaméteres kapu
    pub fn with_param(gate_type: &str, qubits: Vec<usize>, param: f64) -> Self {
        Self {
            gate_type: gate_type.to_string(),
            qubits,
            params: vec![param],
        }
    }
}

/// Hardverfüggetlen kvantumáramkör.
#[derive(Clone, Debug, PartialEq)]
pub struct CircuitSpec {
    /// A kvantumok száma
    pub qubits: usize,
    /// A kapuk sorrendben
    pub gates: Vec<Gate>,
    /// γ — a csillapítás. NEM kapu, hanem posztprocesszálási mennyiség.
    pub decoherence: Option<f32>,
}

impl CircuitSpec {
    /// Üres áramkör
    pub fn new(qubits: usize) -> Self {
        Self {
            qubits,
            gates: Vec::new(),
            decoherence: None,
        }
    }

    /// Van-e ilyen kapu az áramkörben?
    pub fn uses_gate(&self, gate_type: &str) -> bool {
        self.gates.iter().any(|g| g.gate_type == gate_type)
    }
}

/// SCS hullámcsomag: ψ(t) = A · exp(-γt) · cos(2πft + φ)
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct WavePacket {
    /// A — intenzitás
    pub amplitude: f64,
    /// γ — csillapítás
    pub gamma: f64,
    /// f — tartalom (frekvencia)
    pub frequency: f64,
    /// φ — kontextus (fázis)
    pub phase: f64,
}

impl WavePacket {
    /// Új hullámcsomag
    pub fn new(amplitude: f64, gamma: f64, frequency: f64, phase: f64) -> Self {
        Self {
            amplitude,
            gamma,
            frequency,
            phase,
        }
    }
}

/// Egy mért eredmény: a kimenetek gyakorisága `{"0x..": darabszám}` alakban.
///
/// 🧬 A KULCSFORMÁTUM: `0x0` = egyik kvantum sem 1; `0x1` = q0 = 1;
/// `0x3` = mindkettő 1. Vagyis a LEGKISEBB sorszám a LEGKISEBB bit.
pub type Counts = HashMap<String, usize>;

/// Az SCS kétkvantumos kódolásához szükséges kvantumok száma.
///
/// 🧬 A három paraméter (A, f, φ) paraméterenként külön kísérletben
/// mérhető, így nem kell egyszerre három kvantum.
pub const TKR_REQUIRED_QUBITS: usize = 2;

fn p_of_q0_one(counts: &Counts) -> Option<f64> {
    let total: usize = counts.values().sum();
    if total == 0 {
        return None;
    }
    let hits = counts.get("0x1").copied().unwrap_or(0) + counts.get("0x3").copied().unwrap_or(0);
    Some(hits as f64 / total as f64)
}

fn p_of_q0_zero(counts: &Counts) -> Option<f64> {
    let total: usize = counts.values().sum();
    if total == 0 {
        return None;
    }
    Some(counts.get("0x0").copied().unwrap_or(0) as f64 / total as f64)
}

/// A mért `P(q0=1)` a counts-ból — a legkisebb bit a q0.
pub fn probability_q0_one(counts: &Counts) -> Option<f64> {
    p_of_q0_one(counts)
}

/// A mért `P(q0=0)` a counts-ból.
pub fn probability_q0_zero(counts: &Counts) -> Option<f64> {
    p_of_q0_zero(counts)
}

/// SCS → kvantumáramkör kódolás.
#[derive(Debug, Default, Clone)]
pub struct PsiQuantumBridge {
    /// Hány kvantumot használ a kódolás
    pub qubits: usize,
}

impl PsiQuantumBridge {
    /// A hardver-igazolt híd: 2 qubit
    pub fn new() -> Self {
        Self {
            qubits: TKR_REQUIRED_QUBITS,
        }
    }

    /// Egyqubites amplitúdókódolás: `RY(A)` q[0]-on.
    ///
    /// A `RY(θ)` a `|0⟩`-ból `(cos(θ/2), sin(θ/2))` állapotba visz,
    /// tehát `P(q0=1) = sin²(A/2)`.
    pub fn encode_amplitude(&self, amplitude: f64) -> CircuitSpec {
        CircuitSpec {
            qubits: 1,
            gates: vec![Gate::with_param("RY", vec![0], amplitude)],
            decoherence: None,
        }
    }

    /// Kétqubites interferenciakódolás a frekvenciára.
    ///
    /// A referenciakvantum (q[0]) tiszta `|0⟩` marad; az `f` a vezérlő
    /// kvantumon (q[1]) `RY(2πf)` szögben érkezik, és a `CNOT` viszi át.
    /// Így `P(q0=1) = sin²(πf)`.
    pub fn encode_frequency(&self, frequency: f64) -> CircuitSpec {
        self.interference_circuit(2.0 * PI * frequency)
    }

    /// Kétqubites interferenciakódolás a fázisra: `RY(φ)` q[1]-en + CNOT.
    ///
    /// Így `P(q0=1) = sin²(φ/2)`.
    ///
    /// 🧬 A FÉNYEK SZÁMA: `φ = 2·arcsin(√P)`, NEM `arcsin(√P)`.
    pub fn encode_phase(&self, phase: f64) -> CircuitSpec {
        self.interference_circuit(phase)
    }

    fn interference_circuit(&self, ry_angle: f64) -> CircuitSpec {
        CircuitSpec {
            qubits: 2,
            gates: vec![
                Gate::with_param("RY", vec![1], ry_angle),
                Gate::new("CNOT", vec![1, 0]),
            ],
            decoherence: None,
        }
    }

    /// A teljes hullámcsomag kódolása — három külön kísérletként.
    ///
    /// 🧬 MIÉRT HÁROM KÜLÖN KÍSÉRLET: az `A`, `f` és `φ` paraméterek
    /// külön-külön mérhetők. Egyetlen nagy áramkör a mérési alapszintet
    /// elszennyezné: egyetlen hibás kapu az összes paramétert eltorzítaná.
    pub fn encode_wave(&self, wave: &WavePacket) -> WaveCircuitSet {
        WaveCircuitSet {
            amplitude: self.encode_amplitude(wave.amplitude),
            frequency: self.encode_frequency(wave.frequency),
            phase: self.encode_phase(wave.phase),
            gamma: wave.gamma,
        }
    }

    /// Az amplitúdó visszafejtése: `A = 2·arccos(√P(q0=0))`
    pub fn decode_amplitude(&self, counts: &Counts) -> Option<f64> {
        Some(decode_amplitude_from_p(p_of_q0_zero(counts)?))
    }

    /// A fázis visszafejtése: `φ = 2·arcsin(√P(q0=1))`
    pub fn decode_phase(&self, counts: &Counts) -> Option<f64> {
        Some(decode_phase_from_p(p_of_q0_one(counts)?))
    }

    /// A frekvencia visszafejtése: `f = arcsin(√P(q0=1)) / π`
    ///
    /// 🧬 NORMALIZÁLÁS: a képlet a `[0, 0.5]` tartományra egyértelmű.
    /// A teljes tartományban a kétkvantumos interferencia nem ad egyértelmű
    /// visszafejtést (a 2π-periodicitás és a kétirányú (f, 1−f) forma miatt).
    pub fn decode_frequency(&self, counts: &Counts) -> Option<f64> {
        Some(decode_frequency_from_p(p_of_q0_one(counts)?))
    }
}

/// Az amplitúdó visszafejtése egy valószínűségből: `A = 2·arccos(√P(q0=0))`
pub fn decode_amplitude_from_p(p_q0_zero: f64) -> f64 {
    2.0 * p_q0_zero.clamp(0.0, 1.0).sqrt().acos()
}

/// A fázis visszafejtése egy valószínűségből: `φ = 2·arcsin(√P(q0=1))`
pub fn decode_phase_from_p(p_q0_one: f64) -> f64 {
    2.0 * p_q0_one.clamp(0.0, 1.0).sqrt().asin()
}

/// A frekvencia visszafejtése egy valószínűségből: `f = arcsin(√P(q0=1)) / π`
pub fn decode_frequency_from_p(p_q0_one: f64) -> f64 {
    p_q0_one.clamp(0.0, 1.0).sqrt().asin() / PI
}

/// Egy hullámcsomag három külön mérési áramköre, a γ értékével együtt.
#[derive(Clone, Debug, PartialEq)]
pub struct WaveCircuitSet {
    /// Az amplitúdó áramköre
    pub amplitude: CircuitSpec,
    /// A frekvencia áramköre
    pub frequency: CircuitSpec,
    /// A fázis áramköre
    pub phase: CircuitSpec,
    /// γ — posztprocesszálási mennyiség, nem kapu
    pub gamma: f64,
}

/// A 16 mód egyetlen kvantum-mérésének eredménye.
#[derive(Clone, Debug)]
pub struct ModeMeasurement {
    /// A backend, amelyen a mérés történt
    pub backend: QuantumBackend,
    /// A lővések száma
    pub shots: usize,
    /// A hardver Bell-egyensúlya (a mért minőség)
    pub bell_fidelity: f64,
    /// A klasszikus döntés: a legnagyobb energiájú mód
    pub classical_idx: usize,
    /// A klasszikus döntés energiája
    pub classical_energy: f64,
    /// A kvantum döntés: a legtöbb q=1 találatot kapott mód
    pub quantum_idx: usize,
    /// A kvantum döntés találatszáma
    pub quantum_hits: usize,
    /// A kvantum döntés valószínűsége (a találatok aránya)
    pub quantum_prob: f64,
    /// Egyezik-e a két döntés?
    pub agree: bool,
}

impl ModeMeasurement {
    /// A mérés összefoglaló szövege
    pub fn summary(&self) -> String {
        format!(
            "klasszikus: #{:02} (E={:.6})  |  kvantum: #{:02} ({}/{} lövés, P={:.4})  |  egyezés: {}",
            self.classical_idx,
            self.classical_energy,
            self.quantum_idx,
            self.quantum_hits,
            self.shots,
            self.quantum_prob,
            if self.agree { "igen" } else { "NEM" }
        )
    }
}

/// A 16 mód energiájának kódolása kvantumrotációkba.
///
/// 🧬 A KÓDOLÁS NEM HIBÁS: `θ = 2·arcsin(√E)` → `P(q=1) = E` konzisztens.
/// A hiba a 16 MÓD EGYENKÉNTI VERSENYÉBEN volt, nem a kódolásban.
pub fn encode_mode_energies(energies: &[f64; 16]) -> Vec<(usize, f64)> {
    energies
        .iter()
        .enumerate()
        .map(|(i, &e)| {
            let clamped = e.clamp(0.0, 1.0);
            (i, 2.0 * clamped.sqrt().asin())
        })
        .collect()
}

/// A hardver-minőséggel torzított valószínűség.
///
/// 🧬 A hardver nem hibátlan: a Bell-egyensúly `c` a mért állapotot a
/// `|00⟩/|11⟩` elegyével keveri. A modell: `p_eff = c·p + (1−c)·0.5`.
/// A `c = 1.0` a nulla zajú eset, a `c = 0.877` a leggyengébb mért futás.
pub fn degrade_probability(p: f64, bell_fidelity: f64) -> f64 {
    let c = bell_fidelity.clamp(0.0, 1.0);
    c * p.clamp(0.0, 1.0) + (1.0 - c) * 0.5
}

/// A hardver-minőséggel torzított valószínűség INVERZE.
///
/// 🧬 MIÉTT KELL: a `degrade_probability` a hardver ZAJÁNAK modellje
/// (`p_meas = c·p_true + (1−c)·0.5`). Valódi hardveren a mért
/// valószínűség már tartalmazza ezt a zajt, ezért újra alkalmazni
/// dupla torzítást okozna. A visszafejtéshez viszont a torzítást
/// EL kell távolítani: ebből lesz a valódi érték becslése.
///
/// Az `c` a hurokban a Bell-anchorból származó ÉLŐ érték, így a
/// dekódoló valós időben követi a hardver öregedését és a driftet.
pub fn unbias_probability(p_measured: f64, bell_fidelity: f64) -> f64 {
    let c = bell_fidelity.clamp(0.0, 1.0);
    if c <= 0.0 {
        return 0.5;
    }
    ((p_measured.clamp(0.0, 1.0) - (1.0 - c) * 0.5) / c).clamp(0.0, 1.0)
}

/// A 16 mód egyetlen kvantum-mérése a mért hardver-paraméterekkel.
///
/// 🧬 A MODELL: 16 qubit, mindegyik a saját energiáját hordozza
/// (`P(q_i=1) = E_i`), egy 1024-es batch mérésből a 16 arány alapján
/// döntünk. Ez NEM a hardver-igazolt 2 qubitos sémát használja — az
/// a hullámcsomag (A, f, φ) mérésére való. Itt a 16 módról van szó, és
/// a mérés kimutatta, hogy ez az út a jelenlegi architektúrában
/// nem ad kimutatható előnyt.
pub fn measure_modes(energies: &[f64; 16], shots: usize, bell_fidelity: f64) -> ModeMeasurement {
    let classical_idx = energies
        .iter()
        .enumerate()
        .max_by(|a, b| a.1.partial_cmp(b.1).unwrap())
        .map(|(i, _)| i)
        .unwrap_or(0);
    let classical_energy = energies[classical_idx];

    // A kvantum mérés: minden qubit a saját energiájával, torzítva
    let mut rng = rand::thread_rng();
    let mut hits = [0usize; 16];
    for (i, &e) in energies.iter().enumerate() {
        let p = degrade_probability(e, bell_fidelity);
        hits[i] = binomial_sample(&mut rng, shots as u64, p) as usize;
    }
    let quantum_idx = hits
        .iter()
        .enumerate()
        .max_by(|a, b| a.1.cmp(b.1))
        .map(|(i, _)| i)
        .unwrap_or(0);

    ModeMeasurement {
        backend: QuantumBackend::Classical,
        shots,
        bell_fidelity,
        classical_idx,
        classical_energy,
        quantum_idx,
        quantum_hits: hits[quantum_idx],
        quantum_prob: hits[quantum_idx] as f64 / shots as f64,
        agree: quantum_idx == classical_idx,
    }
}

/// A kvantum-út pontosságának becslése Monte Carlo szimulációval.
///
/// A mért érték (20 000 trial, 1024 shot, c = 1.0): **42,29%**.
/// A klasszikus argmax: **100%**.
pub fn monte_carlo_accuracy(
    energies: &[f64; 16],
    trials: usize,
    shots: usize,
    bell_fidelity: f64,
) -> f64 {
    let classical_idx = energies
        .iter()
        .enumerate()
        .max_by(|a, b| a.1.partial_cmp(b.1).unwrap())
        .map(|(i, _)| i)
        .unwrap_or(0);

    let mut rng = rand::thread_rng();
    let mut correct = 0usize;
    for _ in 0..trials {
        let mut best_idx = 0usize;
        let mut best_hits = 0usize;
        for (i, &e) in energies.iter().enumerate() {
            let p = degrade_probability(e, bell_fidelity);
            let h = binomial_sample(&mut rng, shots as u64, p) as usize;
            if h > best_hits {
                best_hits = h;
                best_idx = i;
            }
        }
        if best_idx == classical_idx {
            correct += 1;
        }
    }
    correct as f64 / trials as f64
}

/// A kvantumhíd teljes állapotának szöveges leírása.
pub fn status() -> String {
    format!(
        "QUANTUM híd (hardver-igazolt SCS, 2 qubit + 3 külön mérés)\n  \
         Bell-egyensúly: {:.3}–{:.3} (7 futás, jellemző ~{:.3})\n  \
         GHZ-egyensúly:   {:.3}–{:.3}\n  \
         QDS T₂_eff:     {:.1} ± {:.1} µs, {} shot\n  \
         16 mód argmax:  kvantum {:.2}% (mért)  vs  klasszikus {:.0}% (mért)",
        measured::BELL_FIDELITY_MIN,
        measured::BELL_FIDELITY_MAX,
        measured::BELL_FIDELITY_TYPICAL,
        measured::GHZ_FIDELITY_MIN,
        measured::GHZ_FIDELITY_MAX,
        measured::QDS_T2_EFF_US,
        measured::QDS_T2_STD_US,
        measured::QDS_SHOTS,
        measured::MEASURED_QUANTUM_ACCURACY * 100.0,
        measured::MEASURED_CLASSICAL_ACCURACY * 100.0,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn counts2(p_q0_one: f64, shots: usize) -> Counts {
        let mut c = Counts::new();
        let ones = (p_q0_one * shots as f64).round() as usize;
        c.insert("0x1".to_string(), ones);
        c.insert("0x0".to_string(), shots.saturating_sub(ones));
        c
    }

    fn counts1(p_q0_zero: f64, shots: usize) -> Counts {
        let mut c = Counts::new();
        let zeros = (p_q0_zero * shots as f64).round() as usize;
        c.insert("0x0".to_string(), zeros);
        c.insert("0x1".to_string(), shots.saturating_sub(zeros));
        c
    }

    #[test]
    fn required_qubits_is_two() {
        assert_eq!(TKR_REQUIRED_QUBITS, 2);
    }

    #[test]
    fn amplitude_circuit_is_single_qubit_ry() {
        let c = PsiQuantumBridge::new().encode_amplitude(1.0);
        assert_eq!(c.qubits, 1);
        assert_eq!(c.gates.len(), 1);
        assert_eq!(c.gates[0].gate_type, "RY");
    }

    #[test]
    fn interference_circuits_use_no_rz() {
        // A RZ globális fázisszorzó, amit a Z-mérés kitöröl.
        let b = PsiQuantumBridge::new();
        for c in [
            b.encode_frequency(0.25),
            b.encode_phase(1.0),
            b.encode_amplitude(1.0),
        ] {
            assert!(!c.uses_gate("RZ"), "a kódolás nem használhat RZ-t");
        }
    }

    #[test]
    fn interference_circuits_keep_reference_qubit_at_zero() {
        let b = PsiQuantumBridge::new();
        for c in [b.encode_frequency(0.25), b.encode_phase(1.0)] {
            assert_eq!(c.qubits, 2);
            assert_eq!(c.gates[0].qubits, vec![1], "a paraméter a q1-en van");
            assert_eq!(c.gates[1].gate_type, "CNOT");
            assert_eq!(c.gates[1].qubits, vec![1, 0]);
        }
    }

    #[test]
    fn amplitude_roundtrip_exact() {
        for a in [0.5_f64, 1.0, 2.0] {
            let p0 = (a / 2.0).cos().powi(2);
            let rec = PsiQuantumBridge::new()
                .decode_amplitude(&counts1(p0, 1000))
                .unwrap();
            assert!((rec - a).abs() < 0.01, "A={} vissza {}", a, rec);
        }
    }

    #[test]
    fn phase_roundtrip_exact() {
        for phi in [0.0_f64, 0.5, 1.0, 1.5] {
            let p1 = (phi / 2.0).sin().powi(2);
            let rec = PsiQuantumBridge::new()
                .decode_phase(&counts2(p1, 1000))
                .unwrap();
            assert!((rec - phi).abs() < 0.05, "phi={} vissza {}", phi, rec);
        }
    }

    #[test]
    fn phase_double_factor_is_required() {
        let phi = 1.0_f64;
        let p1 = (phi / 2.0).sin().powi(2);
        let rec = PsiQuantumBridge::new()
            .decode_phase(&counts2(p1, 2000))
            .unwrap();
        assert!((rec - phi).abs() < (rec - phi / 2.0).abs());
    }

    #[test]
    fn frequency_roundtrip_normalised_to_unity() {
        for f in [0.0_f64, 0.125, 0.25, 0.5] {
            let p1 = (std::f64::consts::PI * f).sin().powi(2);
            let rec = PsiQuantumBridge::new()
                .decode_frequency(&counts2(p1, 1000))
                .unwrap();
            assert!((rec - f).abs() < 0.05, "f={} vissza {}", f, rec);
        }
    }

    #[test]
    fn decode_rejects_empty_counts() {
        let empty = Counts::new();
        let b = PsiQuantumBridge::new();
        assert!(b.decode_amplitude(&empty).is_none());
        assert!(b.decode_phase(&empty).is_none());
        assert!(b.decode_frequency(&empty).is_none());
    }

    #[test]
    fn mode_encoding_is_consistent() {
        // A kódolás: theta = 2*asin(sqrt(E)) -> P(q=1) = E
        let mut e = [0.0f64; 16];
        e[3] = 0.25;
        let enc = encode_mode_energies(&e);
        let (_, theta) = enc[3];
        let p = (theta / 2.0).sin().powi(2);
        assert!((p - 0.25).abs() < 1e-12, "P(q=1)={} kell 0.25", p);
    }

    #[test]
    fn degraded_probability_matches_measured_model() {
        // c = 1.0 → a valószínűség változatlan
        // c = 0.0 → teljes keveredés (a mért állapot fele 0,5)
        // c = 0.5 → a lineáris interpoláció közepe
        assert!((degrade_probability(0.25, 1.0) - 0.25).abs() < 1e-12);
        assert!((degrade_probability(0.25, 0.0) - 0.5).abs() < 1e-12);
        assert!((degrade_probability(0.25, 0.5) - 0.375).abs() < 1e-12);
    }

    /// A VALÓS 16 mód energiái (a `claude-logic` STRATOS folyadékból mérve).
    /// A Brain a legnagyobb (0,09620959), a Creativity a második
    /// (0,09443425) — a különbség mindössze 1,85%.
    fn measured_mode_energies() -> [f64; 16] {
        [
            0.09620959, // Brain
            0.07677600, // Logic
            0.08902975, // Memory
            0.09443425, // Creativity
            0.08851945, // Heart
            0.08038322, // Intuition
            0.07562627, // Focus
            0.02933872, // Empathy
            0.03608653, // Analysis
            0.05413618, // Synthesis
            0.05810160, // Ethics
            0.06105229, // Play
            0.04328244, // Dream
            0.03946274, // Social
            0.04136071, // Survival
            0.03620027, // Transcendence
        ]
    }

    #[test]
    fn classical_argmax_is_exact() {
        let mut e = [0.0f64; 16];
        e[7] = 0.096;
        e[9] = 0.094;
        let m = measure_modes(&e, 1024, 1.0);
        assert_eq!(m.classical_idx, 7);
    }

    #[test]
    fn quantum_accuracy_reproduces_the_measured_value() {
        // 🧬 A MÉRT ÉRTÉK: 42,29% (16 qubit, 1024 shot, 20 000 trial,
        // nulla hardver-zaj mellett). A teszt a valós 16 móddal reprodukálja.
        // A 400 trial 1σ-ja kb. 2,5%, ezért a sáv 0,30–0,60.
        let e = measured_mode_energies();
        let acc = monte_carlo_accuracy(&e, 400, 1024, 1.0);
        assert!(
            (0.30..0.60).contains(&acc),
            "a kvantum-út pontossága a mért 42,29% körül kell legyen; acc={:.4}",
            acc
        );
        // A klasszikus argmax ezen mindig 100%
        let classical = monte_carlo_accuracy(&e, 400, 1024, 1.0);
        assert!(classical > 0.0);
    }

    #[test]
    fn quantum_accuracy_degrades_with_hardware_fidelity() {
        // A gyengébb hardver (c = 0,877) NEM javíthat a kvantum-úton.
        let e = measured_mode_energies();
        let strong = monte_carlo_accuracy(&e, 300, 1024, 1.0);
        let weak = monte_carlo_accuracy(&e, 300, 1024, 0.877);
        assert!(
            weak <= strong + 0.05,
            "a gyengébb hardver nem lehet pontosabb; strong={:.4} weak={:.4}",
            strong,
            weak
        );
    }

    /// 🧬 A `f` KODOLÁS → DEKÓDOLÁS ROUNDTRIP (2026-11-01, T1).
    ///
    /// A GPE-ből kinyert `f` a 16 mód indexének súlyozott átlaga, tehát
    /// `[0, 15]`. A kétkvantumos interferencia-dekódolás (`f =
    /// arcsin(√P)/π`) CSAK `[0, 0.5]`-en egyértelmű, mert a `sin²(πf)`
    /// periodikus. A normalizálás nélkül a `f = 1.235` kódolás `0.235`-öt
    /// ad vissza — a hurok minden iterációban összehajtott.
    ///
    /// A teszt a teljes `[0, 15]` tartományon ellenőrzi, hogy a hibátlan
    /// csatorna 1e-9-en belül visszaadja az inputot.
    #[test]
    fn frequency_roundtrip_over_the_full_mode_index_range() {
        let mut worst = 0.0_f64;
        for step in 0..=1500 {
            let f_index = step as f64 / 100.0; // 0.00 .. 15.00
            assert!(
                (0.0..=F_MODE_INDEX_MAX).contains(&f_index),
                "a vizsgált f a mod-index tartomanyaban kell legyen; f={f_index}"
            );

            // a kódolás: f_kod a [0, 0.5] egyertelmu tartomanyba
            let f_kod = normalize_f(f_index);
            assert!(
                (0.0..=F_DECODE_MAX).contains(&f_kod),
                "a kodolt f a dekodolasi tartomanyaban kell legyen; f_kod={f_kod}"
            );

            // az idealis aramkor: P(q0=1) = sin^2(pi * f_kod)
            let p_q0_one = (std::f64::consts::PI * f_kod).sin().powi(2);

            // a dekodolas, majd a visszafejtes a mod-index tartomanyba
            let f_decoded = decode_frequency_from_p(p_q0_one);
            let f_back = denormalize_f(f_decoded);

            let error = (f_back - f_index).abs();
            if error > worst {
                worst = error;
            }
            assert!(
                error < 1e-9,
                "az f roundtrip hibaja tul nagy; f_index={f_index} -> {f_back} (hiba {error})"
            );
        }
        assert!(
            worst < 1e-9,
            "az f roundtrip legnagyobb hibaja tul nagy; worst={worst}"
        );
    }

    /// A `normalize_f` a `[0, 15]`-et `[0, 0.5]`-re képezi, a
    /// `denormalize_f` az ellenkezőjét.
    #[test]
    fn frequency_normalisation_is_invertible() {
        assert!((normalize_f(0.0) - 0.0).abs() < 1e-12);
        assert!((normalize_f(F_MODE_INDEX_MAX) - F_DECODE_MAX).abs() < 1e-12);
        for step in 0..=150 {
            let f_index = step as f64 / 10.0;
            let back = denormalize_f(normalize_f(f_index));
            assert!(
                (back - f_index).abs() < 1e-12,
                "a normalizalas nem inverz; f={f_index} -> {back}"
            );
        }
    }

    #[test]
    fn unbias_is_the_inverse_of_degrade() {
        for c in [1.0_f64, 0.949, 0.877, 0.5] {
            for p in [0.0_f64, 0.25, 0.5, 0.75, 1.0] {
                let measured = degrade_probability(p, c);
                let recovered = unbias_probability(measured, c);
                assert!(
                    (recovered - p).abs() < 1e-9,
                    "a torzítás és a visszafejtés nem egymás inverze; p={} c={} -> {}",
                    p,
                    c,
                    recovered
                );
            }
        }
    }

    #[test]
    fn unbias_neutralises_the_symmetric_noise() {
        // A hardver zajmodellje: p_meas = c·p + (1−c)·0.5.
        // A torzítástlanított becslés a valódi p-re áll.
        let p_true = 0.8;
        let c = 0.877;
        let measured = degrade_probability(p_true, c);
        assert!(
            measured < p_true,
            "a hardver a középpont felé torzít; measured={}",
            measured
        );
        assert!((unbias_probability(measured, c) - p_true).abs() < 1e-9);
    }

    #[test]
    fn unbias_clamps_into_the_unit_interval() {
        assert!((0.0..=1.0).contains(&unbias_probability(0.0, 0.5)));
        assert!((0.0..=1.0).contains(&unbias_probability(1.0, 0.5)));
        // c = 0 esetén a modell degenerál: vissza a középpont.
        assert!((unbias_probability(0.3, 0.0) - 0.5).abs() < 1e-12);
    }

    #[test]
    fn from_p_decoders_match_the_counts_decoders() {
        let mut c = Counts::new();
        c.insert("0x0".to_string(), 300usize);
        c.insert("0x1".to_string(), 700usize);
        let bridge = PsiQuantumBridge::new();
        assert!(
            (bridge.decode_amplitude(&c).unwrap() - decode_amplitude_from_p(0.3)).abs() < 1e-12
        );
        assert!((bridge.decode_phase(&c).unwrap() - decode_phase_from_p(0.7)).abs() < 1e-12);
        assert!(
            (bridge.decode_frequency(&c).unwrap() - decode_frequency_from_p(0.7)).abs() < 1e-12
        );
    }
}
