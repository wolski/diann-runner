"""Helper functions for Snakemake workflow."""

import os
import yaml
import pandas as pd
import re
from pathlib import Path
from typing import Tuple, List, Dict


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


def load_config(raw_dir: Path) -> dict:
    """Load params.yml with environment-specific defaults.

    Load order (later overrides earlier):
    1. params.yml (bfabric-generated, required)
    2. defaults_server.yml or defaults_local.yml (auto-detected)
    3. deploy_config.yml (manual overrides)

    Config files are searched in: raw_dir, then package config/ dir.
    """
    with open(os.path.join(raw_dir, "params.yml")) as f:
        config_dict = yaml.safe_load(f)

    # Determine environment and config file
    env = "server" if is_server_environment() else "local"
    defaults_filename = f"defaults_{env}.yml"

    # Search paths: raw_dir first, then package config dir
    package_config_dir = Path(__file__).parent / "config"
    search_paths = [Path(raw_dir), package_config_dir]

    # Load environment defaults if found
    for search_dir in search_paths:
        defaults_path = search_dir / defaults_filename
        if defaults_path.exists():
            with open(defaults_path) as f:
                defaults = yaml.safe_load(f) or {}
            if "params" in defaults:
                config_dict["params"].update(defaults["params"])
            break

    # Load deploy_config.yml overrides (highest priority)
    deploy_config_path = os.path.join(raw_dir, "deploy_config.yml")
    if os.path.exists(deploy_config_path):
        with open(deploy_config_path) as f:
            deploy_config = yaml.safe_load(f) or {}
        if "params" in deploy_config:
            config_dict["params"].update(deploy_config["params"])

    return config_dict


def detect_input_files(raw_dir: Path) -> Tuple[List[str], str, Dict[str, List[Path]]]:
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

    diann['no_peptidoforms'] = flat_params.get('06b_diann_mods_no_peptidoforms', 'false').lower() == 'true'
    diann['unimod4'] = flat_params.get('06c_diann_mods_unimod4', 'true').lower() == 'true'
    diann['met_excision'] = flat_params.get('06d_diann_mods_met_excision', 'true').lower() == 'true'

    # Parse peptide constraints
    diann['min_pep_len'] = int(flat_params.get('07_diann_peptide_min_length', '6'))
    diann['max_pep_len'] = int(flat_params.get('07_diann_peptide_max_length', '30'))
    diann['min_pr_charge'] = int(flat_params.get('07_diann_peptide_precursor_charge_min', '2'))
    diann['max_pr_charge'] = int(flat_params.get('07_diann_peptide_precursor_charge_max', '3'))
    diann['min_pr_mz'] = int(flat_params.get('07_diann_peptide_precursor_mz_min', '400'))
    diann['max_pr_mz'] = int(flat_params.get('07_diann_peptide_precursor_mz_max', '1500'))
    diann['min_fr_mz'] = int(flat_params.get('07_diann_peptide_fragment_mz_min', '200'))
    diann['max_fr_mz'] = int(flat_params.get('07_diann_peptide_fragment_mz_max', '1800'))

    # Parse digestion
    diann['cut'] = flat_params.get('08_diann_digestion_cut', 'K*,R*')
    missed_cleavages_str = flat_params.get('08_diann_digestion_missed_cleavages', '1')
    if missed_cleavages_str != 'None':
        diann['missed_cleavages'] = int(missed_cleavages_str)
    else:
        diann['missed_cleavages'] = 1

    # Parse mass accuracy
    mass_acc_ms2_str = flat_params.get('09_diann_mass_acc_ms2', '20')
    diann['mass_acc'] = int(mass_acc_ms2_str) if mass_acc_ms2_str != 'None' else 20
    mass_acc_ms1_str = flat_params.get('09_diann_mass_acc_ms1', '15')
    diann['mass_acc_ms1'] = int(mass_acc_ms1_str) if mass_acc_ms1_str != 'None' else 15

    # Parse scoring
    diann['qvalue'] = float(flat_params.get('10_diann_scoring_qvalue', '0.01'))

    # Parse protein inference
    diann['pg_level'] = int(flat_params.get('11a_diann_protein_pg_level', '1'))
    diann['relaxed_prot_inf'] = flat_params.get('11b_diann_protein_relaxed_prot_inf', 'false').lower() == 'true'

    # Parse quantification & normalization (NEW SECTION 12)
    diann['reanalyse'] = flat_params.get('12a_diann_quantification_reanalyse', 'true').lower() == 'true'
    diann['no_norm'] = flat_params.get('12b_diann_quantification_no_norm', 'false').lower() == 'true'

    # Parse other settings
    diann['verbose'] = int(flat_params.get('99_other_verbose', '1'))
    diann['diann_bin'] = flat_params.get('98_diann_binary', 'diann-docker')
    diann['threads'] = int(flat_params.get('threads', '64'))
    diann['docker_image'] = flat_params.get('diann_docker_image', 'diann:2.3.1')

    # Parse DDA mode
    diann['is_dda'] = flat_params.get('05_diann_is_dda', 'false').lower() == 'true'

    # Parse FASTA
    fasta['database_path'] = flat_params.get('03_fasta_database_path', '')
    fasta['use_custom_fasta'] = flat_params.get('03_fasta_use_custom', 'false').lower() == 'true'

    # Convert var_mods to tuples for DiannWorkflow
    var_mods_tuples = [tuple(mod) for mod in diann.get('var_mods', [])]

    # Parse workflow control parameters (not in Bfabric XML - use defaults)
    # Library predictor: 'diann' (default) or 'oktoberfest'
    library_predictor = flat_params.get('library_predictor', 'diann')

    # Step C: disabled by default (false) - can be enabled via params.yml if needed
    enable_step_c_str = flat_params.get('enable_step_c', 'false')
    enable_step_c = enable_step_c_str.lower() == 'true' if isinstance(enable_step_c_str, str) else bool(enable_step_c_str)

    return {
        'diann': diann,
        'fasta': fasta,
        'var_mods': var_mods_tuples,
        'library_predictor': library_predictor,
        'enable_step_c': enable_step_c
    }


def create_diann_workflow(
    workunit_id: str,
    output_prefix: str,
    temp_dir_base: str,
    fasta_path: str,
    var_mods: list,
    diann_params: dict
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
        diann_bin=diann_params.get("diann_bin", "diann-docker"),
        threads=diann_params.get("threads", 64),
        qvalue=diann_params.get("qvalue", 0.01),
        min_pep_len=diann_params.get("min_pep_len", 6),
        max_pep_len=diann_params.get("max_pep_len", 30),
        min_pr_charge=diann_params.get("min_pr_charge", 2),
        max_pr_charge=diann_params.get("max_pr_charge", 3),
        min_pr_mz=diann_params.get("min_pr_mz", 400),
        max_pr_mz=diann_params.get("max_pr_mz", 1500),
        min_fr_mz=diann_params.get("min_fr_mz", 200),
        max_fr_mz=diann_params.get("max_fr_mz", 1800),
        missed_cleavages=diann_params.get("missed_cleavages", 1),
        cut=diann_params.get("cut", "K*,R*"),
        mass_acc=diann_params.get("mass_acc", 20),
        mass_acc_ms1=diann_params.get("mass_acc_ms1", 15),
        verbose=diann_params.get("verbose", 1),
        pg_level=diann_params.get("pg_level", 0),
        is_dda=diann_params.get("is_dda", False),
        unimod4=diann_params.get("unimod4", True),
        met_excision=diann_params.get("met_excision", True),
        relaxed_prot_inf=diann_params.get("relaxed_prot_inf", False),
        reanalyse=diann_params.get("reanalyse", True),
        no_norm=diann_params.get("no_norm", False),
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
        print(f"Added PG.Quantity column from PG.MaxLFQ for DDA data compatibility")

    df.to_csv(tsv_path, sep='\t', index=False)
    print(f"Converted {parquet_path} -> {tsv_path}")


def zip_diann_results(
    output_dir: str,
    zip_path: str,
    workunit_id: str
) -> None:
    """
    Zip DIA-NN results directory.

    Args:
        output_dir: Output directory to zip (e.g., "out-DIANN_quantB")
        zip_path: Path to output zip file
        workunit_id: Workunit ID for logging
    """
    import zipfile
    import os
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
                diann_params.get("min_pr_charge", 2),
                diann_params.get("max_pr_charge", 3) + 1
            )),
            "minIntensity": oktoberfest_params.get("min_intensity", 0.0005),
            "nrOx": oktoberfest_params.get("nr_ox", 1),
            "batchsize": oktoberfest_params.get("batchsize", 10000),
            "format": oktoberfest_params.get("format", "msp")
        },
        "fastaDigestOptions": {
            "fragmentation": oktoberfest_params.get("fragmentation", "HCD"),
            "digestion": oktoberfest_params.get("digestion", "full"),
            "missedCleavages": diann_params.get("missed_cleavages", 1),
            "minLength": diann_params.get("min_pep_len", 6),
            "maxLength": diann_params.get("max_pep_len", 30),
            "enzyme": oktoberfest_params.get("enzyme", "trypsin"),
            "specialAas": diann_params.get("cut", "K*,R*").replace("*", "").replace(",", ""),
            "db": oktoberfest_params.get("db", "concat")
        }
    }

    return config
