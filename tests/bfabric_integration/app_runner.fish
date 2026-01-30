#!/usr/bin/env fish

# Usage: ./app_runner.fish <workunit_ref>
set -q argv[1]; or begin
  echo "Usage: $argv[0] <workunit_ref>"
  exit 1
end
set WORKUNIT_REF $argv[1]
bfabric-app-runner prepare workunit \
  --app-spec ~/projects/slurmworker/config/A386_DIANN_23/app.yml \
  --work-dir WU$WORKUNIT_REF --workunit-ref $WORKUNIT_REF --read-only \
  --force-app-version devel
