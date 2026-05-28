# TODO: Add Apptainer Compatibility

## Goal

Run the full workflow (DIA-NN, ThermoRawFileParser, msconvert, prolfqua) on machines that have Apptainer but no Docker, while keeping the existing Docker deployment working unchanged.

Confirmed target host:

```bash
apptainer --version
# apptainer version 1.4.2
```

Confirmed scope: **all** Dockerised steps need Apptainer support, not just DIA-NN.

## Constraints

- Docker deployment must continue to work unchanged.
- Fix at the correct upstream package/file, no wrapper-only workarounds.
- Keep public API additions minimal — no new CLI entry points if existing ones can be re-used.
- Container runtime naming, parameter names, and config keys must be consistent across the workflow.
- XML executable is the source of truth for *analyst-facing* parameters. Runtime selection is **deployment-level**, not analyst-facing — do **not** add it to `executable_new.xml`.
- No environment-variable runtime override and no per-host config file — `/home/bfabric/` is NFS-shared and would be identical on every host, so per-host plumbing there is pointless.

## Architecture Decision

The codebase already routes all three Docker wrappers
([diann_docker.py](../src/diann_runner/diann_docker.py),
[thermoraw_docker.py](../src/diann_runner/thermoraw_docker.py),
[prolfquapp_docker.py](../src/diann_runner/prolfquapp_docker.py))
through [`DockerCommandBuilder`](../src/diann_runner/docker_utils.py) in `docker_utils.py`,
and the Snakefile only invokes the Python wrappers — never raw `docker run`.
That single chokepoint is where the abstraction belongs.

**Therefore:**

- **Do not** create parallel `diann-apptainer`, `thermoraw-apptainer`, `prolfquapp-apptainer` CLIs.
- **Do** generalise the builder to support both runtimes, with the existing CLI entry points (`diann-docker`, `thermoraw`, `prolfquapp-docker`) dispatching internally.
- **Do not** use Snakemake's native `--use-apptainer` / `container:` directives — that would bypass our wrapper layer. Keep the wrappers as the single integration point.

The wrapper names retain "-docker" for backwards compatibility. They are slightly misleading after this change, but the AGENTS.md "consistent naming" rule favours stable public names over a rename.

## Runtime Selection — Auto-detect from PATH

**Single source of truth: what's installed on the host.** No YAML key, no env var, no per-host file. The shared `defaults_server.yml` carries *both* runtime image blocks; the code picks based on `shutil.which()`.

```python
def detect_runtime() -> str:
    if shutil.which("apptainer"):
        return "apptainer"
    if shutil.which("docker"):
        return "docker"
    raise RuntimeError("Neither apptainer nor docker found on host")
```

**Precedence: apptainer wins** if both are installed. Rationale: a host with both installed is almost certainly a dev box in transition; the operator's intent in installing apptainer is to use it. Production hosts will have exactly one.

### Why not `container_runtime:` in YAML?

Earlier draft proposed a YAML key. Killed because:

- `/home/bfabric/` is NFS-shared, so a config file there would be identical on every host — useless as a per-host switch.
- Detection from PATH is exactly what the operator does anyway: installs the runtime they want and expects code to use it.
- Detection means migrating a host docker → apptainer is purely an ops action (install apptainer, populate `/opt/sif/`); no diann_runner config change needed.

### Why ship one config in the package?

Because there is no other place to put it. The "raw_dir first" search in `load_deploy_config()` stays as a *capability* for one-off testing in a workunit directory, but **all production hosts read the file shipped inside `src/diann_runner/config/defaults_server.yml`** — the slurmworker lockfile pulls diann_runner from git, that's where the file lives, that's what every host sees.

`deploy_config.yaml` (root) is *build-time* config for `deploy.smk`. Unrelated to runtime.

## Image Resolution

The shipped config gains a two-key `images:` block. Existing flat keys (`diann_images`, `thermoraw_image`, `msconvert_docker`, `prolfquapp_image`) move under `docker:` and `apptainer:`:

```yaml
# src/diann_runner/config/defaults_server.yml  (shipped with package, single source of truth)
threads: 64
app_runner: "fgcz_app_runner"

images:
  docker:
    diann_images:
      "2.3.2": "diann:2.3.2"
      "2.5.0": "diann:2.5.0-thermo"
    diann_docker_image: "diann:2.3.2"
    thermoraw_image: "thermorawfileparser:2.0.0"
    msconvert_docker: "chambm/pwiz-skyline-i-agree-to-the-vendor-licenses"
    prolfquapp_image: "prolfqua/prolfquapp:2.0.10"

  apptainer:
    diann_images:
      "2.3.2": "/opt/sif/diann_2.3.2.sif"
      "2.5.0": "/opt/sif/diann_2.5.0-thermo.sif"
    diann_docker_image: "/opt/sif/diann_2.3.2.sif"
    thermoraw_image: "/opt/sif/thermorawfileparser_2.0.0.sif"
    msconvert_docker: "/opt/sif/pwiz.sif"
    prolfquapp_image: "/opt/sif/prolfquapp_2.0.10.sif"
```

`load_deploy_config()` calls `detect_runtime()`, picks the matching sub-block, flattens it back into the same top-level shape the Snakefile sees today (`deploy_dict["diann_images"]`, `deploy_dict["thermoraw_image"]`, …) plus a synthesised `deploy_dict["container_runtime"]` for downstream forwarding. **The Snakefile and existing helpers see the same keys they see today.**

## Parameter Flow

```
src/diann_runner/config/defaults_server.yml   (shipped in package, same on every host)
  └── images:
       ├── docker:    { diann_images, thermoraw_image, msconvert_docker, prolfquapp_image }
       └── apptainer: { diann_images, thermoraw_image, msconvert_docker, prolfquapp_image }
       │
       ▼  load_deploy_config(raw_dir)
       │     1. detect_runtime() from PATH (apptainer wins if both)
       │     2. flatten config["images"][runtime] to top level
       │     3. synthesise deploy_dict["container_runtime"]
       ▼
deploy_dict   ── Snakefile passes deploy_dict["…_image"] as --image (unchanged today)
       │      ── Snakefile passes deploy_dict["container_runtime"] as --runtime (new)
       ▼
wrapper receives matched (runtime, image) pair
       ▼
ContainerCommandBuilder(image, runtime=runtime)
       ▼
builder.build() emits  docker run …  OR  apptainer exec …
```

## Runtime Differences (Docker vs Apptainer)

| Concern | Docker today | Apptainer |
|---|---|---|
| UID/GID mapping | Explicit `-u $UID:$GID` | No-op — runs as caller |
| Apple Silicon platform | `--platform linux/amd64` injected | No-op — Apptainer is Linux-only |
| Mount syntax | `-v src:dst` | `--bind src:dst` |
| Working directory | `-w /work` | `--pwd /work` |
| Image reference | `name:tag` (from local docker daemon) | `.sif` path or `docker://` URI |
| Cleanup (`--rm`) | Required | No-op — Apptainer is stateless |
| Resource limits (`--shm-size`, `--ulimit`, `--ipc host`) | Required for large workloads | No-op — inherits host limits |
| Signal handling (`--init`) | Required for zombie reaping | No-op — Apptainer handles this |
| Stdio (`-it` / `-i`) | Required | No-op — Apptainer inherits stdio |
| Writable container FS | Default | Read-only; needs `--writable-tmpfs` for tools that write inside the image (e.g. Wine for msconvert) |

Apptainer is broadly *simpler* — most Docker-specific flags collapse to no-ops.

## Plan

### Step 1 — Generalise the builder

Rename [`docker_utils.py`](../src/diann_runner/docker_utils.py) → `container_utils.py`. Replace `DockerCommandBuilder` with `ContainerCommandBuilder` that takes a `runtime: Literal["docker", "apptainer"]` argument. Each `with_*` method becomes runtime-aware per the table above. `build()` emits either:

```bash
docker run [flags] image [args]
apptainer exec [flags] image [args]
```

Add `detect_runtime()` here. A grep confirms only the three wrappers import `DockerCommandBuilder`, so delete it outright — no compatibility shim.

### Step 2 — Wire all three wrappers through the new builder

[`diann_docker.py`](../src/diann_runner/diann_docker.py), [`thermoraw_docker.py`](../src/diann_runner/thermoraw_docker.py), [`prolfquapp_docker.py`](../src/diann_runner/prolfquapp_docker.py): add a `--runtime {docker,apptainer}` CLI flag (default `docker` for backwards compatibility) and replace direct `DockerCommandBuilder(image)` calls with `ContainerCommandBuilder(image, runtime=runtime)`. The fluent chain stays the same.

For the msconvert code path specifically, the builder must, under Apptainer, emit `--writable-tmpfs --env WINEPREFIX=/tmp/.wine` (no-ops under Docker). Expose via a `with_wine_compat()` builder method.

The Snakefile reads `container_runtime` from `deploy_dict` and forwards it as `--runtime` on every wrapper invocation. The wrappers themselves do **not** read YAML or environment variables — they trust the caller.

### Step 3 — Restructure `defaults_server.yml` / `defaults_local.yml`

Move existing image keys under `images.docker.*`. Add a sibling `images.apptainer.*` block populated with SIF paths (placeholder paths in the initial PR — production fills them once SIFs exist on hosts).

Update `load_deploy_config()` in [snakemake_helpers.py](../src/diann_runner/snakemake_helpers.py) to:

1. Load the YAML.
2. Call `detect_runtime()`.
3. Replace `deploy_dict["images"]` with the contents of `deploy_dict["images"][runtime]` flattened to top level.
4. Add `deploy_dict["container_runtime"] = runtime`.
5. Existing callers continue to see `deploy_dict["diann_images"]`, `deploy_dict["thermoraw_image"]`, etc.

Tighten [pyproject.toml:38-39](../pyproject.toml#L38-L39):

```toml
[tool.setuptools.package-data]
diann_runner = ["Snakefile.DIANN3step.smk", "config/*.yml"]
```

so the YAML files are reliably shipped regardless of build backend.

### Step 4 — Snakefile forwards `--runtime`

In [Snakefile.DIANN3step.smk](../src/diann_runner/Snakefile.DIANN3step.smk), every rule that shells out to a wrapper (`thermoraw`, `prolfquapp-docker`, and the DIA-NN script-generation path via `workflow.py`) adds `--runtime {deploy_dict[container_runtime]}` to the command line.

For the DIA-NN bash scripts that `workflow.py` writes, the `diann_bin` value is currently `diann-docker`. Either:

- Keep `diann_bin = "diann-docker"` and have `workflow.py` append `--runtime <runtime>` to the generated invocation, OR
- Pass `container_runtime` into `DiannWorkflow` constructor and let it bake the flag into the script.

The second is cleaner — `container_runtime` becomes a `DiannWorkflow` constructor parameter and lands in `.config.json` alongside the other parameters.

### Step 5 — Build / distribute `.sif` images

Apptainer can pull from any OCI-compatible source via `docker://` (registry) or `docker-daemon://` (local Docker daemon). Distribution is naturally **mixed** because the project consumes both upstream images and locally-built ones:

| Image | Source today | Apptainer pull source |
|---|---|---|
| `diann:<v>` | Locally built from `docker/Dockerfile.diann` | `docker-daemon://diann:<v>` (Option A), or a registry push (Option B) |
| `diann:<v>-thermo` | Locally built from `docker/Dockerfile.diann_thermofilereader` | Same as above |
| `thermorawfileparser:2.0.0` | Locally built from `docker/Dockerfile.thermorawfileparser-linux` | Same as above |
| `chambm/pwiz-skyline-i-agree-to-the-vendor-licenses` (msconvert) | Pulled from Docker Hub | `docker://chambm/pwiz-skyline-i-agree-to-the-vendor-licenses` |
| `prolfqua/prolfquapp:2.0.10` | Pulled from Docker Hub | `docker://prolfqua/prolfquapp:2.0.10` |

Two acceptable patterns for the **locally-built** images — pick one per deployment site:

- **Option A: docker-host builds SIFs.** Extend `deploy.smk` with rules that run `apptainer pull diann_<v>.sif docker-daemon://diann:<v>` after each docker build. Output SIFs get copied to the apptainer target. One build host, two output formats. Add `build_sif: true` to `deploy_config.yaml` to enable.
- **Option B: apptainer host pulls from a registry.** A one-shot script on the apptainer host: `apptainer pull /opt/sif/diann_2.3.2.sif docker://<registry>/diann:2.3.2`. No `deploy.smk` involvement on the apptainer side. Requires a registry that the apptainer host can reach.

Upstream images (msconvert, prolfquapp) are always pulled directly with `docker://` on the apptainer host. Provide a `docs/pull_sif_images.sh` script for first-time setup.

### Step 6 — Lockfile / slurmworker

`.make_lockfile.sh` requires **no changes**. The shipped `defaults_server.yml` is now self-sufficient: it contains both runtime blocks and the auto-detect logic picks the right one at runtime. One lockfile, both host types, same pull-and-go production workflow.

### Step 7 — Tests

Add to `tests/`:

- Docker command construction unchanged for `runtime=docker` (snapshot test against current behaviour).
- Apptainer command construction emits `apptainer exec`, `--bind`, `--pwd`, no `-u`, no `--platform`, no `--rm`, no `--shm-size`.
- All three wrappers accept `--runtime` and route correctly (parametrised over `{docker, apptainer}`).
- `detect_runtime()` precedence: apptainer wins when both on PATH; raises when neither.
- `load_deploy_config()` correctly flattens `images.<runtime>` to top level and synthesises `container_runtime`.
- Missing `images.<runtime>` block raises with a clear error.
- Snakefile forwards `deploy_dict["container_runtime"]` to every wrapper invocation.
- msconvert path under apptainer adds `--writable-tmpfs` and `WINEPREFIX`.
- Snakefile-generated DIA-NN step scripts still produce byte-identical `.config.json` files on both runtimes (modulo paths).

Run existing tests:

```bash
python3 -m pytest tests/
```

### Step 8 — Smoke testing

**Done locally (darwin docker host):**

- `detect_runtime()` returns `docker` on this host (no apptainer installed) ✓
- All three wrappers accept `--runtime {docker,apptainer}` with `docker` default ✓
- Generated `docker run …` commands match historical behaviour ✓
- Generated `apptainer exec …` commands:
  - emit `--bind`, `--pwd`, `.sif` paths
  - drop `--rm`, `--init`, `--platform`, `-u/--user`, `--shm-size`, `--ulimit`, `--ipc` (all Docker-only)
  - emit `--writable-tmpfs --env WINEPREFIX=/tmp/.wine` for the msconvert path only
- `DiannWorkflow(container_runtime="apptainer", docker_image="/opt/sif/diann_2.3.2.sif")` emits bash scripts with `--runtime apptainer --image /opt/sif/…` baked in ✓

**Requires the apptainer 1.4.2 host:**

```bash
# 1. Populate SIFs (one-time, per Step 5 above)
sudo mkdir -p /opt/sif
apptainer pull /opt/sif/diann_2.3.2.sif docker-daemon://diann:2.3.2
apptainer pull /opt/sif/diann_2.5.0-thermo.sif docker-daemon://diann:2.5.0-thermo
apptainer pull /opt/sif/thermorawfileparser_2.0.0.sif docker-daemon://thermorawfileparser:2.0.0
apptainer pull /opt/sif/pwiz.sif docker://chambm/pwiz-skyline-i-agree-to-the-vendor-licenses
apptainer pull /opt/sif/prolfquapp_2.0.10.sif docker://prolfqua/prolfquapp:2.0.10

# 2. Verify detection picks apptainer
python3 -c "from diann_runner.container_utils import detect_runtime; print(detect_runtime())"
# Expected: apptainer

# 3. Smoke-run each container directly (validates SIF integrity)
apptainer exec /opt/sif/diann_2.3.2.sif diann --help

# 4. Smoke-run via the wrappers (validates the runtime flag plumbing)
diann-docker --runtime apptainer --image /opt/sif/diann_2.3.2.sif -- --help
thermoraw --runtime apptainer --image /opt/sif/thermorawfileparser_2.0.0.sif -i sample.raw -o sample.mzML
prolfquapp-docker --runtime apptainer --image /opt/sif/prolfquapp_2.0.10.sif -- prolfqua_qc.sh --help

# 5. Full Snakemake run end-to-end on a small dataset
diann-snakemake --cores 8 -p all
```

The msconvert step under apptainer is the highest-risk smoke test — if `--writable-tmpfs --env WINEPREFIX=/tmp/.wine` doesn't satisfy Wine, the prefix init will fail there.

### Step 9 — Documentation

Update `README_DEPLOYMENT.md` with:

- Required Apptainer version (1.4.2 confirmed).
- How to populate `/opt/sif/` (Option A or Option B from step 5).
- Statement that the package's `defaults_server.yml` carries both runtime blocks and the right one is auto-selected.
- Statement that Docker remains supported. Hosts with only docker continue to work unchanged.
- Note that no XML executable changes are required and analysts see no UI difference.
- Apptainer-wins-if-both precedence rule, with rationale.

## What this avoids

- No 3× CLI proliferation.
- No `executable_new.xml` change.
- No `.make_lockfile.sh` change.
- No per-host config files; nothing under `/home/bfabric/`.
- No environment variables.
- No `slurmworker/dispatch.py` change.
- One bug fix in mount/workdir/UID handling fixes all three wrappers.

## Open questions

1. **Does the apptainer host have any GPU steps?** DIA-NN's deep learning predictor can use GPU; if the apptainer host has CUDA, `--nv` must be added to `apptainer exec`. Defer until confirmed needed.
2. **`diann_bin` plumbing in `workflow.py`** — pass `container_runtime` into `DiannWorkflow` constructor (recommended) vs append flag at script-emit time. Step 4 picks the constructor approach; revisit if it complicates `.config.json` round-trips.
