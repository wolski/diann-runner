# uv run --verbose --locked --project "." snakemake -d "work" all -p
# snakemake --delete-all-output
# uv run --verbose --locked --project "." snakemake -d "work" --delete-all-output all
# uv run --verbose --locked --project "." snakemake -d "work" --rerun-incomplete
# /home/bfabric/slurmworker/bin/fgcz_app_runner 0.0.17 outputs register --help

import sys
import os
import yaml
import datetime
from pathlib import Path


RAW_DIR = Path(".")
dzip_files = list(RAW_DIR.glob("*.d.zip"))
raw_files = list(RAW_DIR.glob("*.raw"))

# Ensure we only have one file type
if dzip_files and raw_files:
    raise ValueError("Error: Both .d.zip and .raw files detected in the same run!")
# Identify sample names dynamically
if dzip_files:
    SAMPLES = [f.stem.removesuffix(".d") for f in dzip_files]
elif raw_files:
    SAMPLES = [f.stem for f in raw_files]
else:
    raise ValueError("No valid input files (.d.zip or .raw) found.")



with open(os.path.join(RAW_DIR, "params.yml")) as f:
    config_dict = yaml.safe_load(f)

# Example: store some variables
WORKUNITID = config_dict["registration"]["workunit_id"]
CONTAINERID = config_dict["registration"]["container_id"]

# Where we store DIA-NN output (similarly to out-<date>/ in Makefile)
# WEW Not sure if this is a good idea?
today_str = datetime.date.today().isoformat()  # e.g. 2025-01-10
DIANNTEMP   = f"temp-DIANN"
DIANNOUTPUT = f"out-DIANN"

# Example placeholders for DIANN arguments:

rule convert_d_zip:
    input:
        file=RAW_DIR / "{sample}.d.zip"
    output:
        file=directory(RAW_DIR / "{sample}.d")
    shell:
        """
        echo "Extracting {input.file} -> {output.file}"
        # cp {input.file} {output.file}
        unzip {input.file}
        """


rule convert_raw:
    """
    Convert *.raw -> *.mzML using the 'convert_raw_to_format' command.
    """
    input:
        file=RAW_DIR / "{sample}.raw"
    output:
        file=RAW_DIR / "{sample}.mzML"
    params:
        msconvert = config_dict["params"]["01|msconvertopts"]
    retries: 3

    shell:
        """
        # echo "msconvert params: {params.msconvert}"
        # ./convert_raw_to_mzML.sh {input.file} {output.file}
        docker run -t --rm -v $PWD:$PWD -w $PWD \
            --stop-timeout 43200 --stop-signal SIGKILL \
            {params.msconvert} --outdir {RAW_DIR} {input.file};
        """

def get_converted_file(sample : str):
    """Returns the formatted output file path for a given sample."""
    print(f"Checking for sample: {sample}")
    if dzip_files:
        return RAW_DIR / f"{sample}.d"
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


rule diann_sh:
    input: 
        [get_converted_file(sample) for sample in SAMPLES]
    output:
        script = "rundiann.sh"
    params:
        DIANNCUSTOMSEQ = config_dict["params"]["DIANNCUSTOMSEQ"],
        DIANNBIN = "/usr/diann/diann-2.3.0/diann-linux",
    run:    
        """Return the command that runs DIA-NN based on config and current folder."""
        # Collect input .d directories or .mzML
        # Same approach as in Makefile: find .d or .mzML

        for key, value in config_dict["params"].items():
            if value == "None":
                config_dict["params"][key] = None

        DIANNCFG_PARTS = (
        "--threads 64 --qvalue 0.01 --matrices --predictor",
        "--met-excision --cut K*,R* --min-pep-len 6 --max-pep-len 30 --smart-profiling",
        config_dict["params"]["DIANNVARMOD"],
        config_dict["params"]["DIANNCFG0"],
        config_dict["params"]["DIANNCFG1"],
        config_dict["params"]["DIANNCFG4"],
        config_dict["params"]["DIANNCFG5"],
        config_dict["params"]["DIANNCFG6"],
        config_dict["params"]["DIANNCFG7"],
        config_dict["params"]["DIANNCFG8"],
        config_dict["params"]["DIANNFreestyle"],
        )
        DIANNCFG = " \\\n".join(filter(None, DIANNCFG_PARTS))

        #if config_dict["params"]["DIANNFreestyle"] != "None":
        #    DIANNCFG = DIANNCFG + " \\\n" + config_dict["params"]["DIANNFreestyle"]
            
        diann_input_dirs = []
        
        for item in input:
            diann_input_dirs.append(f"--f {item} ")

        diann_input_str = " ".join(diann_input_dirs)
        print(f"diann_input_str: {diann_input_str}")


        fasta_default = config_dict["params"]["DIANNFASTA0"]
        fasta_default = re.sub(r"--fasta-search --fasta", "", fasta_default).strip()
        fasta_default = f"--fasta-search --fasta {fasta_default}"
        print("DIANNCUSTOMSEQ:", params.DIANNCUSTOMSEQ)
        
        fasta_path = RAW_DIR / "order.fasta"
        if fasta_path.exists() and fasta_path.stat().st_size > 0 and  params.DIANNCUSTOMSEQ == "true":
            fasta = fasta_default + " " + (f"--fasta {fasta_path}")
        else:
            fasta  =  fasta_default

        print("----------------")
        print(fasta)
        
        # Generate final command
        cmd = (
        f"#!/bin/bash \n"
        f"set -ex \n"
        f"mkdir -p {DIANNTEMP} \n"
        f"mkdir -p {DIANNOUTPUT} \n"
        f"nice -19 {params.DIANNBIN} \\\n" 
        f"{fasta} \\\n"
        f"{diann_input_str} \\\n"
        f"{DIANNCFG} \\\n"
        f"--out-lib {DIANNOUTPUT}/WU{WORKUNITID}_report-lib.tsv --out-lib-copy \\\n"
        f"--temp {DIANNTEMP} \\\n"
        f"--out {DIANNOUTPUT}/WU{WORKUNITID}_report.tsv \\\n"
        f"| tee diann.log.txt"
        )
        # Write the command to rundiann.sh
        with open(output.script, "w") as f:
            f.write(cmd)

        # Make the script executable
        os.chmod(output.script, 0o755)

rule run_diann_sh:
    input:
        rules.diann_sh.output.script

rule diann:
    """
    Runs DIA-NN on the .mzML (or .d) data, producing a final TSV report + logs.
    The Makefile used a variable $(DIANNTMP) with lots of arguments.
    """
    input:
        diannsh = rules.diann_sh.output.script   # after write_rundiann
    output:
        # Key DIA-NN outputs
        report_tsv = f"{DIANNOUTPUT}/WU{WORKUNITID}_report.tsv",
        stats_tsv    = f"{DIANNOUTPUT}/WU{WORKUNITID}_report.stats.tsv",
        diann_log  = "diann.log.txt",
    shell:
        """
        echo {input.diannsh}
        ./{input.diannsh}
        """


rule diannqc:
    input:
        stats_tsv=rules.diann.output.stats_tsv,
        report_tsv=rules.diann.output.report_tsv
    output:
        pdf=f"{DIANNOUTPUT}/WU{WORKUNITID}_DIANN_qc_report.pdf"
    params:
        script="/home/bfabric/slurmworker/config/DIANN/DIA-NN-Plotter.py"
    shell:
        """

        {sys.executable} {params.script} {input.stats_tsv} {input.report_tsv} {output.pdf}
        """

rule zip_diann_result:
    input:
        rules.diannqc.output.pdf
    output:
        zip=f"DIANN_Result_WU{WORKUNITID}.zip",
        log="zip.log"
    shell:
        """
        find . -type f -regex ".*log\.txt$\|.*\.yml$\|.*\.sh$\|.*database[0-9]*\.fasta$\|.*[ct]sv$\|.*tsv\.speclib$\|.*\.pdf$\|.*report\.manifest\.txt" ! -regex ".*first-pass.*"\
    	| sort \
	    | zip -9 -@ {output.zip} \
	    | tee {output.log}
        """

rule prolfqua_qc:
    input:
        report_tsv=rules.diann.output.report_tsv
    output:
        zip=f"Result_WU{WORKUNITID}.zip",
        log1="Rqc.1.log"


    params:
        PROLFQUAPP = "/home/bfabric/slurmworker/bin/prolfquapp_docker.sh"

    shell:
        """
    	{params.PROLFQUAPP} --image-version 0.1.8 prolfqua_qc.sh --indir {DIANNOUTPUT} -s DIANN \
        --dataset dataset.csv \
        --project {CONTAINERID} --order {CONTAINERID} --workunit {WORKUNITID} --outdir qc_result | tee {output.log1}
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

        # Step 3: Create the main dictionary and assign the outputs list to the key 'outputs'
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
       rules.outputsyml.output.yaml

rule print_config_dict:
    """
    Print all keys and values from config_dict["params"].
    """
    run:
        print("Printing configuration parameters from config_dict['params']:")
        # Option 1: Using a simple loop (sorted alphabetically by key)
        for key, value in sorted(config_dict["params"].items()):
            print(f"{key}: {value}")



