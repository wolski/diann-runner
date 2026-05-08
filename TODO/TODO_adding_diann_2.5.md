# Adding DIA-NN 2.5.0 alongside 2.3.2 (production)

DIA-NN 2.5.0 ships a managed Thermo `.raw` reader (RawWrapper.dll +
ThermoFisher.CommonCore.*.dll) requiring .NET 8. We want to support both
versions side-by-side via a Bfabric dropdown, with 2.3.2 staying default until
2.5.0 has been validated in production.

Status: approved 2026-05-08. Smoke test of `diann:2.5.0-thermo` on
`LFQ_Astral_DIA_15min_50ng_Condition_A_REP1.raw` passed end-to-end (10 237
protein groups @ 1% global q-value, no errors related to the Thermo reader).

## Semantics matrix

| Version | Converter             | Behavior                                            |
|---------|-----------------------|-----------------------------------------------------|
| 2.3.2   | thermoraw             | `.raw` → mzML via thermoraw → DIA-NN 2.3.2 (today)  |
| 2.3.2   | msconvert             | `.raw` → mzML via msconvert → DIA-NN 2.3.2 (today)  |
| 2.3.2   | msconvert-demultiplex | `.raw` → mzML demux → DIA-NN 2.3.2 (today)          |
| **2.5.0** | **thermoraw**         | **`.raw` straight into DIA-NN 2.5 (no conversion)** |
| 2.5.0   | msconvert             | `.raw` → mzML via msconvert → DIA-NN 2.5            |
| 2.5.0   | msconvert-demultiplex | `.raw` → mzML demux → DIA-NN 2.5                    |

`thermoraw` under 2.5.0 means "use DIA-NN's built-in Thermo reader". msconvert
paths still convert (kept for demultiplexing / FAIMS / non-standard cases).
`.d.zip` and `.mzML` inputs are unaffected — the version dropdown only changes
which DIA-NN image runs.

## XML changes (`bfabric_executable/executable_A386_DIANN_3.2.xml`)

Add a new numbered parameter near the converter dropdown:

```xml
<parameter>
  <name>01_diann_version</name>
  <type>String</type>
  <enumeration>2.3.2</enumeration>
  <enumeration>2.5.0</enumeration>
  <value>2.3.2</value>   <!-- default: keep production stable -->
</parameter>
```

Existing `raw_converter` enum (`thermoraw`, `msconvert`, `msconvert-demultiplex`)
stays exactly as-is.

`98_diann_binary` (parses to `diann['diann_bin']`): keep as a power-user
override. If set, wins; otherwise the version dropdown picks the image from a
server-side map.

## Server-side image map

`src/diann_runner/config/defaults_server.yml` and `defaults_local.yml`:

```yaml
diann_images:
  "2.3.2": "diann:2.3.2"
  "2.5.0": "diann:2.5.0-thermo"
# legacy single-image key kept as fallback for old params.yml without 01_diann_version:
diann_docker_image: "diann:2.3.2"
```

## Code touchpoints

1. **`snakemake_helpers.py:parse_flat_params()`** — parse `01_diann_version`
   into `diann['diann_version']`. Keep `98_diann_binary` parsing untouched.
2. **`snakemake_helpers.py:create_diann_workflow()`** — image resolution order:
   `diann_bin` (XML 98) → `diann_images[diann_version]` → `diann_docker_image`
   (legacy). Fail fast if none resolve.
3. **`Snakefile.DIANN3step.smk` `get_converted_file()` (line 126)** — compute
   `raw_native = (diann_version == "2.5.0" and converter == "thermoraw" and INPUT_TYPE == "raw")`.
   When true, return `RAW_DIR / f"{sample}.raw"`; else current logic. Existing
   `convert_raw` rule stays in the file; it just doesn't fire when nobody
   requests its mzML output.
4. **Tests** — add cases for:
   - `parse_flat_params` (the new key parses correctly)
   - image resolution in `create_diann_workflow` (override vs map vs legacy)
   - `get_diann_input_file` covering the 6 cells of the matrix above plus
     d.zip / mzML passthroughs
5. **Docker** — build & push both images: keep `diann:2.3.2`, add
   `diann:2.5.0-thermo` from `docker/Dockerfile.diann_thermofilereader`.
6. **CLAUDE.md** — short note in the Bfabric Parameter Flow section about the
   version dropdown and the version × converter matrix above.
7. **`deploy.smk`** — currently has a single `build_diann_docker` rule
   (`docker/Dockerfile.diann`, default `DIANN_VERSION=2.3.2`) and an `all`
   target that depends on its flag plus `thermorawfileparser_docker_built.flag`.
   Add a parallel `build_diann_thermo_docker` rule:
   - dockerfile: `docker/Dockerfile.diann_thermofilereader`
   - tag: `diann:${DIANN_THERMO_VERSION}-thermo` (default `2.5.0`)
   - flag: `FLAGS_DIR / "diann_thermo_docker_built.flag"`
   - same skip-if-image-exists / `force_rebuild` logic as the existing rule
   Wire its flag into the `all` target's input list and into
   `check_docker_images()` (in `snakemake_helpers.py`) so deployment validates
   both images. Add `diann_thermo_version` config option (mirroring the
   existing `diann_version`) and update the cleanup rule to also `docker rmi`
   the thermo image.

## Decisions (locked in)

- Default version in XML: **2.3.2** (safe rollout).
- `98_diann_binary`: **kept** as silent power-user override.
- 2.5 image tag: **`diann:2.5.0-thermo`**.
- XML key number: **`01_diann_version`** (top of the form, before converter).

## Rollout

1. Land XML + parsing + Snakefile dispatch + tests, default
   `01_diann_version: 2.3.2` → zero behavior change for current workunits.
2. Build/tag `diann:2.5.0-thermo` on the FGCZ server via
   `snakemake -s deploy.smk build_diann_thermo_docker --cores 1`.
3. Manual test: run a workunit with `01_diann_version=2.5.0,
   raw_converter=thermoraw` on a small dataset.
4. Once green, leave 2.3.2 as default; users opt-in to 2.5.0 per workunit.
