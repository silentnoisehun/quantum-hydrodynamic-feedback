# Changelog

## [0.2.1] — 2026-10-31

### Fixed

- **Local damping in GPE solver** (`crates/fluid-stratos/src/gpe.rs`): the
  dissipative term is now `exp(-γ·dt·|ψ|²)` (local, density-dependent) instead
  of the global `exp(-γ·dt)` scalar which was a no-op after normalization.
  This makes the γ parameter actually affect the dynamics. The fix is
  documented in `gpe.rs` lines 285–290 and 388–408.

## [0.2.0] — 2026-10-27

### Added

- **The quantum–classical loop on a real QPU** (`scripts/quantum_loop_hardware.py`),
  with the three layers: the three circuits of an iteration bundled into
  one job, a Runtime Session when the plan allows it, and a live Bell
  anchor that refreshes the measured hardware quality `c`.
- **`crates/quantum-bridge/src/bin/bridge-cli.rs`** — the decoding lives in
  Rust and is callable from the loop script, so the mathematics has one
  source. It also computes the ideal decode (`ideal-wave`), which is the
  correct baseline for the decoding error.
- **The raw measurement files are version controlled** (`measurement_raw/`),
  so every number quoted in `docs/` can be traced back to the run it came
  from. `scripts/summarize_hardware_run.py` recomputes the summary from
  them, and the CI checks that the files stay readable.
- A measurement report for the hardware run:
  `docs/MEASUREMENTS-HARDWARE-20261027.txt`, with the run logs in
  `docs/RUNLOG-*.txt`.

### Measured on ibm_fez (156 qubit, 1024 shots)

- **The hardware quality `c` measured live**: 0.9170–0.9531, mean 0.9350
  over 14 anchors, a drift of +0.0361. It tracks the reference value of
  0.949 without being told it.
- **The loop visits 7 of the 16 modes** over 68 iterations (the histogram
  is [27, 4, 3, 0, 0, 0, 9, 10, 0, 0, 0, 0, 0, 0, 6, 9]) — the trajectory
  is structured, not collapsed into a single mode.
- **The 16-mode argmax on hardware: 0/6 = 0.00%** — the quantum path
  never reproduced the classical winner (Brain); the winners were
  Creativity (4×) and Logic (2×). Consistent with the simulated 38.65%
  at the same Bell fidelity ((1−0.3865)⁶ = 5.3%).
- **The decoding is accurate without a correction**: the amplitude
  channel's mean absolute error is 0.026 with a mean signed error of
  +0.0125 (i.e. unbiased within the shot noise).
- **The `c` correction is not a general improvement.** Feeding the live
  `c` back into the decoder as an inverse-noise correction raises the
  amplitude error to 0.212 with a mean signed error of −0.212. A
  deterministic check shows why: the correction already breaks an
  *error-free* measurement (A_kod = 0.3 → error −0.300, saturated). The
  real hardware noise is asymmetric, so the symmetric
  `p = c·p + (1−c)·0.5` model does not hold. The live `c` is a quality
  indicator, not a decoder correction.
- **The open plan refuses sessions** ("not authorized to run a session
  when using the open plan"), so the queue wait had to be measured
  instead of assumed: 6.8 s to 137.5 s per iteration.

### Corrected numbers (post-review)

The external review corrected the Python fluid port's split-step operator
(`fft → KPH → ifft` instead of double `ifft` without forward). The Rust
crate was never affected. The corrected numbers in the paper supersede
the earlier ones:

- max |Δ| density: **2.780** (was 2.766)
- 16-mode energy motion: **9.420** (was 8.444)
- H/Hmax (quantum branch): **0.5268** (was 0.4355)
- TV distance (quantum vs classical): **0.3730** (was 0.2960)
- Classical control: **968/1000** in one mode + 5 others (was "1000/1000 single mode")

### Known limitations

The 1000-iteration protocol is **not runnable on the open plan**: at the
measured 2.96 s of QPU time per iteration it needs ~2960 s against a
600 s quota, and without a session each iteration also waits in the
queue. A plan instance that allows sessions is required for the full
protocol. The report states this as measured, not as an estimate.

## [0.1.0] — 2026-10-27

### Added

- **`crates/fluid-stratos`** — a Gross-Pitaevskii fluid solver for 16 cognitive
  modes with a **real split-step Fourier** kinetic step (row + column
  transforms). The previous implementation used a phase rotation in index
  space with no transform at all, which made the density distribution
  mathematically invariant (measured: max |Δ| = O(1e-13) over 500 steps, γ=0).
  After the fix with local damping (γ=0.002): max |Δ| = **2.780**, a 79×
  improvement over the γ=0.002 dead baseline (the γ=0 dead code was already
  invariant at O(1e-13); the γ=0 baseline ratio is 2.0e13×).
- Three regression tests that **fail on the pre-fix code**:
  the density distribution must move, the 16 mode energies must change,
  and the normalization must hold across FFT steps.
- **`crates/quantum-bridge`** — the hardware-verified quantum bridge:
  2 qubits + 3 separate measurements (A, f, φ), with the decoding formulas
  and the prohibition on `RZ` encoding. Includes the measured hardware
  parameters (Bell fidelity 87.7–99.3%, QDS T₂ = 89.6 ± 39.2 µs).
- A measurement of the 16-mode argmax via the quantum path:
  **38.65%** at Bell c = 0.949 versus **100%** for the classical argmax —
  the difference is 0.137σ and therefore not detectable at 1024 shots.
- **Quantum–classical loop simulation** (`scripts/quantum_loop_sim.py`) with
  four branches: quantum loop, classical control, uniform null model, and
  the dead GPE. **Corrected** H/Hmax: 0.5268 / 0.0000 / 0.9962 / 0.0000
  (was 0.4355 / 0.0000 / 0.9962 / 0.0000).
- Measurement reports in `docs/`.

### Fixed

- The parallel solver carried the same phase-rotation defect as the serial
  one.
- The solver synchronization copied only the scalar fields across after a
  parallel step, so the wavefunction went stale and the 16 mode energies
  would have stayed static.
- The binomials sampler used a uniform variate where a normal variate was
  required, biasing the measured accuracy from 38.65% to ~69%.

### Known limitations

See section 4 ("Limits") of the README. In short: no proof of emergent
intelligence, the histogram test requires the classical control to avoid a
false positive, and the 16-mode argmax is not detectable via the quantum
path with the measured hardware parameters.
