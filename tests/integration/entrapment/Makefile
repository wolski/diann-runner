# ProteoBench DIA-Astral entrapment (no-digestion) integration test driver.
# Run from this directory (`tests/integration/entrapment/`).
#
# The DIA-NN version and mods arm are parameters so the same downloaded data can
# be re-run per version; each combo lands in runs/diann-<version>-<mods>/.
#
#   make setup                          # download FASTA + 6 Astral raws (~21 GB)
#   make dry                            # dry-run one combo (VERSION/MODS below)
#   make run                            # execute one combo
#   make run VERSION=2.5.0 MODS=nomods  # pick version + mods arm
#   make sweep                          # execute every VERSIONS x MODS_ARMS combo
#   make sweep-dry                      # dry-run the full sweep (DAG only)
#   make ... CORES=64
#   make run RUNTIME=apptainer          # use the shared SIF cache (default: docker)
#   make clean run VERSION=2.3.2 MODS=nomods   # force-regenerate a combo, then run

CORES   ?= 32
VERSION ?= 2.5.1
MODS    ?= metox
# Container runtime: docker (default; uses images from `make deploy`) or
# apptainer (reads the shared /misc/fgcz01 SIF cache, only on nodes that mount it).
RUNTIME ?= docker
# Full sweep matrix (override on the command line, e.g. VERSIONS="2.5.1").
VERSIONS  ?= 2.3.2 2.5.0 2.5.1
MODS_ARMS ?= nomods metox

.PHONY: help setup dry run sweep sweep-dry clean clean-runs distclean

help: ## Show this help
	@echo "entrapment integration test — make <target> (VERSION=, MODS=, CORES=, RUNTIME=):"
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*## "}{printf "  %-12s %s\n", $$1, $$2}'

setup: ## download entrapment FASTA + 6 DIA-Astral raws (~21 GB, idempotent)
	./setup_integration_test.py

dry: ## dry-run one combo (VERSION=$(VERSION) MODS=$(MODS)); build DAG only
	VERSION=$(VERSION) MODS=$(MODS) CORES=$(CORES) RUNTIME=$(RUNTIME) ./run.sh dry

run: setup ## setup + execute one combo (VERSION=$(VERSION) MODS=$(MODS))
	VERSION=$(VERSION) MODS=$(MODS) CORES=$(CORES) RUNTIME=$(RUNTIME) ./run.sh run

sweep: setup ## execute every VERSIONS x MODS_ARMS combo, each in its own folder
	@for v in $(VERSIONS); do for m in $(MODS_ARMS); do \
	  echo "=== diann-$$v-$$m ==="; \
	  VERSION=$$v MODS=$$m CORES=$(CORES) RUNTIME=$(RUNTIME) ./run.sh run || exit $$?; \
	done; done

sweep-dry: ## dry-run every VERSIONS x MODS_ARMS combo (no downloads needed if input/ present)
	@for v in $(VERSIONS); do for m in $(MODS_ARMS); do \
	  echo "=== diann-$$v-$$m (dry) ==="; \
	  VERSION=$$v MODS=$$m CORES=$(CORES) RUNTIME=$(RUNTIME) ./run.sh dry || exit $$?; \
	done; done

clean: ## snakemake --delete-all-output for ONE combo (VERSION/MODS) so scripts regenerate
	VERSION=$(VERSION) MODS=$(MODS) CORES=$(CORES) RUNTIME=$(RUNTIME) ./run.sh clean

clean-runs: ## remove ALL run outputs, every combo (keeps downloaded input/)
	rm -rf runs

distclean: clean-runs ## also remove downloaded FASTA + raws
	rm -rf input
