# diann-runner top-level driver.
# Two targets that matter day-to-day: build/verify the container images
# (`deploy`) and run the end-to-end integration test (`integration`).
#
#   make deploy                 # docker images   (rule all  in deploy.smk)
#   make deploy SIF=1           # apptainer SIFs   (rule all_sif)
#   make deploy_sif             # apptainer SIFs   (shortcut for `deploy SIF=1`)
#   make integration            # dry-run the WU346549 end-to-end workflow
#   make integration RUN=1      # execute it (downloads ~9 GB raws, ~2 h)
#   make integration CORES=64   # override core count
#   make entrapment-setup       # download the entrapment inputs (FASTA + Astral raws, ~21 GB)
#   make entrapment-run         # download + run ONE combo (VERSION=/MODS=/CORES= to override)
#   make entrapment-sweep       # download + run ALL DIA-NN version x mods combos
#   make register               # upload the B-Fabric executable YAML (CREATES new)
#   make register ENV=TEST      # ... to the TEST instance

CORES   ?= 32
ENV     ?= PRODUCTION
# entrapment single-combo selection (override on the command line).
VERSION ?= 2.5.1
MODS    ?= metox

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

.PHONY: help deploy deploy_sif integration entrapment-setup entrapment-run entrapment-sweep register

help: ## Show this help
	@echo "diann-runner — make <target>:"
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*## "}{printf "  %-18s %s\n", $$1, $$2}'

deploy: ## build/verify container images (SIF=1 for apptainer)
	snakemake -s deploy.smk $(DEPLOY_TARGET) --cores 1

deploy_sif: ## build apptainer SIFs (native builder, no docker needed)
	snakemake -s deploy.smk all_sif --cores 1

integration: ## run the WU346549 end-to-end test (RUN=1 to execute, CORES=N)
	$(MAKE) -C tests/integration/WU346549 $(INTEGRATION_TARGET) CORES=$(CORES)

entrapment-setup: ## download entrapment inputs (FASTA + Astral raws, ~21 GB)
	$(MAKE) -C tests/integration/entrapment setup

entrapment-run: ## download + run ONE entrapment combo (VERSION=/MODS=/CORES= to override)
	$(MAKE) -C tests/integration/entrapment run VERSION=$(VERSION) MODS=$(MODS) CORES=$(CORES)

entrapment-sweep: ## download + run ALL entrapment version x mods combos (CORES= to override)
	$(MAKE) -C tests/integration/entrapment sweep CORES=$(CORES)

register: ## upload the B-Fabric executable YAML — always CREATES a new one (ENV=TEST)
	$(MAKE) -C bfabric_executable upload ENV=$(ENV)
