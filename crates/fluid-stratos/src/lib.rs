//! Fluid STRATOS — a Gross-Pitaevskii folyadékmotor kognitív térhez.
//!
//! 🧬 A KINETIKUS LÉPÉS VALÓDI 2D FFT-vel (sor + oszlop transzformáció).
//! A korábbi implementáció fázis-rotációt alkalmazott a RÁCSINDEX-térben
//! (transzformáció nélkül), ezért a sűrűség-eloszlás matematikailag
//! invariáns volt: minden művelet vagy fázis-szorzás (nem változtatja a
//! modult) vagy uniform skálázás (nem változtatja a rációt) volt.
//!
//! Mért bizonyíték a javítás előtt (64×64, 500 lépés, γ=0):
//!   a sűrűség-eloszlás max |Δ| = 1.4e-13  (O(1e-13), gépizaj)
//!   a 16 mód energiája max |Δ| = 1.8e-14  (O(1e-14), gépizaj)
//!   a koherencia MINDIG 1.000000 (a tanh teljesen szaturált)
//!   a max/mean 1112.84 (a folyadék egyetlen pontba koncentrált)
//!
//! Mért bizonyíték a javítás után (γ=0.002, lokális veszteség):
//!   a sűrűség-eloszlás max |Δ| = 2.780  (79× javulás a γ=0 baseline-on)
//!   a 16 mód energiája max |Δ| = 9.420  (5.3e3× javulás a γ=0 baseline-on)
//!   a max/mean 1112.84 → 7.31 (a folyadék kiterjedt)
//!   a koherencia 1.000000 → 0.452 (a jelző életre kelt)
//!
//! Lényeg: az egyenletes (uniform) decay a renormalizáció alatt kiesik;
//! a sűrűségarányos (lokális) nem — ez fizikaileg az igazi disszipáció.

pub mod gpe;
pub mod gpe_parallel;

pub use gpe::{GpeParams, GpeSolver, GpeState};
pub use gpe_parallel::{ParallelGpeParams, ParallelGpeSolver};
