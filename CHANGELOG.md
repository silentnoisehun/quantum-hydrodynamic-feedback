# Changelog

## [0.2.2] — 2026-11-01

The audit behind this release measured which claims the repository's own data
support. Four of them did not hold, and this release removes them.

### Fixed

- **The frequency channel was encoded on an ambiguous range**
  (`scripts/quantum_loop_sim.py`, `scripts/quantum_loop_hardware.py`,
  `crates/quantum-bridge/src/lib.rs`): `f` is an energy-weighted average of
  the 16 mode indices and lives in [0, 15], but the two-qubit decode
  `f = arcsin(√P)/π` is only unambiguous on [0, 0.5]. The encoded value was
  `0.5·f` without normalising, so every value above 0.5 folded back.
  Measured on the raw hardware files: the encoded f was 1.24–3.81 and
  **111 of 111 iterations folded back**. The feedback scale was wrong in a
  second way: the classical branch fed the raw mode index while the quantum
  branch fed `f_back/0.5`, so the two branches drove the fluid on different
  scales and their difference did not measure the quantum channel.
- **The amplitude channel decoded the wrong probability**
  (`scripts/quantum_loop_sim.py`): it used `2·arccos(√(1−P(q₀=0)))`, that
  is P(q₀=1), where the hardware bridge uses `2·arccos(√P(q₀=0))`. Because
  RY(θ) sends |0⟩ to (cos(θ/2), sin(θ/2)), decoding from P(q₀=1) returns
  π−θ, so the simulator fed the amplitude back inverted, 1−A instead of A.
  Measured on the 111 recorded amplitude count sets: the bridge convention
  reproduces the stored `decoded_raw.A` to 4.9e-11 (the CLI's print
  precision), the Python convention is off by 2.0–2.7. The frequency and
  phase channels were already lossless (1.5e-12 and 4.0e-13).
- **The classical control branch started from a different seed**
  (`scripts/quantum_loop_sim.py`, `scripts/quantum_loop_hardware.py`): it
  ran with `seed + 1`, so a difference between the two branches could come
  from the changed initial state as well as from the quantum channel.
- **The Bell-reference quantity was named fidelity**
  (`crates/quantum-bridge/src/bin/bridge-cli.rs`): it is the parity
  population P(00)+P(11), the agreement rate of the two bits, not a
  coherence fidelity. Renamed to `bell-parity`, with `bell-fidelity` kept as
  a deprecated alias. The `--correct` flag is now off by default, because
  the measurement shows the symmetric correction makes the amplitude
  channel worse (raw error 0.026, "corrected" 0.212).

### Added

- **`scripts/control_comparison.py`** — the control comparison that answers
  whether the quantum feedback causes the mode switching. The branches: the
  noise-free classical control, the noise-free quantum channel, the
  measured-`c` and the hardware-floor noise models at 10 and 1024 shots, and
  a replay of the hardware's own recorded feedback with ≥200 permutations.
  200 noise seeds per branch, 30 varying initial states, both hardware run
  lengths, and both the corrected and the pre-fix solver. Output in
  `measurement_cpu/control_comparison.json` and
  `docs/MEASUREMENTS-CPU-CONTROLS.txt`.
- **`scripts/legacy/quantum_loop_sim_a72ead4.py`** and
  **`scripts/replay_hardware_log.py`** — the replay that proves which solver
  produced the recorded hardware runs. The legacy solver reproduces their
  mode sequences exactly (20/20, 20/20, 68/68); the corrected solver
  reproduces none of them (7/20, 4/20, 26/68). It is a CI gate: the exit
  code is non-zero if the legacy solver stops reproducing the log, or if the
  corrected one starts reproducing it.
- **`scripts/test_quantum_loop_sim.py`** — the channel-convention regression
  tests, pinned to the recorded hardware data.
- **`docs/QPU-RUN-DECISION-RULE.txt`** — the pre-registered rule that
  decides whether a new QPU run is allowed at all, written before any run.
- **`measurement_cpu/`** — the CPU-side measurements are version controlled,
  so the numbers the paper quotes are traceable the same way the `docs/`
  numbers are.

### CI

- **The numpy version is pinned in the measurement job.** Measured on
  2026-11-01 in isolated environments: the 1000 iteration simulation
  produces a byte identical result under numpy 2.4.6 (what Python 3.11
  resolves to) and numpy 2.5.4, but not under numpy 1.26.4 — numpy's
  `Generator.binomial` stream differs between the 1.x and the 2.x line.
  The CI gate compares the regenerated file with the committed one byte
  by byte, so without the pin a numpy release could break the build for
  a third party reason.

### Changed

- **The claim that the quantum feedback causes the mode switching is
  withdrawn.** The control comparison measures it: with the hardware's own
  recorded feedback replayed at the corrected frequency scale, the mode
  pattern lands inside the band that measurement noise alone produces, on
  all four statistics, for all three hardware runs. The multi-mode pattern
  of the 2026-10-27 runs was produced by the frequency-scale defect, not by
  the quantum channel.
- **The paper's CPU figures are recomputed.** The amplitude fix changed
  them: the quantum branch's marginal concentration is 0.2198 against the
  classical branch's 0.0993 (was 0.5268), the total-variation distance is
  0.0970 (was 0.3730), and the separation is ~6σ (was ~22σ).
- **The hardware report's numbers are corrected**
  (`docs/MEASUREMENTS-HARDWARE-20261027.txt`): the 20-iteration run visited
  5 modes, not 6; the second 20-iteration run (20261027T015558Z, 3 modes)
  is included; the quota consumed at the end of the campaign was 587 of
  600 s, not 525; the 68-iteration run was planned for 100 iterations,
  stopped at 68, and has no classical control.
- **The account identifiers are removed** from `docs/` and the paper. The
  three raw `measurement_raw/loop_summary_*.json` files still carry the
  instance identifiers: the raw files are immutable by rule, and the
  consequence is stated rather than hidden.
- **The README and the paper gained explicit limits**: the frequency channel
  is unambiguous only on [0, 0.5]; the two-qubit encoding carries no
  information beyond the one-qubit form; and A, f and φ are the same
  measurement, so the "phase" is a rotation angle, not a quantum phase.

### Measured

- The noise-free quantum channel produces the same mode sequence as the
  classical control with the corrected solver. The difference between the
  branches is the measurement noise, not the structure of the channel.
- Measurement noise destroys structure rather than creating it: at 20
  iterations the noise-free control visits 3 modes (Brain 0.35, H/Hmax
  0.395), while every noisy branch concentrates on a single mode (Brain
  0.85–0.95, H/Hmax 0.07–0.19).
- The recorded feedback of the hardware runs, at the frequency scale the
  hardware actually used, is outside the noise band on all four
  statistics; at the corrected scale it is inside on all four.
- The full git history (33 commits, 413 objects) was scanned for IBM API
  keys: none is present. No key rotation is required.

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
