# Snakemake workflow for DIA-NN 3-stage analysis
# Usage:
#   snakemake -s Snakefile.DIANN3step --cores 64 all
#   snakemake -s Snakefile.DIANN3step --cores 64 -n  # dry run

import sys
import datetime
from pathlib import Path

# Import the workflow generator and helpers from diann_runner package
from diann_runner.workflow import DiannWorkflow
from diann_runner.snakemake_helpers import (
    build_oktoberfest_config,
    get_final_quantification_outputs,
    parse_flat_params,
    create_diann_workflow,
    detect_input_files,
    convert_parquet_to_tsv,
    zip_diann_results,
    load_config,
    write_outputs_yml,
)

# Plotter is now available as diann-qc command via pyproject.toml entry point

# Detect input files using helper function
RAW_DIR = Path(".")
SAMPLES, INPUT_TYPE, _ = detect_input_files(RAW_DIR)

# Load params (with optional deploy_config.yml overrides)
config_dict = load_config(RAW_DIR)

# Store variables from config
WORKUNITID = config_dict["registration"]["workunit_id"]
CONTAINERID = config_dict["registration"]["container_id"]

# Output directories - keep "out-DIANN" as prefix, but use separate dirs per step
# out-DIANN_libA, out-DIANN_quantB, out-DIANN_quantC
DIANNTEMP = "temp-DIANN"
OUTPUT_PREFIX = "out-DIANN"

# Parse all workflow parameters in one place
# Note: Use WORKFLOW_PARAMS instead of "params" to avoid conflict with Snakemake's
# built-in params object inside rule `run:` blocks
WORKFLOW_PARAMS = parse_flat_params(config_dict["params"])

# Only create globals needed for Snakemake wildcards and conditionals
LIBRARY_PREDICTOR = WORKFLOW_PARAMS["library_predictor"]
ENABLE_STEP_C = WORKFLOW_PARAMS["enable_step_c"]
fasta_config = WORKFLOW_PARAMS["fasta"]  # Alias for fasta parameters used in rules
FINAL_QUANT_OUTPUTS = get_final_quantification_outputs(OUTPUT_PREFIX, WORKUNITID, ENABLE_STEP_C)

# Helper function to get final quantification outputs (must be in Snakefile for Snakemake)
def final_quant_outputs(wildcards):
    """Snakemake input function wrapper for get_final_quantification_outputs."""
    return get_final_quantification_outputs(OUTPUT_PREFIX, WORKUNITID, ENABLE_STEP_C)

# ============================================================================
# Default target rule (must be first rule to be default)
# ============================================================================

rule all:
    input:
        qc_zip = f"Result_WU{WORKUNITID}.zip",
        diann_zip = f"DIANN_Result_WU{WORKUNITID}.zip",
        outputs_yml = "outputs.yml"

# ============================================================================
# File conversion rules
# ============================================================================

rule convert_d_zip:
    input:
        file = RAW_DIR / "{sample}.d.zip"
    output:
        outdir = directory(RAW_DIR / "{sample}.d")
    log:
        logfile = "logs/convert_d_zip_{sample}.log"
    shell:
        """
        echo "Extracting {input.file:q} -> {output.outdir:q}"
        unzip {input.file:q}
        """

rule convert_raw:
    """Convert *.raw -> *.mzML using ThermoRawFileParser.

    Uses native binary if raw_converter_binary is set (for ARM Mac),
    otherwise uses Docker (for x86_64 servers).
    """
    input:
        file = RAW_DIR / "{sample}.raw"
    output:
        file = RAW_DIR / "{sample}.mzML"
    log:
        logfile = "logs/convert_raw_{sample}.log"
    params:
        converter_binary = config_dict["params"].get("raw_converter_binary", ""),
        docker_image = config_dict["params"].get("raw_converter_docker", "thermorawfileparser:2.0.0")
    retries: 3
    shell:
        """
        if [ -n "{params.converter_binary}" ] && [ -x "{params.converter_binary}" ]; then
            # Use native binary (for ARM Mac local testing)
            {params.converter_binary} -i {input.file:q} -o . -f 2
        else
            # Use Docker (for x86_64 servers)
            docker run --rm -v "$PWD":/data {params.docker_image} \
                -i /data/{wildcards.sample}.raw -o /data -f 2
        fi
        """

def get_converted_file(sample: str):
    """Returns the formatted output file path for a given sample."""
    if INPUT_TYPE == "d.zip":
        return RAW_DIR / f"{sample}.d"
    else:  # raw or mzML
        return RAW_DIR / f"{sample}.mzML"

rule convert:
    input:
        files = [get_converted_file(sample) for sample in SAMPLES]
    output:
        result = "results.txt"
    log:
        logfile = "logs/convert.log"
    shell:
        """
        echo "Running analysis on {input.files:q} -> {output.result:q}"
        touch {output.result:q}
        """

# ============================================================================
# FASTA preparation (copy to work dir for Docker access)
# ============================================================================

rule copy_fasta:
    """Copy FASTA database to work directory for Docker container access."""
    output:
        fasta = "database.fasta"
    params:
        source_fasta = fasta_config.get("database_path", "")
    shell:
        """
        echo "Copying FASTA to work directory..."
        cp {params.source_fasta:q} {output.fasta:q}
        """

# ============================================================================
# DIA-NN 3-stage workflow using workflow.py
# ============================================================================

rule diann_generate_scripts:
    """Generate DIA-NN workflow shell scripts using DiannWorkflow class."""
    input:
        mzml_files = [get_converted_file(sample) for sample in SAMPLES],
        fasta = "database.fasta",
        custom_fasta = RAW_DIR / "order.fasta" if (RAW_DIR / "order.fasta").exists() and fasta_config.get("use_custom_fasta", False) else []
    output:
        step_a_script = "step_A_library_search.sh",
        step_b_script = "step_B_quantification_refinement.sh",
        step_c_script = "step_C_final_quantification.sh",
        config_a = f"{OUTPUT_PREFIX}_libA/WU{WORKUNITID}_libA.config.json",
        config_b = f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_quantB.config.json",
        config_c = f"{OUTPUT_PREFIX}_quantC/WU{WORKUNITID}_quantC.config.json"
    log:
        logfile = "logs/diann_generate_scripts.log"
    run:
        # Use local database.fasta (copied from remote path for Docker access)
        fasta_path = str(input.fasta)
        if WORKFLOW_PARAMS["fasta"].get("use_custom_fasta", False) and input.custom_fasta:
            fasta_path = str(input.custom_fasta)

        # Initialize workflow with all parameters from WORKFLOW_PARAMS via helper function
        workflow = create_diann_workflow(
            WORKUNITID, OUTPUT_PREFIX, DIANNTEMP,
            fasta_path, WORKFLOW_PARAMS["var_mods"], WORKFLOW_PARAMS["diann"]
        )

        # Convert input mzML files to list of strings
        raw_files = [str(f) for f in input.mzml_files]

        # Generate all three scripts
        scripts = workflow.generate_all_scripts(
            fasta_path=fasta_path,
            raw_files_step_b=raw_files,
            raw_files_step_c=raw_files,
            quantify_step_b=True,
            use_quant_step_c=True,
            save_library_step_c=True
        )

        print(f"Generated scripts: {scripts}")

# ============================================================================
# Oktoberfest library generation (alternative to DIA-NN Step A)
# ============================================================================

rule generate_oktoberfest_config:
    """Generate Oktoberfest configuration from DIA-NN parameters."""
    input:
        fasta = "database.fasta",
        custom_fasta = RAW_DIR / "order.fasta" if (RAW_DIR / "order.fasta").exists() and fasta_config.get("use_custom_fasta", False) else []
    output:
        config = f"{OUTPUT_PREFIX}_libA/oktoberfest_config.json"
    log:
        logfile = "logs/generate_oktoberfest_config.log"
    run:
        import json

        # Use local database.fasta (copied from remote path for Docker access)
        fasta_path = str(input.fasta)
        if WORKFLOW_PARAMS["fasta"].get("use_custom_fasta", False) and input.custom_fasta:
            fasta_path = str(input.custom_fasta)

        # Build Oktoberfest config using helper function
        # No oktoberfest_params needed - function uses defaults
        oktoberfest_config = build_oktoberfest_config(
            workunit_id=str(WORKUNITID),
            fasta_path=fasta_path,
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
        fasta = "database.fasta"
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

rule run_diann_step_a:
    """Execute Step A: Library Search."""
    input:
        script = rules.diann_generate_scripts.output.step_a_script
    output:
        speclib = f"{OUTPUT_PREFIX}_libA/WU{WORKUNITID}_report-lib.predicted.speclib",
        runlog = f"{OUTPUT_PREFIX}_libA/diann_libA.log.txt"
    log:
        logfile = "logs/run_diann_step_a.log"
    params:
        fasta = lambda wildcards: fasta_config.get("database_path", ""),
        output_dir = f"{OUTPUT_PREFIX}_libA",
        docker_image = WORKFLOW_PARAMS["diann"].get("docker_image", "diann:2.3.1")
    shell:
        """
        export DIANN_DOCKER_IMAGE={params.docker_image:q}
        echo "Running Step A: Library Search (image: $DIANN_DOCKER_IMAGE)"
        bash {input.script:q}

        # Copy FASTA if none exists in output directory
        if ! ls {params.output_dir:q}/*.fasta 1> /dev/null 2>&1; then
            cp {params.fasta:q} {params.output_dir:q}/$(basename {params.fasta:q})
        fi
        """

rule run_diann_step_b:
    """Execute Step B: Quantification with Refinement."""
    input:
        script = rules.diann_generate_scripts.output.step_b_script,
        predicted_lib = get_library_for_step_b()
    output:
        # DIA-NN 2.3.0 creates native .parquet library (with -lib insertion)
        speclib = f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_report-lib.parquet",
        report = f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_report.parquet",
        pg_matrix = f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_report.pg_matrix.tsv",
        stats = f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_report.stats.tsv",
        runlog = f"{OUTPUT_PREFIX}_quantB/diann_quantB.log.txt"
    log:
        logfile = "logs/run_diann_step_b.log"
    params:
        fasta = lambda wildcards: fasta_config.get("database_path", ""),
        output_dir = f"{OUTPUT_PREFIX}_quantB",
        docker_image = WORKFLOW_PARAMS["diann"].get("docker_image", "diann:2.3.1")
    shell:
        """
        export DIANN_DOCKER_IMAGE={params.docker_image:q}
        echo "Running Step B: Quantification with Refinement (image: $DIANN_DOCKER_IMAGE)"
        bash {input.script:q}

        # Copy FASTA if none exists in output directory
        if ! ls {params.output_dir:q}/*.fasta 1> /dev/null 2>&1; then
            cp {params.fasta:q} {params.output_dir:q}/$(basename {params.fasta:q})
        fi
        """

rule run_diann_step_c:
    """Execute Step C: Final Quantification.

    This rule is always defined, but only executes when downstream rules
    (convert_parquet_to_tsv, diannqc, prolfqua_qc) depend on Step C outputs.
    When enable_step_c=False, they depend on Step B outputs instead.
    """
    input:
        script = rules.diann_generate_scripts.output.step_c_script,
        refined_lib = rules.run_diann_step_b.output.speclib
    output:
        # DIA-NN 2.3.0 creates native .parquet library (same as Step B)
        library = f"{OUTPUT_PREFIX}_quantC/WU{WORKUNITID}_report-lib.parquet",
        report = f"{OUTPUT_PREFIX}_quantC/WU{WORKUNITID}_report.parquet",
        pg_matrix = f"{OUTPUT_PREFIX}_quantC/WU{WORKUNITID}_report.pg_matrix.tsv",
        stats = f"{OUTPUT_PREFIX}_quantC/WU{WORKUNITID}_report.stats.tsv",
        runlog = f"{OUTPUT_PREFIX}_quantC/diann_quantC.log.txt"
    log:
        logfile = "logs/run_diann_step_c.log"
    params:
        fasta = lambda wildcards: fasta_config.get("database_path", ""),
        output_dir = f"{OUTPUT_PREFIX}_quantC",
        docker_image = WORKFLOW_PARAMS["diann"].get("docker_image", "diann:2.3.1")
    shell:
        """
        export DIANN_DOCKER_IMAGE={params.docker_image:q}
        echo "Running Step C: Final Quantification (image: $DIANN_DOCKER_IMAGE)"
        bash {input.script:q}

        # Copy FASTA if none exists in output directory
        if ! ls {params.output_dir:q}/*.fasta 1> /dev/null 2>&1; then
            cp {params.fasta:q} {params.output_dir:q}/$(basename {params.fasta:q})
        fi
        """

rule convert_parquet_to_tsv:
    """Convert main parquet report to TSV format for prolfqua and diann-qc."""
    input:
        report_parquet = FINAL_QUANT_OUTPUTS["report_parquet"]
    output:
        tsv = FINAL_QUANT_OUTPUTS["report_tsv"]
    log:
        logfile = "logs/convert_parquet_to_tsv.log"
    params:
        is_dda = WORKFLOW_PARAMS["diann"].get("is_dda", False)
    run:
        convert_parquet_to_tsv(str(input.report_parquet), str(output.tsv), params.is_dda)

rule diannqc:
    """Generate DIA-NN QC plots using diann-qc command."""
    input:
        unpack(final_quant_outputs)
    output:
        pdf = FINAL_QUANT_OUTPUTS["stats"].replace("_report.stats.tsv", "_qc_report.pdf")
    log:
        logfile = "logs/diannqc.log"
    shell:
        """
        diann-qc {input.stats:q} {input.report_tsv:q} {output.pdf:q}
        """

# ============================================================================
# Downstream processing (from old Snakefile)
# ============================================================================

rule zip_diann_result:
    input:
        pdf = rules.diannqc.output.pdf
    output:
        zip = f"DIANN_Result_WU{WORKUNITID}.zip"
    log:
        logfile = "logs/zip_diann_result.log"
    params:
        output_dir = lambda wildcards, input: str(Path(input.pdf).parent),
        workunit_id = WORKUNITID
    run:
        zip_diann_results(
            output_dir=params.output_dir,
            zip_path=output.zip,
            workunit_id=params.workunit_id
        )

rule prolfqua_qc:
    input:
        unpack(final_quant_outputs),
        dataset = "dataset.csv"
    output:
        zip = f"Result_WU{WORKUNITID}.zip",
        runlog = "Rqc.1.log"
    log:
        logfile = "logs/prolfqua_qc.log"
    params:
        prolfquapp_version = config_dict["params"].get("prolfquapp_version", "0.1.8"),
        indir = lambda wildcards, input: str(Path(input.report_tsv).parent),
        container_id = CONTAINERID,
        workunit_id = WORKUNITID
    shell:
        """
        prolfquapp-docker --image-version {params.prolfquapp_version} prolfqua_qc.sh \
            --indir {params.indir:q} -s DIANN \
            --dataset {input.dataset:q} \
            --project {params.container_id} --order {params.container_id} --workunit {params.workunit_id} \
            --outdir qc_result | tee {output.runlog:q}
        zip -r {output.zip:q} qc_result
        """

rule outputsyml:
    input:
        qc = rules.prolfqua_qc.output.zip,
        diann = rules.zip_diann_result.output.zip
    output:
        yaml = "outputs.yml"
    log:
        logfile = "logs/outputsyml.log"
    run:
        write_outputs_yml(output.yaml, input.diann, input.qc)

rule stageoutput:
    input:
        yaml = rules.outputsyml.output.yaml
    output:
        runlog = "staging.log"
    log:
        logfile = "logs/stageoutput.log"
    params:
        app_runner = config_dict["params"].get("app_runner", "fgcz_app_runner"),
        workunit_id = WORKUNITID
    shell:
        """
        {params.app_runner} outputs register --outputs-yaml {input.yaml:q} --workunit-ref {params.workunit_id} \
            | tee {output.runlog:q}
        """


rule print_config_dict:
    """Print all keys and values from config_dict['params']."""
    log:
        logfile = "logs/print_config_dict.log"
    run:
        print("Printing configuration parameters from config_dict['params']:")
        for key, value in sorted(config_dict["params"].items()):
            print(f"{key}: {value}")
