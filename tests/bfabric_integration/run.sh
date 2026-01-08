#!/bin/bash
# Bfabric integration testing and deployment cheatsheet
# See README_DEPLOYMENT.md "Slurmworker Integration" section for full details

### SETUP ###
uv tool install -p 3.13 bfabric-app-runner

### LOCAL TESTING ###
# Prepare workunit (use configured app version):
bfabric-app-runner prepare workunit \
  --app-spec ~/projects/slurmworker/config/A386_DIANN_23/app.yml \
  --work-dir WU338923 --workunit-ref 338923 --read-only

# Or force devel version:
bfabric-app-runner prepare workunit \
  --app-spec ~/projects/slurmworker/config/A386_DIANN_23/app.yml \
  --work-dir WU338923 --workunit-ref 338923 --read-only \
  --force-app-version devel

# Run workunit (in WU338923 dir):
make run-all        # or run steps individually:
make dispatch && make inputs && make process && make stage

### DEPLOY ###
# 1. Push diann_runner changes
cd ~/projects/diann_runner
git add -A && git commit -m "update" && git push

# 2. Update lock in slurmworker
cd ~/projects/slurmworker/config/A386_DIANN_23
uv lock -U && uv sync
uv export --format pylock.toml -o pylock.toml --no-emit-project
git add pylock.toml pyproject.toml && git commit -m "update pylock" && git push

# 3. On server (fgcz-r-035):
# cd /home/bfabric/slurmworker && git pull

