# TODO: Run DIA-NN on gstore datasets (sushi/ezRun parity)

## Goal

Make `diann-runner` able to consume datasets registered in gstore the same way the existing sushi/ezRun DIA-NN app does, so a workunit on `fgcz-sushi.uzh.ch` can be reproduced/replaced by this workflow.

## References

- Current sushi/ezRun DIA-NN app: https://github.com/uzh/ezRun/blob/master/R/app-DIANN.R
- Example dataset (p34486 workunit 112148): https://fgcz-sushi.uzh.ch/data_set/p34486/112148

## Open questions

- How does the sushi app resolve dataset rows → raw/mzML paths under `/srv/gstore/projects/pNNNNN/...`? Does `diann-runner` need a gstore-aware path resolver, or do we expect the caller to write absolute paths into `dataset.csv` already?
- Which parameters in `app-DIANN.R` map to existing fields in `parse_flat_params()` / the XML executable, and which are missing?
- FASTA: ezRun pulls it from the order; what does the equivalent look like for `diann-runner` (params.yml `database_path`?) and where on gstore does it live?
- Read-only mounts: `/srv/gstore/projects/*` is NFS-RO. Verify the apptainer wrappers bind it read-only and write outputs to a separate scratch dir.

## First steps

1. Pull `app-DIANN.R` and diff its parameter list against `parse_flat_params()` in `snakemake_helpers.py`.
2. Mirror the dataset/params from p34486/112148 into a local test workdir (raw paths point at `/srv/gstore/projects/p34486/...` if accessible from this host).
3. Run the workflow end-to-end using the apptainer SIFs in `/misc/fgcz01/nextflow_apptainer_cache/`, compare report against the sushi run.

## Notes

- SIFs are deployed at `/misc/fgcz01/nextflow_apptainer_cache/` (see `defaults_server.yml` / `defaults_local.yml`).
- Access to `/srv/gstore/projects/p34486` requires the user to be in `SG_p34486` (autofs map is LDAP-driven).
