# TODO: delete staged inputs after a successful A386 run

Verdict: feasible and safe on the AppRunner path. Implement it in diann_runner, right after Snakemake exits 0, behind a new executable checkbox `output_cleanup_on_success`. Raw copies are over 99 % of a workunit dir, so this alone would have freed WU351848's 1.3 TB two days before WU351887 died with `No space left on device` (inferred from the 2026-09-21 sizes).

## Decisions (Witold, 2026-09-25)

- Code default off: `cleanup_on_success` is `False` when the key is absent
- Executable checkbox on: `output_cleanup_on_success` defaults to `'true'`
- Failed runs keep their raws; nothing is deleted unless Snakemake exits 0

## Premises checked in the code

- Staged: only `Result_WU<id>.zip`, plus `DIANN_Libs_WU<id>.zip` when `output_include_libs` is on (`write_outputs_yml` in `snakemake_helpers.py`)
- The zip already holds pmultiqc, `qc_result`, index pages, `dataset.csv` (`rule zip_diann_result`)
- Raws in `work/input/raw` are copies made by the app-runner `inputs` step; pstore stays the source of truth
- Containers run with `--user uid:gid`, so every DIA-NN output is bfabric-owned and deletable

Sizes in WU351848:

| Path | Size |
|---|---|
| `input/raw` | 1.3 TB |
| `temp-DIANN_quantB` | 2.1 GB |
| `out-DIANN_libA` | 1.7 GB |
| `Result_WU351848.zip` | 1.3 GB |
| `out-DIANN_quantB` | 0.98 GB |

## Where it runs

app-runner runs, per chunk: inputs, process, collect, register outputs, then sets the workunit `available` (`run_app` in `app_runner/runner.py`). It has no hook after registration.

- **In `process`, after Snakemake exit 0**: in `prepare.run_request`, next to `deliver_outputs`. Recommended. The zip and `outputs.yml` stay, so a failed registration can still be re-staged without the raws.
- **After registration**: matches "success means delivered", but needs a new post-register hook in bfabric-app-runner. That is a cross-repo change with no gain, because registration only reads the zip.
- **Snakemake `onsuccess:`**: same timing as option 1, but it fires for any successful invocation, including partial targets in dev sessions.

## Delete and keep

Delete:

- `input/raw` data: `.raw`, `.d`, `.d.zip`, converted `.mzML`, extracted `.d`
- `temp-DIANN_*`: `.quant` files
- `out-DIANN_*`: once the raws are gone, Snakemake cannot resume in this dir anyway

Keep:

- `Result_WU<id>.zip`, `DIANN_Libs_WU<id>.zip`, `outputs.yml`
- `logs/`, `params.yml`, `inputs.yml`, `diann_runner_params.toml`, `dataset.csv`, `input/raw/dataset.parquet`

What remains is a few GB, and `workunit_cleaner` removes it after 7 days.

## Safety rules

1. Delete raws only when `raw_dir` resolves inside `work_dir`. On the SUSHI path `prepare.py` reads raws in place from the original data directory ("decision 5"), so a blind delete there destroys primary data. When the guard fails, only converted files under `work_dir/input/raw` may go.
2. Run only on exit 0, with a non-empty Result zip and an existing `outputs.yml`.
3. Make read-only dirs writable before deleting. Staged timsTOF `.d` dirs arrive with mode 555, which is why `workunit_cleaner` fails on WU345467. Use `shutil.rmtree` with an `onexc` handler that adds `u+w` and retries.
4. Never follow symlinks; `shutil.rmtree` does not.
5. Write every removed path and the bytes freed to `logs/cleanup.log`. If the cleanup fails, log a warning and still exit 0: the analysis is already good, and the cleaner catches the rest after 7 days.
6. On failure, delete nothing. The cleaner keeps FAILED dirs for 21 days.

## Parameter plumbing

- `param_core.py`: `"cleanup_on_success": FieldSpec("output", _to_bool, default=False)`, next to `pmultiqc`
- Executable: BOOLEAN `output_cleanup_on_success`, label "Delete input and intermediate files after success", value `'true'`, in `slurmworker/config/A386_DIANN_23/executable_A386_DIANN23plus.yaml` and its copy `bfabric_executable/executable_A386_DIANN_3.2.yaml`
- `make upload` creates a new executable, so rewire A386 through the GUI Edit (see `README_deploy.md`)
- Release: diann_runner commit, then `make_lock.sh`, then pull on the deploy host

Decided: code default `False`, checkbox default `true`, so rollout is safe. Old executables, SUSHI runs, the entrapment harness, and local `prepare workunit` reproductions never delete. Only new submissions with the box ticked do, and method development just unticks it.

## Not solved by this

- Failed runs still hold their raws for 21 days, e.g. WU351887 with 342 GB
- Reruns still copy the raws again. Reusing a previous workunit's raws, as Tobias suggested, is a separate feature, and delete-on-success removes exactly the cache it would reuse.

## Verification plan

- Unit tests: guard with `raw_dir` outside `work_dir` deletes nothing; a mode-555 `.d` dir is removed; the keep-list survives
- TEST instance: one workunit ticked, one unticked; check the dir afterwards and the registered zip in B-Fabric
