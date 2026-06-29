# Upload the DIA-NN A386 executable definition (YAML) to B-Fabric.
#
# `bfabric-cli executable upload` rejects any id and always CREATES A NEW
# executable (it prints the new id). Edit the YAML — it is the source of truth.
# Needs ~/.bfabricpy.yml (web-service password). ENV selects the instance.
#   make upload            # create a new executable on PRODUCTION
#   make upload ENV=TEST   # ... on the TEST instance
#   make validate          # local check: single 'executable', no id, has parameters
#   make dump ID=40588     # dump an existing executable to XML for reference

YAML := executable_A386_DIANN_3.2.yaml
ENV  ?= PRODUCTION

.PHONY: upload validate dump
.DEFAULT_GOAL := upload

validate:
	@python3 -c "import yaml; d=yaml.safe_load(open('$(YAML)')); e=d['executable']; assert set(d)=={'executable'}, 'top level must be exactly executable:'; assert 'id' not in e, 'remove id (upload always CREATES a new executable)'; assert e.get('parameter'), 'no parameters'; print('OK: $(YAML) (%d params, no id)' % len(e['parameter']))"

upload: validate
	BFABRICPY_CONFIG_ENV=$(ENV) bfabric-cli executable upload $(YAML)

dump:
	@test -n "$(ID)" || { echo "usage: make dump ID=<executable-id>"; exit 1; }
	bfabric-cli executable dump $(ID) dumped_$(ID).xml --format xml
