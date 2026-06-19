# diann-runner top-level driver.
# Two targets that matter day-to-day: build/verify the container images
# (`deploy`) and run the end-to-end integration test (`integration`).
#
#   make deploy                 # docker images   (rule all  in deploy.smk)
#   make deploy SIF=1           # apptainer SIFs   (rule all_sif)
#   make integration            # dry-run the WU346549 end-to-end workflow
#   make integration RUN=1      # execute it (downloads ~9 GB raws, ~2 h)
#   make integration CORES=64   # override core count

CORES ?= 32

# deploy: docker by default; `SIF=1` switches to the apptainer SIF build.
ifdef SIF
DEPLOY_TARGET := all_sif
else
DEPLOY_TARGET := all
endif

# integration: dry-run by default; `RUN=1` executes the full workflow.
ifdef RUN
INTEGRATION_TARGET := test
else
INTEGRATION_TARGET := dry
endif

.PHONY: help deploy integration

help: ## Show this help
	@echo "diann-runner — make <target>:"
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*## "}{printf "  %-14s %s\n", $$1, $$2}'

deploy: ## build/verify container images (SIF=1 for apptainer)
	snakemake -s deploy.smk $(DEPLOY_TARGET) --cores 1

integration: ## run the WU346549 end-to-end test (RUN=1 to execute, CORES=N)
	$(MAKE) -C tests/integration/WU346549 $(INTEGRATION_TARGET) CORES=$(CORES)
