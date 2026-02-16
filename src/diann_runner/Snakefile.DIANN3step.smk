# Snakemake workflow for DIA-NN 3-stage analysis
# Usage:
#   snakemake -s Snakefile.DIANN3step --cores 64 all
#   snakemake -s Snakefile.DIANN3step --cores 64 -n  # dry run

import sys
from pathlib import Path

import pandas as pd

# Import helpers from diann_runner package
from diann_runner.snakemake_helpers import (
    copy_fasta_if_missing,
    get_fasta_paths,
    get_final_quantification_outputs,
    get_msconvert_options,
    parse_flat_params,
    create_diann_workflow,
    detect_input_files,
    convert_parquet_to_tsv,
    zip_diann_results,
    zip_library_files,
    load_config,
    load_deploy_config,
    write_outputs_yml,
    resolve_fasta_path,
    run_prozor_inference,
)

# Local rules that don't need cluster execution
localrules: all, print_config_dict, outputsyml, run_prozor_inference

# Detect input files using helper function
RAW_DIR = Path("input/raw")
SAMPLES, INPUT_TYPE, _ = detect_input_files(RAW_DIR)

# Load configs separately for clarity
config_dict = load_config(".")  # params.yml (bfabric parameters)
deploy_dict = load_deploy_config(".")  # defaults_server.yml or defaults_local.yml (docker images, etc.)

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
ENABLE_STEP_C = WORKFLOW_PARAMS["enable_step_c"]
fasta_config = WORKFLOW_PARAMS["fasta"]  # Alias for fasta parameters used in rules
# Resolve FASTA path (handles /misc/fasta/... paths that don't exist locally)
fasta_config["database_path"] = str(resolve_fasta_path(fasta_config["database_path"]))
# Get all FASTA paths (database + custom order.fasta if enabled)
# DIA-NN merges multiple --fasta arguments internally
FASTA_PATHS = get_fasta_paths(fasta_config)
FINAL_QUANT_OUTPUTS = get_final_quantification_outputs(OUTPUT_PREFIX, WORKUNITID, ENABLE_STEP_C)
WORKFLOW_MODE = WORKFLOW_PARAMS.get("workflow_mode", "two_step")
INCLUDE_LIBS = WORKFLOW_PARAMS.get("include_libs", False)

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
    """Extract .d.zip to .d folder for direct use by DIA-NN.

    DIA-NN natively supports Bruker .d input — no mzML conversion needed.
    """
    input:
        file = RAW_DIR / "{sample}.d.zip"
    output:
        folder = directory(RAW_DIR / "{sample}.d")
    log:
        logfile = "logs/convert_d_zip_{sample}.log"
    retries: 3
    shell:
        """
        echo "Extracting {input.file:q}"
        unzip -o {input.file:q}
        """

rule convert_raw:
    """Convert *.raw -> *.mzML using thermoraw CLI.

    Converter options: thermoraw (default), msconvert, msconvert-demultiplex
    """
    input:
        file = RAW_DIR / "{sample}.raw"
    output:
        file = RAW_DIR / "{sample}.mzML"
    log:
        logfile = "logs/convert_raw_{sample}.log"
    params:
        converter = WORKFLOW_PARAMS["raw_converter"],
        image = deploy_dict["thermoraw_image"]
    retries: 3
    shell:
        """
        thermoraw --image {params.image:q} -i {input.file:q} -o {output.file:q} --converter {params.converter}
        """

def get_converted_file(sample: str):
    """Returns the formatted output file path for a given sample."""
    if INPUT_TYPE == "d.zip":
        return RAW_DIR / f"{sample}.d"
    return RAW_DIR / f"{sample}.mzML"

# ============================================================================
# DIA-NN workflow rules (conditional on WORKFLOW_MODE)
# ============================================================================

if WORKFLOW_MODE == "single_step":

    rule diann_generate_single_step_script:
        """Generate single-step DIA-NN script (library prediction + quantification)."""
        input:
            mzml_files = [get_converted_file(sample) for sample in SAMPLES],
            fasta_files = FASTA_PATHS,
        output:
            script = "step_single.sh",
            config_b = f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_quantB.config.json"
        log:
            logfile = "logs/diann_generate_single_step_script.log"
        run:
            fasta_paths = [str(f) for f in input.fasta_files]

            workflow = create_diann_workflow(
                WORKUNITID, OUTPUT_PREFIX, DIANNTEMP,
                fasta_paths[0], WORKFLOW_PARAMS["var_mods"], WORKFLOW_PARAMS["diann"],
                deploy_dict
            )

            raw_files = [str(f) for f in input.mzml_files]

            workflow.generate_single_step(
                fasta_paths=fasta_paths,
                raw_files=raw_files,
            )

    rule run_diann_single_step:
        """Execute single-step DIA-NN: library prediction + quantification."""
        input:
            script = rules.diann_generate_single_step_script.output.script
        output:
            speclib = f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_report-lib.parquet",
            report = f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_report.parquet",
            pg_matrix = f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_report.pg_matrix.tsv",
            stats = f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_report.stats.tsv",
            runlog = f"{OUTPUT_PREFIX}_quantB/diann_quantB.log.txt"
        log:
            logfile = "logs/run_diann_single_step.log"
        params:
            copy_fasta_cmd = lambda wildcards: copy_fasta_if_missing(f"{OUTPUT_PREFIX}_quantB", fasta_config["database_path"])
        shell:
            """
            echo "Running single-step DIA-NN: library prediction + quantification"
            bash {input.script:q}
            {params.copy_fasta_cmd}
            """

    localrules: diann_generate_single_step_script

else:

    rule diann_generate_scripts:
        """Generate DIA-NN workflow shell scripts using DiannWorkflow class."""
        input:
            mzml_files = [get_converted_file(sample) for sample in SAMPLES],
            fasta_files = FASTA_PATHS,
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
            # Get FASTA paths as list of strings
            fasta_paths = [str(f) for f in input.fasta_files]

            # Initialize workflow with all parameters from WORKFLOW_PARAMS via helper function
            # Use first FASTA (database) for workflow initialization
            workflow = create_diann_workflow(
                WORKUNITID, OUTPUT_PREFIX, DIANNTEMP,
                fasta_paths[0], WORKFLOW_PARAMS["var_mods"], WORKFLOW_PARAMS["diann"],
                deploy_dict
            )

            # Convert input mzML files to list of strings
            raw_files = [str(f) for f in input.mzml_files]

            # Generate all three scripts (pass all FASTA paths - DIA-NN merges them)
            scripts = workflow.generate_all_scripts(
                fasta_paths=fasta_paths,
                raw_files_step_b=raw_files,
                raw_files_step_c=raw_files,
                quantify_step_b=True,
                use_quant_step_c=True,
                save_library_step_c=True
            )

            print(f"Generated scripts: {scripts}")

    localrules: diann_generate_scripts

    # ============================================================================
    # DIA-NN 3-stage execution
    # ============================================================================

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
            fasta = lambda wildcards: fasta_config["database_path"],
            output_dir = f"{OUTPUT_PREFIX}_libA",
            copy_fasta_cmd = lambda wildcards: copy_fasta_if_missing(f"{OUTPUT_PREFIX}_libA", fasta_config["database_path"])
        shell:
            """
            echo "Running Step A: Library Search"
            bash {input.script:q}
            {params.copy_fasta_cmd}
            """

    rule run_diann_step_b:
        """Execute Step B: Quantification with Refinement."""
        input:
            script = rules.diann_generate_scripts.output.step_b_script,
            predicted_lib = rules.run_diann_step_a.output.speclib
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
            copy_fasta_cmd = lambda wildcards: copy_fasta_if_missing(f"{OUTPUT_PREFIX}_quantB", fasta_config["database_path"])
        shell:
            """
            echo "Running Step B: Quantification with Refinement"
            bash {input.script:q}
            {params.copy_fasta_cmd}
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
            copy_fasta_cmd = lambda wildcards: copy_fasta_if_missing(f"{OUTPUT_PREFIX}_quantC", fasta_config["database_path"])
        shell:
            """
            echo "Running Step C: Final Quantification"
            bash {input.script:q}
            {params.copy_fasta_cmd}
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
        is_dda = WORKFLOW_PARAMS["diann"]["is_dda"]
    run:
        convert_parquet_to_tsv(str(input.report_parquet), str(output.tsv), params.is_dda)

rule run_prozor_inference:
    """Run prozor protein inference on DIA-NN report.

    Uses Aho-Corasick peptide matching and greedy parsimony to re-annotate
    proteins from the FASTA database. Produces a new parquet file with
    updated Protein.Ids and Protein.Group columns.
    """
    input:
        report_parquet = FINAL_QUANT_OUTPUTS["report_parquet"],
        fasta = lambda wildcards: fasta_config["database_path"]
    output:
        prozor_parquet = FINAL_QUANT_OUTPUTS["report_parquet"].replace(".parquet", "_prozor.parquet"),
        prozor_log = FINAL_QUANT_OUTPUTS["report_parquet"].replace("_report.parquet", "_prozor.log")
    log:
        logfile = "logs/run_prozor_inference.log"
    run:
        run_prozor_inference(
            report_parquet=str(input.report_parquet),
            fasta_path=str(input.fasta),
            output_parquet=str(output.prozor_parquet),
            log_path=str(output.prozor_log),
        )

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
        pdf = rules.diannqc.output.pdf,
        prozor = rules.run_prozor_inference.output.prozor_parquet
    output:
        zip = f"DIANN_Result_WU{WORKUNITID}.zip"
    log:
        logfile = "logs/zip_diann_result.log"
    params:
        output_dir = lambda wildcards, input: str(Path(input.pdf).parent)
    run:
        zip_diann_results(
            output_dir=params.output_dir,
            zip_path=output.zip
        )

if INCLUDE_LIBS:
    rule zip_diann_libs:
        """Zip spectral library files from all output directories."""
        input:
            diann_zip = rules.zip_diann_result.output.zip
        output:
            zip = f"DIANN_Libs_WU{WORKUNITID}.zip"
        log:
            logfile = "logs/zip_diann_libs.log"
        run:
            zip_library_files(OUTPUT_PREFIX, output.zip)

rule dataset_csv:
    input:
        parquet="input/raw/dataset.parquet",
    output:
        csv="dataset.csv",
    run:
        pd.read_parquet(input.parquet).to_csv(output.csv, index=False)


rule prolfqua_qc:
    input:
        unpack(final_quant_outputs),
        dataset = rules.dataset_csv.output.csv,
    output:
        zip = f"Result_WU{WORKUNITID}.zip",
        runlog = "Rqc.1.log"
    log:
        logfile = "logs/prolfqua_qc.log"
    params:
        prolfquapp_image = deploy_dict["prolfquapp_image"],
        indir = lambda wildcards, input: str(Path(input.report_tsv).parent),
        container_id = CONTAINERID,
        workunit_id = WORKUNITID
    shell:
        """
        prolfquapp-docker --image {params.prolfquapp_image} -- prolfqua_qc.sh \
            --indir {params.indir:q} -s DIANN \
            --dataset {input.dataset:q} \
            --project {params.container_id} --order {params.container_id} --workunit {params.workunit_id} \
            --outdir qc_result | tee {output.runlog:q}
        zip -r {output.zip:q} qc_result
        """

rule outputsyml:
    input:
        qc = rules.prolfqua_qc.output.zip,
        diann = rules.zip_diann_result.output.zip,
        libs = f"DIANN_Libs_WU{WORKUNITID}.zip" if INCLUDE_LIBS else []
    output:
        yaml = "outputs.yml"
    log:
        logfile = "logs/outputsyml.log"
    run:
        libs_zip = input.libs if INCLUDE_LIBS else None
        write_outputs_yml(output.yaml, input.diann, input.qc, libs_zip=libs_zip)

rule stageoutput:
    input:
        yaml = rules.outputsyml.output.yaml
    output:
        runlog = "staging.log"
    log:
        logfile = "logs/stageoutput.log"
    params:
        app_runner = deploy_dict["app_runner"],
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
