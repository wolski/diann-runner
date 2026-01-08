# Bfabric Deployment

## Architecture

```
Bfabric → slurmworker/config/A386_DIANN_23/ → diann_runner
              ├── app.yml        (commands)
              ├── dispatch.py    (workunit → params.yml)
              ├── pyproject.toml (deps, refs diann_runner)
              └── pylock.toml    (locked deps)
```

## Deploy Changes

```bash
# 1. Push diann_runner
cd ~/projects/diann_runner
git add -A && git commit -m "update" && git push

# 2. Update slurmworker lock
cd ~/projects/slurmworker/config/A386_DIANN_23
uv lock -U && uv sync
uv export --format pylock.toml -o pylock.toml --no-emit-project
git add pylock.toml && git commit -m "update pylock" && git push

# 3. Server (fgcz-r-035)
cd /home/bfabric/slurmworker && git pull
```

## Local Testing

```bash
# Setup
uv tool install -p 3.13 bfabric-app-runner

# Prepare workunit
bfabric-app-runner prepare workunit \
  --app-spec ~/projects/slurmworker/config/A386_DIANN_23/app.yml \
  --work-dir WU338923 --workunit-ref 338923 --read-only

# Run (in WU dir)
make run-all
# or: make dispatch && make inputs && make process && make stage
```
