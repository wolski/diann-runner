#!/usr/bin/env python3
"""
Command-line interface for DIA-NN workflow generation using cyclopts.
"""

from __future__ import annotations

import json
from pathlib import Path

import cyclopts

from .workflow import DiannWorkflow

app = cyclopts.App(
    name="diann-workflow",
    help="Generate DIA-NN three-stage workflow shell scripts",
)


def _load_workflow_from_defaults(
    config_defaults: Path | None,
    workunit_id: str | None = None,
    output_dir: Path | None = None,
    var_mods: list[str] | None = None,
    threads: int | None = None,
    qvalue: float | None = None,
    diann_bin: str | None = None,
) -> DiannWorkflow:
    """
    Load DiannWorkflow with parameters from config defaults and CLI overrides.
    
    Args:
        config_defaults: Optional JSON config file with default parameters
        workunit_id: Override workunit_id
        output_dir: Override output directory
        var_mods: Override variable modifications
        threads: Override thread count
        qvalue: Override q-value
        diann_bin: Override DIA-NN binary path
    
    Returns:
        Initialized DiannWorkflow instance
    """
    # Load defaults from config if provided
    defaults = {}
    if config_defaults:
        if not config_defaults.exists():
            raise FileNotFoundError(f"Config defaults file not found: {config_defaults}")
        with open(config_defaults) as f:
            defaults = json.load(f)
    
    # Apply defaults, with command-line args taking precedence
    workunit_id = workunit_id or defaults.get("workunit_id")
    output_dir_str = str(output_dir) if output_dir else defaults.get("output_base_dir", "out-DIANN")
    threads = threads if threads is not None else defaults.get("threads", 64)
    qvalue = qvalue if qvalue is not None else defaults.get("qvalue", 0.01)
    diann_bin = diann_bin or defaults.get("diann_bin", "diann-docker")
    
    # Load all other parameters from defaults
    unimod4 = defaults.get("unimod4", True)
    met_excision = defaults.get("met_excision", True)
    no_peptidoforms = defaults.get("no_peptidoforms", False)
    relaxed_prot_inf = defaults.get("relaxed_prot_inf", False)
    reanalyse = defaults.get("reanalyse", True)
    no_norm = defaults.get("no_norm", False)
    min_pep_len = defaults.get("min_pep_len", 6)
    max_pep_len = defaults.get("max_pep_len", 30)
    min_pr_charge = defaults.get("min_pr_charge", 2)
    max_pr_charge = defaults.get("max_pr_charge", 3)
    min_pr_mz = defaults.get("min_pr_mz", 400)
    max_pr_mz = defaults.get("max_pr_mz", 1500)
    missed_cleavages = defaults.get("missed_cleavages", 1)
    cut = defaults.get("cut", "K*,R*")
    mass_acc = defaults.get("mass_acc", 20)
    mass_acc_ms1 = defaults.get("mass_acc_ms1", 15)
    verbose = defaults.get("verbose", 1)
    pg_level = defaults.get("pg_level", 0)
    is_dda = defaults.get("is_dda", False)
    temp_dir_base = defaults.get("temp_dir_base", "temp-DIANN")
    
    if not workunit_id:
        raise ValueError("workunit_id is required (either via --workunit-id or --config-defaults)")
    
    # Parse variable modifications (from CLI or defaults)
    parsed_var_mods = []
    var_mods_source = var_mods if var_mods else defaults.get("var_mods", [])
    if var_mods_source:
        for mod in var_mods_source:
            if isinstance(mod, str):
                parts = mod.split(',')
            else:
                parts = mod
            if len(parts) != 3:
                raise ValueError(f"Invalid var-mod format: {mod}. Expected: unimod_id,mass,residues")
            parsed_var_mods.append(tuple(parts))
    
    return DiannWorkflow(
        workunit_id=workunit_id,
        output_base_dir=output_dir_str,
        var_mods=parsed_var_mods,
        threads=threads,
        qvalue=qvalue,
        diann_bin=diann_bin,
        unimod4=unimod4,
        met_excision=met_excision,
        no_peptidoforms=no_peptidoforms,
        relaxed_prot_inf=relaxed_prot_inf,
        reanalyse=reanalyse,
        no_norm=no_norm,
        min_pep_len=min_pep_len,
        max_pep_len=max_pep_len,
        min_pr_charge=min_pr_charge,
        max_pr_charge=max_pr_charge,
        min_pr_mz=min_pr_mz,
        max_pr_mz=max_pr_mz,
        missed_cleavages=missed_cleavages,
        cut=cut,
        mass_acc=mass_acc,
        mass_acc_ms1=mass_acc_ms1,
        verbose=verbose,
        pg_level=pg_level,
        is_dda=is_dda,
        temp_dir_base=temp_dir_base,
    )


@app.command
def library_search(
    fasta: Path,
    output_dir: Path | None = None,
    workunit_id: str | None = None,
    var_mods: list[str] | None = None,
    threads: int | None = None,
    qvalue: float | None = None,
    diann_bin: str | None = None,
    script_name: str = "step_A_library_search.sh",
    config_defaults: Path | None = None,
):
    """
    Generate Step A: Library search script (predicted library from FASTA).
    
    Args:
        fasta: Path to FASTA database
        output_dir: Output directory for library
        workunit_id: Workunit identifier
        var_mods: Variable modifications in format "unimod_id,mass,residues" (e.g., "35,15.994915,M")
        threads: Number of threads
        qvalue: Q-value threshold
        diann_bin: Path to DIA-NN binary
        script_name: Output script name
        config_defaults: Optional JSON file with default parameters
    
    Example:
        diann-workflow library-search \\
            --fasta /path/to/db.fasta \\
            --output-dir out_A \\
            --workunit-id WU123 \\
            --var-mods "35,15.994915,M" \\
            --threads 64
        
        # Or with config defaults:
        diann-workflow library-search \\
            --config-defaults my_defaults.json \\
            --fasta /path/to/db.fasta
    """
    workflow = _load_workflow_from_defaults(
        config_defaults=config_defaults,
        workunit_id=workunit_id,
        output_dir=output_dir,
        var_mods=var_mods,
        threads=threads,
        qvalue=qvalue,
        diann_bin=diann_bin,
    )
    
    script_path = workflow.generate_step_a_library(
        fasta_path=str(fasta),
        script_name=script_name,
    )
    
    print(f"✓ Generated: {script_path}")


@app.command
def quantification_refinement(
    config: Path,
    predicted_lib: Path,
    raw_files: list[Path],
    quantify: bool = True,
    script_name: str = "step_B_quantification_refinement.sh",
):
    """
    Generate Step B: Quantification with refinement script.

    Requires config JSON from Step A to ensure parameter consistency.

    Args:
        config: Path to .config.json file from Step A (required)
        predicted_lib: Path to predicted library from Step A
        raw_files: List of raw/mzML files
        quantify: Generate quantification matrices (default: True). Set to False to only build refined library.
        script_name: Output script name

    Example:
        # Full quantification (default):
        diann-workflow quantification-refinement \\
            --config out_A_libA/WU123_predicted.speclib.config.json \\
            --predicted-lib out_A_libA/WU123_predicted.speclib \\
            --raw-files sample1.mzML sample2.mzML

        # Library building only (for subset → full workflow):
        diann-workflow quantification-refinement \\
            --config out_A_libA/WU123_predicted.speclib.config.json \\
            --predicted-lib out_A_libA/WU123_predicted.speclib \\
            --raw-files pilot1.mzML pilot2.mzML \\
            --no-quantify
    """
    if not config.exists():
        raise FileNotFoundError(f"Config file not found: {config}")

    # Load workflow from config
    workflow = DiannWorkflow.from_config_file(str(config))

    # Generate script
    script_path = workflow.generate_step_b_quantification_with_refinement(
        raw_files=[str(f) for f in raw_files],
        predicted_lib_path=str(predicted_lib),
        quantify=quantify,
        script_name=script_name,
    )

    mode = "with quantification" if quantify else "library building only"
    print(f"✓ Generated: {script_path} ({mode})")


@app.command
def final_quantification(
    config: Path,
    refined_lib: Path,
    raw_files: list[Path],
    force: bool = False,
    script_name: str = "step_C_final_quantification.sh",
):
    """
    Generate Step C: Final quantification script.

    Requires config JSON from Step B to ensure parameter consistency.

    NOTE: Step C is typically only needed when Step B was run with --no-quantify
    (library building only). If Step B already did quantification with the same
    files, running Step C is redundant. Use --force to override this check.

    Args:
        config: Path to .config.json file from Step B (required)
        refined_lib: Path to refined library from Step B
        raw_files: List of raw/mzML files
        force: Force generation even if Step B already quantified
        script_name: Output script name

    Example:
        diann-workflow final-quantification \\
            --config out_B_quantB/WU123_refined.speclib.config.json \\
            --refined-lib out_B_quantB/WU123_refined.speclib \\
            --raw-files sample*.mzML
    """
    if not config.exists():
        raise FileNotFoundError(f"Config file not found: {config}")

    # Load workflow from config
    workflow = DiannWorkflow.from_config_file(str(config))

    # Check if Step B already did quantification
    if not force:
        # Check for Step B report files indicating quantification was done
        quant_b_dir = Path(workflow.quant_b_dir)
        report_file = quant_b_dir / f"{workflow.workunit_id}_reportB.tsv"
        matrix_file = quant_b_dir / f"{workflow.workunit_id}_reportB.pg_matrix.tsv"

        if report_file.exists() or matrix_file.exists():
            print("⚠️  Warning: Step B appears to have already performed quantification.")
            print(f"   Found: {report_file if report_file.exists() else matrix_file}")
            print("")
            print("   Step C is typically only needed when:")
            print("   - Step B was run with --no-quantify (library building only)")
            print("   - You want to quantify a different/larger set of files than Step B")
            print("")
            print("   If Step B already quantified your target files, the results are")
            print("   already in out-DIANN_quantB/ and Step C is redundant.")
            print("")
            print("   Use --force to generate Step C anyway.")
            return

    # Generate script
    script_path = workflow.generate_step_c_final_quantification(
        raw_files=[str(f) for f in raw_files],
        refined_lib_path=str(refined_lib),
        script_name=script_name,
    )

    print(f"✓ Generated: {script_path}")


@app.command
def all_stages(
    fasta: Path,
    raw_files: list[Path],
    workunit_id: str | None = None,
    var_mods: list[str] | None = None,
    threads: int | None = None,
    qvalue: float | None = None,
    diann_bin: str | None = None,
    config_defaults: Path | None = None,
):
    """
    Generate all three workflow stages at once.
    
    Args:
        fasta: Path to FASTA database
        raw_files: List of raw/mzML files
        workunit_id: Workunit identifier
        var_mods: Variable modifications in format "unimod_id,mass,residues"
        threads: Number of threads
        qvalue: Q-value threshold
        diann_bin: Path to DIA-NN binary
        config_defaults: Optional JSON file with default parameters
    
    Example:
        diann-workflow all-stages \\
            --fasta /path/to/db.fasta \\
            --raw-files sample1.mzML sample2.mzML \\
            --workunit-id WU123 \\
            --var-mods "35,15.994915,M"
        
        # Or with config defaults:
        diann-workflow all-stages \\
            --config-defaults my_defaults.json \\
            --fasta /path/to/db.fasta \\
            --raw-files sample1.mzML sample2.mzML
    """
    workflow = _load_workflow_from_defaults(
        config_defaults=config_defaults,
        workunit_id=workunit_id,
        output_dir=None,  # all_stages uses hardcoded 'out-DIANN'
        var_mods=var_mods,
        threads=threads,
        qvalue=qvalue,
        diann_bin=diann_bin,
    )
    
    print("Generating three-stage DIA-NN workflow...")
    print()
    
    scripts = workflow.generate_all_scripts(
        fasta_path=str(fasta),
        raw_files_step_b=[str(f) for f in raw_files],
        raw_files_step_c=[str(f) for f in raw_files],
    )
    
    print(f"✓ Step A: {scripts['step_a']}")
    print(f"✓ Step B: {scripts['step_b']}")
    print(f"✓ Step C: {scripts['step_c']}")
    
    print()
    print("Run them in order:")
    print(f"  bash {scripts['step_a']}")
    print(f"  bash {scripts['step_b']}")
    print(f"  bash {scripts['step_c']}")


@app.command
def create_config(
    output: Path = Path("diann_config.json"),
    workunit_id: str = "WU001",
    output_base_dir: str = "out-DIANN",
    var_mods: list[str] | None = None,
    diann_bin: str = "diann-docker",
    threads: int = 64,
    qvalue: float = 0.01,
    min_pep_len: int = 6,
    max_pep_len: int = 30,
    min_pr_charge: int = 2,
    max_pr_charge: int = 3,
    min_pr_mz: int = 400,
    max_pr_mz: int = 1500,
    missed_cleavages: int = 1,
    cut: str = "K*,R*",
    mass_acc: int = 20,
    mass_acc_ms1: int = 15,
    verbose: int = 1,
    pg_level: int = 0,
    is_dda: bool = False,
    temp_dir_base: str = "temp-DIANN",
    unimod4: bool = True,
    met_excision: bool = True,
    no_peptidoforms: bool = False,
):
    """
    Create a default configuration JSON file for DIA-NN workflow parameters.
    
    This config can be used with --config-defaults in library-search or all-stages commands
    to set default parameters without specifying them all on the command line.
    
    All DiannWorkflow initialization parameters are supported.
    
    Args:
        output: Path where to save the config JSON
        workunit_id: Workunit identifier
        output_base_dir: Base directory for outputs
        var_mods: Variable modifications in format "unimod_id,mass,residues"
        diann_bin: Path to DIA-NN binary
        threads: Number of threads
        qvalue: Q-value threshold
        min_pep_len: Minimum peptide length
        max_pep_len: Maximum peptide length
        min_pr_charge: Minimum precursor charge
        max_pr_charge: Maximum precursor charge
        min_pr_mz: Minimum precursor m/z
        max_pr_mz: Maximum precursor m/z
        missed_cleavages: Maximum missed cleavages
        cut: Protease specificity
        mass_acc: MS2 mass accuracy (ppm)
        mass_acc_ms1: MS1 mass accuracy (ppm)
        verbose: Verbosity level
        pg_level: Protein grouping level
        is_dda: DDA mode
        temp_dir_base: Base name for temp directories
        unimod4: Enable Carbamidomethyl (C) fixed modification
        met_excision: Enable N-terminal methionine excision
    
    Example:
        # Create a config with custom settings
        diann-workflow create-config \\
            --output my_defaults.json \\
            --workunit-id WU123 \\
            --var-mods "35,15.994915,M" \\
            --threads 32 \\
            --qvalue 0.01
        
        # Then use it
        diann-workflow library-search \\
            --config-defaults my_defaults.json \\
            --fasta db.fasta
    """
    # Parse variable modifications
    parsed_var_mods = []
    if var_mods:
        for mod in var_mods:
            parts = mod.split(',')
            if len(parts) != 3:
                raise ValueError(f"Invalid var-mod format: {mod}. Expected: unimod_id,mass,residues")
            parsed_var_mods.append(list(parts))
    
    config = {
        "workunit_id": workunit_id,
        "output_base_dir": output_base_dir,
        "var_mods": parsed_var_mods,
        "diann_bin": diann_bin,
        "threads": threads,
        "qvalue": qvalue,
        "min_pep_len": min_pep_len,
        "max_pep_len": max_pep_len,
        "min_pr_charge": min_pr_charge,
        "max_pr_charge": max_pr_charge,
        "min_pr_mz": min_pr_mz,
        "max_pr_mz": max_pr_mz,
        "missed_cleavages": missed_cleavages,
        "cut": cut,
        "mass_acc": mass_acc,
        "mass_acc_ms1": mass_acc_ms1,
        "verbose": verbose,
        "pg_level": pg_level,
        "is_dda": is_dda,
        "temp_dir_base": temp_dir_base,
        "unimod4": unimod4,
        "met_excision": met_excision,
        "no_peptidoforms": no_peptidoforms,
    }

    with open(output, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"✓ Created config: {output}")
    print()
    print("Config contents:")
    print(json.dumps(config, indent=2))


@app.command
def run_script(
    script: Path,
    verbose: bool = True,
):
    """
    Execute a generated shell script.
    
    Args:
        script: Path to the shell script to execute
        verbose: Print the command being run
    
    Example:
        diann-workflow run-script --script step_A_library_search.sh
    """
    import subprocess
    import sys
    
    if not script.exists():
        raise FileNotFoundError(f"Script not found: {script}")
    
    if verbose:
        print(f"→ Executing: {script}")
        print()
    
    try:
        # Run the shell script with bash
        result = subprocess.run(
            ["bash", str(script)],
            check=False,  # Don't raise exception, just return the code
        )
        
        if result.returncode == 0:
            print()
            print(f"✓ Script completed successfully")
        else:
            print()
            print(f"✗ Script failed with exit code {result.returncode}", file=sys.stderr)
            sys.exit(result.returncode)
            
    except KeyboardInterrupt:
        print()
        print("✗ Script execution interrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"✗ Error executing script: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    app()

