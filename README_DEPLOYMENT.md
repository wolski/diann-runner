# Deployment Guide

This repo is deployed in two different ways:

- `deploy.smk` builds or verifies the Docker images used by `diann_runner`.
- The FGCZ production app is run through the separate `slurmworker` repo, which installs `diann_runner` from the git revision locked in `pylock.toml`.

For ordinary workflow code changes, such as edits to `Snakefile.DIANN3step.smk` or Python helpers, push the `diann_runner` change, regenerate the slurmworker lockfile on the development machine, then pull `slurmworker` on production. You do not need to rebuild Docker images unless a Dockerfile, Docker image version, or container dependency changed.

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
