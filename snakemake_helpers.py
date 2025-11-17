"""Helper functions for Snakemake workflow."""

import pandas as pd


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
    oktoberfest_params: dict
) -> dict:
    """
    Build Oktoberfest configuration dictionary.

    Args:
        workunit_id: Workunit ID for tagging
        fasta_path: Path to FASTA database
        output_dir: Output directory for Oktoberfest results
        diann_params: DIA-NN parameters dict (for extracting relevant settings)
        oktoberfest_params: Oktoberfest-specific parameters

    Returns:
        Dictionary containing Oktoberfest configuration
    """
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
