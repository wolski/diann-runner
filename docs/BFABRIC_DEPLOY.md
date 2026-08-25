# Bfabric Deployment

## Architecture

```
Bfabric → slurmworker/config/A386_DIANN_23/ → diann_runner
              ├── app.yml        (commands)
              ├── dispatch.py    (workunit → work/params.yml + work/inputs.yml)
              ├── pyproject.toml (deps, refs diann_runner by git)
              └── pylock.toml    (locked deps — pins the diann_runner revision)
```

`pylock.toml` is the ground truth for which `diann_runner` revision production
runs. Pushing a `diann_runner` commit changes nothing until the lock is
regenerated and pulled.

## Deploy Changes

```bash
# 1. Push diann_runner
cd ~/projects/diann_runner
git add -A && git commit -m "update" && git push

# 2. Regenerate the pin (commits and pushes pylock.toml itself)
cd ~/projects/slurmworker/config/A386_DIANN_23
./make_lock.sh

# 3. Deploy host (the machine holding /home/bfabric/slurmworker)
cd /home/bfabric/slurmworker && git pull
```

Do not hand-run `uv lock` / `uv sync` / `uv export` instead of `make_lock.sh`.
Beyond the export, the script:

- **strips every `polars-lts-cpu` package block.** `uv export --format
  pylock.toml` drops environment markers, so bfabric's macOS-x86_64-only
  `polars-lts-cpu` becomes installable on the Linux host, collides with
  `polars-runtime-32`, and leaves a `polars` that will not import —
  `dispatch.py` then dies before writing `chunks.yml`;
- **verifies the export** in a throwaway 3.13 venv (`uv pip install -r
  pylock.toml`, then imports `polars` and `bfabric.entities.Dataset`), so a
  non-installable lock is never committed;
- commits `pylock.toml` + `pyproject.toml` and pushes, only if something
  changed.

It runs under `set -exo pipefail` and tees everything to
`A386_DIANN_23/log` (gitignored). Read that file when it fails.

## Register the Executable in B-Fabric

The executable **YAML** (`diann_runner/bfabric_executable/executable_A386_DIANN_3.2.yaml`)
is the source of truth for the B-Fabric GUI parameters. Use the Makefile beside
it:

```bash
# ~/.bfabricpy.yml = web-service password (not login). ENV selects the instance.
cd bfabric_executable

make validate                 # local: top level is exactly `executable:`, no id, has parameters
make upload ENV=TEST          # create a NEW executable on the TEST instance
make upload                   # ... on PRODUCTION (default ENV)
make dump ID=<executable-id>  # scratch dumped_<ID>.xml, for reference/diffing only
```

**`upload` only CREATES — it cannot UPDATE.** `bfabric-cli executable upload`
rejects an `id` (`"Executable data must not contain an 'id' key."`) and calls
`client.save("executable", data)` with no id, so B-Fabric always makes a **new**
executable and prints its id. It cannot modify the executable the A386
application is currently wired to.

To **update an existing executable in place**, use the web GUI **Edit**, or the
bfabricPy Python API with the id present (`save` with an `id` updates that
record):

```python
from bfabric import Bfabric
client = Bfabric.connect()              # BFABRICPY_CONFIG_ENV=TEST first
client.save("executable", {"id": <executable-id>, "name": "A386_DIANN_v2.3.0",
                           "program": "/home/bfabric/slurmworker/config/A386_DIANN_23/app.yml",
                           "parameter": [ {"key": "pipeline_diann_version", ...}, ... ]})
```

`parameter` is replaced wholesale, not merged. Verify nested-parameter
replacement semantics on a TEST instance before PRODUCTION.

Confirm the live executable id from B-Fabric before using either path — do not
copy an id out of this file or the Makefile comment.

### A GUI "XML Export" is not uploadable

If you pull an executable out of the web GUI as XML, note that
`bfabric-cli executable upload` parses XML with `xmltodict`, which turns every
XML attribute into an `@`-prefixed key (`@classname`, `@id`); the SUDS SOAP
marshaller then aborts with `suds.TypeNotFound: Type not found: '@classname'`.
The GUI export carries a root `<executable classname="executable" id="...">` and
a per-parameter `<executable .../>` back-reference, so it fails as-is. The
uploadable shape holds only definition fields (`name`, `description`, `program`,
`context`, `enabled`, and per-parameter
`key/label/description/context/type/value/required/modifiable/enumeration`) —
which is what the YAML holds.

### The YAML exists twice

`diann_runner/bfabric_executable/executable_A386_DIANN_3.2.yaml` and
`slurmworker/config/A386_DIANN_23/executable_A386_DIANN23plus.yaml` are
currently byte-identical copies under different names in different repos, with
no sync mechanism. After editing one, diff the other and copy it across.

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

`app.yml` also defines `devel` and `devel_linux` versions
(`--force-app-version devel`), but their commands carry hardcoded developer
paths — point them at your own checkout first.

Two `app.yml` details that break silently if disturbed:

- the `process` command **must end with `--work-dir`** — AppRunner appends the
  work dir as a trailing argument and that flag consumes it;
- `--docker` on the `process` command pins the runtime to docker. Drop it on a
  host with a populated SIF cache.
