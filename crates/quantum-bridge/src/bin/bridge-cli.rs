//! A quantum-bridge parancssori felülete.
//!
//! 🧬 MIÉTT VAN: a Python hurok-szkript a valós hardveren mért
//! `(A, f, φ)` értékeket dekódolja vissza. A dekódolás matematikája
//! EGYETLEN forrásból kell jöjjön — a Rust kőnyvtárból.
//!
//! 🧬 A `--correct` ALAPBÓL KI (2026-11-01, T4): a mért hardver-zaj
//! aszimmetrikus, ezért a szimmetrikus `c`-korrekció a dekódolást
//! RONTJA (a mért nyers A-hiba 0.026 volt, a "korrigált" 0.212). A `c`
//! (a Bell-anchor paritáspopulációja) csak MINŐSÉG-INDIKÁTOR.

use quantum_bridge::measured::{BELL_PARITY_MAX, BELL_PARITY_MIN, BELL_PARITY_TYPICAL};
use quantum_bridge::{
    decode_amplitude_from_p, decode_frequency_from_p, decode_phase_from_p, degrade_probability,
    probability_q0_one, probability_q0_zero, unbias_probability, Counts, QuantumBackend,
};
use std::collections::HashMap;
use std::env;
use std::process;

fn usage() {
    println!(
        "bridge-cli — a quantum-bridge dekódoló felülete\n\
         \n\
         decode-wave --amplitude-counts C --frequency-counts C --phase-counts C\n\
         \x20             [--parity C] [--correct]\n\
         \x20   A visszafejtett értékek: A_n f_n phi_n, majd A_c f_c phi_c.\n\
         \x20   A --correct a --parity értékkel torzítástlanít (opcionális,\n\
         \x20   a valós hardveren NEM ajánlott: a zaj aszimmetrikus).\n\
         \n\
         decode --kind amplitude|frequency|phase --counts C [--parity C] [--correct]\n\
         degrade --p P --parity C\n\
         unbias  --p P --parity C\n\
         bell-parity --counts C\n\
         status\n\
         \n\
         A counts formátuma: 0x0:512,0x1:488\n\
         \n\
         ELAVULT (deprecated alias): bell-fidelity, --fidelity"
    );
}

/// A counts megadása: "0x0:512,0x1:488" → a kulcsok egységes "0xN" alakban.
fn parse_counts(spec: &str) -> Result<Counts, String> {
    let mut out: Counts = HashMap::new();
    for part in spec.split(',') {
        let part = part.trim();
        if part.is_empty() {
            continue;
        }
        let (key, value) = part
            .split_once(':')
            .ok_or_else(|| format!("hibás counts elem: {part}"))?;
        let key = key.trim();
        let n = match key.strip_prefix("0x").or_else(|| key.strip_prefix("0X")) {
            Some(hex) => {
                u64::from_str_radix(hex, 16).map_err(|_| format!("nem hex counts kulcs: {key}"))?
            }
            None => u64::from_str_radix(key, 2)
                .map_err(|_| format!("nem bináris counts kulcs: {key}"))?,
        };
        let count: usize = value
            .trim()
            .parse()
            .map_err(|_| format!("nem szám a counts értékben: {value}"))?;
        *out.entry(format!("0x{n:x}")).or_insert(0) += count;
    }
    if out.is_empty() {
        return Err("üres counts".to_string());
    }
    Ok(out)
}

fn flag(flags: &HashMap<String, String>, name: &str) -> Result<String, String> {
    flags
        .get(name)
        .cloned()
        .ok_or_else(|| format!("hiányzó argumentum: --{name}"))
}

/// A `c` (paritáspopuláció) értéke: `--parity` az új név, `--fidelity` a
/// deprecated alias. Ha egyik sincs megadva, nincs korrekció.
fn parity_flag(flags: &HashMap<String, String>) -> Result<f64, String> {
    if let Some(raw) = flags.get("parity") {
        return raw
            .trim()
            .parse::<f64>()
            .map_err(|_| format!("nem szám: --parity {raw}"));
    }
    if let Some(raw) = flags.get("fidelity") {
        eprintln!(
            "bridge-cli: figyelem: --fidelity elavult alias, hasznald --parity-t. \
             A 'fidelity' elnevezés pontatlan: ez PARITÁSPOPULÁCIÓ (P(00)+P(11)), \
             nem koherencia-fidelity."
        );
        return raw
            .trim()
            .parse::<f64>()
            .map_err(|_| format!("nem szám: --fidelity {raw}"));
    }
    Err("hiányzó argumentum: --parity C".to_string())
}

fn number(flags: &HashMap<String, String>, name: &str) -> Result<f64, String> {
    let raw = flag(flags, name)?;
    raw.trim()
        .parse::<f64>()
        .map_err(|_| format!("nem szám: --{name} {raw}"))
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.is_empty() {
        usage();
        process::exit(1);
    }

    let command = args[0].clone();
    let mut flags: HashMap<String, String> = HashMap::new();
    let mut correct = false;
    let mut i = 1;
    while i < args.len() {
        let arg = args[i].clone();
        if arg == "--correct" {
            correct = true;
            i += 1;
        } else if let Some(name) = arg.strip_prefix("--") {
            if i + 1 >= args.len() {
                eprintln!("hiányzó érték: {arg}");
                process::exit(2);
            }
            flags.insert(name.to_string(), args[i + 1].clone());
            i += 2;
        } else {
            eprintln!("ismeretlen argumentum: {arg}");
            process::exit(2);
        }
    }

    let result = run(&command, &flags, correct);
    match result {
        Ok(text) => println!("{text}"),
        Err(message) => {
            eprintln!("bridge-cli: {message}");
            process::exit(2);
        }
    }
}

fn run(command: &str, flags: &HashMap<String, String>, correct: bool) -> Result<String, String> {
    match command {
        "status" => Ok(format!(
            "bell-parity: {:.3} (tipikus) | {:.3}-{:.3} (mért tartomány)\n{}",
            BELL_PARITY_TYPICAL,
            BELL_PARITY_MIN,
            BELL_PARITY_MAX,
            QuantumBackend::IbmEagle.status()
        )),
        "bell-parity" | "bell-fidelity" => {
            if command == "bell-fidelity" {
                eprintln!(
                    "bridge-cli: figyelem: a 'bell-fidelity' parancs elavult alias, \
                     használd a 'bell-parity'-t. Ez a paritáspopuláció \
                     (P(00)+P(11)), NEM koherencia-fidelity."
                );
            }
            let counts = parse_counts(&flag(flags, "counts")?)?;
            let total: usize = counts.values().sum();
            if total == 0 {
                return Err("üres counts".to_string());
            }
            // A Bell-állapot a |00⟩ és |11⟩ felé kerül → a két bit egyezik.
            // 🧬 Ez PARITÁSPOPULÁCIÓ, nem fidelity: a koherenciát nem méri.
            let balance =
                counts.get("0x0").copied().unwrap_or(0) + counts.get("0x3").copied().unwrap_or(0);
            Ok(format!("{:.10}", balance as f64 / total as f64))
        }
        "ideal-wave" => {
            // 🧬 A HIBAMÉRTÉK BÁZISA: az IDEÁLIS visszafejtett érték.
            // Az `f` csatorna modul 1 szerint összefügg (a sin² periodikus),
            // ezért a nyers kódolt érték NEM a helyes bázis — az, amit az
            // ideális áramkör adna vissza. A `A` és a `φ` involúciós, azoknál
            // a bázis megegyezik a kódolt értékkel.
            let a = number(flags, "amplitude")?;
            let f = number(flags, "frequency")?;
            let phi = number(flags, "phase")?;
            Ok(format!(
                "{:.10} {:.10} {:.10}",
                decode_amplitude_from_p((a / 2.0).cos().powi(2)),
                decode_frequency_from_p((std::f64::consts::PI * f).sin().powi(2)),
                decode_phase_from_p((phi / 2.0).sin().powi(2))
            ))
        }
        "degrade" => {
            let p = number(flags, "p")?;
            let c = parity_flag(flags)?;
            Ok(format!("{:.10}", degrade_probability(p, c)))
        }
        "unbias" => {
            let p = number(flags, "p")?;
            let c = parity_flag(flags)?;
            Ok(format!("{:.10}", unbias_probability(p, c)))
        }
        "decode" => {
            let kind = flag(flags, "kind")?;
            let counts = parse_counts(&flag(flags, "counts")?)?;
            let (raw, corrected) = decode_one(&kind, &counts, flags, correct)?;
            Ok(format!("{raw:.10} {corrected:.10}"))
        }
        "decode-wave" => {
            let a_counts = parse_counts(&flag(flags, "amplitude-counts")?)?;
            let f_counts = parse_counts(&flag(flags, "frequency-counts")?)?;
            let p_counts = parse_counts(&flag(flags, "phase-counts")?)?;
            let (a_raw, a_cor) = decode_one("amplitude", &a_counts, flags, correct)?;
            let (f_raw, f_cor) = decode_one("frequency", &f_counts, flags, correct)?;
            let (p_raw, p_cor) = decode_one("phase", &p_counts, flags, correct)?;
            Ok(format!(
                "{a_raw:.10} {f_raw:.10} {p_raw:.10} {a_cor:.10} {f_cor:.10} {p_cor:.10}"
            ))
        }
        "help" | "--help" | "-h" => {
            usage();
            Ok(String::new())
        }
        other => Err(format!("ismeretlen parancs: {other}")),
    }
}

/// Egy paraméter visszafejtése: (nyers, torzítástlanított).
fn decode_one(
    kind: &str,
    counts: &Counts,
    flags: &HashMap<String, String>,
    correct: bool,
) -> Result<(f64, f64), String> {
    let p_zero = probability_q0_zero(counts).ok_or("üres counts")?;
    let p_one = probability_q0_one(counts).ok_or("üres counts")?;

    let raw = match kind {
        "amplitude" => decode_amplitude_from_p(p_zero),
        "frequency" => decode_frequency_from_p(p_one),
        "phase" => decode_phase_from_p(p_one),
        other => return Err(format!("ismeretlen paraméter: {other}")),
    };

    if !correct {
        return Ok((raw, raw));
    }

    let c = parity_flag(flags)?;
    let corrected = match kind {
        "amplitude" => decode_amplitude_from_p(unbias_probability(p_zero, c)),
        "frequency" => decode_frequency_from_p(unbias_probability(p_one, c)),
        _ => decode_phase_from_p(unbias_probability(p_one, c)),
    };
    Ok((raw, corrected))
}
