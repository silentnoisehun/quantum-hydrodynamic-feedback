# Quantum Organic Intelligence

A Gross-Pitaevskii folyadék, a quantumhíd, amelynek kódolását és dekódolását a rögzített hardvermérések igazolják, és a mérések, amelyek dokumentálják — és korlátozzák — a rendszer dinamikai viselkedését. Ez a repó három mérhető komponensen alapul:

* `crates/fluid-stratos`: A 16 kognitív módra képezett GPE-folyadékmotor, valódi split-step Fourier kinetikus lépéssel.
* `crates/quantum-bridge`: A quantumhíd: 2 qubit + 3 külön mérés ($A, f, \varphi$), mérve egy 156 kvantos QPU-n. Amit ez a mérés bizonyít és amit nem, az [Ismert problémák](#ismert-problémák--mit-nem-mutat-ez) szekcióban van.
* `docs/`: Mérési jelentések, módszertan és korlátok.

---

## 1. Architektúra és Módszertan

### A Fluid STRATOS (GPE Folyadékmotor)

A motor a 16 kognitív módot egy két dimenziós Gross-Pitaevskii mezőn valósítja meg, valódi split-step Fourier transzformációs kinetikus lépéssel (`rustfft 6.4.1`) és Strang-féle időléptetéssel.

### A Quantumhíd

A kódolás a valódi $156$ qubites szupravezető QPU mérésein alapul:

* **Kódolási séma (2 qubit + 3 külön mérés):**
  * $A$ (intenzitás): 1 qubit, $\text{RY}(A) \to P(q_0=1) = \sin^2(A/2)$
  * $f$ (frekvencia): 2 qubit, $\text{RY}(2\pi f) + \text{CNOT} \to P(q_0=1) = \sin^2(\pi f)$
  * $\varphi$ (fázis): 2 qubit, $\text{RY}(\varphi) + \text{CNOT} \to P(q_0=1) = \sin^2(\varphi/2)$

* **Visszafejtés:**
  * $A = 2 \cdot \arccos(\sqrt{P(q_0=0)})$
  * $\varphi = 2 \cdot \arcsin(\sqrt{P(q_0=1)})$
  * $f = \arcsin(\sqrt{P(q_0=1)}) / \pi$

---

## 2. A Kvantum–Klasszikus Hurok Szimulációja

A szimulációs protokoll során a CPU-ról kinyert paramétereket $(A, f, \varphi)$ beküldjük a 3 kvantumáramkörbe (10 lövés/mérés), visszafejtjük, majd a mutált értékeket visszatöltjük a folyadékba 50 GPE-lépés erejéig.

---

## 3. Elvárások és Korlátok

* **A perturbáció szerepe:** a mérési zaj **nem** struktúraforrás. A javított folyadékkal a zajmentes klasszikus kontroll több módra terjed (20 iteráció után 16-ból 3, marginális entrópia H/Hmax 0,395), míg ugyanez a hurok mérési zajjal egyetlen módra koncentrálódik (Brain-arány 0,85-0,95, H/Hmax 0,07-0,19). A zaj tehát **elbontja** a struktúrát, nem létrehozza. A teljes sávok és a hardver helye: `docs/MEASUREMENTS-CPU-CONTROLS.txt`.
* **Korlátok:**
  1. A mért adatok egy koherens folyadék-attraktor létezését igazolják. **Nem** igazolják, hogy a kvantum-visszacsatolás okozza a módváltást: a hardver saját rögzített mérési értékeit a **valódi reziduumként** (`decoded_raw − ideal`) a javított frekvenciaskálán, a javított solverrel visszajátszva a módminta **KIVÚL esik** a sávon, amit a puszta mérési zaj létrehoz (a valódi reziduum arm M1=látogatott módok és M2=Brain-arány a zajsávon kívül esik mindhárom hardveres futásra, mind a 20, mind a 68 iterációnál). Egy új QPU-futtatás indokolt a `docs/QPU-RUN-DECISION-RULE.txt` szerint.
  2. A hisztogram-tesztet minden esetben össze kell vetni a klasszikus kontrollal a hamis pozitív eredmények elkerülése érdekében.
  3. A kvantumhíd a hullámcsomag $(A, f, \varphi)$ mérésére alkalmas; a 16 mód közötti verseny kvantum-úton történő eldöntése a jelenlegi hardver-paraméterek mellett nem mutatható ki.

### Mit tud és mit nem a híd

* **A frekvenciacsatorna csak $[0, 0,5]$-ön egyértelmű.** A kétkvantumos interferenciadekódolás $f = \arcsin(\sqrt{P})/\pi$, és a $\sin^2(\pi f)$ periodikus, tehát az $f > 0,5$ visszahoozik. A folyadék $f$-je a 16 mód indexének energiával súlyozott átlaga, tehát $[0, 15]$-ben van; kódolás előtt a $[0, 0,5]$ tartományba kell normalizálni, dekódolás után vissza kell skálázni. A rögzített hardverfájlokon mérve: a kódolt érték 1,24-3,81 volt, és **111-ből 111 iterációban visszahajtott**.
* **A két kvubit itt nem ad kvantumelőnyt.** A frekvencia- és fázisáramkör a vezérlő kvantumon egy `RY` plusz egy `CNOT`, amely átmásolja az értéket a mérő kvantumra. A valószínűségi törvény $P(q_0=1) = \sin^2(\theta/2)$ — ugyanaz, mint egy egykvantumos forgatásnál. A plusz kvubit áramkör-méretet (és QPU-időt) ad, nem információt.
* **Az $A$, az $f$ és a $\varphi$ ugyanaz a mérés.** Mindhárom erre egyszerűsül: „egy forgatási szög $\theta$, mérd $P(q_0=1)$, fordítsd meg a $\sin^2(\theta/2)$-et". Az $A$ és a $\varphi$ szó szerint ugyanaz az inverz, $2\arcsin(\sqrt{P})$; az $f$ ugyanez $1/\pi$-vel skálázva. A „fázis" tehát **nem kvantumfázis** — forgatási szög, és ugyanazzal a statisztikával mérjük, mint az amplitúdót.

### Ismert problémák / Mit NEM mutat ez

* **A 2026-10-27-i hardveres futások két javítás előtt készültek, és nem futottak újra.** Olyan solverrel futottak, amelynek kinetikus lépése nem volt Fourier-transzformáció, és a frekvenciát hibás skálán vezették vissza. A `scripts/replay_hardware_log.py` a rögzített modsorokat pontosan visszaadja a régi solverrel (20/20, 20/20, 68/68), és egyiket sem az újjal (7/20, 4/20, 26/68) — ez a bizonyíték arra, hogy melyik kóddal futottak. A modsorozataik tehát **nem** bizonyítékok a jelenlegi modellre.
* **A hardverriport modsorozatai nem bizonyítékok a kvantumcsatornára.** A rögzített visszacsatolást a helyes frekvenciaskálán visszajátszva a hardver saját mérései ugyanazt az egyetlen módra összeomlást adják, mint a klasszikus kontroll és a szimulált zaj. A több módra járó mintát azokban a futásokban a frekvenciaskála hibája okozta.
* **A 16 mód argmax mérése nem informatív.** Hat próbából 0/6 egyezés a klasszikus argmaxszal. $N = 6$ esetén ez a szám nem különbözteti meg a „nincs kvantumhatást" a „kis kvantumhatástól"; ezért jelentjük, nem értelmezzük.
* **A Bell-referencia mennyisége paritás-populáció, nem fidelitás.** A $P(00) + P(11)$-t méri, vagyis a két bit egyezésének arányát. Nem méri a koherenciát. A belőle származó szimmetrikus $c$-korrekció az amplitúdócsatornát **rontja** (átlagos hiba 0,026 nyersen, 0,212 korrigáltan), ezért a híd a $c$-t csak minőség-indikátorként kezeli, és a `--correct` alapból ki van kapcsolva.
* **Nincs emergens intelligencia.** Semmi itt nem mutat önszerveződő intelligenciát. A GPE folyadéknak önmagában is van módváltó dinamikája: a javított operátorral a klasszikus ág önmagában is több módot jár be.
* **A koherencia nem önálló mérőszám.** A `gpe.rs` definíciója szerint normalizált arány, amit a szimuláció a dead GPE-n is 1,0000-nak mér.
* **Egy új QPU-futtatás alapból nem engedélyezett.** A feltételt előre rögzíti a `docs/QPU-RUN-DECISION-RULE.txt`.

### Mi validálja a teljes állítást

A protokoll 1000 iteráció. A teljes állítást **a mérés végigfutásával** lehet
validálni: a teljes, 1000 iterációs futással, a klasszikus kontrollal együtt,
hogy a hisztogram-tesztnek legyen elegendő statisztikai ereje. A `docs/`
mögötti futások ennél rövidebbek, a
`docs/MEASUREMENTS-HARDWARE-20261027.txt` 6. szakaszában mért okok miatt: az
open csomag 600 s-os kvótája és a Runtime Session hiánya.

Amíg a kontroll-összehasonlítás nem mondja, hogy a hardver viselkedése a zajsávon
kívül esik, egy új hardveres futás nem indokolt; ezt a feltételt előre rögzíti a
`docs/QPU-RUN-DECISION-RULE.txt`.

---

## 4. Használat

A tesztek és szimulációk futtatása a repón belül:

```bash
# A fluid folyadékmotor regressziós tesztjei
cargo test --manifest-path crates/fluid-stratos/Cargo.toml

# A quantumhíd tesztjei
cargo test --manifest-path crates/quantum-bridge/Cargo.toml

# A folyadék ébredésének mérése (numpy, ~1 perc)
python scripts/gpe_fft_measurement.py

# A kvantum-klasszikus hurok 4 ággal (numpy, ~15 perc)
python scripts/quantum_loop_sim.py

# A 10 lövés matematikájának ellenőrzése
python scripts/quantum_10shot_math.py
```

### A valós hardveres mérés

A quantumhíd valódi QPU-n is futtatható. A token az `IBM_QUANTUM_API_TOKEN`
környezetváltozóban kell (a `scs_quantum` saját `.env` fájlját is betölti).

```bash
# A pipeline ellenőrzése ideális szimulátoron — token NEM kell,
# de ez NEM QPU-bizonyíték, csak a kód helyességének igazolása
python scripts/hardware_measure.py --local

# A valódi hardver: a Bell-paritás, a 16 mód argmax, az (A, f, φ) dekódolás
python scripts/hardware_measure.py --backend ibm_fez --shots 1024 --mode-trials 20
```

A mérés három dolgot mér:

1. a **bit-sorrend-ellenőrzés** — a mérés előfeltétele; ha nem megy át, a mérés elutasításra kerül
2. a **hardver-minőséget** (a Bell-referencia egyensúlya) — ez a `c`, amit a szimuláció használ
3. a **16 mód argmax pontosságát** a klasszikus argmaxhoz képest, és az **$(A, f, \varphi)$ dekódolás** pontosságát

A nyers mérési adatok a `measurement_raw/` mappába kerülnek (a job ID-vel, a
backenddel és az időbélyeggel) — ez **verziókövetett**, így a `docs/`-ban
idézett minden szám visszakövethető a mérési fájljához.

### A kvantum–klasszikus hurok valódi hardveren

A `scripts/quantum_loop_hardware.py` a hurkot futtatja egy QPU-n. Az iteráció
három áramkörét (A, f, φ) egy jobba kötegeli, minden N. iterációban
Bell-anchort ad hozzá, és a mért hardver-minőséget (`c`) visszaadja a
dekódolóba a Rust bridge-en keresztül
(`crates/quantum-bridge/src/bin/bridge-cli.rs`) — így a dekódolás
matematikája pontosan egy helyen van.

```bash
# A hurok: 100 iteráció, 1024 lövés, az anchor minden 5. iterációban
python scripts/quantum_loop_hardware.py --backend ibm_fez --iterations 100 --shots 1024 --anchor-every 5
```

> **Az open csomagban nincs session.** Az IBM megtagadja a Runtime Session-t az
> open csomagon ("not authorized to run a session when using the open plan"),
> így minden iteráció önálló jobként áll sorba. A szkript ezért a
> sor-várakozást **méri**, nem feltételezi, és a QPU-mp-eket meg a falióra-időt
> külön kiírja. A fenntartott ablakhoz másik plan instance kell.

> **A hardveres futás mérési jelentése** —
> `docs/MEASUREMENTS-HARDWARE-20261027.txt`, a futásnaplókkal együtt
> (`docs/RUNLOG-*.txt`). Minden szám a `measurement_raw/` nyers fájljaiból
> újraszámítható a `scripts/summarize_hardware_run.py` szkripttel.

> **Környezet:** a méréshez tiszta virtuális környezet ajánlott. A Qiskit 1.x és
> 2.x nem él együtt ugyanabban a Pythonban:
> ```bash
> python -m venv .venv-quantum
> .venv-quantum/Scripts/pip install "qiskit>=2.0" "qiskit-ibm-runtime>=0.50" python-dotenv numpy
> .venv-quantum/Scripts/python scripts/hardware_measure.py --local
> ```
> A `scs_quantum` csomag telepített példány hiányában a `SCS_QUANTUM_PATH`
> környezetváltozó mutatja a `python/` mappát.

---

## Nyílt Kutatás

Ez a munka nyitott a együttműködésre, szakmai ellenőrzésre és független validációra.
Ha bármelyik alábbi területen dolgozol, szívesen beszélek veled:

* **Quantum error mitigation** — az aszimmetrikus mérésizaj és a `c`-indikátor megközelítés
* **Neuromorph memóriamodellek** — a rekonzolidációs dinamika és a 16-módos folyadék-attraktor
* **Agentikus AI architektúrák** — a kognitív gradiens tervezés és a kvantum-klasszikus visszacsatolási hurok
* **Cross-validáció** — különösen a rekonzolidációs modell biológiai plauszibilitására
* **Előadások** — a pószt-akadémiai tudományról és az ipar-to-kutató útról

### Kapcsolat

**ORCID:** 0009-0003-3986-6039  
**Email:** materobi86@gmail.com  
**Sponsor:** github.com/sponsors/silentnoisehun  
**GitHub:** github.com/silentnoisehun/quantum-organic-intelligence

---

## 5. Licenc

MIT licenc. A hivatkozási adatok a `CITATION.cff` fájlban találhatók.