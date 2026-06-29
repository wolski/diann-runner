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

## Register / Update the Executable in B-Fabric

The executable XML
(`diann_runner/bfabric_executable/executable_A386_DIANN_3.2.xml`, mirrored
byte-for-byte into
`slurmworker/config/A386_DIANN_23/executable_A386_DIANN23plus.xml`) is the
**source of truth** for the B-Fabric GUI parameters (keys, order, enums,
defaults). After editing it, push it to B-Fabric programmatically with the
bfabricPy CLI — no manual web-GUI paste:

```bash
# Needs ~/.bfabricpy.yml (web-service password, not the login password).
# Defaults to PRODUCTION; prepend BFABRICPY_CONFIG_ENV=TEST to hit the test instance.

# 0. (optional) back up the live definition first
bfabric-cli executable dump 26960 /tmp/exec_26960_before.xml --format xml

# 1. TEST first
BFABRICPY_CONFIG_ENV=TEST bfabric-cli executable upload \
  bfabric_executable/executable_A386_DIANN_3.2.xml

# 2. promote to PRODUCTION
bfabric-cli executable upload bfabric_executable/executable_A386_DIANN_3.2.xml

# 3. verify the live definition round-trips back to the committed file
bfabric-cli executable dump 26960 /tmp/exec_26960_after.xml --format xml
diff <(sed -n '18,$p' bfabric_executable/executable_A386_DIANN_3.2.xml) \
     <(sed -n '18,$p' /tmp/exec_26960_after.xml)
```

The XML's `id` (26960) identifies the executable, so `upload` targets that
record (the same id the repo XML and the slurmworker mirror share). Because
B-Fabric now renders parameters in **document order**, the live GUI ordering
becomes exactly the committed XML's order. The companion `bfabric-cli executable
dump <id> <path>` is how the repo XML is produced/refreshed from B-Fabric.

> The two A386 XMLs are byte-identical (guarded by
> `tests/test_executable_contract.py::test_slurmworker_mirror_body_identical`), so
> uploading either is equivalent; upload the `diann_runner` copy as the canonical
> source.

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
