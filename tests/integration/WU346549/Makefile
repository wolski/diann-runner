## WU346549 integration test driver.
##
## Convenience targets so you can clean + restart without remembering the
## individual commands. Run from this directory (`tests/integration/WU346549/`).
##
## Common flow:
##     make setup            # idempotent download of FASTA + 6 raws (~9 GB, skips if present)
##     make dry              # dry-run via diann-snakemake (DAG only, no execution)
##     make dry-apprunner    # dry-run via `run-diann apprunner` (exercises params/dataset parsing)
##     make test             # setup (if needed) + execute the full workflow (~2 h on 32 cores)
##     make test-apprunner   # setup (if needed) + execute via `run-diann apprunner`
##     make clean            # remove generated outputs; keep raws/FASTA/fixtures
##     make distclean        # nuke everything generated AND downloaded
##
## Override core count:  make test CORES=64

CORES ?= 32

.PHONY: help setup dry dry-apprunner test test-apprunner run clean distclean

help:
	@sed -n 's/^## //p' Makefile

setup:
	./setup_integration_test.py

dry:
	CORES=$(CORES) ./run.sh

## Dry-run the AppRunner entry point (run-diann apprunner) on the same inputs.
dry-apprunner:
	CORES=$(CORES) ./run.sh apprunner

test: setup
	CORES=$(CORES) ./run.sh run

## Execute the full workflow via the AppRunner entry point.
test-apprunner: setup
	CORES=$(CORES) ./run.sh apprunner run

# Back-compat alias.
run: test

## Remove generated outputs (lets you re-run from setup state).
## Keeps: fixtures (params.yml, dataset.csv, inputs.yml), downloads
## (input/*.fasta, input/raw/*.raw), and input/raw/dataset.parquet.
## Note: we don't call `diann-cleanup` here — it does `snakemake
## --delete-all-output`, which eagerly evaluates every rule's input
## function and trips `resolve_raw_converter_image()` when the
## workflow's `97_raw_converter` resolves to False/NO. rm -rf does the
## job.
clean:
	rm -rf .snakemake logs qc_result \
	       out-DIANN_libA out-DIANN_quantB out-DIANN_quantC \
	       temp-DIANN_libA temp-DIANN_quantB temp-DIANN_quantC \
	       step_A_library_search.sh step_B_quantification_refinement.sh step_C_final_quantification.sh \
	       Result_WU346549.zip outputs.yml Rqc.1.log dataset.csv diann_runner_params.toml

## Also remove downloaded raws + FASTA (forces full re-download on next `make setup`).
distclean: clean
	rm -f input/p34486_Proteobench_TripleProteome_20240614.fasta
	rm -f input/raw/LFQ_Orbitrap_AIF_*.raw
