# TODO: mass-accuracy defaults — `AUTO` vs fixed ppm, and are 20/15 too large?

**Date:** 2026-06-22
**Status:** Decided — keep `AUTO` default + show read-only guidance. Implemented in
the A386 executable XML (source + deployed slurmworker copy); see action items.

## Why this came up

The older **A366_DIANN** executable ships fixed mass-accuracy defaults
(`bfabric_executable/executable_A366_DIANN.xml`):

- MS2: `--mass-acc 20` (default `--mass-acc 20`, enums 10/15/20)
- MS1: `--mass-acc-ms1 15` (default `--mass-acc-ms1 15`, enums 10/15/20)

The current **A386_DIANN_3.2** executable instead defaults both to `AUTO`
(`executable_A386_DIANN_3.2.xml:561,581`; SUSHI `DIANNApp.rb` enums
`['AUTO','5','10','15','20']`). The question raised: **20 ppm (MS2) / 15 ppm
(MS1) look large — are they?** And: is `AUTO` the right default?

Short answer: **20/15 are loose** — they are the right numbers only for TripleTOF
6600 / ZenoTOF, are slightly loose for timsTOF, and are **2–5× too loose for
modern Orbitraps and the Astral**. `AUTO` is a safer default than a wrong fixed
number, but it has real reproducibility caveats. See below.

## How DIA-NN mass accuracy actually works

From the DIA-NN README (vdemichev/DiaNN):

- The settings are **`--mass-acc <ppm>`** (MS2) and **`--mass-acc-ms1 <ppm>`**
  (MS1). A value of **`0` = automatic** (this is what our `AUTO` sentinel maps to —
  we omit the flag, so DIA-NN auto-optimises).
- With automatic: *"DIA-NN will optimise them automatically for the first run in
  the experiment and then reuse the optimised settings for other runs."*
- Crucial caveat: *"This optimisation is inherently noisy: even replicate
  injections may not produce identical results, and therefore the analysis
  results will depend on which run is first in the list."*
- These values are **guidance**, not hard windows: DIA-NN uses a per-precursor,
  RT-local m/z window for the actual matching. So a somewhat-too-loose setting is
  not catastrophic (DIA-NN narrows locally), but it is suboptimal — looser windows
  admit more interferences and can cost specificity/quant precision. A
  *too-tight* setting is the more dangerous error (it can clip real signal).

## DIA-NN's recommended values (instrument-specific)

For publication-ready / production analyses, the README recommends **fixing**
mass accuracies to known-good values for the LC-MS setup:

| Instrument | MS1 (ppm) | MS2 (ppm) | Notes |
|---|---|---|---|
| Orbitrap, 240k resolution | 4 | 4 | e.g. Astral / high-res Exploris |
| Orbitrap, 120k resolution | ~7 | 7 | |
| Orbitrap, 60k resolution | ~10 | 10 | |
| Orbitrap, 30k resolution | ~15 | 15 | |
| **Orbitrap Astral** | **4** | **10** | README's explicit Astral pairing (240k) |
| **Bruker timsTOF** | **15** | **15** | |
| **TripleTOF 6600 / ZenoTOF** | **20** | **20** | |

(These match the table already in `docs/DIANN_PARAMETERS.md:103-124`.)

### Verdict on the old 20/15 defaults

- **MS2 = 20 ppm:** correct **only** for TripleTOF/ZenoTOF. ~33% looser than
  timsTOF (15) and **2–5× looser** than any Orbitrap (4–10). For Orbitrap data
  this is clearly too large.
- **MS1 = 15 ppm:** correct for timsTOF; **far too loose** for Orbitrap (4–7
  high-res) and Astral (4).

So the instinct is right: 20/15 are TOF-shaped numbers that should never have been
a global default for a facility that also runs Orbitraps.

## Current state in this repo / SUSHI

- **A386 (current):** both MS1/MS2 default to `AUTO` → no flag emitted → DIA-NN
  auto-optimises from the first run. Safe-ish, but inherits the "depends on first
  run" non-reproducibility above.
- **SUSHI enumerations are incomplete for Orbitrap:** `DIANNApp.rb` offers
  `['AUTO','5','10','15','20']`. **The high-res Orbitrap/Astral values `4` and `7`
  are not selectable.** A user who wants to fix to the *correct* Orbitrap value
  literally cannot pick it from the dropdown.
- **Interaction with "Unrelated runs"** (`--individual-mass-acc --individual-windows`):
  this only does anything **while mass accuracy is `AUTO`** (it makes the
  auto-determination per-run instead of first-run-for-all). If MS1/MS2 are fixed,
  it is inert for mass accuracy. Already documented at
  `docs/DIANN_PARAMETERS.md:136-143`.

## Recommended workflow (calibrate, then fix)

This is the DIA-NN-blessed pattern and what we should steer users toward for any
final / large / publishable run:

1. **Calibration pass:** run on a few representative runs with **Unrelated runs**
   enabled while mass accuracy is `AUTO`.
2. **Read the log:** DIA-NN prints *"Averaged recommended settings for this
   experiment"* — these are the per-experiment optimal MS1/MS2 (and scan window).
3. **Fix** MS1/MS2 to those values and run the full experiment. Reproducible and
   typically ≥ the auto result in IDs/precision.

## Options for the app (decision needed)

- **(A) Keep `AUTO` as the default (status quo A386).** Simplest and robust; never
  ships a wrong fixed number. Downsides: noisy, first-run-dependent, not bit-for-bit
  reproducible across run reordering. → *Recommended default*, but pair with the
  fixes below.
- **(B) Instrument-aware presets.** Add an instrument dropdown (Orbitrap-240k /
  -120k / -60k / Astral / timsTOF / TripleTOF) that sets the recommended MS1/MS2.
  Best UX, but requires reliable instrument metadata per workunit (B-Fabric
  instrument field?) — verify availability before committing.
- **(C) Surface DIA-NN's recommendation in QC.** Parse the
  "Averaged recommended settings" line from the DIA-NN log and show it in the QC
  report, so users can confidently re-run with fixed values. Cheap, high value,
  composes with (A).

**Recommendation:** keep `AUTO` default (do **not** resurrect fixed 20/15), and do
(C) + the enumeration fix; consider (B) later if instrument metadata is reliable.

## Action items

- [x] **Keep `AUTO` as the default** in A386; do not copy A366's fixed 20/15.
- [x] **Add a read-only recommendations field** (`09_diann_mass_acc_recommendations`,
      `modifiable=false` STRING) to the A386 executable XML — both the source
      (`bfabric_executable/executable_A386_DIANN_3.2.xml`) and the deployed copy
      (`slurmworker/config/A386_DIANN_23/executable_A386_DIANN23plus.xml`). The
      parser ignores the key (`parse_flat_params` only maps keys in
      `BFABRIC_TO_DRUNNER`), so it is display-only and cannot affect a run.
- [x] **Add `4/5/7` ppm to the MS1/MS2 enumerations** in both A386 executable XMLs
      (now `4/5/7/10/15/20/AUTO`), so the recommended high-res Orbitrap/Astral
      values are selectable.
- [ ] **VERIFY rendering on the B-Fabric test instance:** does the read-only field
      show the `<value>` with line breaks? B-Fabric may collapse newlines in a STRING
      widget. If so, fall back to a single-line pipe-separated value or move the text
      into `<description>`.
- [ ] **Re-upload / re-register** the updated A386 executable in B-Fabric for the new
      field + dropdown values to appear (XML edits alone don't change the live app).
- [ ] **Confirm the FGCZ instrument fleet** for this app (Orbitrap Exploris /
      Fusion Lumos / Astral, Bruker timsTOF, …) to sanity-check the quoted numbers.
- [x] **SUSHI enums aligned:** `DIANNApp.rb` MS1/MS2 now
      `['AUTO','4','5','7','10','15','20']`, matching the A386 executable. (SUSHI
      still has no clean read-only guidance field — the recommendation text lives
      only in the B-Fabric executable.)
- [ ] **Document the calibrate-then-fix workflow** in `docs/DIANN_PARAMETERS.md`
      / app help (the "don't rely on auto" note at line 634 is blunt and could be
      read as "always fix to 20/15", which is wrong).
- [ ] **(C)** Extract "Averaged recommended settings for this experiment" from the
      DIA-NN log into the QC report (parse in `qc_report.py` / `snakemake_helpers`).
- [ ] **(B, optional)** Instrument-preset dropdown once metadata is confirmed.
- [ ] **Retire / migrate A366** if it is still pointing users at fixed 20/15.

## References

- DIA-NN README (settings, automatic vs fixed, instrument values, "first run"
  caveat, "Averaged recommended settings"): https://github.com/vdemichev/DiaNN
- Repo's compiled parameter notes: `docs/DIANN_PARAMETERS.md:103-143`
- Example of the "auto-recommend then fix" practice in the literature (QuantUMS):
  https://www.nature.com/articles/s41587-026-03131-2
