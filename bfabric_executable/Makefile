# Upload the DIA-NN A386 executable definition to B-Fabric.
#
# `bfabric-cli executable upload` rejects any id and always CREATES A NEW
# executable (prints its new id). It accepts XML or YAML.
#
# Edit the YAML — it is the hand-editable upload source. Needs ~/.bfabricpy.yml
# (web-service password). ENV selects the instance.
#   make upload              # create a new executable from the YAML on PRODUCTION
#   make upload ENV=TEST     # ... on the TEST instance
#   make validate            # check the YAML is uploadable (single 'executable', no id)
#   make upload-xml          # upload via the generated clean XML instead
#   make yaml                # (re)generate the YAML from the GUI-export XML — OVERWRITES edits
#   make dump ID=40588       # dump an existing executable to XML for reference

SRC   := executable_A386_DIANN_3.2.xml          # B-Fabric web-GUI "XML Export" (capture/reference)
YAML  := executable_A386_DIANN_3.2.yaml          # hand-editable upload source (committed)
UPXML := executable_A386_DIANN_3.2.upload.xml     # generated clean XML (gitignored)
ENV   ?= PRODUCTION

.PHONY: upload upload-xml validate yaml xml dump
.DEFAULT_GOAL := upload

validate:
	python3 make_upload.py validate $(YAML)

upload: validate
	BFABRICPY_CONFIG_ENV=$(ENV) bfabric-cli executable upload $(YAML)

upload-xml: xml
	BFABRICPY_CONFIG_ENV=$(ENV) bfabric-cli executable upload $(UPXML)

# Regenerate the editable YAML from the GUI-export XML. OVERWRITES hand edits —
# use only after re-exporting the executable from the B-Fabric web GUI.
yaml:
	python3 make_upload.py $(SRC) $(YAML)

xml:
	python3 make_upload.py $(SRC) $(UPXML)

dump:
	@test -n "$(ID)" || { echo "usage: make dump ID=<executable-id>"; exit 1; }
	bfabric-cli executable dump $(ID) dumped_$(ID).xml --format xml
