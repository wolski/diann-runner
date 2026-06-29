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

## Register the Executable in B-Fabric

The executable XML
(`diann_runner/bfabric_executable/executable_A386_DIANN_3.2.xml`) is the
source of truth for the B-Fabric GUI parameters. Two constraints (verified
against the bfabricPy `cli/executable/upload.py` source) govern pushing it back:

**1. Format — the committed file is NOT uploadable as-is.** It is a *web-GUI
"XML Export"*: root `<executable classname="executable" id="26960">` and every
`<parameter>` carries a `<executable .../>` back-reference. `bfabric-cli
executable upload` parses XML with `xmltodict`, which turns every XML attribute
into an `@`-prefixed key (`@classname`, `@id`); the SUDS SOAP marshaller then
aborts with `suds.TypeNotFound: Type not found: '@classname'`. The uploadable
shape is the one `bfabric-cli executable dump` produces — a clean `<executable>`
with **no attributes**, **no** parameter back-references, and only definition
fields (`name`, `description`, `program`, `context`, `enabled`, and per-parameter
`key/label/description/context/type/value/required/modifiable/enumeration`).

**2. `upload` only CREATES — it cannot UPDATE.** `upload` explicitly rejects an
`id` (`"Executable data must not contain an 'id' key."`) and calls
`client.save("executable", data)` with no id, so B-Fabric always makes a **new**
executable. It will not modify executable 26960.

```bash
# ~/.bfabricpy.yml = web-service password (not login). Prepend BFABRICPY_CONFIG_ENV=TEST first.

# Back up / get a known-good clean (uploadable) file:
bfabric-cli executable dump 26960 /tmp/exec_26960.xml --format xml

# Create a NEW executable from a clean-format file (prints the new id):
bfabric-cli executable upload <clean-format>.xml
```

**To UPDATE an existing executable in place** (e.g. 26960, already wired to the
DIANN application) keep using the web GUI **Edit**, or the bfabricPy Python API
with the id present (`save` with an `id` updates that record):

```python
from bfabric import Bfabric
client = Bfabric.connect()              # BFABRICPY_CONFIG_ENV=TEST first
client.save("executable", {"id": 26960, "name": "A386_DIANN_v2.3.0",
                           "program": "/home/bfabric/slurmworker/config/A386_DIANN_23/app.yml",
                           "parameter": [ {"key": "pipeline_diann_version", ...}, ... ]})
```

Verify nested-parameter replacement semantics on a TEST instance before
PRODUCTION. `bfabric-cli executable dump <id>` is how the repo XML is
produced/refreshed from B-Fabric.

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
