# Snakemake workflow for DIA-NN 3-stage analysis
# Usage:
#   snakemake -s Snakefile.DIANN3step --cores 64 all
#   snakemake -s Snakefile.DIANN3step --cores 64 -n  # dry run

import sys
import os
import yaml
import datetime
import re
from pathlib import Path

# Import the workflow generator and helpers
SNAKEFILE_DIR = Path(workflow.basedir)
sys.path.insert(0, str(SNAKEFILE_DIR / 'src'))
sys.path.insert(0, str(SNAKEFILE_DIR))  # For snakemake_helpers
from diann_runner.workflow import DiannWorkflow
from snakemake_helpers import build_oktoberfest_config, get_final_quantification_outputs, parse_flat_params, create_diann_workflow, detect_input_files

# Plotter is now available as diann-qc command via pyproject.toml entry point

# Detect input files using helper function
RAW_DIR = Path(".")
SAMPLES, INPUT_TYPE, _ = detect_input_files(RAW_DIR)

# Load params
with open(os.path.join(RAW_DIR, "params.yml")) as f:
    config_dict = yaml.safe_load(f)

# Store variables from config
WORKUNITID = config_dict["registration"]["workunit_id"]
CONTAINERID = config_dict["registration"]["container_id"]

# Output directories - keep "out-DIANN" as prefix, but use separate dirs per step
# out-DIANN_libA, out-DIANN_quantB, out-DIANN_quantC
DIANNTEMP = "temp-DIANN"
OUTPUT_PREFIX = "out-DIANN"

# Parse all workflow parameters in one place
params = parse_flat_params(config_dict["params"])

# Only create globals needed for Snakemake wildcards and conditionals
LIBRARY_PREDICTOR = params["library_predictor"]
ENABLE_STEP_C = params["enable_step_c"]
FINAL_QUANT_OUTPUTS = get_final_quantification_outputs(OUTPUT_PREFIX, WORKUNITID, ENABLE_STEP_C)

# Helper function to get final quantification outputs (must be in Snakefile for Snakemake)
def final_quant_outputs(wildcards):
    """Snakemake input function wrapper for get_final_quantification_outputs."""
    return get_final_quantification_outputs(OUTPUT_PREFIX, WORKUNITID, ENABLE_STEP_C)

# ============================================================================
# File conversion rules (unchanged from old Snakefile)
# ============================================================================

rule convert_d_zip:
    input:
        file=RAW_DIR / "{sample}.d.zip"
    output:
        file=directory(RAW_DIR / "{sample}.d")
    shell:
        """
        echo "Extracting {input.file} -> {output.file}"
        unzip {input.file}
        """

rule convert_raw:
    """Convert *.raw -> *.mzML using msconvert."""
    input:
        file=RAW_DIR / "{sample}.raw"
    output:
        file=RAW_DIR / "{sample}.mzML"
    params:
        msconvert_opts = config_dict["params"].get("msconvert_docker_image", "--mzML --64 --zlib --filter \"peakPicking vendor msLevel=1-\""),
        docker_image = "chambm/pwiz-skyline-i-agree-to-the-vendor-licenses timeout 7200 wine msconvert"
    retries: 3
    shell:
        """
        docker run -t --rm --network none -w $PWD -v $PWD:$PWD \
            {params.docker_image} {params.msconvert_opts} {input.file};
        """

def get_converted_file(sample: str):
    """Returns the formatted output file path for a given sample."""
    if INPUT_TYPE == "d.zip":
        return RAW_DIR / f"{sample}.d"
    else:  # raw or mzML
        return RAW_DIR / f"{sample}.mzML"

rule convert:
    input:
        [get_converted_file(sample) for sample in SAMPLES]
    output:
        "results.txt"
    shell:
        """
        echo "Running analysis on {input} -> {output}"
        touch {output}
        """

# ============================================================================
# DIA-NN 3-stage workflow using workflow.py
# ============================================================================

rule diann_generate_scripts:
    """Generate DIA-NN workflow shell scripts using DiannWorkflow class."""
    input:
        mzml_files=[get_converted_file(sample) for sample in SAMPLES],
        fasta=RAW_DIR / "order.fasta" if (RAW_DIR / "order.fasta").exists() and fasta_config.get("use_custom_fasta", False) else []
    output:
        step_a_script="step_A_library_search.sh",
        step_b_script="step_B_quantification_refinement.sh",
        step_c_script="step_C_final_quantification.sh",
        config_a=f"{OUTPUT_PREFIX}_libA/WU{WORKUNITID}_libA.config.json",
        config_b=f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_quantB.config.json",
        config_c=f"{OUTPUT_PREFIX}_quantC/WU{WORKUNITID}_quantC.config.json"
    run:
        # Initialize workflow with all parameters from params via helper function
        workflow = create_diann_workflow(
            WORKUNITID, OUTPUT_PREFIX, DIANNTEMP,
            params["fasta"]["database_path"], params["var_mods"], params["diann"]
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
        fasta=RAW_DIR / "order.fasta" if (RAW_DIR / "order.fasta").exists() and fasta_config.get("use_custom_fasta", False) else []
    output:
        config=f"{OUTPUT_PREFIX}_libA/oktoberfest_config.json"
    run:
        import json

        # Determine FASTA path
        fasta_path = params["fasta"]["database_path"]
        if params["fasta"].get("use_custom_fasta", False) and (RAW_DIR / "order.fasta").exists():
            fasta_path = str(RAW_DIR / "order.fasta")

        # Build Oktoberfest config using helper function
        # No oktoberfest_params needed - function uses defaults
        oktoberfest_config = build_oktoberfest_config(
            workunit_id=str(WORKUNITID),
            fasta_path=fasta_path,
            output_dir=f"{OUTPUT_PREFIX}_libA",
            diann_params=params["diann"]
        )

        # Write config to file
        with open(output.config, 'w') as f:
            json.dump(oktoberfest_config, f, indent=2)

        print(f"Generated Oktoberfest config: {output.config}")

rule run_oktoberfest_library:
    """Execute Oktoberfest library generation."""
    input:
        config=rules.generate_oktoberfest_config.output.config,
        fasta=RAW_DIR / "order.fasta" if (RAW_DIR / "order.fasta").exists() and fasta_config.get("use_custom_fasta", False) else []
    output:
        speclib=f"{OUTPUT_PREFIX}_libA/WU{WORKUNITID}_oktoberfest.speclib.msp",
        log=f"{OUTPUT_PREFIX}_libA/oktoberfest.log.txt"
    shell:
        """
        echo "Running Oktoberfest library generation"
        oktoberfest-docker -c {input.config} 2>&1 | tee {output.log}
        mv {OUTPUT_PREFIX}_libA/speclib.msp {output.speclib}
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
        script=rules.diann_generate_scripts.output.step_a_script
    output:
        speclib=f"{OUTPUT_PREFIX}_libA/WU{WORKUNITID}_report-lib.predicted.speclib",
        log=f"{OUTPUT_PREFIX}_libA/diann_libA.log.txt"
    params:
        fasta=lambda wildcards: fasta_config.get("database_path", ""),
        output_dir=f"{OUTPUT_PREFIX}_libA"
    shell:
        """
        echo "Running Step A: Library Search"
        echo "Command: bash {input.script}"
        bash {input.script}

        # Copy FASTA if none exists in output directory
        if ! ls {params.output_dir}/*.fasta 1> /dev/null 2>&1; then
            echo "Copying FASTA to {params.output_dir}"
            cp "{params.fasta}" "{params.output_dir}/$(basename {params.fasta})"
        fi
        """

rule run_diann_step_b:
    """Execute Step B: Quantification with Refinement."""
    input:
        script=rules.diann_generate_scripts.output.step_b_script,
        predicted_lib=get_library_for_step_b()
    output:
        # DIA-NN 2.3.0 creates native .parquet library (with -lib insertion)
        speclib=f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_report-lib.parquet",
        report=f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_report.parquet",
        pg_matrix=f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_report.pg_matrix.tsv",
        stats=f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_report.stats.tsv",
        log=f"{OUTPUT_PREFIX}_quantB/diann_quantB.log.txt"
    params:
        fasta=lambda wildcards: fasta_config.get("database_path", ""),
        output_dir=f"{OUTPUT_PREFIX}_quantB"
    shell:
        """
        echo "Running Step B: Quantification with Refinement"
        echo "Command: bash {input.script}"
        bash {input.script}

        # Copy FASTA if none exists in output directory
        if ! ls {params.output_dir}/*.fasta 1> /dev/null 2>&1; then
            echo "Copying FASTA to {params.output_dir}"
            cp "{params.fasta}" "{params.output_dir}/$(basename {params.fasta})"
        fi
        """

rule run_diann_step_c:
    """Execute Step C: Final Quantification.

    This rule is always defined, but only executes when downstream rules
    (convert_parquet_to_tsv, diannqc, prolfqua_qc) depend on Step C outputs.
    When enable_step_c=False, they depend on Step B outputs instead.
    """
    input:
        script=rules.diann_generate_scripts.output.step_c_script,
        refined_lib=rules.run_diann_step_b.output.speclib
    output:
        # DIA-NN 2.3.0 creates native .parquet library (same as Step B)
        library=f"{OUTPUT_PREFIX}_quantC/WU{WORKUNITID}_report-lib.parquet",
        report=f"{OUTPUT_PREFIX}_quantC/WU{WORKUNITID}_report.parquet",
        pg_matrix=f"{OUTPUT_PREFIX}_quantC/WU{WORKUNITID}_report.pg_matrix.tsv",
        stats=f"{OUTPUT_PREFIX}_quantC/WU{WORKUNITID}_report.stats.tsv",
        log=f"{OUTPUT_PREFIX}_quantC/diann_quantC.log.txt"
    params:
        fasta=lambda wildcards: fasta_config.get("database_path", ""),
        output_dir=f"{OUTPUT_PREFIX}_quantC"
    shell:
        """
        echo "Running Step C: Final Quantification"
        echo "Command: bash {input.script}"
        bash {input.script}

        # Copy FASTA if none exists in output directory
        if ! ls {params.output_dir}/*.fasta 1> /dev/null 2>&1; then
            echo "Copying FASTA to {params.output_dir}"
            cp "{params.fasta}" "{params.output_dir}/$(basename {params.fasta})"
        fi
        """

rule convert_parquet_to_tsv:
    """Convert main parquet report to TSV format for prolfqua and diann-qc."""
    input:
        report_parquet=FINAL_QUANT_OUTPUTS["report_parquet"]
    output:
        tsv=FINAL_QUANT_OUTPUTS["report_tsv"]
    params:
        is_dda=config_dict["params"]["diann"].get("is_dda", False)
    run:
        from snakemake_helpers import convert_parquet_to_tsv
        convert_parquet_to_tsv(str(input.report_parquet), str(output.tsv), params.is_dda)

rule diannqc:
    """Generate DIA-NN QC plots using diann-qc command."""
    input:
        unpack(final_quant_outputs)
    output:
        pdf=FINAL_QUANT_OUTPUTS["stats"].replace("_report.stats.tsv", "_qc_report.pdf")
    shell:
        """
        diann-qc {input.stats} {input.report_tsv} {output.pdf}
        """

# ============================================================================
# Downstream processing (from old Snakefile)
# ============================================================================

rule zip_diann_result:
    input:
        rules.diannqc.output.pdf
    output:
        zip=f"DIANN_Result_WU{WORKUNITID}.zip"
    params:
        output_dir=lambda wildcards, input: str(Path(input[0]).parent),
        workunit_id=WORKUNITID
    run:
        from snakemake_helpers import zip_diann_results
        zip_diann_results(
            output_dir=params.output_dir,
            zip_path=output.zip,
            workunit_id=params.workunit_id
        )

rule prolfqua_qc:
    input:
        unpack(final_quant_outputs),
        dataset="dataset.csv"
    output:
        zip=f"Result_WU{WORKUNITID}.zip",
        log1="Rqc.1.log"
    params:
        prolfquapp_version = config_dict["params"].get("prolfquapp_version", "0.1.8"),
        indir=lambda wildcards, input: str(Path(input.report_tsv).parent)
    shell:
        """
    	prolfquapp-docker --image-version {params.prolfquapp_version} prolfqua_qc.sh \
            --indir {params.indir} -s DIANN \
            --dataset {input.dataset} \
            --project {CONTAINERID} --order {CONTAINERID} --workunit {WORKUNITID} \
            --outdir qc_result | tee {output.log1}
	    zip -r {output.zip} qc_result
        """

rule outputsyml:
    input:
        qc = rules.prolfqua_qc.output.zip,
        diann = rules.zip_diann_result.output.zip
    params:
        APP_RUNNER="/home/bfabric/slurmworker/bin/fgcz_app_runner 0.0.17"
    output:
        yaml = 'outputs.yml'
    run:
        output1 = {
           'local_path': str(Path(input.diann).resolve()),
            'store_entry_path': input.diann,
            'type': 'bfabric_copy_resource'
        }
        output2 = {
           'local_path': str(Path(input.qc).resolve()),
            'store_entry_path': input.qc,
            'type': 'bfabric_copy_resource'
        }
        outputs_list = [output1, output2]

        data = {
            'outputs': outputs_list
        }
        print(f"YAML file {output.yaml} has been generated.")

        with open(output.yaml, 'w') as file:
            yaml.dump(data, file, default_flow_style=False)

rule stageoutput:
    input:
        yaml=rules.outputsyml.output.yaml
    output:
        log="staging.log"
    shell:
        """
         /home/bfabric/slurmworker/bin/fgcz_app_runner 0.0.17 outputs register --outputs-yaml {input.yaml} --workunit-ref {WORKUNITID} \
         |tee {output.log}
        """

rule all:
    input:
       f"Result_WU{WORKUNITID}.zip",
       f"DIANN_Result_WU{WORKUNITID}.zip"

rule print_config_dict:
    """Print all keys and values from config_dict["params"]."""
    run:
        print("Printing configuration parameters from config_dict['params']:")
        for key, value in sorted(config_dict["params"].items()):
            print(f"{key}: {value}")
