# TODO: SUSHI DIA-NN App — Apptainer + params.yml-as-Input

> Source: email from Paul Gueguen (paul.gueguen@fgcz.ethz.ch), 28 May 2026.
> Goal: dataset **p34486/112148** → SUSHI submit → `qc_result/proteinAbundances.html`
> + `Result_WU<id>.zip` land in gstore, **unattended**.

## Context

### Three things we discovered that change the design

1. **The production DIA-NN pipeline at FGCZ already runs via `fgcz_app_runner`, not SUSHI.**
   The Feb 10 workunit dir at `fgcz-r-033:/scratch/A386_DIANN_v23/WU340602/work` shows
   `workunit_definition.yml` + `inputs.yml` (bfabric-app-runner artifacts), files owned by
   `bfabric`, and the Snakefile's `stageoutput` rule calling `fgcz_app_runner outputs register`.
   The Snakefile is meant to be driven by app-runner; SUSHI was never the intended frontend.
   Hubert's `app-DIANN.R` is essentially a SUSHI shim around the same pipeline.

2. **The `diann-docker` CLI from wolski/diann-runner is a Python wrapper that `subprocess.run`s `docker run`.**
   Confirmed in `src/diann_runner/docker_utils.py:56-71` — `find_container_runtime()` only accepts
   `podman` or `docker`. Same pattern in `thermoraw_docker.py`, `prolfquapp_docker.py`.

3. **trxcopy (SUSHI service user) can't reach any docker daemon at FGCZ.**
   - c-050: no docker installed.
   - c-072/c-073 (prx): docker present, daemon group `SG_DockerPRX`, trxcopy NOT a member.
   - c-051 (ShinyProxy): docker present, daemon group `SG_DockerTRX`, trxcopy NOT a member; also not in any SLURM partition.
   - trxcopy groups: `SG_Employees SG_Applications SG_GTprojects SG_p0 SG_Hobbes`. Hubert's Feb runs ran as `rehrauer`/`bfabric`, not via SUSHI/trxcopy.

### Decisions locked in

- **Container path:** patch wolski/diann-runner to use apptainer. Apptainer is rootless, on every FGCZ node we checked (`/usr/bin/apptainer 1.4.2`), needs no group changes for trxcopy. Cost: one PR upstream (or local fork).
- **SUSHI app scaffold:** refactor Hubert's existing `DIANNApp.rb` + `app-DIANN.R`. Keep filenames. Strip the count-QC cruft.
- **params.yml as primary input:** hybrid design. Ship canonical `params.yml` templates inside ezRun (`inst/templates/DIANN_params_*.yml`). User chooses a template via a SUSHI dropdown OR overrides with their own path. Run-specific values (`workunit_id`, `container_id`, `dataRoot`, ...) come from SUSHI job context as a `registration:` block injected at run time.
- **Out of scope:** no custom FGCZ Rmd report layer. Ship exactly what diann-runner produces (`proteinAbundances.html`, `QC_sampleSizeEstimation.html`, `Result_WU*.zip`).

## Strategy at a glance

```
User picks a paramsTemplate (default-DIA / default-DDA / custom path)
            │
            ▼
SUSHI submits SBATCH → trxcopy@fgcz-c-050
            │
            ▼
app-DIANN.R: read template OR customParamsYml from /srv/gstore;
             inject `registration:` block from job context;
             write work/params.yml + work/dataset.csv;
             symlink /usr/local/ngseq/opt/diann-runner
            │
            ▼
snakemake (gi_snakemake8.20.5 env) -> diann-docker / thermoraw /
                                      prolfquapp-docker python CLIs
            │
            ▼
(PATCHED) docker_utils → apptainer exec <sif> <cmd>  ← runs as trxcopy
            │
            ▼
out-DIANN_quantC/* + qc_result/* moved to SUSHI output dir
```

### Two single chokepoints

1. **Container runtime:** every container call funnels through `DockerCommandBuilder.build()` in `docker_utils.py`. Patching that one class redirects every wrapper.
2. **Workflow params:** the snakemake pipeline reads exactly one file — `work/params.yml` — whose schema is documented in `src/diann_runner/snakemake_helpers.py::parse_flat_params`. So the SUSHI app's only real job, once container plumbing works, is to put the right `params.yml` in `work/`.

## Tasks

### 1. Fork wolski/diann-runner; patch `docker_utils.py` for apptainer

Clone to `~/git/diann-runner` on the dev box; branch `apptainer-support`. Open PR upstream after smoke test passes, run from the fork in the meantime.

Patches to `src/diann_runner/docker_utils.py`:

- `find_container_runtime()` — extend tuple from `("podman", "docker")` to `("docker", "podman", "apptainer", "singularity")`. Preserve current priority so existing docker hosts behave identically.
- `DockerCommandBuilder.__init__` — store the resolved runtime; expose `is_apptainer` property.
- `DockerCommandBuilder.build()` — branch on runtime:
  - docker/podman path: unchanged (`[runtime, "run"] + flags + [image] + args`).
  - apptainer path: emit `[runtime, "exec"] + bind_args + workdir_args + [resolve_image(image)] + container_args`.
- `.with_mount(src, dst)` — apptainer branch records `--bind src:dst` (style="bind" maps cleanly). `.with_workdir(p)` → `--pwd p`.
- `.with_cleanup`, `.with_init`, `.with_interactive`, `.with_platform`, `.with_uid_gid`, `.with_resource_limits` — no-ops on apptainer (it runs rootless as host user, single-shot, host arch).
- Image resolution — new private helper `_resolve_image_for_apptainer(image)`:
  - If `${DIANN_RUNNER_SIF_CACHE_DIR}` env var set, look for `<sanitized_image>.sif` there (replace `:` and `/` with `_`). E.g. `diann:2.3.2` → `diann_2.3.2.sif`.
  - Else fall through to `docker://image:tag` (apptainer pulls on demand, requires internet from the compute node — works on c-050).
- Add a tiny unit test under `tests/` covering the apptainer branch (mock `shutil.which`).

The three wrapper modules (`diann_docker.py`, `thermoraw_docker.py`, `prolfquapp_docker.py`) and `workflow.py` need **NO changes** — they all go through `DockerCommandBuilder`.

### 2. Pre-build `.sif` images (one-time, on a docker-capable node)

The canonical DIA-NN images are built locally from `docker/Dockerfile.diann` and `docker/Dockerfile.thermorawfileparser-linux` (see `deploy.smk:75-146`). They are **NOT** on Docker Hub. Image tags from `src/diann_runner/config/defaults_server.yml`:

| Tag | Source |
|-----|--------|
| `diann:2.3.2` | local build (Dockerfile.diann + DIA-NN binary download) |
| `diann:2.5.0-thermo` | local build (Dockerfile.diann_thermofilereader) |
| `thermorawfileparser:2.0.0` | local build (Dockerfile.thermorawfileparser-linux); biocontainers has a similar tag too |
| `prolfqua/prolfquapp:2.0.10` | likely on Docker Hub (namespaced) |
| `chambm/pwiz-skyline-...` | Docker Hub (public) |

Bootstrap procedure (needs cooperation with wolski/rehrauer since `SG_DockerPRX` group is required — Paul can't do this as pgueguen on c-050):

```bash
# On a docker host with wolski or rehrauer identity (e.g. c-072 in prx):
cd ~/git/diann-runner
snakemake -s deploy.smk --cores 1                  # builds docker images
mkdir -p /misc/ngseq12/opt/sif
for img in diann:2.3.2 thermorawfileparser:2.0.0 prolfqua/prolfquapp:2.0.10; do
  sane=$(echo "$img" | tr ':/' '__')
  docker save "$img" | apptainer build "/misc/ngseq12/opt/sif/${sane}.sif" \
    docker-archive:/dev/stdin
done
chmod 644 /misc/ngseq12/opt/sif/*.sif
```

Once stored under `/misc/ngseq12/opt/sif/`, the `.sif` files are NFS-visible on every node and trxcopy can read them without group membership.

**Open question for the user:** is Hubert/wolski willing to do the one-time build, or should Paul attempt it as pgueguen on c-072 (probably needs `SG_DockerPRX` membership for him too)?

### 3. Pre-clone patched runner + verify snakemake conda env

Once the `docker_utils` patch is committed to the fork:

```bash
ssh fgcz-r-029
git clone -b apptainer-support https://github.com/<fork>/diann-runner.git \
  /usr/local/ngseq/opt/diann-runner
# Verify gi_snakemake8.20.5 conda env exists; create if missing:
mamba env list | grep gi_snakemake8.20.5 || mamba create -n gi_snakemake8.20.5 \
  -c bioconda -c conda-forge snakemake-minimal=8.20.5 uv pyyaml python=3.13
mamba run -n gi_snakemake8.20.5 uv pip install -e /usr/local/ngseq/opt/diann-runner
```

### 4. Smoke test the patched runner on c-050 (manual, before touching SUSHI)

Recreate Hubert's WU340602 work dir layout (`fgcz-r-033:/scratch/A386_DIANN_v23/WU340602/work/`) on `/scratch` on c-050 with a fresh `work/` directory; copy the 2 raw files; write a minimal `params.yml` (no `registration:` block needed for manual run, or use a stub `workunit_id: '0'`, `container_id: '0'`); run snakemake by hand.

```bash
ssh fgcz-c-050
export DIANN_RUNNER_SIF_CACHE_DIR=/misc/ngseq12/opt/sif
mkdir -p /scratch/diann_smoke/work/input/raw
# stage params.yml, dataset.csv, 2 raw files, fasta files
mamba activate gi_snakemake8.20.5
cd /scratch/diann_smoke
snakemake -s /usr/local/ngseq/opt/diann-runner/src/diann_runner/Snakefile.DIANN3step.smk \
  --cores 64 -p all -d ./work
```

**Pass criterion:** `work/out-DIANN_quantC/WU0_report.pg_matrix.tsv` exists and is non-empty; `work/qc_result/proteinAbundances.html` exists.

### 5. Ship default `params.yml` templates in ezRun

Add to `/home/pgueguen/git/ezRun/inst/templates/`:

- `DIANN_params_default-DIA.yml` — copy of WU340602 `params.yml`'s `params:` block verbatim (it's a known-good DIA-NN 2.3 DIA setup). No `registration:` block; that gets injected at run time.
- `DIANN_params_default-DDA.yml` — same skeleton but with `05_diann_is_dda: 'true'` and DDA-tuned defaults (mirror the p34486 Feb 5 `params.yml` `params:` block).
- Each template includes a one-line header comment naming the source workunit it was derived from, so users can trace.

These templates are R-package data — accessed at run time via `system.file("templates/DIANN_params_default-DIA.yml", package = "ezRun")`, the same pattern app-DIANN.R already uses for `fgcz_header.html` / `fgcz.css`.

### 6. Refactor `app-DIANN.R`

(`/home/pgueguen/git/ezRun/R/app-DIANN.R`)

Keep the function name `ezMethodDIANN` and the EzApp class `EzAppDIANN`. New shape:

```r
ezMethodDIANN <- function(input, output, param, htmlFile = "00index.html") {
  dir.create("work")

  # --- 1. Resolve params.yml: bundled template OR user override -----------
  paramsYml <- resolve_params_yml(param)         # ezRun helper, new
  yaml_params <- yaml::read_yaml(paramsYml)$params

  # --- 2. Inject registration block from SUSHI/B-Fabric job context -------
  registration <- list(
    workunit_id = as.character(param$workunit_id %||% "0"),
    container_id = as.character(param$container_id %||% "0"),
    application_id = "386",   # constant for now; replace once we have B-Fabric app id
    application_name = "DIANN_v23",
    container_type = "order",
    storage_id = "2",
    storage_output_folder = param$resultDir
  )
  yaml::write_yaml(
    list(params = yaml_params, registration = registration),
    "work/params.yml"
  )

  # --- 3. Stage raw files + FASTAs (current SCP block, cleaned) -----------
  stage_raw_files(input, "work/input/raw")       # ezRun helper, refactored
  stage_fastas(yaml_params, "work/input")        # idem

  # --- 4. Build work/dataset.csv from the SUSHI dataset -------------------
  write_dataset_csv(input, "work/dataset.csv")   # 3-cols: Relative Path, Name, Grouping Var

  # --- 5. Run snakemake via the pre-installed conda env -------------------
  file.symlink("/usr/local/ngseq/opt/diann-runner", "diann-runner")
  snakeFile <- "diann-runner/src/diann_runner/Snakefile.DIANN3step.smk"
  Sys.setenv(DIANN_RUNNER_SIF_CACHE_DIR = "/misc/ngseq12/opt/sif")
  ezSystem("snakemake -s diann-runner/src/diann_runner/Snakefile.DIANN3step.smk --cores 64 -p all -d ./work")

  # --- 6. Stage outputs back to SUSHI's expected paths --------------------
  ezSystem(paste("mv", "work/out-DIANN_quantC", output$getColumn("DIANN Quant")))
  ezSystem(paste("mv", "work/qc_result",       output$getColumn("qc_result")))
  return("Success")
}
```

Specific edits vs current `app-DIANN.R`:

- **L63-84** — replace the uv venv + git clone + snakemake call with the cleaner conda-env / pre-installed runner / symlink pattern above.
- **L77-83** — drop `uv venv --managed-python`; the runner is installed once into `gi_snakemake8.20.5`.
- **L89** — `out-DIANN_quantB` → `out-DIANN_quantC`. (Confirmed against both the Feb 5 and Feb 10 reference runs.)
- **L92** — `mv work/qc_result/*/*` → `mv work/qc_result <output>` (the contents live one level higher than the original glob assumed).
- **L61-62** — delete the obsolete "ALERT: fails on transcriptomics nodes" comment; apptainer makes node affinity irrelevant.
- **L109-130** — remove unused appDefaults (`runGO`, `nSampleClusters`, `selectByFtest`, `topGeneSize`).
- Replace **L20-26** inline `write_yaml(list(params = param, ...))` with the template/override resolution described in step 5.
- New helper `resolve_params_yml(param)` in ezRun (small, can live in app-DIANN.R for now): if `param$customParamsYml` is set and the file exists, return that path; else `system.file("templates/DIANN_params_default-DIA.yml", package = "ezRun")` or `-DDA.yml` keyed on `param$paramsTemplate`.

### 7. Refactor `DIANNApp.rb`

(`/home/pgueguen/git/sushi/master/lib/DIANNApp.rb`)

The 25 `@params['07_diann_*']` / `08_*` / `09_*` … defaults move from Ruby into the YAML template. The Ruby side keeps only run-time control:

```ruby
@name = 'DIANN'
@description = 'DIA / DDA quantification via DIA-NN 2.3 + prolfqua QC.'
@analysis_category = 'Proteomics'
@required_columns = ['Name', 'RAW']         # 'Grouping Var' is recommended but optional
@params['process_mode'] = 'DATASET'

# Compute resources
@params['cores'] = '64'  ; @params['cores', "context"]   = "slurm"
@params['ram']   = '32'  ; @params['ram',   "context"]   = "slurm"
@params['scratch']='20'  ; @params['scratch',"context"]  = "slurm"
@params['node']  = ['fgcz-c-050']
@params['node', "context"] = "slurm"

# Params.yml selection (the new hybrid input)
@params['paramsTemplate']    = ['default-DIA', 'default-DDA', 'custom']
@params['paramsTemplate', 'selected'] = 0
@params['customParamsYml']   = 'NONE'   # path used only when paramsTemplate=='custom'

# Run identity
@params['name']              = 'DIANN_v23_DIA'
@params['mail']              = ''
@modules = ["Dev/R"]            # snakemake env activated by ezMethodDIANN
@conda_env = 'gi_snakemake8.20.5'

def next_dataset
  result_dir = @result_dir
  {
    'Name'                    => @params['name'],
    'Protein Abundances [Link]' => File.join(result_dir, 'qc_result/proteinAbundances.html'),
    'Sample Sizes [Link]'     => File.join(result_dir, 'qc_result/QC_sampleSizeEstimation.html'),
    'qc_result [File]'        => File.join(result_dir, 'qc_result'),
    'DIANN Quant [File]'      => File.join(result_dir, 'DIANN_quantC')
  }.merge(extract_columns(colnames: @inherit_columns))
end

def commands
  run_RApp("EzAppDIANN", conda_env: "gi_snakemake8.20.5")
end
```

Net change: ~25 `@params['NN_diann_*']` defaults DELETED from Ruby; one `paramsTemplate` dropdown + one `customParamsYml` path field added. Validation: when `paramsTemplate=='custom'` and `customParamsYml=='NONE'`, the app errors out cleanly before submitting.

### 8. Confirm dataset 112148 + deploy

- Confirm dataset: download `dataset.tsv` from `https://fgcz-sushi.uzh.ch/data_set/p34486/112148` with LDAP basic auth and diff against Hubert's `dataset.tsv` to confirm columns are still `Name`, `RAW`, `Resource`, `Grouping Var`. If the columns drifted, adjust app-DIANN.R's `input$getColumn("RAW")` calls.
- Install ezRun to both R libraries (per `feedback_ezrun_deploy_two_libraries`).
- Deploy SUSHI via git pull (per `feedback_sushi_deploy_via_git_only`). Dev first.
- Submit dataset 112148 via the dev SUSHI web UI. Watch `squeue -u trxcopy` and `/scratch/<job>/logs/`.
- Promote to production only after dev passes.

Deploy commands:

```bash
ssh trxcopy@fgcz-h-082
cd /srv/sushi/production/master && git pull --ff-only && touch tmp/restart.txt

ssh trxcopy@fgcz-h-083
cd /srv/sushi/dev_sushi/master && git pull --ff-only && touch tmp/restart.txt

ssh fgcz-r-029 && cd ~/git/ezRun
R CMD INSTALL --library=/misc/ngseq12/packages/Dev/R/4.5.0/lib/R/library .
R CMD INSTALL --library=/home/trxcopy/R/x86_64-pc-linux-gnu-library/4.5 .
```

## Verification

End-to-end pass criteria:

- `squeue` shows job on fgcz-c-050.
- `work/params.yml` contains the templated `params:` block + the injected `registration:` block matching the SUSHI workunit context.
- `qc_result/proteinAbundances.html` renders protein-level plots (open via `https://fgcz-sushi.uzh.ch/projects/p34486/<resdir>/qc_result/proteinAbundances.html`).
- `Result_WU<id>.zip` > 10MB and contains `report.tsv`, `report.pr_matrix.tsv`, `report.pg_matrix.tsv`.
- Re-submit the same dataset with `paramsTemplate='custom'` pointing to a user-edited copy at `/srv/gstore/projects/p34486/configs/diann_params.yml` and confirm the run honors the override (e.g. flip `05_diann_is_dda` and observe the change in the diann log).
- ezRun package check still passes: `cd ~/git/ezRun && R CMD check --no-build-vignettes .`
- Spot-diff a few rows against the WU340602 reference run at `fgcz-r-033:/scratch/A386_DIANN_v23/WU340602/work/out-DIANN_quantB/WU340602_report.pg_matrix.tsv`: same DIA-NN params → same protein groups (within numerical jitter).

## Risks / open questions

- **Image bootstrap permission:** the `.sif` build needs docker access; only wolski/rehrauer/IT have `SG_DockerPRX`. If they can't help promptly, the fallback is `docker://` apptainer pulls — but `diann:2.3.2` is a private tag, not on Docker Hub. We'd need an alternate public image (biocontainers DIA-NN exists but version match isn't guaranteed).
- **prolfqua image:** `prolfqua/prolfquapp:2.0.10` may be on Docker Hub; if so, apptainer can pull `docker://prolfqua/prolfquapp:2.0.10` with no pre-baking needed. Worth checking first to reduce bootstrap scope.
- **Two parallel pipelines coexist:** the same DIANN workflow is already driven in production by `fgcz_app_runner` against B-Fabric workunits (e.g. WU340602). Once the SUSHI path is also working, FGCZ has two paths to the same outputs. Long-term simplification: route SUSHI submissions through `fgcz_app_runner` instead of duplicating its work in ezRun. Out of scope for this iteration — flag it for a follow-up.
- **Upstream PR:** wolski/diann-runner is the canonical home. Until the PR lands, SUSHI runs from our fork. Track and update once merged.
- **Apptainer vs docker subtleties:** `--shm-size`, `--ipc host`, `fakeroot` — the docker wrappers pass these for DIA-NN. Apptainer doesn't translate them. Smoke test is where we'd catch any IPC/thread regression.
- **trxcopy SCP credentials:** app-DIANN.R still SCPs raw files from `fgcz-ms.uzh.ch:/srv/www/htdocs`. Verify `ssh trxcopy@fgcz-c-050 'ssh fgcz-ms.uzh.ch hostname'` succeeds. If not, add a `cp` branch (the source may be NFS-mounted under another path).
- **Single-node pin:** pinning to c-050 means concurrent DIANN jobs serialize there. Fine for proof-of-concept with one early user. Revisit if uptake grows.
- **dataset 112148 dev visibility:** if it was registered against production B-Fabric, dev SUSHI might not see it. Fallback is to test against production after a synthetic dev smoke test.
- **Path validation for `customParamsYml`:** when a user supplies a path on `/srv/gstore/projects/pXXXXX/...`, the app should validate (a) file exists, (b) is readable by trxcopy, (c) parses as YAML with a `params:` block, BEFORE the SBATCH job lands on c-050 — fail fast in the Ruby app or in `commands`.
