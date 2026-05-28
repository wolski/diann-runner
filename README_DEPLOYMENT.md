# Deployment Guide

This repo is deployed in two different ways:

- `deploy.smk` builds or verifies the Docker images used by `diann_runner`.
- The FGCZ production app is run through the separate `slurmworker` repo, which installs `diann_runner` from the git revision locked in `pylock.toml`.

For ordinary workflow code changes, such as edits to `Snakefile.DIANN3step.smk` or Python helpers, push the `diann_runner` change, regenerate the slurmworker lockfile on the development machine, then pull `slurmworker` on production. You do not need to rebuild Docker images unless a Dockerfile, Docker image version, or container dependency changed.

## Container Runtime

The CLI wrappers (`diann-docker`, `thermoraw`, `prolfquapp-docker`) work with either Docker or Apptainer. Selection is **automatic**: at workflow start, `load_deploy_config()` calls `detect_runtime()`, which checks `PATH` and picks `apptainer` if installed, otherwise `docker`. There is no per-host config file, no environment variable, and no UI knob — the host's installed runtime is the source of truth.

The shipped `src/diann_runner/config/defaults_server.yml` carries both runtime blocks:

```yaml
images:
  docker:
    diann_images: { "2.3.2": "diann:2.3.2", "2.5.0": "diann:2.5.0-thermo" }
    thermoraw_image: "thermorawfileparser:2.0.0"
    msconvert_docker: "chambm/pwiz-skyline-i-agree-to-the-vendor-licenses"
    prolfquapp_image: "prolfqua/prolfquapp:2.0.10"
  apptainer:
    diann_images: { "2.3.2": "/opt/sif/diann_2.3.2.sif", "2.5.0": "/opt/sif/diann_2.5.0-thermo.sif" }
    thermoraw_image: "/opt/sif/thermorawfileparser_2.0.0.sif"
    msconvert_docker: "/opt/sif/pwiz.sif"
    prolfquapp_image: "/opt/sif/prolfquapp_2.0.10.sif"
```

Migrating a host from Docker to Apptainer is purely an ops action: install `apptainer`, populate `/opt/sif/` (see below), pull `slurmworker`. No `diann_runner` config change needed.

### Apptainer Host Setup

Tested with `apptainer version 1.4.2`. The SIF paths in `defaults_server.yml` assume the `/opt/sif/` layout. Two ways to populate it:

#### Option A — Build SIFs on the docker host with `deploy.smk` (recommended)

Run on a host that has **both** docker (with daemon running) and apptainer installed. The locally-built images come from the docker daemon; the upstream images (msconvert, prolfquapp) come from Docker Hub.

```bash
snakemake -s deploy.smk all_sif --cores 1                    # build all SIFs into ./sif/
snakemake -s deploy.smk all_sif --cores 1 --config sif_output_dir=/opt/sif   # or write straight to /opt/sif
```

Then copy to the apptainer host:

```bash
rsync -av sif/ <apptainer-host>:/opt/sif/
```

`deploy.smk` adds these rules for the SIF path:

- `build_diann_sif`, `build_diann_thermo_sif`, `build_thermorawfileparser_sif` — `apptainer pull docker-daemon://<tag>`
- `pull_msconvert_sif`, `pull_prolfquapp_sif` — `apptainer pull docker://<ref>`
- `sif_deployment_complete` — combined marker

Versions and the msconvert image reference come from `deploy_config.yaml` (`thermoraw_version`, `prolfquapp_version`, `msconvert_image`) and default to the values in `defaults_server.yml`.

#### Option B — Pull from a registry on the apptainer host

If you have a registry the apptainer host can reach (and the locally-built images have been pushed to it), pull directly:

```bash
sudo mkdir -p /opt/sif
apptainer pull /opt/sif/diann_2.3.2.sif docker://<registry>/diann:2.3.2
apptainer pull /opt/sif/pwiz.sif docker://chambm/pwiz-skyline-i-agree-to-the-vendor-licenses
# ... etc
```

No `deploy.smk` involvement on the apptainer side. Requires registry setup.

#### Verify

```bash
python3 -c "from diann_runner.container_utils import detect_runtime; print(detect_runtime())"
# Expected: apptainer

apptainer exec /opt/sif/diann_2.3.2.sif diann --help
diann-docker --runtime apptainer --image /opt/sif/diann_2.3.2.sif -- --help
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

`make_lock.sh` runs:

```bash
uv lock -U && uv sync
uv export --format pylock.toml -o pylock.toml --no-emit-project
git add pylock.toml pyproject.toml && git commit -m "update pylock" && git push
```

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

Build or verify a specific image:

```bash
snakemake -s deploy.smk build_diann_docker --cores 1
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
cat logs/build_diann_docker.log
```

Snakemake dry run:

```bash
snakemake -s deploy.smk --cores 1 --dry-run
```
