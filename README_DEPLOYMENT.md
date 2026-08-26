# Deployment Guide

This repo is deployed in two different ways:

- `deploy.smk` builds or verifies the Docker images used by `diann_runner`.
- The FGCZ production app is run through the separate `slurmworker` repo, which installs `diann_runner` from the git revision locked in `pylock.toml`.

For ordinary workflow code changes, such as edits to `Snakefile.DIANN3step.smk` or Python helpers, push the `diann_runner` change, regenerate the slurmworker lockfile on the development machine, then pull `slurmworker` on production. You do not need to rebuild Docker images unless a Dockerfile, Docker image version, or container dependency changed.

## Container Runtime

The CLI wrappers (`diann-docker`, `thermoraw`, `prolfquapp-docker`) work with either Docker or Apptainer. Selection defaults to **automatic**, but can be pinned. `load_deploy_config()` resolves the runtime by precedence:

1. an explicit per-invocation override — `run-diann --runtime docker`, or `diann-snakemake --config container_runtime=docker`;
2. a `container_runtime:` key in `defaults_server.yml`;
3. host auto-detection — `detect_runtime()` checks `PATH` and picks `apptainer` if installed, otherwise `docker`.

The override exists for a host that has apptainer installed but no populated SIF cache: it uses docker without editing any config. The deployed `app.yml` process command relies on this and passes `--docker`.

The shipped `src/diann_runner/config/defaults_server.yml` carries both runtime blocks:

```yaml
images:
  docker:
    diann_images: { "2.3.2": "diann:2.3.2", "2.5.0": "diann:2.5.0", "2.5.1": "diann:2.5.1", "2.6.0": "diann:2.6.0", "2.6.1": "diann:2.6.1" }
    diann_docker_image: "diann:2.3.2"     # legacy fallback for params.yml without pipeline_diann_version
    thermoraw_image: "thermorawfileparser:2.0.0"
    msconvert_docker: "chambm/pwiz-skyline-i-agree-to-the-vendor-licenses"
    prolfquapp_image: "ghcr.io/prolfqua/prolfquapp:2.9.0"
  apptainer:
    diann_images: { "2.3.2": "/misc/container/exp/diann/diann-2.3.2.sif", ... }
    thermoraw_image: "/misc/container/exp/thermorawfileparser/thermorawfileparser-2.0.0.sif"
    msconvert_docker: "/misc/container/exp/pwiz/pwiz-2026-08-26.sif"   # untagged upstream; date = capture
    prolfquapp_image: "/misc/container/exp/prolfquapp/prolfquapp-2.9.0.sif"
```

The DIA-NN keys are the `pipeline_diann_version` dropdown values from the B-Fabric executable, so the two must be kept in step: adding a version to the GUI enumeration without adding its image here yields a KeyError at runtime.

`prolfquapp_image` must track the DIA-NN output format the runner produces — an image too old for DIA-NN 2.5+ parquet fails QC. It is the single source of truth for the SIF too: `deploy.smk` derives both the pulled reference (registry included) and the SIF filename from it.

### Bumping prolfquapp without a diann_runner release

`PROLFQUAPP_IMAGE` in the environment overrides `prolfquapp_image` for whichever runtime block was selected. The A386 app sets it in `app.yml`, the same way A414_DEA does:

```yaml
      process:
        command: python -m diann_runner.run_diann_cli apprunner --docker ... --work-dir
        env:
          PROLFQUAPP_IMAGE: ghcr.io/prolfqua/prolfquapp:2.9.0
```

So a QC image bump is a one-line `slurmworker` change plus a pull on the deploy host — no `diann_runner` commit, no `pylock.toml` regeneration. Under apptainer the value is a SIF path.

The catch: `deploy.smk` reads the config, not the environment. An image set only via `PROLFQUAPP_IMAGE` is never built or pulled by a local `deploy.smk` run, so it must already exist in the registry (or as a SIF). Keep `defaults_server.yml` in step when you intend the new version to be the built default.

Migrating a host from Docker to Apptainer is purely an ops action: install `apptainer`, make sure the SIFs are installed (see below), pull `slurmworker`. No `diann_runner` config change needed.

### Apptainer: where SIFs live

SIFs follow the FGCZ apptainer standard (slurmworker `docs/apptainer-build.md`):

```
/misc/container/exp/<app>/<app>-<version>.sif
```

The version in the filename is the reproducibility anchor — bump the path, never overwrite an installed SIF in place. That path is what `images.apptainer` in `defaults_server.yml` points at, and what a job invokes directly: Apptainer does **not** pull it, so it must already exist and be readable on every node the job can land on.

**Building and installing are separate steps, deliberately.** `/misc/container/exp` is a privileged NFS export that compute nodes mount read-only, so `deploy.smk` cannot write it. It builds into `deploy.sif_staging_dir` (node-local scratch, `${USER}` expanded) with the installed filenames already applied; `scripts/install_sif.py` does the copy to the NFS host:

```bash
snakemake -s deploy.smk all_sif --cores 1        # -> /scratch/$USER/sif/diann-2.6.1.sif
python3 scripts/install_sif.py --dry-run         # what would be copied where
python3 scripts/install_sif.py                   # validate + scp to the export
```

`install_sif.py` validates each SIF with `apptainer inspect`, skips any version already installed rather than overwriting it, and derives the per-app directory from the filename. It needs to run from a host that reaches the NFS host directly, with write access to the export — `ls -ld /export/nfs4/container/exp/<app>/` shows who that is. The install host and root come from the `deploy:` block.

Keep the previous SIF in place until the new one has been validated in a real run, so a rollback is just repointing the config.

### Apptainer Host Setup

Tested with `apptainer version 1.4.2`. `deploy.smk all_sif` offers two builders, selected via `--config sif_builder={native,docker}`:

#### Option A — Native builder (default; apptainer-only host, no docker needed)

Run on a host that has apptainer but no docker. `deploy.smk` calls [spython](https://github.com/singularityhub/singularity-cli) to translate each Dockerfile into an apptainer `.def` file under `build/`, then runs `apptainer build` directly. `spython` is a runtime dependency of `diann_runner`, so it's already installed.

```bash
# On the apptainer host, e.g. fgcz-c-043
cd /scratch/diann-runner   # or wherever the repo is checked out
snakemake -s deploy.smk all_sif --cores 1
```

The `.def` files are regenerated from the Dockerfiles every time the Dockerfile changes — there's no parallel apptainer recipe to drift out of sync. Build versions are pinned via `--build-arg`–style overrides applied to the generated `.def`.

Native builder requires apptainer's user-namespace to be configured on the host (no `--fakeroot` flag needed if `apptainer build /tmp/test.sif docker://hello-world` works without sudo on that host).

#### Option B — Docker builder (requires docker + apptainer)

Run on a host with **both** docker (daemon running) and apptainer. Locally-built images come from the docker daemon via `docker-daemon://`; upstream images (msconvert, prolfquapp) come from Docker Hub via `docker://`.

```bash
snakemake -s deploy.smk all_sif --cores 1 --config sif_builder=docker
snakemake -s deploy.smk all_sif --cores 1 --config sif_builder=docker sif_staging_dir=./sif
```

Then install from the staging dir as above:

```bash
python3 scripts/install_sif.py --staging-dir ./sif
```

#### Option C — Pull from a registry on the apptainer host

If you have a registry the apptainer host can reach (and the locally-built images have been pushed to it), pull directly without `deploy.smk`:

```bash
mkdir -p "/scratch/$(id -un)/sif"
apptainer pull "/scratch/$(id -un)/sif/diann-2.3.2.sif" docker://<registry>/diann:2.3.2
apptainer pull "/scratch/$(id -un)/sif/pwiz-2026-08-26.sif" docker://chambm/pwiz-skyline-i-agree-to-the-vendor-licenses
python3 scripts/install_sif.py
```

Useful when several apptainer hosts share the same registry. Name the file as it will be installed — `install_sif.py` derives the target directory from the filename.

#### Build rules summary

`deploy.smk` registers these rules for the SIF path:

- `build_diann_sif` (one per DIA-NN version in `diann_images`), `build_thermorawfileparser_sif` — body depends on `sif_builder`:
  - `docker`: `apptainer pull docker-daemon://<tag>`
  - `native`: `apptainer build <sif> <generated.def>`
- `generate_diann_def` (one per version), `generate_thermorawfileparser_def` — only when `sif_builder=native`; spython conversion
- `pull_msconvert_sif`, `pull_prolfquapp_sif` — same in both modes (`apptainer pull docker://<ref>`, no docker needed)
- `sif_deployment_complete` — combined marker

All deploy configuration lives in one file, `src/diann_runner/config/defaults_server.yml` — the same file the runtime workflow reads, so nothing can drift. Image versions (DIA-NN, thermorawfileparser, prolfquapp, msconvert) are derived from its `images:` block; build-time knobs (`sif_staging_dir`, `sif_builder`, `force_rebuild`, the `sif_install_*` target, `msconvert_capture_date`) live in its `deploy:` block. Override any of them for a one-off build with `--config key=value`.

#### Verify

```bash
python3 -c "from diann_runner.container_utils import detect_runtime; print(detect_runtime())"
# Expected: apptainer

apptainer exec /misc/container/exp/diann/diann-2.3.2.sif diann --help
diann-docker --runtime apptainer --image /misc/container/exp/diann/diann-2.3.2.sif -- --help
```

Note for msconvert: Wine inside the pwiz image needs a writable `$WINEPREFIX`. The `thermoraw` wrapper handles this automatically under apptainer by adding `--writable-tmpfs --env WINEPREFIX=/tmp/.wine` to the `apptainer exec` invocation. No setup required.

## Production Update

Use this after changing `diann_runner` workflow code.

On the development machine, push the `diann_runner` change:

```bash
cd ~/projects/diann_runner
git push
```

Then regenerate and push the app lockfile from the development-machine `slurmworker` checkout:

```bash
cd ~/projects/slurmworker/config/A386_DIANN_23
./make_lock.sh
```

Use the script rather than running the `uv` commands by hand. It does four things, and the middle two are the reason it exists:

1. `uv lock -U && uv sync && uv export --format pylock.toml -o pylock.toml --no-emit-project`
2. **Strips every `polars-lts-cpu` package block.** `uv export --format pylock.toml` drops environment markers, so bfabric's macOS-x86_64-only `polars-lts-cpu` becomes installable on the Linux host, collides with `polars-runtime-32`, and leaves a `polars` that will not import — `dispatch.py` then dies before writing `chunks.yml`.
3. **Verifies the export** in a throwaway 3.13 venv (`uv pip install -r pylock.toml`, then imports `polars` and `bfabric.entities.Dataset`), so a non-installable lock is never committed.
4. `git add pylock.toml pyproject.toml`, commit `update pylock`, push — only if something changed.

It runs under `set -exo pipefail` and tees everything, including the `set -x` trace, to `A386_DIANN_23/log` (gitignored). Read that file when it fails.

On the production machine, pull the updated `slurmworker` checkout:

```bash
cd /home/bfabric/slurmworker
git pull
```

The important point is that `A386_DIANN_23/pyproject.toml` references `diann_runner` through git:

```toml
diann-runner @ git+https://github.com/wolski/diann-runner.git
```

The lockfile pins the exact revision. Production gets that pin by pulling the updated `slurmworker` repo.

## Docker Deployment

Use this only for first-time setup or Docker-related changes.

Prerequisites:

- Python 3.12+
- Docker with the daemon running
- Git
- Snakemake
- `uv`
- Enough disk space for Docker images

Run from the `diann_runner` repo:

```bash
snakemake -s deploy.smk --cores 1 --dry-run
snakemake -s deploy.smk --cores 1
```

Force Docker image rebuilds:

```bash
snakemake -s deploy.smk --cores 1 --config force_rebuild=true
```

Build or verify a specific image (target its flag; one per `diann_images` version):

```bash
snakemake -s deploy.smk .deploy_flags/diann_2.5.1_built.flag --cores 1
snakemake -s deploy.smk check_images --cores 1
```

## Verification

Check the Python tools:

```bash
source .venv/bin/activate
diann-docker --help
diann-qc --help
diann-snakemake --help
```

Check Docker images:

```bash
docker images | grep -E "^(diann|thermorawfileparser)"
```

Run the test suite before deploying code changes:

```bash
uv run pytest tests/
```

## How Production Runs

The production app lives in the `slurmworker` repository:

```text
/home/bfabric/slurmworker/config/A386_DIANN_23/
  app.yml
  dispatch.py
  pyproject.toml
  pylock.toml
```

That app depends on the git-pinned `diann_runner` package:

```toml
diann-runner @ git+https://github.com/wolski/diann-runner.git
```

Execution flow:

1. `make dispatch` creates `params.yml` and `inputs.yml`.
2. `make inputs` downloads the input files.
3. `make process` runs `diann_runner.snakemake_cli`.
4. `make stage` uploads the generated outputs.

For local integration testing:

```bash
bfabric-app-runner prepare workunit \
  --app-spec ~/projects/slurmworker/config/A386_DIANN_23/app.yml \
  --work-dir WU338923 --workunit-ref 338923 --read-only \
  --force-app-version devel

cd WU338923
make run-all
```

## Cleanup

Remove deployment flags and allow `deploy.smk` to rerun:

```bash
snakemake -s deploy.smk clean --cores 1
snakemake -s deploy.smk --cores 1
```

Remove flags and Docker images:

```bash
snakemake -s deploy.smk clean_all --cores 1
```

`clean_all` removes only the tags currently listed in `diann_images` (currently `diann:2.3.2`, `diann:2.5.0`, `diann:2.5.1`, `diann:2.6.0`, `diann:2.6.1`) plus `thermorawfileparser`. Tags dropped from that list are left behind — remove those by hand.

### Removing old images after the .NET 8 unification

DIA-NN images were unified onto a single Debian + .NET 8 `Dockerfile.diann`, and the per-version `-thermo` tag suffix was dropped — tags are now `diann:2.5.0` / `diann:2.5.1` (all read Thermo `.raw` natively). Two kinds of stale artifacts can linger:

**1. Orphaned `-thermo` images.** `clean_all` does not touch these (they are no longer in `diann_images`), so remove them by hand:

```bash
# Docker host
docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^diann:.*-thermo$' | xargs -r docker rmi
docker image prune -f      # drop now-dangling layers (old Ubuntu base, etc.)
```

```bash
# Apptainer host
rm -f "/scratch/$(id -un)/sif/"diann-*-thermo.sif
```

**2. Reused tags built on the old base.** `diann:2.3.2` keeps its name, but its base changed (Ubuntu → Debian + .NET 8). Force a rebuild so it gains native `.raw` support, then refresh the SIFs:

```bash
snakemake -s deploy.smk --cores 1 --config force_rebuild=true
# Apptainer: re-pull/rebuild SIFs (delete stale ones first if names are unchanged)
rm -f "/scratch/$(id -un)/sif/"diann-{2.3.2,2.5.0,2.5.1,2.6.0,2.6.1}.sif
snakemake -s deploy.smk all_sif --cores 1
```

## Troubleshooting

Docker daemon:

```bash
docker ps
```

Disk space:

```bash
df -h .
```

Deployment logs:

```bash
ls logs/
cat logs/build_diann_2.3.2.log
```

Snakemake dry run:

```bash
snakemake -s deploy.smk --cores 1 --dry-run
```
