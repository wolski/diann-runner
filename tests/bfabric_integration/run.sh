uv tool install -p 3.13 bfabric-app-runner
bfabric-app-runner --help
bfabric-app-runner run workunit --help


# running a workunit locally.

# use configured version of the workunit:
bfabric-app-runner prepare workunit --app-spec ~/projects/slurmworker/config/A386_DIANN_23/app.yml  --work-dir WU338923 --workunit-ref 338923 --read-only

# force a specific version, e.g. "devel" version, which is e:
bfabric-app-runner prepare workunit --app-spec /Users/witoldwolski/__checkout/slurmworker/config/A386_DIANN_23/app.yml  --work-dir WU338923 --workunit-ref 338923 --read-only --force-app-version devel

#run workunit:
make run-all
make dispatch
make inputs
make process
make stage


# updating and exporting the lock file
uv lock -U && uv sync 
uv export --format pylock.toml -o pylock.toml --no-emit-project
git add pylock.toml
git commit -m "new pylock 383"
git push
ssh33.sh
tmux attach
cd /home/bfabric/slurmworker
git pull

