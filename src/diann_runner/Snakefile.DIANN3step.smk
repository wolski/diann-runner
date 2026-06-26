# Snakemake workflow for DIA-NN 3-stage analysis
# Usage:
#   snakemake -s Snakefile.DIANN3step --cores 64 all
#   snakemake -s Snakefile.DIANN3step --cores 64 -n  # dry run

import sys
import shutil
from pathlib import Path

import pandas as pd

# Import helpers from diann_runner package
from diann_runner.snakemake_helpers import (
    copy_fasta_if_missing,
    get_diann_input_dependency,
    get_diann_input_path,
    get_fasta_paths,
    get_final_quantification_outputs,
    get_msconvert_options,
    parse_flat_params,
    load_workflow_params,
    resolve_raw_converter_image,
    create_diann_workflow,
    detect_input_files,
    write_result_index,
    zip_diann_results,
    zip_library_files,
    load_deploy_config,
    write_outputs_yml,
    resolve_fasta_path,
    run_prozor_inference,
)

# Local rules that don't need cluster execution
localrules: all, print_config_dict, outputsyml, result_index, run_prozor_inference

# Raw-file source directory (may be external / read-only). Conversion OUTPUTS go
# to CONVERTED_DIR under the work dir, never back into an external source dir.
# Defaults reproduce the historical AppRunner layout (everything in input/raw).
RAW_SOURCE_DIR = Path(config.get("raw_file_dir", "input/raw"))
CONVERTED_DIR = Path(config.get("converted_dir", str(RAW_SOURCE_DIR)))
# In-container mount target when RAW_SOURCE_DIR is external (set by run-diann);
# None means the source dir is under the work dir and needs no extra mount.
RAW_MOUNT_TARGET = config.get("raw_mount_target")
RAW_MOUNT = (
    (str(RAW_SOURCE_DIR.resolve()), RAW_MOUNT_TARGET) if RAW_MOUNT_TARGET else None
)

# Detect input files in the source directory
SAMPLES, INPUT_TYPE, _ = detect_input_files(RAW_SOURCE_DIR)

# Deploy config (docker images, threads, etc.). An explicit container_runtime
# (run-diann --runtime / snakemake --config container_runtime=...) overrides the
# config key and host auto-detection.
deploy_dict = load_deploy_config(".", runtime_override=config.get("container_runtime"))

# Dual-mode params + registration: normalized diann_runner_params.toml if present,
# else legacy params.yml + parse_flat_params (keeps diann-snakemake / AppRunner working).
WORKFLOW_PARAMS, REGISTRATION = load_workflow_params(".", config)
WORKUNITID = REGISTRATION["workunit_id"]
CONTAINERID = REGISTRATION["container_id"]

# Normalized dataset paths + whether to register outputs (AppRunner-only).
DATASET_CSV = config.get("dataset_csv", "dataset.csv")
DATASET_PARQUET = config.get("dataset_parquet", "input/raw/dataset.parquet")
# Robust to bool (eval'd --config) or string ("false") values.
REGISTER_OUTPUTS = str(config.get("register_outputs", True)).lower() != "false"

# Output directories - keep "out-DIANN" as prefix, but use separate dirs per step
# out-DIANN_libA, out-DIANN_quantB, out-DIANN_quantC
DIANNTEMP = "temp-DIANN"
OUTPUT_PREFIX = "out-DIANN"

# WORKFLOW_PARAMS / REGISTRATION are loaded above via load_workflow_params()
# (dual-mode TOML or legacy params.yml). Use WORKFLOW_PARAMS (not "params") to
# avoid clashing with Snakemake's built-in params object inside rule run-blocks.

# Only create globals needed for Snakemake wildcards and conditionals
ENABLE_STEP_C = WORKFLOW_PARAMS["enable_step_c"]
DIANN_VERSION = WORKFLOW_PARAMS["diann"]["diann_version"]
RAW_CONVERTER = WORKFLOW_PARAMS["raw_converter"]
fasta_config = WORKFLOW_PARAMS["fasta"]  # Alias for fasta parameters used in rules
# Resolve FASTA path (handles /misc/fasta/... paths that don't exist locally)
fasta_config["database_path"] = str(resolve_fasta_path(fasta_config["database_path"]))
# Get all FASTA paths (database + custom order.fasta if enabled)
# DIA-NN merges multiple --fasta arguments internally
FASTA_PATHS = get_fasta_paths(fasta_config)
FINAL_QUANT_OUTPUTS = get_final_quantification_outputs(OUTPUT_PREFIX, WORKUNITID, ENABLE_STEP_C)
WORKFLOW_MODE = WORKFLOW_PARAMS.get("workflow_mode", "two_step")
INCLUDE_LIBS = WORKFLOW_PARAMS.get("include_libs", False)
GENERATE_PMULTIQC = WORKFLOW_PARAMS.get("generate_pmultiqc", True)
PMULTIQC_HTML = "pmultiqc_result/pmultiqc_diann_report.html"
RESULT_INDEX_MD = "index.md"
RESULT_INDEX_HTML = "index.html"

# Helper function to get final quantification outputs (must be in Snakefile for Snakemake)
def final_quant_outputs(wildcards):
    """Snakemake input function wrapper for get_final_quantification_outputs."""
    return get_final_quantification_outputs(OUTPUT_PREFIX, WORKUNITID, ENABLE_STEP_C)



# ============================================================================
# Default target rule (must be first rule to be default)
# ============================================================================

# Final targets. outputs.yml (and B-Fabric registration) is AppRunner-only;
# the SUSHI path sets register_outputs=false so the DIA-NN run does not register.
FINAL_TARGETS = [f"Result_WU{WORKUNITID}.zip"]
if REGISTER_OUTPUTS:
    FINAL_TARGETS.append("outputs.yml")
# Optional pmultiqc HTML report — standalone final target (not folded into the
# Result zip yet). Gated on the generate_pmultiqc flag (default true).
if GENERATE_PMULTIQC:
    FINAL_TARGETS.append(PMULTIQC_HTML)

rule all:
    input:
        FINAL_TARGETS

# ============================================================================
# File conversion rules
# ============================================================================

rule convert_d_zip:
    """Extract .d.zip to .d folder for direct use by DIA-NN.

    DIA-NN natively supports Bruker .d input — no mzML conversion needed.
    """
    input:
        file = RAW_SOURCE_DIR / "{sample}.d.zip"
    output:
        marker = CONVERTED_DIR / "{sample}.done"
    log:
        logfile = "logs/convert_d_zip_{sample}.log"
    params:
        extract_dir = CONVERTED_DIR,
        folder = lambda wildcards: CONVERTED_DIR / f"{wildcards.sample}.d"
    retries: 3
    shell:
        """
        echo "Extracting {input.file:q}"
        unzip -o {input.file:q} -d {params.extract_dir:q}
        test -d {params.folder:q}
        touch {output.marker:q}
        """

rule convert_raw:
    """Convert *.raw -> *.mzML using thermoraw CLI.

    Converter options: thermoraw, msconvert, msconvert-demultiplex. Not used
    when raw_converter is 'native' (DIA-NN reads the .raw directly), so the
    image is resolved lazily — resolve_raw_converter_image() rejects 'native'
    and must not run at parse time.
    """
    input:
        file = RAW_SOURCE_DIR / "{sample}.raw"
    output:
        file = CONVERTED_DIR / "{sample}.mzML"
    log:
        logfile = "logs/convert_raw_{sample}.log"
    params:
        converter = WORKFLOW_PARAMS["raw_converter"],
        image = lambda wildcards: resolve_raw_converter_image(WORKFLOW_PARAMS["raw_converter"], deploy_dict),
        runtime = deploy_dict["container_runtime"]
    retries: 3
    shell:
        """
        thermoraw --runtime {params.runtime} --image {params.image:q} -i {input.file:q} -o {output.file:q} --converter {params.converter}
        """

def get_converted_file(sample: str):
    """Returns the container-visible input path for DIA-NN for a given sample."""
    return get_diann_input_path(
        sample, INPUT_TYPE, RAW_CONVERTER, RAW_SOURCE_DIR, CONVERTED_DIR, RAW_MOUNT_TARGET
    )

def get_conversion_dependency(sample: str):
    """Returns the Snakemake dependency (host path) that prepares a DIA-NN input."""
    return get_diann_input_dependency(
        sample, INPUT_TYPE, RAW_CONVERTER, RAW_SOURCE_DIR, CONVERTED_DIR
    )

# ============================================================================
# DIA-NN workflow rules (conditional on WORKFLOW_MODE)
# ============================================================================

if WORKFLOW_MODE == "single_step":

    rule diann_generate_single_step_script:
        """Generate single-step DIA-NN script (library prediction + quantification)."""
        input:
            raw_dependencies = [get_conversion_dependency(sample) for sample in SAMPLES],
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
                fasta_paths, WORKFLOW_PARAMS["var_mods"], WORKFLOW_PARAMS["diann"],
                deploy_dict, raw_mount=RAW_MOUNT
            )

            raw_files = [str(get_converted_file(sample)) for sample in SAMPLES]

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
            copy_fasta_cmd = lambda wildcards: copy_fasta_if_missing(f"{OUTPUT_PREFIX}_quantB", FASTA_PATHS)
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
            raw_dependencies = [get_conversion_dependency(sample) for sample in SAMPLES],
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
            workflow = create_diann_workflow(
                WORKUNITID, OUTPUT_PREFIX, DIANNTEMP,
                fasta_paths, WORKFLOW_PARAMS["var_mods"], WORKFLOW_PARAMS["diann"],
                deploy_dict, raw_mount=RAW_MOUNT
            )

            # Convert input files to DIA-NN input paths.
            raw_files = [str(get_converted_file(sample)) for sample in SAMPLES]

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
            output_dir = f"{OUTPUT_PREFIX}_libA",
            copy_fasta_cmd = lambda wildcards: copy_fasta_if_missing(f"{OUTPUT_PREFIX}_libA", FASTA_PATHS)
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
            copy_fasta_cmd = lambda wildcards: copy_fasta_if_missing(f"{OUTPUT_PREFIX}_quantB", FASTA_PATHS)
        shell:
            """
            echo "Running Step B: Quantification with Refinement"
            bash {input.script:q}
            {params.copy_fasta_cmd}
            """

    rule run_diann_step_c:
        """Execute Step C: Final Quantification.

        This rule is always defined, but only executes when downstream rules
        (diannqc, prolfqua_qc, pmultiqc_diann_report) depend on Step C outputs.
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
            copy_fasta_cmd = lambda wildcards: copy_fasta_if_missing(f"{OUTPUT_PREFIX}_quantC", FASTA_PATHS)
        shell:
            """
            echo "Running Step C: Final Quantification"
            bash {input.script:q}
            {params.copy_fasta_cmd}
            """

rule run_prozor_inference:
    """Run prozor protein inference on DIA-NN report.

    Uses Aho-Corasick peptide matching and greedy parsimony to re-annotate
    proteins from the FASTA database. Produces a new parquet file with
    updated Protein.Ids and Protein.Group columns.
    """
    input:
        report_parquet = FINAL_QUANT_OUTPUTS["report_parquet"],
        fasta = FASTA_PATHS
    output:
        prozor_parquet = FINAL_QUANT_OUTPUTS["report_parquet"].replace(".parquet", "_prozor.parquet"),
        prozor_log = FINAL_QUANT_OUTPUTS["report_parquet"].replace("_report.parquet", "_prozor.log")
    log:
        logfile = "logs/run_prozor_inference.log"
    run:
        run_prozor_inference(
            report_parquet=str(input.report_parquet),
            fasta_path=[str(path) for path in input.fasta],
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
        diann-qc {input.stats:q} {input.report_parquet:q} {output.pdf:q}
        """

# ============================================================================
# Downstream processing (from old Snakefile)
# ============================================================================

rule zip_diann_result:
    input:
        pdf = rules.diannqc.output.pdf,
        prozor = rules.run_prozor_inference.output.prozor_parquet,
        dataset = DATASET_CSV,
        qc_dir = "qc_result",
        index_md = RESULT_INDEX_MD,
        index_html = RESULT_INDEX_HTML,
        pmultiqc = PMULTIQC_HTML if GENERATE_PMULTIQC else []
    output:
        zip = f"Result_WU{WORKUNITID}.zip"
    log:
        logfile = "logs/zip_diann_result.log"
    params:
        output_dir = lambda wildcards, input: str(Path(input.pdf).parent)
    run:
        shutil.copy2(input.dataset, Path(params.output_dir) / Path(input.dataset).name)
        extra_dirs = [input.qc_dir]
        if GENERATE_PMULTIQC:
            extra_dirs.append(str(Path(input.pmultiqc).parent))
        zip_diann_results(
            output_dir=params.output_dir,
            zip_path=output.zip,
            extra_files=[input.index_md, input.index_html],
            extra_dirs=extra_dirs
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

# Build dataset.csv from the AppRunner parquet only when needed. In the
# normalized (run-diann) path, prepare_work_dir() has already written
# DATASET_CSV, so this rule is not defined and DATASET_CSV is used as a source.
if not Path(DATASET_CSV).exists() and Path(DATASET_PARQUET).exists():
    rule dataset_csv:
        input:
            parquet=DATASET_PARQUET,
        output:
            csv=DATASET_CSV,
        run:
            pd.read_parquet(input.parquet).to_csv(output.csv, index=False)


rule prolfqua_qc:
    input:
        unpack(final_quant_outputs),
        dataset = DATASET_CSV,
    output:
        qc_dir = directory("qc_result"),
        runlog = "Rqc.1.log"
    log:
        logfile = "logs/prolfqua_qc.log"
    params:
        prolfquapp_image = deploy_dict["prolfquapp_image"],
        runtime = deploy_dict["container_runtime"],
        # prolfquapp X.Y.Z discovers and reads the native DIA-NN parquet in this
        # directory directly (no Run->File.Name TSV needed).
        indir = lambda wildcards, input: str(Path(input.report_parquet).parent),
        container_id = CONTAINERID,
        workunit_id = WORKUNITID
    shell:
        """
        prolfquapp-docker --runtime {params.runtime} --image {params.prolfquapp_image} -- prolfqua_qc.sh \
            --indir {params.indir:q} -s DIANN \
            --dataset {input.dataset:q} \
            --project {params.container_id} --order {params.container_id} --workunit {params.workunit_id} \
            --outdir qc_result --flat_outdir | tee {output.runlog:q}
        cp {input.dataset:q} qc_result/dataset.csv
        """

rule result_index:
    input:
        unpack(final_quant_outputs),
        pdf = rules.diannqc.output.pdf,
        prozor = rules.run_prozor_inference.output.prozor_parquet,
        qc_dir = "qc_result",
        pmultiqc = PMULTIQC_HTML if GENERATE_PMULTIQC else []
    output:
        md = RESULT_INDEX_MD,
        html = RESULT_INDEX_HTML
    run:
        write_result_index(
            index_md=output.md,
            index_html=output.html,
            workunit_id=WORKUNITID,
            quant_dir=str(Path(input.pdf).parent),
            final_outputs=FINAL_QUANT_OUTPUTS,
            fasta_paths=[str(path) for path in FASTA_PATHS],
            include_pmultiqc=GENERATE_PMULTIQC,
        )

rule pmultiqc_diann_report:
    """Generate a pmultiqc HTML report from the native DIA-NN parquet.

    Stages a clean input dir (the parquet renamed to report.parquet, the run log
    to report.log.txt) so pmultiqc's exact-name file patterns match, then runs
    MultiQC with the DIA-NN plugin. The staging dir deliberately contains no
    *report.tsv: pmultiqc tries the TSV pattern first and the DIA-NN reader needs
    the native Run column. Report-derived sections populate; experimental-design
    and MS1-level metrics are not shown (the runner does not emit those inputs).
    """
    input:
        report = FINAL_QUANT_OUTPUTS["report_parquet"],
        runlog = FINAL_QUANT_OUTPUTS["runlog"],
    output:
        html = PMULTIQC_HTML
    log:
        logfile = "logs/pmultiqc_diann_report.log"
    shell:
        """
        rm -rf pmultiqc_input pmultiqc_result
        mkdir -p pmultiqc_input
        cp {input.report:q} pmultiqc_input/report.parquet
        cp {input.runlog:q} pmultiqc_input/report.log.txt
        multiqc pmultiqc_input --diann-plugin \
            -o pmultiqc_result \
            --filename pmultiqc_diann_report.html \
            --force --verbose
        test -s {output.html:q}
        """

rule outputsyml:
    input:
        diann = rules.zip_diann_result.output.zip,
        libs = f"DIANN_Libs_WU{WORKUNITID}.zip" if INCLUDE_LIBS else []
    output:
        yaml = "outputs.yml"
    log:
        logfile = "logs/outputsyml.log"
    run:
        libs_zip = input.libs if INCLUDE_LIBS else None
        write_outputs_yml(output.yaml, input.diann, libs_zip=libs_zip)

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
    """Print the normalized DIA-NN workflow parameters."""
    log:
        logfile = "logs/print_config_dict.log"
    run:
        print("Normalized DIA-NN workflow parameters:")
        for key, value in sorted(WORKFLOW_PARAMS["diann"].items()):
            print(f"{key}: {value}")
