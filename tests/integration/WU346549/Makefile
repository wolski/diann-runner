# WU346549 integration test driver.
# Run from this directory (`tests/integration/WU346549/`).
# Both entry points read the same committed inputs (params.yml +
# input/raw/dataset.parquet); see ../README.md and ../sushi/ for the SUSHI side.
#
# Override core count:  make test CORES=64

CORES ?= 32

.PHONY: help setup dry dry-apprunner dry-sushi test test-apprunner run clean distclean

help: ## Show this help
	@echo "WU346549 integration test — make <target> (override cores: CORES=64):"
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*## "}{printf "  %-16s %s\n", $$1, $$2}'

setup: ## download FASTA + 6 raws (~9 GB, idempotent — skips if present)
	./setup_integration_test.py

dry: ## dry-run via diann-snakemake (DAG only, no execution)
	CORES=$(CORES) ./run.sh

dry-apprunner: ## dry-run via run-diann apprunner (exercises params/dataset parsing)
	CORES=$(CORES) ./run.sh apprunner

dry-sushi: ## dry-run via run-diann sushi (../sushi/ — committed fixture, no download)
	cd ../sushi && ./run.sh

test: setup ## setup + execute the full workflow via diann-snakemake (~2 h on 32 cores)
	CORES=$(CORES) ./run.sh run

test-apprunner: setup ## setup + execute the full workflow via run-diann apprunner
	CORES=$(CORES) ./run.sh apprunner run

run: test ## back-compat alias for `test`

# clean: remove generated outputs (re-run from setup state). Keeps fixtures
# (params.yml, input/raw/dataset.parquet) + downloads (input/*.fasta,
# input/raw/*.raw). We don't call `diann-cleanup` — it runs `snakemake
# --delete-all-output`, which eagerly evaluates every rule's input function and
# trips resolve_raw_converter_image() when 97_raw_converter resolves to False.
clean: ## remove generated outputs; keep raws/FASTA/fixtures
	rm -rf .snakemake logs qc_result \
	       out-DIANN_libA out-DIANN_quantB out-DIANN_quantC \
	       temp-DIANN_libA temp-DIANN_quantB temp-DIANN_quantC \
	       step_A_library_search.sh step_B_quantification_refinement.sh step_C_final_quantification.sh \
	       Result_WU346549.zip outputs.yml Rqc.1.log dataset.csv diann_runner_params.toml

distclean: clean ## also remove downloaded raws + FASTA (forces re-download)
	rm -f input/p34486_Proteobench_TripleProteome_20240614.fasta
	rm -f input/raw/LFQ_Orbitrap_AIF_*.raw
