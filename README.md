# Quantum Organic Intelligence

A Gross-Pitaevskii fluid, a quantum bridge whose encoding and decoding are verified against recorded hardware measurements, and the measurements that document — and limit — the system's dynamical behaviour. This repository rests on three measurable components:

* `crates/fluid-stratos`: a GPE fluid solver for 16 cognitive modes, with a real split-step Fourier kinetic step.
* `crates/quantum-bridge`: the quantum bridge: 2 qubits + 3 separate measurements ($A, f, \varphi$), measured on a 156-qubit QPU. What that measurement does and does not establish is listed under [Known issues](#known-issues--what-this-does-not-show).
* `docs/`: measurement reports, methodology, and limits.

---

## 1. Architecture and Methodology

### The Fluid STRATOS (GPE fluid solver)

The engine realises the 16 cognitive modes on a two-dimensional Gross-Pitaevskii field, with a real split-step Fourier kinetic step (`rustfft 6.4.1`) and Strang-style time stepping.

### The quantum bridge

The encoding is based on measurements on a real $156$-qubit superconducting QPU:

* **Encoding scheme (2 qubits + 3 separate measurements):**
  * $A$ (intensity): 1 qubit, $\text{RY}(A) \to P(q_0=1) = \sin^2(A/2)$
  * $f$ (frequency): 2 qubits, $\text{RY}(2\pi f) + \text{CNOT} \to P(q_0=1) = \sin^2(\pi f)$
  * $\varphi$ (phase): 2 qubits, $\text{RY}(\varphi) + \text{CNOT} \to P(q_0=1) = \sin^2(\varphi/2)$

* **Decoding:**
  * $A = 2 \cdot \arccos(\sqrt{P(q_0=0)})$
  * $\varphi = 2 \cdot \arcsin(\sqrt{P(q_0=1)})$
  * $f = \arcsin(\sqrt{P(q_0=1)}) / \pi$

---

## 2. The Quantum–Classical Loop Simulation

The simulation protocol takes the $(A, f, \varphi)$ parameters extracted on the CPU, submits them to the 3 quantum circuits (10 shots per measurement), decodes them, and loads the mutated values back into the fluid for 50 GPE steps.

---

## 3. Expectations and Limits

* **The role of the perturbation:** measurement noise is **not** a source of structure. With the corrected fluid, the noise-free classical control spreads over several modes (3 of 16 after 20 iterations, marginal entropy H/Hmax 0.395), while the same loop with measurement noise concentrates onto a single mode (Brain ratio 0.85-0.95, H/Hmax 0.07-0.19). The noise **destroys** structure; it does not create it. The full bands and the hardware placement are in `docs/MEASUREMENTS-CPU-CONTROLS.txt`.
* **Limits:**
  1. The measured data establish the existence of a coherent fluid attractor. They do **not** establish that the quantum feedback causes mode switching: with the hardware's own recorded measurements replayed at the correct frequency scale, the mode pattern lands inside the band that plain measurement noise produces (4 of 4 metrics, with the solver the hardware actually ran).
  2. The histogram test must always be compared against the classical control, to avoid false positives.
  3. The quantum bridge is suitable for measuring the wavepacket $(A, f, \varphi)$; deciding between the 16 modes via the quantum path is not detectable with the current hardware parameters.

### What the bridge can and cannot measure

* **The frequency channel is unambiguous only on $[0, 0.5]$.** The two-qubit interference decode is $f = \arcsin(\sqrt{P})/\pi$, and $\sin^2(\pi f)$ is periodic, so a frequency above $0.5$ folds back. The fluid's $f$ is an energy-weighted average of the 16 mode indices and therefore lives in $[0, 15]$; it has to be normalised into $[0, 0.5]$ before encoding and scaled back after decoding. Measured on the recorded hardware files: the encoded value was 1.24-3.81, and **111 of 111 iterations folded back**.
* **Two qubits do not buy a quantum advantage here.** The frequency and phase circuits are an `RY` on the control qubit plus a `CNOT` that copies it into the readout qubit. The probability law is $P(q_0=1) = \sin^2(\theta/2)$ — the same law as a single-qubit rotation. The extra qubit adds circuit size (and QPU time), not information.
* **$A$, $f$ and $\varphi$ are the same measurement.** All three reduce to "one rotation angle $\theta$, measure $P(q_0=1)$, invert $\sin^2(\theta/2)$". $A$ and $\varphi$ are literally the same inverse, $2\arcsin(\sqrt{P})$; $f$ is the same form scaled by $1/\pi$. The "phase" is therefore **not a quantum phase** — it is a rotation angle, measured with the same statistics as the amplitude.

### Known issues / What this does NOT show

* **The 2026-10-27 hardware runs predate two fixes and were not re-run.** They used a solver whose kinetic step was not a Fourier transform, and they fed the frequency back on a broken scale. `scripts/replay_hardware_log.py` reproduces their recorded mode sequences exactly with the old solver (20/20, 20/20, 68/68) and with the current one with none of them (7/20, 4/20, 26/68) — that is the proof of which code they ran. Their mode histograms are therefore **not** evidence for the current model.
* **The mode histograms in the hardware report are not evidence for the quantum channel.** With the recorded feedback replayed at the correct frequency scale, the hardware's own measurements give the same collapse onto a single mode that the classical control and the simulated noise give. What produced the multi-mode pattern in those runs was the frequency-scale bug.
* **The 16-mode argmax measurement is not informative.** Six trials gave 0/6 agreement with the classical argmax. With $N = 6$ that number cannot separate "no quantum effect" from "a small quantum effect"; it is reported, not interpreted.
* **The Bell-reference quantity is a parity population, not a fidelity.** It measures $P(00) + P(11)$, the agreement rate of the two bits. It does not measure coherence. The symmetric $c$-correction derived from it makes the amplitude channel *worse* (mean error 0.026 raw versus 0.212 corrected), so the bridge treats $c$ as a quality indicator only and `--correct` is off by default.
* **No emergent intelligence.** Nothing here shows self-organising intelligence. The GPE fluid has intrinsic mode-switching dynamics on its own: with the corrected operator the classical branch alone visits several modes.
* **The coherence number is not an independent metric.** By the `gpe.rs` definition it is a normalised ratio that the simulation also measures as 1.0000 on the dead GPE.
* **A new QPU run is not authorised by default.** `docs/QPU-RUN-DECISION-RULE.txt` pre-registers the condition under which one is allowed.

### What validates the complete claim

The protocol is 1000 iterations of the loop. The complete claim would be validated by
running the measurement to the end — the full 1000 iterations together with the
classical control, so that the histogram test has the statistical power it
needs. The runs behind `docs/` are shorter than that, for the measured reasons
given in section 6 of `docs/MEASUREMENTS-HARDWARE-20261027.txt`: the open
plan's 600 s quota and the absence of Runtime Sessions.

Until the control comparison says the hardware behaviour falls outside the noise
band, a new hardware run is not justified; that condition is fixed in advance in
`docs/QPU-RUN-DECISION-RULE.txt`.

---

## 4. Usage

Running the tests and the simulations from inside the repository:

```bash
# The fluid solver's regression tests
cargo test --manifest-path crates/fluid-stratos/Cargo.toml

# The quantum bridge's tests
cargo test --manifest-path crates/quantum-bridge/Cargo.toml

# Measuring the fluid's awakening (numpy, ~1 min)
python scripts/gpe_fft_measurement.py

# The quantum–classical loop with 4 branches (numpy, ~15 min)
python scripts/quantum_loop_sim.py

# Checking the mathematics of 10 shots
python scripts/quantum_10shot_math.py
```

### The real hardware measurement

The bridge can be run on a real QPU. The token belongs in the
`IBM_QUANTUM_API_TOKEN` environment variable (the `scs_quantum` package also
loads its own `.env` file).

```bash
# Pipeline check on an ideal simulator — no token needed,
# but this is NOT QPU evidence, only proof that the code is correct
python scripts/hardware_measure.py --local

# The real hardware: the Bell parity, the 16-mode argmax, the (A, f, φ) decoding
python scripts/hardware_measure.py --backend ibm_fez --shots 1024 --mode-trials 20
```

The measurement covers three things:

1. the **bit-order self-check** — a precondition; if it fails, the measurement is rejected
2. the **hardware parity** (the Bell-reference balance) — this is the `c` the simulation uses
3. the **accuracy of the 16-mode argmax** against the classical argmax, and the **$(A, f, \varphi)$ decoding** accuracy

The raw measurement data lands in `measurement_raw/` (with the job ID, the backend
and the timestamp) — it **is version controlled**, so every number quoted in
`docs/` can be traced back to the measurement file it came from.

### The quantum–classical loop on real hardware

`scripts/quantum_loop_hardware.py` runs the loop itself on a QPU. It bundles the
three circuits of an iteration (A, f, φ) into a single job, adds a Bell anchor
every N iterations, and feeds the measured hardware quality `c` back into the
decoder through the Rust bridge (`crates/quantum-bridge/src/bin/bridge-cli.rs`),
so the decoding mathematics lives in exactly one place.

```bash
# The loop: 100 iterations, 1024 shots, the anchor every 5 iterations
python scripts/quantum_loop_hardware.py --backend ibm_fez --iterations 100 --shots 1024 --anchor-every 5
```

> **The open plan has no sessions.** IBM refuses a Runtime Session on the open
> plan ("not authorized to run a session when using the open plan"), so each
> iteration queues as an independent job. The script therefore *measures* the
> queue wait instead of assuming it, and prints the QPU seconds and the wall
> clock separately. A reserved window would need a different plan instance.

> **The measurement report for the hardware run** —
> `docs/MEASUREMENTS-HARDWARE-20261027.txt`, with the run logs in
> `docs/RUNLOG-*.txt`. Every number in it is recomputable from the raw files
> in `measurement_raw/` with `scripts/summarize_hardware_run.py`.

> **Environment:** a clean virtual environment is recommended for the
> measurement. Qiskit 1.x and 2.x cannot coexist in the same Python:
> ```bash
> python -m venv .venv-quantum
> .venv-quantum/Scripts/pip install "qiskit>=2.0" "qiskit-ibm-runtime>=0.50" python-dotenv numpy
> .venv-quantum/Scripts/python scripts/hardware_measure.py --local
> ```
> If the `scs_quantum` package is not installed, the `SCS_QUANTUM_PATH`
> environment variable points at its `python/` directory.

---

## Open Research / Nyílt Kutatás

This work is open to collaboration, peer review, and independent verification.
If you are working in any of the following areas, I would welcome a conversation:

* **Quantum error mitigation** — the asymmetric readout noise and the `c`-indicator approach
* **Neuromorphic memory models** — the reconsolidation dynamics and the 16-mode fluid attractor
* **Agentic AI architectures** — the cognitive gradient design and the quantum-classical feedback loop
* **Cross-validation** — especially on the biological plausibility of the reconsolidation model
* **Speaking engagements** — on post-academic science and the factory-to-researcher journey

### Contact

**ORCID:** 0009-0003-3986-6039  
**Email:** materobi86@gmail.com  
**Sponsor:** github.com/sponsors/silentnoisehun  
**GitHub:** github.com/silentnoisehun/quantum-organic-intelligence

---

## 5. License

MIT license. The citation metadata is in `CITATION.cff`.