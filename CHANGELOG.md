# Changelog

## [0.2.3] — 2026-11-02

A second hardware campaign on a fourth account, and the audit of the rule that
authorised it. The audit changes the answer: **the trigger does not fire.**

### Fixed

- **The `hardware_permuted` arm of the varying-initial-state round ran on the
  wrong hardware run** (`scripts/control_comparison.py`): in `build_tasks` the
  block that appends the permuted-feedback arms was indented one level out of
  the `for hw in HARDWARE_RUNS` loop, so it used the **leaked** loop variable —
  the last entry of `HARDWARE_RUNS` — instead of the run being iterated. Two
  measured consequences: (1) in the committed 20-iteration section the arm
  `hardware_permuted_20261027T003737Z` replayed the **68-iteration** run's
  feedback truncated to 20 iterations, a bogus arm that has no counterpart in
  the fixed-initial-state round, while the two genuine 20-run permuted arms
  were missing from that round; (2) at 100 iterations the 68-entry feedback
  list was indexed past its end and `IndexError: list index out of range`
  killed the whole 13 377-run comparison at about 6 200 runs. The block is
  now inside the loop, and `run_task` raises a descriptive error
  (`_require_length`) instead of an `IndexError` if a list is ever too short.
- **The per-iteration QPU time was silently zero**
  (`scripts/quantum_loop_hardware.py`): `job.usage()` is not yet available
  when `result()` returns. Measured on a 2-iteration smoke test: both
  iterations recorded 0.0 s while the account quota showed exactly 6.0 s
  (2 × 3.0 s) — the zero was the API's availability, not the measurement. The
  new `job_qpu_seconds()` polls until a positive value appears, so the
  per-iteration QPU time stays traceable in the raw files.
- **The replay gate assumed every run was made with the legacy solver**
  (`scripts/replay_hardware_log.py`): the expectation is now per run. The
  three 2026-10-27 runs were made with the legacy solver, the 2026-11-02 run
  with the corrected one. Measured on the new run's first 10 iterations: the
  corrected solver reproduces the logged mode sequence **10/10**, the legacy
  solver only 2/10.

### Changed

- **The decision rule is amended, dated and BEFORE the run**
  (`docs/QPU-RUN-DECISION-RULE.txt`, new point 0): a measurement may now
  consist of the registered 20–30 iterations **plus one 100-iteration run**.
  The justification as it stood on 2026-11-01 was measured: the trigger
  (M1/M2 outside the `true_residual_permuted` band) fired only for the
  68-iteration hardware run, and the 20-iteration cases are inside the band,
  so a 20–30 iteration run cannot answer the question the rule asks. 100
  iterations is also the *designed* length of the 2026-10-27 run (the RUNLOG
  shows `iter N/100`), so this completes the original protocol rather than
  inventing a new one. The amendment caps the deviation: the quota gate must
  pass before the submission, the run costs 296 s of the 600 s free on that
  account, and if the gate says no, the run does not start.
  ⚠ **The premise of this amendment was itself a 10-permutation band.** See
  the entry below: with the rule's own required 200 permutations the trigger
  does not fire at all.
  A second dated amendment (2026-11-02, also before the run) fixes only the
  **account and the date**: the run executes on the "hope" account
  (`E:\apikey.json`, 600 s free) on 2026-11-02, because the 556 s on the
  SILENT account does not exist before 2026-11-06. The protocol itself is
  unchanged (100 iterations = 296 s of QPU time, 356 s with the 20-iteration
  control run), the hardware is the same (`ibm_fez`), and the decisive
  comparator is untouched — the length guard in `scripts/control_comparison.py`
  always protected the `true_residual_permuted` arm.
- **The control comparison is regenerated with the full parameter set.**
  The committed `measurement_cpu/control_comparison.json` had been replaced by
  a reduced run (10 noise seeds, 5 initial states, one solver, 348 runs),
  which made the `true_residual_permuted` band a 10-sample band — not a valid
  5–95% band. It is regenerated with the original parameters (200 noise
  seeds, 30 initial states, 6 noise seeds per initial state, both solvers,
  13 377 runs) and now covers 20, 68 and 100 iterations.
- **The trigger does not fire with the band the rule itself requires.**
  `docs/QPU-RUN-DECISION-RULE.txt` point 1 defines the decision band as the
  `true_residual_permuted` arm with **≥200 permutations per hardware run**.
  The band in the committed report had **10** permutations, so the rule's own
  exception applied ("ha a sav nincs rendben... a szabaly NEM dont — a hiba
  elott nem szabad QPU-idot burnelni"). Regenerated with the required 200
  permutations (13 377 runs, 30 varying initial states, 6 noise seeds per
  initial state, both solvers, lengths 20/68/100), the hardware's true
  residual is **inside** the band for every run. The exact permutation test
  (computed from the 200 individual runs stored in the JSON, not from the
  band): for the 68-iteration run, M1 — 135/200 permutations reach the
  hardware value (p=0.675), M2 — 11/200 (p=0.055), both at once — 3/200
  (p=0.015). The old 10-permutation band had M2 p95=0.6765 and put the same
  hardware value outside; a 10-sample percentile underestimates the 95th
  percentile. **The trigger was an artifact of the too-small band.**
  `docs/MEASUREMENTS-HARDWARE-20261102.txt` records the measured result.
- **The protocol deviation is recorded, not rationalised.**
  `docs/QPU-RUN-DECISION-RULE.txt` carries three dated amendments, the third
  written *before* the run finished: the corrected band does not fire the
  trigger, the run was submitted at 13:07 — before the corrected band was
  ready at 13:20 — and the run is therefore **exploratory**. Its analysis
  plan is fixed in advance (compare against the band at the same length;
  report the exact permutation p-values; report the outcome either way), and
  its result cannot on its own support the paper's "the quantum channel
  causes the mode switching" claim; that would need a new pre-registered
  confirmation.

### Added

- **`scripts/check_qpu_quota.py`** — the quota gate that
  `docs/QPU-RUN-DECISION-RULE.txt` point h) requires *before* a measurement is
  submitted ("on an exhausted account the job never runs"). It reads the quota
  from the IBM Quantum Platform API, resolves the instance CRN, and exits
  non-zero when no account can cover the requested QPU time. `--self-test`
  proves the decision logic on injected payloads without touching the network.
- **`docs/QPU-QUOTA-20261102.txt`** — the measured quota state of the four
  accounts, the release calendar and the run plan. The quota model was
  measured, not assumed: it is a **rolling 28-day window**, not a monthly
  reset. `usage_consumed_seconds` is the trailing 28 days of QPU time,
  `time_available_at` is when the oldest usage rolls out of the window, and
  the free seconds therefore return gradually, one job at a time. A fourth
  account (`E:\apikey.json`, "hope") was found on 2026-11-02 with **0 s
  consumed and 600 s free**, which is what makes the run possible on that day.
- **`docs/MEASUREMENTS-HARDWARE-20261102.txt`** — the campaign report: the
  measured trigger result, the exact permutation p-values, the protocol
  deviation and the quota table.
- **The CPU control comparison covers 100 iterations**
  (`scripts/control_comparison.py`): the 2026-10-27 hardware run was designed
  for 100 iterations (the RUNLOG shows `iter N/100`; it stopped at 68), and
  the decision compares the hardware result against the magnitude-matched
  band **at the same length**, so the band has to exist for 100 iterations too.

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
- **The `hardware_residual` arm used recorded decoded values instead of
  true residuals** (`scripts/control_comparison.py`): the arm previously
  replayed the hardware's recorded decoded values on the corrected f-scale,
  but the correct residual is `decoded_raw − ideal` per iteration on the
  corrected f-scale with the corrected solver. The old arm is renamed to
  `hardware_recorded_replay`; the new `hardware_residual` computes the
  true residual and runs only with the corrected solver.
- **README claim "4 of 4 metrics within noise band" was incorrect** — it
  applied only to the `hardware_rescaled` hybrid arm (recorded feedback on
  corrected f-scale), not to the true residual. The README and Hungarian
  README are updated to state what the true residual arm shows: M1 and M2
  fall outside the noise bands on all three hardware runs.
- **Account identifiers (CRN/instance_id) removed from raw
  `measurement_raw/loop_summary_*.json`** files in a separate documented
  commit. The `counts` data remains untouched; only the `usage_before`
  and `usage_after` metadata blocks are sanitised.
- **Typo fixes in `docs/QPU-RUN-DECISION-RULE.txt`**: "f不加" → "f-korlataival";
  "pre-regisztrált" / "PRE-REGISZTRALT" → "előre rögzített" / "ELŐRE
  ROGZITETT"; `docs/MEASUREMENTS-GPE-QUANTUM-20261026.txt`: "不受" → "nem erinti".
- **True residual now adds to fluid's own values instead of replacing
  feedback** (`scripts/quantum_loop_sim.py`, `scripts/control_comparison.py`):
  `run_loop_channel` accepts a `residual_list` that is added to the
  fluid's current (A, f, phi) before clipping to physical ranges. This
  correctly models the residual as an additive perturbation.
- **`ideal.f` fallback uses `abs(encoded.f - round(encoded.f))`** instead of
  `encoded.f % 0.5`. This matches the recorded `ideal.f` on all 20-iteration
  runs (verified against the `ideal` field in raw files).

### Added

- **`scripts/control_comparison.py`** — the control comparison that answers
  whether the quantum feedback causes the mode switching. The branches: the
  noise-free classical control, the noise-free quantum channel, the
  measured-`c` and the hardware-floor noise models at 10 and 1024 shots, and
  a replay of the hardware's own recorded feedback with ≥200 permutations.
  **New in this release:** the **true residual arm** (`hardware_residual`)
  computes `decoded_raw − ideal` per iteration on the corrected f-scale with
  the corrected solver, added to the fluid's own values; and the **magnitude-
  matched comparator** (`true_residual_permuted`) permutes the true residual
  ≥200 times (fixed and varying initial states) to establish the decision
  band. 200 noise seeds per branch, 30 varying initial states, both hardware
  run lengths, and both the corrected and the pre-fix solver. Output in
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
- **The hardware measurement script records the time of every job**
  (`scripts/hardware_measure.py`): the QPU seconds and the wall seconds
  are now measured per job and stored in the raw file, like the loop
  measurement already did. The reason is a measured gap: the 3σ
  measurement of the 16-mode gap needs about 481 jobs (492 000 shots /
  1024), and whether that campaign fits into the 600 s quota is decided
  by the QPU time per job — which had never been measured, because the
  modes job is a 16 qubit circuit while the only measured circuit time
  (0.74 s) comes from the 2 qubit loop circuits. The measurement was
  extrapolated across circuit sizes; now it will be measured.

### CI

- **Every script is byte-compiled in the CI.** The hardware scripts need
  `scs_quantum` and `qiskit`, so the CI cannot run them, and a syntax
  error in them would have stayed invisible until the next real QPU run.
- **The byte-identity gate on the CPU measurement was wrong, and the CI
  itself proved it.** Run 41300523065 failed on the Linux runner while the
  same commit was byte identical on Windows. The measured cause is the
  floating point noise of the coherence values, about 1e-13 relative; the
  mode sequences, the histograms and every metric derived from them were
  identical. The smallest decision margin over the 1000 iterations is
  1.4e-4 (quantum branch) and 7.8e-4 (classical branch), so the mode
  sequence is not close to a tie. `scripts/check_cpu_result.py` replaces
  the `git diff --exit-code` with the rule that matches the measurement:
  integers exactly, floats within a relative tolerance of 1e-9.
  `scripts/test_check_cpu_result.py` proves that the gate fires, by
  injecting a changed mode sequence, a changed histogram, a changed
  integer metric, a float outside the tolerance and a changed key set.
- **The numpy version is pinned in the measurement job.** Measured on
  2026-11-01 in three isolated environments (numpy 1.26.4, 2.4.6 and
  2.5.4, on Python 3.11 and 3.14): the mode sequences are identical in
  all three, and only the coherence floats differ, by about 1e-13. The
  pin keeps the committed file byte-stable, so a real change shows up as
  a visible diff instead of a tolerance-sized one.

### Changed

- **The claim about quantum feedback causing mode switching is
  re-evaluated with the true residual and magnitude-matched comparator.**
  The control comparison measures the true residual
  (`decoded_raw − ideal` on corrected f-scale with corrected solver, added
  to the fluid's own values) and compares it against the **magnitude-matched
  comparator** (`true_residual_permuted`, the true residual permuted ≥200
  times at fixed and varying initial states).
  Results per `docs/QPU-RUN-DECISION-RULE.txt`:
  - 20-iter runs (both fixed and varying init): M1/M2 fall INSIDE the
    true_residual_permuted band → QPU run NOT justified.
  - 68-iter fixed_init: M1=6, M2=0.7206 OUTSIDE the band → QPU run
    justified.
  - 68-iter varying_init: M1/M2 INSIDE the band → NOT justified.
  ⚠ **CORRECTED IN 0.2.3:** the 68-iteration bullet above was computed from a
  **10-permutation** band, which does not meet the rule's own requirement of
  ≥200 permutations. With the required 200 permutations the same hardware
  value falls **inside** the band, and the trigger does not fire. See
  0.2.3 and `docs/MEASUREMENTS-HARDWARE-20261102.txt`.
  Overall: the true residual does NOT consistently fall outside the
  magnitude-matched noise band. A new QPU run is only conditionally
  justified for the 68-iter fixed-init case.
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
- **The QPU decision rule updated**: the decisive comparator is now the
  `true_residual_permuted` band (magnitude-matched noise), not the
  shot-noise arms. The rule, arm names, and metrics are documented in
  `docs/QPU-RUN-DECISION-RULE.txt`.

### Measured

- The noise-free quantum channel produces the same mode sequence as the
  classical control with the corrected solver. The difference between the
  branches is the measurement noise, not the structure of the channel.
- Measurement noise destroys structure rather than creating it: at 20
  iterations the noise-free control visits 3 modes (Brain 0.35, H/Hmax
  0.395), while every noisy branch concentrates on a single mode (Brain
  0.85–0.95, H/Hmax 0.07–0.19).
- The **true residual** (`decoded_raw − ideal` on corrected f-scale with
  corrected solver, added to fluid's own values) compared against the
  **magnitude-matched comparator** (`true_residual_permuted`, ≥200 permutations
  of the true residual):
  - 20-iter fixed_init: M1=3.0, M2=0.55 INSIDE band [3.0,3.0]×[0.25,0.55]
  - 20-iter varying_init: M1=4.0/3.0, M2=0.60/0.40 INSIDE bands
  - 68-iter fixed_init: M1=6.0, M2=0.7206 OUTSIDE band [5.0,6.0]×[0.588,0.676]
  - 68-iter varying_init: M1=6.0, M2=0.6618 INSIDE band [3.0,6.0]×[0.485,0.824]
  → The true residual does NOT consistently fall outside the magnitude-matched
    noise band. Only 68-iter fixed_init is outside.
  The recorded feedback at the hardware's original f-scale was outside the
  shot-noise bands; the recorded feedback at the corrected f-scale
  (`hardware_rescaled`) is inside the shot-noise bands — the multi-mode
  pattern was caused by the f-scale bug.
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
