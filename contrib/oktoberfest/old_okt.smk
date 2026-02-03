# Old Oktoberfest rules removed from Snakefile.DIANN3step.smk
# Kept here for documentation purposes only - these rules are NOT included in the workflow
#
# To use Oktoberfest, see the contrib/oktoberfest/README.md for the standalone workflow.
#
# These rules were removed because:
# 1. Oktoberfest is optional and rarely used
# 2. Keeping them in the main Snakefile adds complexity
# 3. The LIBRARY_PREDICTOR parameter is now deprecated

# ============================================================================
# Oktoberfest library generation (alternative to DIA-NN Step A)
# ============================================================================

rule generate_oktoberfest_config:
    """Generate Oktoberfest configuration from DIA-NN parameters."""
    input:
        fasta_files = FASTA_PATHS,
    output:
        config = f"{OUTPUT_PREFIX}_libA/oktoberfest_config.json"
    log:
        logfile = "logs/generate_oktoberfest_config.log"
    run:
        # Oktoberfest uses single FASTA - use first (database) only
        # TODO: Support multiple FASTAs in Oktoberfest if needed
        oktoberfest_config = build_oktoberfest_config(
            workunit_id=str(WORKUNITID),
            fasta_path=str(input.fasta_files[0]),
            output_dir=f"{OUTPUT_PREFIX}_libA",
            diann_params=WORKFLOW_PARAMS["diann"]
        )

        # Write config to file
        with open(output.config, 'w') as f:
            json.dump(oktoberfest_config, f, indent=2)

        print(f"Generated Oktoberfest config: {output.config}")

rule run_oktoberfest_library:
    """Execute Oktoberfest library generation."""
    input:
        config = rules.generate_oktoberfest_config.output.config,
        fasta_files = FASTA_PATHS
    output:
        speclib = f"{OUTPUT_PREFIX}_libA/WU{WORKUNITID}_oktoberfest.speclib.msp",
        runlog = f"{OUTPUT_PREFIX}_libA/oktoberfest.log.txt"
    log:
        logfile = "logs/run_oktoberfest_library.log"
    params:
        output_prefix = OUTPUT_PREFIX
    shell:
        """
        echo "Running Oktoberfest library generation"
        oktoberfest-docker -c {input.config:q} 2>&1 | tee {output.runlog:q}
        mv {params.output_prefix}_libA/speclib.msp {output.speclib:q}
        """

def get_library_for_step_b():
    """Return the appropriate library file for Step B based on LIBRARY_PREDICTOR."""
    if LIBRARY_PREDICTOR == "oktoberfest":
        return f"{OUTPUT_PREFIX}_libA/WU{WORKUNITID}_oktoberfest.speclib.msp"
    else:
        return f"{OUTPUT_PREFIX}_libA/WU{WORKUNITID}_report-lib.predicted.speclib"

# Required import (was in main Snakefile):
# from diann_runner.snakemake_helpers import build_oktoberfest_config
#
# Required in localrules:
# localrules: ..., generate_oktoberfest_config, ...
#
# Required global variable:
# LIBRARY_PREDICTOR = WORKFLOW_PARAMS["library_predictor"]
