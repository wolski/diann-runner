# Upload the DIA-NN A386 executable definition to B-Fabric.
#
# `bfabric-cli executable upload` rejects any id and always CREATES A NEW
# executable (prints its new id). It needs the clean XML shape (no attributes,
# no parameter back-references) — NOT the web-GUI "XML Export". `make generate`
# derives that clean file from the committed export.
#
# Needs ~/.bfabricpy.yml (web-service password). ENV selects the instance.
#   make generate           # rebuild the clean upload file from the export
#   make upload              # create a new executable on PRODUCTION
#   make upload ENV=TEST     # create a new executable on the TEST instance
#   make dump ID=26960       # dump an existing executable (clean format) for reference

SRC    := executable_A386_DIANN_3.2.xml
UPLOAD := executable_A386_DIANN_3.2.upload.xml
ENV    ?= PRODUCTION

.PHONY: generate validate upload dump
.DEFAULT_GOAL := upload

generate:
	python3 make_upload_xml.py $(SRC) $(UPLOAD)

validate: generate
	@if grep -q 'classname=' $(UPLOAD); then \
	  echo "ERROR: $(UPLOAD) still has classname= attributes (not uploadable)"; exit 1; \
	else echo "OK: $(UPLOAD) is clean"; fi

upload: validate
	BFABRICPY_CONFIG_ENV=$(ENV) bfabric-cli executable upload $(UPLOAD)

dump:
	@test -n "$(ID)" || { echo "usage: make dump ID=<executable-id>"; exit 1; }
	bfabric-cli executable dump $(ID) dumped_$(ID).xml --format xml
