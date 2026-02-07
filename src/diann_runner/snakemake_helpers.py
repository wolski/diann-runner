"""Helper functions for Snakemake workflow."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd
import yaml


def write_outputs_yml(output_file: str, diann_zip: str, qc_zip: str) -> None:
    """Write outputs.yml for bfabric-app-runner staging."""
    output1 = {
        "local_path": str(Path(diann_zip).resolve()),
        "store_entry_path": diann_zip,
        "type": "bfabric_copy_resource"
    }
    output2 = {
        "local_path": str(Path(qc_zip).resolve()),
        "store_entry_path": qc_zip,
        "type": "bfabric_copy_resource"
    }
    data = {"outputs": [output1, output2]}
    with open(output_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False)
    print(f"YAML file {output_file} has been generated.")


def is_server_environment() -> bool:
    """Detect if running on production server (as bfabric user)."""
    import getpass
    return getpass.getuser() == "bfabric" or os.path.exists("/home/bfabric")


def resolve_fasta_path(fasta_path: str | Path) -> Path:
    """Resolve FASTA path, enforcing use of input/ directory copy.

    The dispatcher (or user) must ensure the FASTA file is copied to input/
    so it is accessible within the Docker container.
    """
    fasta_path = Path(fasta_path)
    return Path("input") / fasta_path.name


def load_config(raw_dir: Path) -> dict:
    """Load params.yml (bfabric-generated parameters).

    Returns:
        config_dict with 'params' and 'registration' from params.yml
    """
    with open(os.path.join(raw_dir, "params.yml")) as f:
        config_dict = yaml.safe_load(f)
    return config_dict


def load_deploy_config(raw_dir: Path) -> dict:
    """Load deployment config (docker images, threads, etc.).

    Loads defaults_server.yml or defaults_local.yml based on environment.
    Search order: raw_dir first, then package config/ dir.

    Returns:
        Dict with deployment settings from the yaml file.
    """
    env = "server" if is_server_environment() else "local"
    defaults_filename = f"defaults_{env}.yml"

    package_config_dir = Path(__file__).parent / "config"
    search_paths = [Path(raw_dir), package_config_dir]

    for search_dir in search_paths:
        defaults_path = search_dir / defaults_filename
        if defaults_path.exists():
            with open(defaults_path) as f:
                return yaml.safe_load(f)

    raise FileNotFoundError(f"Deploy config not found: {defaults_filename} (searched: {search_paths})")


def detect_input_files(raw_dir: Path) -> tuple[list[str], str, dict[str, list[Path]]]:
    """
    Detect and validate input mass spectrometry files in a directory.

    This function scans for .d.zip, .raw, and .mzML files, validates that no
    conflicting source types coexist, and prioritizes source files over
    converted outputs.

    Priority logic:
    - .d.zip and .raw are "source" files (cannot coexist)
    - .mzML files are conversion outputs (lower priority)
    - If .raw + .mzML exist together, use .raw (mzML are conversion outputs)
    - If .d.zip + .d exist together, use .d.zip (d folders are extraction outputs)

    Args:
        raw_dir: Path to directory containing input files

    Returns:
        Tuple of (samples, input_type, file_lists):
        - samples: List of sample names (file stems)
        - input_type: String indicating file type ("d.zip", "raw", or "mzML")
        - file_lists: Dict with keys 'dzip_files', 'raw_files', 'mzml_files'

    Raises:
        ValueError: If both .d.zip and .raw files exist (conflicting source types)
        ValueError: If no valid input files are found

    Example:
        >>> samples, input_type, files = detect_input_files(Path("."))
        >>> print(f"Found {len(samples)} {input_type} files")
    """
    # Glob for all potential input files
    dzip_files = list(raw_dir.glob("*.d.zip"))
    raw_files = list(raw_dir.glob("*.raw"))
    mzml_files = list(raw_dir.glob("*.mzML"))

    # Error only if incompatible SOURCE types coexist
    if dzip_files and raw_files:
        raise ValueError("Error: Both .d.zip and .raw files detected - choose one input type!")

    # Prioritize source files over converted outputs
    # If .raw + .mzML exist together, use .raw (mzML are conversion outputs)
    # If .d.zip + .d exist together, use .d.zip (d folders are extraction outputs)
    if dzip_files:
        samples = [f.stem.removesuffix(".d") for f in dzip_files]
        input_type = "d.zip"
    elif raw_files:
        # Use .raw even if .mzML exist (they're conversion outputs)
        samples = [f.stem for f in raw_files]
        input_type = "raw"
    elif mzml_files:
        # Only use .mzML if no source files exist
        samples = [f.stem for f in mzml_files]
        input_type = "mzML"
    else:
        raise ValueError("No valid input files (.d.zip, .raw, or .mzML) found.")

    # Return file lists for reference if needed
    file_lists = {
        'dzip_files': dzip_files,
        'raw_files': raw_files,
        'mzml_files': mzml_files
    }

    return samples, input_type, file_lists


def parse_var_mods_string(var_mods_str):
    """Parse variable modifications string from XML format to list of tuples.

    Example input: '--var-mods 1 --var-mod UniMod:35,15.994915,M'
    Returns: [('35', '15.994915', 'M')]

    Args:
        var_mods_str: String from Bfabric XML parameter

    Returns:
        List of tuples: [(unimod_id, mass_delta, residues), ...]
    """
    if not var_mods_str or var_mods_str == 'None':
        return []

    var_mods = []
    # Find all --var-mod definitions
    pattern = r'--var-mod UniMod:(\d+),([0-9.]+),([A-Z^]+)'
    matches = re.findall(pattern, var_mods_str)

    for unimod_id, mass, residues in matches:
        var_mods.append((unimod_id, mass, residues))

    return var_mods


def parse_flat_params(flat_params):
    """Transform flat Bfabric XML keys to nested structure expected by workflow.

    Maps Bfabric XML keys (e.g., '06a_diann_mods_variable') to Python-friendly
    nested structure (e.g., diann.var_mods).

    Args:
        flat_params: Dictionary with flat XML parameter keys from params.yml

    Returns:
        Dictionary with keys:
        - 'diann': Dict of DIA-NN parameters
        - 'fasta': Dict of FASTA parameters
        - 'var_mods': List of modification tuples (already converted from diann.var_mods)
        - 'library_predictor': String ('diann' or 'oktoberfest')
        - 'enable_step_c': Boolean (whether to run Step C quantification)
    """
    diann = {}
    fasta = {}

    # Parse modification parameters
    if '06a_diann_mods_variable' in flat_params:
        var_mods_str = flat_params['06a_diann_mods_variable']
        diann['var_mods'] = parse_var_mods_string(var_mods_str)
    else:
        diann['var_mods'] = []

    diann['no_peptidoforms'] = flat_params['06b_diann_mods_no_peptidoforms'].lower() == 'true'
    diann['unimod4'] = flat_params['06c_diann_mods_unimod4'].lower() == 'true'
    diann['met_excision'] = flat_params['06d_diann_mods_met_excision'].lower() == 'true'

    # Parse peptide constraints
    diann['min_pep_len'] = int(flat_params['07_diann_peptide_min_length'])
    diann['max_pep_len'] = int(flat_params['07_diann_peptide_max_length'])
    diann['min_pr_charge'] = int(flat_params['07_diann_peptide_precursor_charge_min'])
    diann['max_pr_charge'] = int(flat_params['07_diann_peptide_precursor_charge_max'])
    diann['min_pr_mz'] = int(flat_params['07_diann_peptide_precursor_mz_min'])
    diann['max_pr_mz'] = int(flat_params['07_diann_peptide_precursor_mz_max'])
    diann['min_fr_mz'] = int(flat_params['07_diann_peptide_fragment_mz_min'])
    diann['max_fr_mz'] = int(flat_params['07_diann_peptide_fragment_mz_max'])

    # Parse digestion
    diann['cut'] = flat_params['08_diann_digestion_cut']
    diann['missed_cleavages'] = int(flat_params['08_diann_digestion_missed_cleavages'])

    # Parse mass accuracy (0 = auto-determine)
    mass_acc_ms2_str = flat_params['09_diann_mass_acc_ms2']
    diann['mass_acc'] = int(mass_acc_ms2_str) if mass_acc_ms2_str != 'AUTO' else 0
    mass_acc_ms1_str = flat_params['09_diann_mass_acc_ms1']
    diann['mass_acc_ms1'] = int(mass_acc_ms1_str) if mass_acc_ms1_str != 'AUTO' else 0

    # Parse scoring
    diann['qvalue'] = float(flat_params['10_diann_scoring_qvalue'])

    # Parse protein inference (e.g., "protein_names_1" -> 1)
    pg_level_str = flat_params['11a_diann_protein_pg_level']
    diann['pg_level'] = int(pg_level_str.split("_")[-1])
    diann['relaxed_prot_inf'] = flat_params['11b_diann_protein_relaxed_prot_inf'].lower() == 'true'

    # Parse quantification & normalization
    diann['reanalyse'] = flat_params['12a_diann_quantification_reanalyse'].lower() == 'true'
    diann['no_norm'] = flat_params['12b_diann_quantification_no_norm'].lower() == 'true'

    # Parse other settings
    diann['verbose'] = int(flat_params['99_other_verbose'])
    diann['diann_bin'] = flat_params['98_diann_binary']

    # Parse DDA mode
    diann['is_dda'] = flat_params['05_diann_is_dda'].lower() == 'true'

    # Parse scan window
    scan_window_str = flat_params.get('05b_diann_scan_window', 'AUTO')
    diann['scan_window'] = 'AUTO' if scan_window_str == 'AUTO' else int(scan_window_str)

    # Parse FASTA - use alternate path if main is NONE
    fasta_main = flat_params['03_fasta_database_path']
    if fasta_main.upper() == 'NONE':
        fasta['database_path'] = flat_params['03b_additional_fasta_database_path']
    else:
        fasta['database_path'] = fasta_main
    fasta['use_custom_fasta'] = flat_params['03_fasta_use_custom'].lower() == 'true'

    # Convert var_mods to tuples for DiannWorkflow
    var_mods_tuples = [tuple(mod) for mod in diann['var_mods']]

    # Parse workflow control parameters
    library_predictor = flat_params.get('library_predictor', 'diann')  # Default to diann
    enable_step_c_str = flat_params.get('enable_step_c', 'false')
    enable_step_c = enable_step_c_str.lower() == 'true' if isinstance(enable_step_c_str, str) else bool(enable_step_c_str)
    workflow_mode = flat_params.get('02_workflow_mode', 'two_step')

    # Parse conversion/runtime parameters
    # raw_converter: thermoraw (default), msconvert, msconvert-demultiplex
    raw_converter = flat_params.get('97_raw_converter', 'thermoraw')

    return {
        'diann': diann,
        'fasta': fasta,
        'var_mods': var_mods_tuples,
        'library_predictor': library_predictor,
        'enable_step_c': enable_step_c,
        'workflow_mode': workflow_mode,
        'raw_converter': raw_converter,
    }


def create_diann_workflow(
    workunit_id: str,
    output_prefix: str,
    temp_dir_base: str,
    fasta_path: str,
    var_mods: list,
    diann_params: dict,
    deploy_params: dict
):
    """
    Create DiannWorkflow instance from parsed parameters.

    This helper function encapsulates the initialization of DiannWorkflow with all
    required and optional parameters, using sensible defaults from the diann_params
    dictionary.

    Args:
        workunit_id: Workunit ID (will be prefixed with "WU")
        output_prefix: Output directory prefix (e.g., "out-DIANN")
        temp_dir_base: Base name for temporary directories
        fasta_path: Path to FASTA database file
        var_mods: List of variable modification tuples
        diann_params: Dictionary of DIA-NN parameters from parse_flat_params()
        deploy_params: Dictionary of deployment settings from load_deploy_config()

    Returns:
        Initialized DiannWorkflow instance
    """
    from diann_runner.workflow import DiannWorkflow

    return DiannWorkflow(
        workunit_id=f"WU{workunit_id}",
        output_base_dir=output_prefix,
        temp_dir_base=temp_dir_base,
        fasta_file=fasta_path,
        var_mods=var_mods,
        diann_bin=diann_params["diann_bin"],
        docker_image=deploy_params["diann_docker_image"],
        threads=deploy_params["threads"],
        qvalue=diann_params["qvalue"],
        min_pep_len=diann_params["min_pep_len"],
        max_pep_len=diann_params["max_pep_len"],
        min_pr_charge=diann_params["min_pr_charge"],
        max_pr_charge=diann_params["max_pr_charge"],
        min_pr_mz=diann_params["min_pr_mz"],
        max_pr_mz=diann_params["max_pr_mz"],
        min_fr_mz=diann_params["min_fr_mz"],
        max_fr_mz=diann_params["max_fr_mz"],
        missed_cleavages=diann_params["missed_cleavages"],
        cut=diann_params["cut"],
        mass_acc=diann_params["mass_acc"],
        mass_acc_ms1=diann_params["mass_acc_ms1"],
        scan_window=diann_params["scan_window"],
        verbose=diann_params["verbose"],
        pg_level=diann_params["pg_level"],
        is_dda=diann_params["is_dda"],
        unimod4=diann_params["unimod4"],
        met_excision=diann_params["met_excision"],
        relaxed_prot_inf=diann_params["relaxed_prot_inf"],
        reanalyse=diann_params["reanalyse"],
        no_norm=diann_params["no_norm"],
    )


def get_final_quantification_outputs(
    output_prefix: str,
    workunit_id: str,
    enable_step_c: bool = True
) -> dict:
    """
    Get final quantification outputs from Step B or Step C.

    DIA-NN 2.3.0 creates native .speclib libraries with consistent naming.
    Both Step B and Step C create: WU{id}_report-lib.parquet.speclib

    Args:
        output_prefix: Output directory prefix (e.g., "out-DIANN")
        workunit_id: Workunit ID
        enable_step_c: If True, use Step C outputs; if False, use Step B outputs

    Returns:
        Dictionary with keys: report_parquet, report_tsv, pg_matrix,
                             stats, library
    """
    step = "quantC" if enable_step_c else "quantB"

    # Both steps use the same library naming (.parquet)
    library_filename = f"WU{workunit_id}_report-lib.parquet"

    return {
        "report_parquet": f"{output_prefix}_{step}/WU{workunit_id}_report.parquet",
        "report_tsv": f"{output_prefix}_{step}/WU{workunit_id}_report.tsv",
        "pg_matrix": f"{output_prefix}_{step}/WU{workunit_id}_report.pg_matrix.tsv",
        "stats": f"{output_prefix}_{step}/WU{workunit_id}_report.stats.tsv",
        "library": f"{output_prefix}_{step}/{library_filename}"
    }


def convert_parquet_to_tsv(parquet_path: str, tsv_path: str, is_dda: bool = False) -> None:
    """
    Convert a parquet file to TSV format.

    DIA-NN 2.3+ uses different column names than older versions.
    This function renames columns to match the old naming scheme for compatibility.

    Args:
        parquet_path: Path to input parquet file
        tsv_path: Path to output TSV file
        is_dda: If True, also copy PG.MaxLFQ to PG.Quantity for prolfqua compatibility
    """
    df = pd.read_parquet(parquet_path)

    # Map DIA-NN 2.3+ column names to old column names for compatibility
    # Note: DIA-NN 2.3 already outputs PG.MaxLFQ and Genes.MaxLFQ, so only rename Run
    column_mapping = {
        'Run': 'File.Name',
    }
    df = df.rename(columns=column_mapping)

    # For DDA data: prolfqua expects PG.Quantity but DIA-NN outputs PG.MaxLFQ
    # Copy PG.MaxLFQ to PG.Quantity for compatibility with both diann-qc and prolfqua
    if is_dda and 'PG.MaxLFQ' in df.columns and 'PG.Quantity' not in df.columns:
        df['PG.Quantity'] = df['PG.MaxLFQ']
        print("Added PG.Quantity column from PG.MaxLFQ for DDA data compatibility")

    df.to_csv(tsv_path, sep='\t', index=False)
    print(f"Converted {parquet_path} -> {tsv_path}")


def zip_diann_results(output_dir: str, zip_path: str) -> None:
    """
    Zip DIA-NN results directory.

    Args:
        output_dir: Output directory to zip (e.g., "out-DIANN_quantB")
        zip_path: Path to output zip file
    """
    import zipfile
    from pathlib import Path

    output_path = Path(output_dir)
    if not output_path.exists():
        raise FileNotFoundError(f"Output directory {output_dir} does not exist")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        # Add all files from the output directory
        for file_path in output_path.rglob('*'):
            if file_path.is_file():
                # Store with relative path from output directory
                arcname = file_path.relative_to(output_path.parent)
                zipf.write(file_path, arcname)
                print(f"  adding: {arcname}")

    print(f"Created {zip_path} with results from {output_dir}")


def copy_fasta_if_missing(output_dir: str, fasta_path: str) -> str:
    """
    Generate shell command to copy FASTA to output directory if not already present.

    Args:
        output_dir: Output directory path
        fasta_path: Source FASTA file path

    Returns:
        Shell command string for FASTA copy with existence check
    """
    return f'''
# Copy FASTA if none exists in output directory
if ! ls "{output_dir}"/*.fasta 1> /dev/null 2>&1; then
    cp "{fasta_path}" "{output_dir}"/$(basename "{fasta_path}")
fi'''


def build_oktoberfest_config(
    workunit_id: str,
    fasta_path: str,
    output_dir: str,
    diann_params: dict,
    oktoberfest_params: dict = None
) -> dict:
    """
    Build Oktoberfest configuration dictionary.

    Most settings are derived from diann_params or use sensible defaults.
    oktoberfest_params is optional and typically empty (not defined in Bfabric XML).

    Args:
        workunit_id: Workunit ID for tagging
        fasta_path: Path to FASTA database
        output_dir: Output directory for Oktoberfest results
        diann_params: DIA-NN parameters dict (for extracting relevant settings)
        oktoberfest_params: Optional dict of Oktoberfest-specific parameters
                           (defaults to {} if not provided)

    Returns:
        Dictionary containing Oktoberfest configuration
    """
    oktoberfest_params = oktoberfest_params or {}

    config = {
        "type": "SpectralLibraryGeneration",
        "tag": f"WU{workunit_id}",
        "inputs": {
            "library_input": fasta_path,
            "library_input_type": "fasta",
            "instrument_type": oktoberfest_params.get("instrument_type", "QE")
        },
        "output": output_dir,
        "models": {
            "intensity": oktoberfest_params.get(
                "intensity_model",
                "Prosit_2023_intensity_timsTOF"
            ),
            "irt": oktoberfest_params.get("irt_model", "Prosit_2019_irt")
        },
        "prediction_server": oktoberfest_params.get(
            "prediction_server",
            "koina.wilhelmlab.org:443"
        ),
        "ssl": oktoberfest_params.get("ssl", True),
        "spectralLibraryOptions": {
            "fragmentation": oktoberfest_params.get("fragmentation", "HCD"),
            "collisionEnergy": oktoberfest_params.get("collision_energy", 25),
            "precursorCharge": list(range(
                diann_params["min_pr_charge"],
                diann_params["max_pr_charge"] + 1
            )),
            "minIntensity": oktoberfest_params.get("min_intensity", 0.0005),
            "nrOx": oktoberfest_params.get("nr_ox", 1),
            "batchsize": oktoberfest_params.get("batchsize", 10000),
            "format": oktoberfest_params.get("format", "msp")
        },
        "fastaDigestOptions": {
            "fragmentation": oktoberfest_params.get("fragmentation", "HCD"),
            "digestion": oktoberfest_params.get("digestion", "full"),
            "missedCleavages": diann_params["missed_cleavages"],
            "minLength": diann_params["min_pep_len"],
            "maxLength": diann_params["max_pep_len"],
            "enzyme": oktoberfest_params.get("enzyme", "trypsin"),
            "specialAas": diann_params["cut"].replace("*", "").replace(",", ""),
            "db": oktoberfest_params.get("db", "concat")
        }
    }

    return config


def get_fasta_paths(fasta_config: dict) -> list[str]:
    """Return all FASTA paths to use for the workflow.

    DIA-NN can accept multiple --fasta arguments and merges them internally.
    Dispatcher stages all files to input/:
    - Database FASTA: input/<filename>.fasta
    - Custom FASTA: input/order.fasta

    Args:
        fasta_config: Dict with 'database_path' and 'use_custom_fasta' keys

    Returns:
        List of FASTA paths (database first, then custom if enabled)
    """
    paths = [fasta_config["database_path"]]

    # Add custom order.fasta if enabled and exists
    if fasta_config["use_custom_fasta"]:
        order_fasta = Path("input/order.fasta")
        if order_fasta.exists() and order_fasta.stat().st_size > 0:
            paths.append(str(order_fasta))

    return paths


def get_msconvert_options(raw_converter: str) -> str:
    """Get msconvert CLI options based on raw_converter setting.

    For Bruker .d files, thermoraw is not applicable, so both 'thermoraw'
    and 'msconvert' map to standard msconvert options.

    Args:
        raw_converter: One of 'thermoraw', 'msconvert', 'msconvert-demultiplex'

    Returns:
        msconvert CLI options string
    """
    base_options = '--mzML --64 --zlib --filter "peakPicking vendor msLevel=1-"'
    demux_filter = '--filter "demultiplex optimization=overlap_only massError=10.0ppm"'

    if raw_converter == "msconvert-demultiplex":
        return f"{base_options} {demux_filter}"
    # thermoraw and msconvert both use standard options for .d files
    return base_options


def run_prozor_inference(
    report_parquet: str,
    fasta_path: str,
    output_parquet: str,
    log_path: str | None = None,
    min_peptide_length: int = 6,
) -> dict:
    """Run prozor protein inference on a DIA-NN report.

    Args:
        report_parquet: Path to DIA-NN report parquet file
        fasta_path: Path to FASTA database
        output_parquet: Path for output parquet file
        log_path: Path for log file (default: prozor.log in output directory)
        min_peptide_length: Minimum peptide length to consider

    Returns:
        Dict with inference statistics
    """
    from diann_runner.prozor_diann import run_prozor_inference as _run_prozor
    from diann_runner.prozor_diann import _setup_file_logging

    output_path = Path(output_parquet)
    if log_path is None:
        log_path = output_path.parent / "prozor.log"
    else:
        log_path = Path(log_path)

    # Set up file logging
    _setup_file_logging(log_path)

    return _run_prozor(
        report_path=Path(report_parquet),
        fasta_path=Path(fasta_path),
        output_path=output_path,
        min_peptide_length=min_peptide_length,
    )
