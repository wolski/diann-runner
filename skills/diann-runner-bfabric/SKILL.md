---
name: diann-runner-bfabric
description: Deploy, change, reproduce, and verify the FGCZ B-Fabric A386 DIA-NN application (diann_runner driven through slurmworker/config/A386_DIANN_23). Use when a DIA-NN workunit fails or runs the wrong code, when a workflow change must reach production, when a GUI parameter has to be added or edited in the A386 executable, when pylock.toml / make_lock.sh must be regenerated, when DIA-NN / thermorawfileparser / msconvert / prolfquapp images or SIFs need building, when docker-versus-apptainer runtime selection is in question, or when a workunit has to be reproduced locally with bfabric-app-runner. Covers the executable-YAML source of truth, the flat-key parameter flow into DiannWorkflow, and the three separate deploy paths.
---

# A386 DIA-NN application on B-Fabric

## The chain

```
B-Fabric A386 application
  -> executable (GUI parameter definitions)          bfabric_executable/executable_A386_DIANN_3.2.yaml
  -> app.yml                                         slurmworker/config/A386_DIANN_23/app.yml
  -> dispatch.py            workunit -> work/params.yml + work/inputs.yml
  -> pylock.toml            pins the diann_runner git revision
  -> diann_runner           run_diann_cli apprunner -> Snakefile.DIANN3step.smk
  -> container runtime      docker images or apptainer SIFs
```

Three independent things can be out of date, and they deploy differently.
Identify which one before touching anything:

| Symptom | What is stale | Path |
|---|---|---|
| Workflow logic, helper, or Snakefile change not taking effect | `pylock.toml` git pin | [A — workflow code](#path-a--workflow-code) |
| Parameter missing/wrong in the B-Fabric GUI; new enum value | executable definition | [B — executable](#path-b--gui-parameters) |
| Wrong DIA-NN version available; image or SIF missing | images / installed SIFs | [C — containers](#path-c--containers) |

## Load first, and resolve the placeholders

`bfabric-app-runner` (app-spec fields, work-dir layout, phase-by-phase
debugging) and `compms-infrastructure` (deploy host, partitions, `/scratch` and
`/misc/fgcz01` layout) own the layer underneath this skill. Add `bfabric-query`
for B-Fabric reads and `bfabric-tools` for any B-Fabric write.
`fix-prolfqua-dea-app` is the sibling skill for A414 and shares the
image-drift and `application_version` reasoning.

- `<workspace>` — the directory holding the user's `diann_runner` and
  `slurmworker` checkouts. Ask; do not clone before confirming none exists.
- `<deploy-host>` — the machine holding `/home/bfabric/slurmworker`. Take it
  from `compms-infrastructure` or ask. It is **not** necessarily the host that
  ran the container, and the in-repo docs do not record it (see
  [What is still unresolved](#what-is-still-unresolved)).

## Consent before the first connection

The deploy host and the compute nodes are shared production machines. Ask before
connecting at all, not only before mutating. Ask a second time for anything that
writes state: `prepare workunit` / `make dispatch` / `make inputs` (these create
directories and pull customer data onto shared storage), `docker build` /
`docker pull` / `apptainer build`, `make upload` against B-Fabric,
`make_lock.sh` (it commits **and pushes**), a `git pull` on the deploy host,
staging outputs, or editing a B-Fabric record.

`--read-only` on `prepare workunit` protects **B-Fabric**, not the node: it
still writes a work dir and still downloads production inputs.

## Read-only orientation first

```bash
bfabric-cli api read workunit id <workunit-id> --format json
bfabric-cli api read comment parentid <workunit-id> parentclassname Workunit --format json

# What is actually deployed, as opposed to what the repo says
ssh <deploy-host> 'git -C /home/bfabric/slurmworker log -1 --format="%h %cI %s"'
ssh <deploy-host> 'grep -A2 "diann-runner" /home/bfabric/slurmworker/config/A386_DIANN_23/pylock.toml'
```

The `pylock.toml` pin is the ground truth for which `diann_runner` revision ran.
A pushed `diann_runner` commit changes nothing in production until the lock is
regenerated and pulled.

## Path A — workflow code

For edits to `Snakefile.DIANN3step.smk`, `src/diann_runner/*.py`, or any
`diann_runner` Python helper. No image rebuild is needed unless a Dockerfile,
an image version, or a container dependency changed.

```bash
# 1. push diann_runner
cd <workspace>/diann_runner
git push

# 2. regenerate the pin, from the development-machine slurmworker checkout
cd <workspace>/slurmworker/config/A386_DIANN_23
./make_lock.sh          # commits AND pushes — consent required

# 3. production picks up the new pin
ssh <deploy-host> 'git -C /home/bfabric/slurmworker pull'
```

`A386_DIANN_23/pyproject.toml` depends on
`diann-runner @ git+https://github.com/wolski/diann-runner.git`, unpinned;
`pylock.toml` carries the exact revision.

### make_lock.sh does more than `uv export`

Do not hand-run the three `uv` commands the older docs list — the script exists
because the plain export is broken:

1. `uv lock -U && uv sync && uv export --format pylock.toml --no-emit-project`
2. **Strips every `polars-lts-cpu` package block.** `uv export` drops
   environment markers, so B-Fabric's macOS-x86_64-only `polars-lts-cpu`
   becomes installable on the Linux host, collides with `polars-runtime-32`, and
   leaves a `polars` that will not import — `dispatch.py` then dies before
   writing `chunks.yml`.
3. **Verifies the export** in a throwaway 3.13 venv (`uv pip install -r
   pylock.toml`, then imports `polars` and `bfabric.entities.Dataset`) so a
   non-installable lock is never committed.
4. `git add pylock.toml pyproject.toml`, commit `update pylock`, push — only if
   something changed.

`set -exo pipefail`, and everything is teed to `A386_DIANN_23/log` (gitignored).
Read that file when the script fails.

## Path B — GUI parameters

**The executable YAML is the source of truth**, not XML. Parameter values,
enumerations, defaults, and sentinel strings are defined there and flow one way:

```
executable YAML -> B-Fabric GUI -> work/params.yml (flat keys)
  -> parse_flat_params()  (snakemake_helpers.py)
  -> create_diann_workflow() -> DiannWorkflow -> DIA-NN CLI flags
  -> tests
```

Adding or changing a parameter, in order:

1. Edit the YAML — key, `label`, `description`, `type`, `enumeration`, `value`.
2. Add parsing in `parse_flat_params()` in `src/diann_runner/snakemake_helpers.py`.
   Complex Python belongs there, never in the Snakefile.
3. Wire it through `create_diann_workflow()` and `_build_common_params()` if it
   maps to a DIA-NN flag.
4. Update tests to the YAML's exact strings — sentinels are uppercase (`AUTO`,
   `NONE`). Tests reflect the UI, not the reverse.

Flat keys use hierarchical numbering or a `pipeline_`/`input_` prefix; order in
the file drives GUI layout. Current examples: `pipeline_diann_version`
(enum `2.3.2` / `2.5.0` / `2.5.1` / `2.6.0` / `2.6.1`, default `2.3.2`),
`pipeline_workflow_mode` (`two_step` / `single_step`), `pipeline_is_dda`,
`06a_diann_mods_variable`, `11b_diann_protein_relaxed_prot_inf`,
`12a_diann_quantification_reanalyse`.

### Upload only CREATES — it never updates

Use the Makefile in `bfabric_executable/`:

```bash
cd <workspace>/diann_runner/bfabric_executable
make validate                 # top level is exactly `executable:`, no id, has parameters
make upload ENV=TEST          # create a NEW executable on the TEST instance
make upload                   # ... on PRODUCTION (default ENV)
make dump ID=<executable-id>  # scratch dumped_<ID>.xml, for reference/diffing only
```

`bfabric-cli executable upload` rejects any `id` key and calls
`client.save("executable", data)` without one, so B-Fabric always creates a new
record and prints its id. It cannot modify the executable the A386 application
is wired to. To **update in place**, either use the web GUI **Edit**, or `save`
with the id present:

```python
from bfabric import Bfabric
client = Bfabric.connect()            # set BFABRICPY_CONFIG_ENV=TEST first
client.save("executable", {"id": <executable-id>, "name": "A386_DIANN_v2.3.0",
                           "program": "/home/bfabric/slurmworker/config/A386_DIANN_23/app.yml",
                           "parameter": [...]})
```

Verify nested-parameter replacement semantics on TEST before PRODUCTION —
`parameter` is replaced wholesale, not merged. `~/.bfabricpy.yml` holds the
**web-service password**, not the login password.

`make dump` writes only scratch `dumped_<ID>.xml` and refuses to overwrite; it
never rewrites a source `*.yaml`. A GUI "XML Export" is **not** uploadable —
its root and per-parameter `@`-attributes make `xmltodict` produce `@classname`
keys and SUDS aborts with `suds.TypeNotFound`.

### The executable YAML exists twice

`diann_runner/bfabric_executable/executable_A386_DIANN_3.2.yaml` and
`slurmworker/config/A386_DIANN_23/executable_A386_DIANN23plus.yaml` are
currently byte-identical copies with different names, in different repos. There
is no sync mechanism. After editing one, diff the other and copy it across, or
the next reader edits the stale one.

## Path C — containers

### Runtime selection is automatic

`load_deploy_config()` calls `detect_runtime()`, which inspects `PATH` and
picks `apptainer` if installed, otherwise `docker`. To override on a host that
has apptainer but no populated SIF cache, either set `container_runtime: docker`
in `src/diann_runner/config/defaults_server.yml` or pass `--docker` — which is
what the deployed `app.yml` process command already does.

`src/diann_runner/config/defaults_server.yml` is the single config for both
runtime and build: an `images:` block with parallel `docker:` and `apptainer:`
sub-blocks (DIA-NN per version, `thermoraw_image`, `msconvert_docker`,
`prolfquapp_image`), and a `deploy:` block (`sif_staging_dir`, `sif_builder`,
`force_rebuild`, the `sif_install_*` target). `deploy.smk` derives image versions from the `images:` block,
so build and runtime cannot drift. Override for a one-off with
`--config key=value`.

Migrating a host to apptainer is ops-only: install apptainer, make sure the
SIFs are installed, pull `slurmworker`. No `diann_runner` change.

### SIFs: build to scratch, install separately

Installed SIFs follow the FGCZ standard,
`/misc/container/exp/<app>/<app>-<version>.sif` (slurmworker
`docs/apptainer-build.md`). The version in the filename is the reproducibility
anchor: bump the path, never overwrite an installed SIF. A job invokes that path
directly — apptainer does not pull it, so it must already exist on every node
the job can land on.

`deploy.smk` cannot write there; `/misc/container/exp` is a privileged NFS
export. It builds into `deploy.sif_staging_dir` (node-local scratch, `${USER}`
expanded) using the installed filenames, and `scripts/install_sif.py` copies to
the NFS host — validating each SIF, and skipping rather than overwriting a
version already installed. Installing needs a host that reaches the NFS host
with write access to the export, so it is a consent-worthy step.

pwiz is the one exception to version-in-filename: upstream publishes no usable
tag, so the filename carries `deploy.msconvert_capture_date` instead.

### Building

```bash
cd <workspace>/diann_runner

# Docker images
snakemake -s deploy.smk --cores 1 --dry-run
snakemake -s deploy.smk --cores 1
snakemake -s deploy.smk --cores 1 --config force_rebuild=true
snakemake -s deploy.smk check_images --cores 1
snakemake -s deploy.smk .deploy_flags/diann_2.5.1_built.flag --cores 1

# SIFs — sif_builder=native (the default) needs no docker: spython converts each
# Dockerfile to a .def under build/, then `apptainer build`. Output goes to the
# staging dir, NOT the shared export.
snakemake -s deploy.smk all_sif --cores 1
# sif_builder=docker converts local docker images via docker-daemon://
snakemake -s deploy.smk all_sif --cores 1 --config sif_builder=docker

# Then install (asks for nothing — check --dry-run first)
python3 scripts/install_sif.py --dry-run
python3 scripts/install_sif.py
```

Native builds need apptainer's user namespace configured — check with
`apptainer build /tmp/test.sif docker://hello-world` succeeding without sudo.
`pull_msconvert_sif` and `pull_prolfquapp_sif` use `apptainer pull docker://`
in both modes and need no docker. `.def` files are regenerated from the
Dockerfiles, so there is no parallel apptainer recipe to drift.

Cleanup: `snakemake -s deploy.smk clean --cores 1` drops flags;
`clean_all` also removes images — but only the tags currently listed in
`diann_images`. Renamed or dropped tags (the old `diann:*-thermo` suffix) must
go by hand, and a reused tag whose base image changed needs
`--config force_rebuild=true` plus deletion of the stale SIF from staging.
Nothing needs deleting under `/misc/container/exp`: an installed SIF is never
overwritten, so a rebuild lands on a new version path.

The prolfquapp image must track the DIA-NN output format the runner produces —
an image too old for DIA-NN 2.5+ parquet fails QC.

To bump it for the running app, set `PROLFQUAPP_IMAGE` in the `process` `env:`
block of `slurmworker/config/A386_DIANN_23/app.yml` — it overrides
`prolfquapp_image` for whichever runtime block was selected, so the bump needs
no `diann_runner` commit and no `pylock.toml` regeneration. This is the same
variable A414_DEA uses. Under apptainer the value is a SIF path.

`deploy.smk` reads the config rather than the environment, so an image set only
via the env var is never built locally and must already exist in the registry.
Bump `defaults_server.yml` too when the new version should be the built default.

### Verify

```bash
python3 -c "from diann_runner.container_utils import detect_runtime; print(detect_runtime())"
apptainer exec /misc/container/exp/diann/diann-2.3.2.sif diann --help
diann-docker --runtime apptainer --image /misc/container/exp/diann/diann-2.3.2.sif -- --help
docker images | grep -E "^(diann|thermorawfileparser)"
```

msconvert needs no setup: the `thermoraw` wrapper adds
`--writable-tmpfs --env WINEPREFIX=/tmp/.wine` under apptainer for Wine.

## Reproduce a workunit locally

```bash
uv tool install -p 3.13 bfabric-app-runner

bfabric-app-runner prepare workunit \
  --app-spec <workspace>/slurmworker/config/A386_DIANN_23/app.yml \
  --work-dir WU<workunit-id> --workunit-ref <workunit-id> --read-only \
  --force-app-version devel

cd WU<workunit-id>
make run-all      # or: make dispatch && make inputs && make process && make stage
```

`app.yml` defines version `2.3` (production, absolute `/home/bfabric` paths)
plus `devel` and `devel_linux`, which point at a developer workspace. The
`devel` entries carry hardcoded personal paths — edit them to your own
`<workspace>` before using `--force-app-version devel`.

Two `app.yml` details that break silently if disturbed:

- The `process` command **must end with `--work-dir`**. AppRunner appends the
  work dir as a trailing argument, and that flag consumes it.
- `--docker` on the process command forces docker. Drop it on a host with a
  populated SIF cache.

`dispatch.py` writes into `<work-dir>/work/`: `params.yml` (the workunit's
`raw_parameters` plus `registration`) and `inputs.yml`. It handles two dataset
shapes — resource IDs become a single `bfabric_resource_dataset` input; relative
paths become one `file`/`ssh` input per row plus a `bfabric_dataset` parquet.
FASTA resolution: `input_fasta_databases`, or `input_fasta_additional` when the
first is `NONE`, with `--fasta-fallback <dir>` for local runs. `order.fasta` is
staged unconditionally and may legitimately be empty — the Snakemake
`get_fasta_paths` step skips an empty one.

Then `run_diann_cli apprunner` normalizes `params.yml` →
`diann_runner_params.toml` and `dataset.parquet` → `dataset.csv`, derives the
FASTA as `input/<input_fasta_databases basename>`, and defaults `output_dir` to
the work dir. Relative input paths resolve under `--work-dir`, not cwd.

Before deploying any code change: `uv run pytest tests/`.

## What is still unresolved

`docs/BFABRIC_DEPLOY.md`, `README_DEPLOYMENT.md`, and `AGENTS.md` were corrected
on 2026-08-25 to match the checkouts (executable YAML rather than XML, the real
`make_lock.sh` behaviour, the shared apptainer cache path, current image
versions, the `container_runtime` precedence). They are trustworthy as of that
date. Two things are still open, and both are traps:

- **The executable YAML is duplicated.**
  `diann_runner/bfabric_executable/executable_A386_DIANN_3.2.yaml` and
  `slurmworker/config/A386_DIANN_23/executable_A386_DIANN23plus.yaml` were
  byte-identical, in different repos, with no sync mechanism. Diff them before
  trusting either, and copy across after editing one.
- **The deploy host is not recorded consistently.** The old
  `docs/BFABRIC_DEPLOY.md` named one host; the `app.yml` comments name another.
  Neither was verifiable from the checkouts, so the docs now say "the deploy
  host" without naming it. Resolve `<deploy-host>` from `compms-infrastructure`
  or ask the user.

Also unverifiable from the repo: the **live executable id**. The old doc cited
`26960`, the Makefile's example is `40588`. Read it from B-Fabric; do not copy
either number.

When a doc and the code disagree, the code wins — `defaults_server.yml`,
`deploy.smk`, `app.yml`, and `make_lock.sh` are the ground truth, and these docs
have drifted from them once already.
