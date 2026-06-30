"""Helper functions for Snakemake workflow."""

from __future__ import annotations

import os
import shlex
from html import escape
from pathlib import Path

import yaml

# parse_var_mods_string is re-exported here for back-compat (historical home).
from diann_runner.param_core import build_internal_params, parse_var_mods_string  # noqa: F401


def write_outputs_yml(
    output_file: str,
    diann_zip: str,
    qc_zip: str | None = None,
    libs_zip: str | None = None,
) -> None:
    """Write outputs.yml for bfabric-app-runner staging."""
    outputs = [
        {
            "local_path": str(Path(diann_zip).resolve()),
            "store_entry_path": diann_zip,
            "type": "bfabric_copy_resource",
        },
    ]
    if qc_zip:
        outputs.append({
            "local_path": str(Path(qc_zip).resolve()),
            "store_entry_path": qc_zip,
            "type": "bfabric_copy_resource",
        })
    if libs_zip:
        outputs.append({
            "local_path": str(Path(libs_zip).resolve()),
            "store_entry_path": libs_zip,
            "type": "bfabric_copy_resource",
        })
    data = {"outputs": outputs}
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


def load_deploy_config(raw_dir: Path, runtime_override: str | None = None) -> dict:
    """Load deployment config (container images, threads, etc.).

    Loads defaults_server.yml or defaults_local.yml based on environment.
    Search order: raw_dir first, then package config/ dir.

    The shipped YAML carries both runtime image blocks under
    ``images.docker`` and ``images.apptainer``. The runtime is resolved by
    precedence: ``runtime_override`` (highest) > an explicit
    ``container_runtime:`` key in the config > host auto-detection
    (:func:`diann_runner.container_utils.detect_runtime`). This function then
    flattens the matching sub-block to the top level so existing callers see
    ``deploy_dict["diann_images"]`` etc. unchanged, and sets
    ``deploy_dict["container_runtime"]`` to the resolved runtime for
    downstream forwarding.

    ``runtime_override`` is how the caller pins the runtime per invocation —
    ``run-diann --runtime docker`` / ``diann-snakemake --config
    container_runtime=docker`` — so a host with apptainer installed but no SIF
    cache (e.g. a docker-only box) uses docker without editing any config.

    Args:
        raw_dir: directory searched (before the package config) for the YAML.
        runtime_override: ``"docker"``/``"apptainer"`` to force the runtime,
            or ``None`` to fall back to the config key / auto-detection.

    Returns:
        Dict with deployment settings flattened for the active runtime.
    """
    from diann_runner.container_utils import detect_runtime

    env = "server" if is_server_environment() else "local"
    defaults_filename = f"defaults_{env}.yml"

    package_config_dir = Path(__file__).parent / "config"
    search_paths = [Path(raw_dir), package_config_dir]

    raw_config: dict | None = None
    for search_dir in search_paths:
        defaults_path = search_dir / defaults_filename
        if defaults_path.exists():
            with open(defaults_path) as f:
                raw_config = yaml.safe_load(f)
            break

    if raw_config is None:
        raise FileNotFoundError(
            f"Deploy config not found: {defaults_filename} (searched: {search_paths})"
        )

    configured_runtime = runtime_override or raw_config.get("container_runtime")
    if configured_runtime is None:
        runtime = detect_runtime()
    elif configured_runtime in ("docker", "apptainer"):
        runtime = configured_runtime
    else:
        source = "--runtime/--config container_runtime" if runtime_override else f"deploy config {defaults_filename}"
        raise ValueError(
            f"Invalid container_runtime {configured_runtime!r} from {source}; "
            f"expected 'docker' or 'apptainer'."
        )

    images_by_runtime = raw_config.get("images")
    if not images_by_runtime or runtime not in images_by_runtime:
        raise KeyError(
            f"Deploy config {defaults_filename} is missing 'images.{runtime}' block "
            f"(found runtimes: {sorted(images_by_runtime or {})})."
        )

    deploy_dict = {k: v for k, v in raw_config.items() if k != "images"}
    deploy_dict.update(images_by_runtime[runtime])
    deploy_dict["container_runtime"] = runtime
    return deploy_dict


def load_workflow_params(workdir: str | Path, config: dict) -> tuple[dict, dict]:
    """Load normalized workflow params + registration (dual-mode).

    Prefers the normalized ``diann_runner_params.toml`` written by ``run-diann``;
    falls back to the legacy ``params.yml`` + :func:`parse_flat_params` path so
    existing AppRunner workdirs and direct ``diann-snakemake`` runs keep working.

    Returns ``(workflow_params, registration)`` where ``workflow_params`` has the
    same shape as :func:`parse_flat_params` output and ``registration`` carries at
    least ``workunit_id`` and ``container_id``. In TOML mode the registration
    values come from the Snakemake ``config`` (passed by ``run-diann``).
    """
    workdir = Path(workdir)
    toml_path = workdir / config.get("params_toml", "diann_runner_params.toml")
    if toml_path.is_file():
        from diann_runner.request import DIANNRunnerParams

        workflow_params = DIANNRunnerParams.from_toml(toml_path).to_parsed()
        registration = {
            "workunit_id": str(config.get("workunit_id", "0")),
            "container_id": str(config.get("container_id", "0")),
        }
        return workflow_params, registration

    config_dict = load_config(workdir)
    return parse_flat_params(config_dict["params"]), config_dict["registration"]


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


# B-Fabric flat key -> diann_runner canonical internal field name. parse_flat_params
# is the BFABRIC_TO_DRUNNER adapter: it renames these keys onto canonical names and
# hands them to build_internal_params (the shared transform core in param_core);
# the value transforms + defaults live there, not here.
BFABRIC_TO_DRUNNER: dict[str, str] = {
    "pipeline_diann_version": "diann_version",
    "pipeline_workflow_mode": "workflow_mode",
    "pipeline_is_dda": "is_dda",
    "pipeline_raw_converter": "raw_converter",
    "lib_digestion_cut": "digestion_cut",
    "lib_digestion_missed_cleavages": "digestion_missed_cleavages",
    "lib_peptide_min_length": "peptide_min_length",
    "lib_peptide_max_length": "peptide_max_length",
    "lib_precursor_charge_min": "precursor_charge_min",
    "lib_precursor_charge_max": "precursor_charge_max",
    "lib_precursor_mz_min": "precursor_mz_min",
    "lib_precursor_mz_max": "precursor_mz_max",
    "lib_fragment_mz_min": "fragment_mz_min",
    "lib_fragment_mz_max": "fragment_mz_max",
    "lib_mods_variable": "mods_variable",
    "lib_mods_unimod4": "mods_unimod4",
    "lib_mods_met_excision": "mods_met_excision",
    "lib_mods_no_peptidoforms": "mods_no_peptidoforms",
    "search_mass_acc_ms1": "mass_acc_ms1",
    "search_mass_acc_ms2": "mass_acc_ms2",
    "search_mass_acc_unrelated_runs": "mass_acc_unrelated_runs",
    "search_scoring_qvalue": "scoring_qvalue",
    "search_protein_pg_level": "protein_pg_level",
    "search_protein_ids_to_names": "protein_ids_to_names",
    "quant_scan_window": "scan_window",
    "quant_reanalyse": "reanalyse",
    "quant_no_norm": "no_norm",
    "output_fragment_quant": "fragment_quant",
    "output_include_libs": "include_libs",
    "output_pmultiqc": "pmultiqc",
    "advanced_freestyle": "freestyle",
    "advanced_verbose": "verbose",
    "library_predictor": "library_predictor",
    "enable_step_c": "enable_step_c",
}


def _bfabric_fasta(flat_params: dict) -> dict:
    """Resolve the B-Fabric FASTA selection into the ``inputs`` sub-dict.

    ``fasta_databases`` is list-shaped (DIA-NN merges multiple ``--fasta``), but the
    B-Fabric executable is single-select: the primary database is the dropdown pick
    (``input_fasta_databases``), or the freestyle ``input_fasta_additional`` path
    when the dropdown is ``NONE``. ``fasta_use_custom`` toggles injecting an
    ``order.fasta`` of per-order custom sequences.
    """
    fasta_main = flat_params["input_fasta_databases"]
    primary = (
        flat_params["input_fasta_additional"]
        if fasta_main.upper() == "NONE"
        else fasta_main
    )
    return {
        "fasta_databases": [primary],
        "fasta_use_custom": flat_params["input_fasta_use_custom"].lower() == "true",
    }


def parse_flat_params(flat_params):
    """Transform flat B-Fabric XML keys into diann_runner's nested internal params.

    This is the ``BFABRIC_TO_DRUNNER`` adapter: it renames the flat ``06a_*`` keys
    onto canonical internal field names (:data:`BFABRIC_TO_DRUNNER`) and delegates
    the value transforms + defaults to
    :func:`diann_runner.param_core.build_internal_params`. Output shape is
    unchanged: ``{'diann', 'fasta', 'var_mods', 'library_predictor',
    'enable_step_c', 'workflow_mode', 'raw_converter', 'include_libs'}``.
    """
    canonical = {
        BFABRIC_TO_DRUNNER[k]: v for k, v in flat_params.items() if k in BFABRIC_TO_DRUNNER
    }
    return build_internal_params(canonical, fasta=_bfabric_fasta(flat_params))


def resolve_diann_docker_image(diann_version: str | None, deploy_params: dict) -> str:
    """Resolve the DIA-NN Docker image tag for a given version.

    Order:
      1. ``deploy_params['diann_images'][diann_version]`` if both present
      2. ``deploy_params['diann_docker_image']`` (legacy single-image fallback)
    Raises KeyError if neither resolves.
    """
    images = deploy_params.get("diann_images") or {}
    if diann_version and diann_version in images:
        return images[diann_version]
    if "diann_docker_image" in deploy_params:
        return deploy_params["diann_docker_image"]
    raise KeyError(
        f"Cannot resolve DIA-NN docker image for version {diann_version!r}: "
        "neither diann_images[version] nor legacy diann_docker_image is set."
    )


def resolve_raw_converter_image(raw_converter: str, deploy_params: dict) -> str:
    """Resolve the Docker image used by the Thermo RAW conversion wrapper."""
    if raw_converter == "thermoraw":
        return deploy_params["thermoraw_image"]
    if raw_converter in ("msconvert", "msconvert-demultiplex"):
        return deploy_params["msconvert_docker"]
    raise ValueError(f"Unsupported raw converter: {raw_converter!r}")


def get_diann_input_path(
    sample: str,
    input_type: str,
    raw_converter: str,
    raw_dir: Path,
    converted_dir: Path | None = None,
    mount_target: str | None = None,
) -> Path:
    """Return the container-visible path to feed into DIA-NN as --f for one sample.

    Every DIA-NN image we ship reads Thermo .raw natively (.NET 8), so when the
    converter is 'native' and inputs are .raw, we skip mzML conversion and pass
    the .raw straight through. The thermoraw/msconvert/msconvert-demultiplex
    options convert to mzML first.

    ``raw_dir`` is where source files live (read directly for native .raw /
    .mzML). ``converted_dir`` (defaults to ``raw_dir``) is where conversion
    outputs are written — the .mzML from thermoraw and the extracted .d from a
    .d.zip — and must be under the work dir. ``mount_target``, when set, is the
    in-container path of an external ``raw_dir`` bind-mounted read-only (e.g.
    ``/raw``); source files read directly are then referenced there rather than
    at their host path. Defaults reproduce the historical single-dir behavior.
    """
    converted_dir = raw_dir if converted_dir is None else converted_dir
    if input_type == "d.zip":
        return Path(converted_dir) / f"{sample}.d"
    if input_type == "raw" and raw_converter != "native":
        return Path(converted_dir) / f"{sample}.mzML"
    # Read source directly: native .raw or .mzML input.
    ext = "raw" if input_type == "raw" else "mzML"
    base = Path(mount_target) if mount_target else Path(raw_dir)
    return base / f"{sample}.{ext}"


def get_diann_input_dependency(
    sample: str,
    input_type: str,
    raw_converter: str,
    raw_dir: Path,
    converted_dir: Path | None = None,
) -> Path:
    """Return the workflow dependency (host path) that prepares a DIA-NN input.

    Bruker .d directories are vendor data folders. Do not make Snakemake own
    them as directory() outputs because Snakemake writes metadata inside managed
    output directories. Use a sibling marker file for the extraction step while
    passing the real .d path to DIA-NN via get_diann_input_path().

    Unlike :func:`get_diann_input_path`, this returns the on-disk *host* path
    Snakemake must verify/build: source files read directly live in ``raw_dir``,
    conversion outputs in ``converted_dir`` (defaults to ``raw_dir``).
    """
    converted_dir = raw_dir if converted_dir is None else converted_dir
    if input_type == "d.zip":
        return Path(converted_dir) / f"{sample}.done"
    if input_type == "raw" and raw_converter != "native":
        return Path(converted_dir) / f"{sample}.mzML"
    ext = "raw" if input_type == "raw" else "mzML"
    return Path(raw_dir) / f"{sample}.{ext}"


def create_diann_workflow(
    workunit_id: str,
    output_prefix: str,
    temp_dir_base: str,
    fasta_path: str | list[str],
    var_mods: list,
    params: dict,
    deploy_params: dict,
    raw_mount: tuple[str, str] | None = None,
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
        fasta_path: Path(s) to FASTA database file
        var_mods: List of variable modification tuples
        params: Full nested parameter dict from parse_flat_params() (7 category sub-dicts)
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
        diann_bin=params["diann_bin"],
        docker_image=resolve_diann_docker_image(params["pipeline"]["diann_version"], deploy_params),
        container_runtime=deploy_params.get("container_runtime", "docker"),
        threads=deploy_params["threads"],
        qvalue=params["search"]["scoring_qvalue"],
        min_pep_len=params["lib"]["peptide_min_length"],
        max_pep_len=params["lib"]["peptide_max_length"],
        min_pr_charge=params["lib"]["precursor_charge_min"],
        max_pr_charge=params["lib"]["precursor_charge_max"],
        min_pr_mz=params["lib"]["precursor_mz_min"],
        max_pr_mz=params["lib"]["precursor_mz_max"],
        min_fr_mz=params["lib"]["fragment_mz_min"],
        max_fr_mz=params["lib"]["fragment_mz_max"],
        missed_cleavages=params["lib"]["digestion_missed_cleavages"],
        cut=params["lib"]["digestion_cut"],
        mass_acc=params["search"]["mass_acc_ms2"],
        mass_acc_ms1=params["search"]["mass_acc_ms1"],
        scan_window=params["quant"]["scan_window"],
        verbose=params["advanced"]["verbose"],
        pg_level=params["search"]["protein_pg_level"],
        is_dda=params["pipeline"]["is_dda"],
        unimod4=params["lib"]["mods_unimod4"],
        met_excision=params["lib"]["mods_met_excision"],
        no_peptidoforms=params["lib"]["mods_no_peptidoforms"],
        reanalyse=params["quant"]["reanalyse"],
        no_norm=params["quant"]["no_norm"],
        export_quant=params["output"]["fragment_quant"],
        unrelated_runs=params["search"]["mass_acc_unrelated_runs"],
        freestyle=params["advanced"]["freestyle"],
        ids_to_names=params["search"]["protein_ids_to_names"],
        raw_mount=raw_mount,
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
        Dictionary with keys: report_parquet, pg_matrix, stats, library, runlog.
        ``report_parquet`` is the native DIA-NN 2.x report (bare ``Run`` column);
        all downstream consumers (diann-qc, prolfqua QC, pmultiqc) read it
        directly. ``runlog`` is the DIA-NN run log for the step.
    """
    step = "quantC" if enable_step_c else "quantB"

    # Both steps use the same library naming (.parquet)
    library_filename = f"WU{workunit_id}_report-lib.parquet"

    return {
        "report_parquet": f"{output_prefix}_{step}/WU{workunit_id}_report.parquet",
        "pg_matrix": f"{output_prefix}_{step}/WU{workunit_id}_report.pg_matrix.tsv",
        "stats": f"{output_prefix}_{step}/WU{workunit_id}_report.stats.tsv",
        "library": f"{output_prefix}_{step}/{library_filename}",
        "runlog": f"{output_prefix}_{step}/diann_{step}.log.txt",
    }


_INDEX_STYLE = """  <style>
    body { font-family: Arial, sans-serif; }
    h1 { text-align: center; }
    h2 {
      text-align: left;
      margin-top: 20px;
      padding-bottom: 10px;
      border-bottom: 1px solid #ecf0f1;
      color: #2c3e50;
    }
    .desc { color: #7f8c8d; font-size: 0.9em; }
  </style>"""


def write_result_index(
    index_md: str | Path,
    index_html: str | Path,
    *,
    workunit_id: str,
    quant_dir: str | Path,
    final_outputs: dict[str, str],
    fasta_paths: list[str | Path],
    include_pmultiqc: bool = False,
) -> None:
    """Write top-level Markdown and HTML indexes for the result zip.

    Links are grouped into a "QC Reports" section (the rendered HTML QC
    reports) and a "Data Files" section (the downloadable parquet/TSV/PDF/log
    and the dataset and FASTA databases). Each entry carries a one-line
    description shown alongside the link.
    """
    quant_path = Path(quant_dir)
    quant_archive_path = Path(quant_path.name) if quant_path.is_absolute() else quant_path
    prozor = final_outputs["report_parquet"].replace(".parquet", "_prozor.parquet")
    qc_pdf = final_outputs["stats"].replace("_report.stats.tsv", "_qc_report.pdf")

    # (label, target, description) entries per section.
    qc_reports: list[tuple[str, str, str]] = [
        (
            "Quality control overview (prolfqua)",
            "qc_result/index.html",
            "Landing page linking all prolfqua QC reports and tables.",
        ),
        (
            "Protein abundance QC report (prolfqua)",
            "qc_result/proteinAbundances.html",
            "Interactive QC: abundance distributions, missing values, "
            "coefficient of variation, sample correlation and clustering.",
        ),
        (
            "Sample size and power estimation (prolfqua)",
            "qc_result/QC_sampleSizeEstimation.html",
            "Variance-based sample-size and power estimation for follow-up "
            "experiments.",
        ),
        (
            "DIA-NN quality control report (PDF)",
            qc_pdf,
            "DIA-NN's own QC plots (precursor/protein counts, mass accuracy, "
            "retention time) rendered as a PDF.",
        ),
    ]
    if include_pmultiqc:
        qc_reports.append((
            "Interactive QC report (pmultiqc)",
            "pmultiqc_result/pmultiqc_diann_report.html",
            "MultiQC-style interactive summary of the DIA-NN run.",
        ))

    data_files: list[tuple[str, str, str]] = [
        (
            "DIA-NN report, native (parquet)",
            final_outputs["report_parquet"],
            "Unmodified DIA-NN precursor/protein report in parquet format.",
        ),
        (
            "DIA-NN report, protein-inferred (prozor, parquet)",
            prozor,
            "DIA-NN report re-annotated with parsimonious protein inference "
            "(prozor).",
        ),
        (
            "Protein group abundance matrix (TSV)",
            final_outputs["pg_matrix"],
            "Protein-group abundances, proteins by sample.",
        ),
        (
            "DIA-NN run statistics (TSV)",
            final_outputs["stats"],
            "Per-run summary statistics.",
        ),
        (
            "DIA-NN run log (text)",
            final_outputs["runlog"],
            "Full DIA-NN console log for the final quantification.",
        ),
        (
            "Sample annotation table (CSV)",
            str(quant_archive_path / "dataset.csv"),
            "Sample annotation / experimental design.",
        ),
    ]
    for fasta_path in fasta_paths:
        staged_fasta = quant_path / Path(fasta_path).name
        if staged_fasta.is_file():
            data_files.append((
                f"FASTA database: {staged_fasta.name}",
                str(quant_archive_path / staged_fasta.name),
                "Protein sequence database used for the search.",
            ))

    sections: list[tuple[str, list[tuple[str, str, str]]]] = [
        ("QC Reports", qc_reports),
        ("Data Files", data_files),
    ]

    title = f"DIA-NN Results for WU : {workunit_id}"
    markdown = [f"# {title}", ""]
    for section_title, entries in sections:
        markdown.extend([f"## {section_title}", ""])
        markdown.extend(
            f"- [{label}]({target}) - {description}"
            for label, target, description in entries
        )
        markdown.append("")
    Path(index_md).write_text("\n".join(markdown), encoding="utf-8")

    html_lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "<meta charset='UTF-8'>",
        f"<title>{escape(title)}</title>",
        _INDEX_STYLE,
        "</head>",
        "<body>",
        f"<h1>{escape(title)}</h1>",
    ]
    for section_title, entries in sections:
        html_lines.extend([f"<h2>{escape(section_title)}</h2>", "<ul>"])
        html_lines.extend(
            f"<li><a href='{escape(target, quote=True)}'>{escape(label)}</a>"
            f"<br><span class='desc'>{escape(description)}</span></li>"
            for label, target, description in entries
        )
        html_lines.append("</ul>")
    html_lines.extend(["</body>", "</html>", ""])
    Path(index_html).write_text("\n".join(html_lines), encoding="utf-8")


def zip_diann_results(
    output_dir: str,
    zip_path: str,
    extra_files: list[str | Path] | None = None,
    extra_dirs: list[str | Path] | None = None,
) -> None:
    """
    Zip DIA-NN results directory.

    Args:
        output_dir: Output directory to zip (e.g., "out-DIANN_quantB")
        zip_path: Path to output zip file
        extra_files: Additional files to include at the archive root
        extra_dirs: Additional directories to include with their relative paths preserved
    """
    import zipfile

    output_path = Path(output_dir)
    if not output_path.exists():
        raise FileNotFoundError(f"Output directory {output_dir} does not exist")

    written_arcnames = set()
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=3) as zipf:
        # Add all files from the output directory, excluding library files
        for file_path in output_path.rglob('*'):
            if file_path.is_file() and 'report-lib.' not in file_path.name:
                # Store with relative path from output directory
                arcname = file_path.relative_to(output_path.parent)
                zipf.write(file_path, arcname)
                written_arcnames.add(str(arcname))
                print(f"  adding: {arcname}")

        for extra_file in extra_files or []:
            extra_path = Path(extra_file)
            if not extra_path.is_file():
                raise FileNotFoundError(f"Extra file {extra_file} does not exist")
            arcname = extra_path.name
            if arcname not in written_arcnames:
                zipf.write(extra_path, arcname)
                written_arcnames.add(arcname)
                print(f"  adding: {arcname}")

        for extra_dir in extra_dirs or []:
            extra_path = Path(extra_dir)
            if not extra_path.is_dir():
                raise FileNotFoundError(f"Extra directory {extra_dir} does not exist")
            for file_path in extra_path.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(extra_path.parent)
                    arcname_str = str(arcname)
                    if arcname_str not in written_arcnames:
                        zipf.write(file_path, arcname)
                        written_arcnames.add(arcname_str)
                        print(f"  adding: {arcname}")

    print(f"Created {zip_path} with results from {output_dir}")


def zip_library_files(output_prefix: str, zip_path: str) -> None:
    """Zip all spectral library files (report-lib.*) from all output directories.

    Args:
        output_prefix: Output directory prefix (e.g., "out-DIANN")
        zip_path: Path to output zip file
    """
    import zipfile

    base = Path(output_prefix).parent or Path(".")
    prefix_name = Path(output_prefix).name

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=3) as zipf:
        for out_dir in sorted(base.glob(f"{prefix_name}_*")):
            for lib_file in out_dir.glob("*report-lib.*"):
                if lib_file.is_file():
                    arcname = lib_file.relative_to(base)
                    zipf.write(lib_file, arcname)
                    print(f"  adding lib: {arcname}")

    print(f"Created {zip_path} with library files from {output_prefix}_* directories")


def copy_fasta_if_missing(output_dir: str, fasta_path: str | list[str]) -> str:
    """
    Generate shell command to copy FASTA to output directory if not already present.

    Args:
        output_dir: Output directory path
        fasta_path: Source FASTA file path(s)

    Returns:
        Shell command string for FASTA copy with existence check
    """
    fasta_paths = [fasta_path] if isinstance(fasta_path, str) else fasta_path
    output_dir_arg = shlex.quote(output_dir)
    commands = ["# Copy FASTA files into output directory"]
    for path in fasta_paths:
        path_arg = shlex.quote(path)
        commands.append(f'cp -n {path_arg} {output_dir_arg}/$(basename {path_arg})')
    return "\n".join(commands)


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
        fasta_config: Dict with 'fasta_databases' (list) and 'fasta_use_custom' keys

    Returns:
        List of FASTA paths (database first, then custom if enabled)

    Custom sequences default to ON, so the common case is "enabled but the order
    carries no custom sequences" → a missing or empty ``input/order.fasta``. That
    is not an error: the empty file is skipped (with a log line) and only the
    database FASTA is used, so DIA-NN is never handed an empty FASTA.
    """
    from loguru import logger

    paths = [fasta_config["fasta_databases"][0]]

    if fasta_config["fasta_use_custom"]:
        order_fasta = Path("input/order.fasta")
        if not order_fasta.exists():
            logger.info("Custom sequences enabled but input/order.fasta is missing — skipping it.")
        elif order_fasta.stat().st_size == 0:
            logger.info("Custom sequences enabled but input/order.fasta is empty — skipping it.")
        else:
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
    fasta_path: str | Path | list[str | Path],
    output_parquet: str,
    log_path: str | None = None,
    min_peptide_length: int = 6,
) -> dict:
    """Run prozor protein inference on a DIA-NN report.

    Args:
        report_parquet: Path to DIA-NN report parquet file
        fasta_path: Path or paths to FASTA database files
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

    if isinstance(fasta_path, (str, Path)):
        fasta_paths = Path(fasta_path)
    else:
        fasta_paths = [Path(path) for path in fasta_path]

    return _run_prozor(
        report_path=Path(report_parquet),
        fasta_path=fasta_paths,
        output_path=output_path,
        min_peptide_length=min_peptide_length,
    )
