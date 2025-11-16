#!/usr/bin/env python3
"""
koina_adapter.py - Translation layer between DIA-NN and Oktoberfest configs.

This module provides utilities to convert DIA-NN workflow configurations
to Oktoberfest config format, enabling seamless integration of Koina/Prosit
predictions into the DIA-NN workflow.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional


class KoinaConfigAdapter:
    """
    Adapter to translate DIA-NN workflow config to Oktoberfest config format.

    This enables using the same DIA-NN config to orchestrate both DIA-NN's
    built-in predictor and Koina/Oktoberfest predictions.
    """

    # Mapping of DIA-NN cut patterns to Oktoberfest enzyme names
    ENZYME_MAPPING = {
        'K*,R*': 'trypsin',
        'K*': 'lysc',
        'D*': 'aspn',
        'E*': 'gluc',
    }

    # Default Koina models for different instrument types
    DEFAULT_MODELS = {
        'QE': {
            'intensity': 'Prosit_2020_intensity_HCD',
            'irt': 'Prosit_2019_irt',
        },
        'TIMSTOF': {
            'intensity': 'Prosit_2023_intensity_timsTOF',
            'irt': 'Prosit_2019_irt',
            'im': 'Prosit_2023_IM',
        },
        'ASTRAL': {
            'intensity': 'Prosit_2020_intensity_HCD',
            'irt': 'Prosit_2019_irt',
        },
    }

    @classmethod
    def from_diann_config(
        cls,
        diann_config_path: str,
        fasta_path: str,
        output_dir: str = './out',
        instrument_type: str = 'QE',
        prediction_server: str = 'koina.wilhelmlab.org:443',
        intensity_model: Optional[str] = None,
        irt_model: Optional[str] = None,
        collision_energy: int = 30,
        output_format: str = 'msp',
    ) -> Dict[str, Any]:
        """
        Generate Oktoberfest config from DIA-NN workflow config.

        Args:
            diann_config_path: Path to DIA-NN .config.json file
            fasta_path: Path to FASTA file (required by Oktoberfest)
            output_dir: Oktoberfest output directory
            instrument_type: Instrument type (QE, TIMSTOF, ASTRAL)
            prediction_server: Koina server address
            intensity_model: Override default intensity model
            irt_model: Override default iRT model
            collision_energy: Collision energy for HCD (default 30)
            output_format: Library format (msp, spectronaut, etc.)

        Returns:
            Dict ready to be saved as Oktoberfest config.json
        """
        # Load DIA-NN config
        with open(diann_config_path, 'r') as f:
            diann_config = json.load(f)

        # Get default models for instrument
        default_models = cls.DEFAULT_MODELS.get(instrument_type, cls.DEFAULT_MODELS['QE'])

        # Build models dict
        models = {
            'intensity': intensity_model or default_models['intensity'],
            'irt': irt_model or default_models['irt'],
        }
        if 'im' in default_models:
            models['im'] = default_models['im']

        # Parse variable modifications
        var_mods = diann_config.get('var_mods', [])
        nr_ox = cls._count_oxidations(var_mods)

        # Determine enzyme from cut pattern
        cut_pattern = diann_config.get('cut', 'K*,R*')
        enzyme = cls.ENZYME_MAPPING.get(cut_pattern, 'trypsin')

        # Build Oktoberfest config
        oktoberfest_config = {
            "type": "SpectralLibraryGeneration",
            "tag": "",
            "inputs": {
                "library_input": str(Path(fasta_path).name),  # Relative to working dir
                "library_input_type": "fasta",
                "instrument_type": instrument_type,
            },
            "output": output_dir,
            "models": models,
            "prediction_server": prediction_server,
            "ssl": True,
            "spectralLibraryOptions": {
                "fragmentation": "HCD",
                "collisionEnergy": collision_energy,
                "precursorCharge": [
                    diann_config.get('min_pr_charge', 2),
                    diann_config.get('max_pr_charge', 3),
                ],
                "minIntensity": 5e-4,
                "nrOx": nr_ox,
                "batchsize": 10000,
                "format": output_format,
            },
            "fastaDigestOptions": {
                "fragmentation": "HCD",
                "digestion": "full",
                "missedCleavages": diann_config.get('missed_cleavages', 1),
                "minLength": diann_config.get('min_pep_len', 6),
                "maxLength": diann_config.get('max_pep_len', 30),
                "enzyme": enzyme,
                "specialAas": cut_pattern.replace('*', '').replace(',', ''),
                "db": "concat",
            },
        }

        return oktoberfest_config

    @staticmethod
    def _count_oxidations(var_mods: List[List[str]]) -> int:
        """
        Count oxidation modifications (UniMod:35) from DIA-NN var_mods.

        Args:
            var_mods: List of [unimod_id, mass_delta, residues]

        Returns:
            Number of allowed oxidations (0, 1, 2, etc.)
        """
        for mod in var_mods:
            if len(mod) >= 3 and mod[0] == '35' and 'M' in mod[2]:
                # Found oxidation on M, return 1 (could be extended to parse max count)
                return 1
        return 0

    @classmethod
    def save_oktoberfest_config(
        cls,
        oktoberfest_config: Dict[str, Any],
        output_path: str,
    ) -> None:
        """
        Save Oktoberfest config to JSON file.

        Args:
            oktoberfest_config: Oktoberfest config dict
            output_path: Path to save config.json
        """
        with open(output_path, 'w') as f:
            json.dump(oktoberfest_config, f, indent=4)
        print(f"Oktoberfest config saved to: {output_path}")

    @classmethod
    def generate_koina_library_command(
        cls,
        diann_config_path: str,
        fasta_path: str,
        oktoberfest_dir: str = '../oktoberfest',
        instrument_type: str = 'QE',
    ) -> str:
        """
        Generate complete command to run Oktoberfest from DIA-NN config.

        Args:
            diann_config_path: Path to DIA-NN config
            fasta_path: Path to FASTA file
            oktoberfest_dir: Directory containing Oktoberfest venv
            instrument_type: Instrument type

        Returns:
            Bash command string to execute
        """
        # Generate config
        config = cls.from_diann_config(
            diann_config_path=diann_config_path,
            fasta_path=fasta_path,
            instrument_type=instrument_type,
        )

        # Save to oktoberfest directory
        config_path = Path(oktoberfest_dir) / 'config.json'
        cls.save_oktoberfest_config(config, str(config_path))

        # Generate command
        cmd = f"""cd {oktoberfest_dir}
source .venv/bin/activate.fish
oktoberfest -c config.json | tee oktoberfest.log.txt"""

        return cmd

    @classmethod
    def print_comparison(
        cls,
        diann_config_path: str,
        oktoberfest_config: Dict[str, Any],
    ) -> None:
        """
        Print parameter comparison between DIA-NN and Oktoberfest configs.

        Args:
            diann_config_path: Path to DIA-NN config
            oktoberfest_config: Generated Oktoberfest config
        """
        with open(diann_config_path, 'r') as f:
            diann_config = json.load(f)

        print("\n=== Config Parameter Mapping ===\n")
        print(f"{'Parameter':<25} {'DIA-NN':<30} {'Oktoberfest':<30}")
        print("-" * 85)

        # Enzyme
        cut = diann_config.get('cut', 'K*,R*')
        enzyme = oktoberfest_config['fastaDigestOptions']['enzyme']
        print(f"{'Enzyme':<25} {cut:<30} {enzyme:<30}")

        # Missed cleavages
        mc_diann = diann_config.get('missed_cleavages', 1)
        mc_okto = oktoberfest_config['fastaDigestOptions']['missedCleavages']
        print(f"{'Missed cleavages':<25} {mc_diann:<30} {mc_okto:<30}")

        # Peptide length
        min_len_d = diann_config.get('min_pep_len', 6)
        max_len_d = diann_config.get('max_pep_len', 30)
        min_len_o = oktoberfest_config['fastaDigestOptions']['minLength']
        max_len_o = oktoberfest_config['fastaDigestOptions']['maxLength']
        print(f"{'Peptide length':<25} {f'{min_len_d}-{max_len_d}':<30} {f'{min_len_o}-{max_len_o}':<30}")

        # Precursor charges
        min_ch_d = diann_config.get('min_pr_charge', 2)
        max_ch_d = diann_config.get('max_pr_charge', 3)
        charges_o = oktoberfest_config['spectralLibraryOptions']['precursorCharge']
        charges_o_str = f"{charges_o[0]}-{charges_o[1]}" if isinstance(charges_o, list) else str(charges_o)
        print(f"{'Precursor charges':<25} {f'{min_ch_d}-{max_ch_d}':<30} {charges_o_str:<30}")

        # Variable mods
        var_mods = diann_config.get('var_mods', [])
        nr_ox = oktoberfest_config['spectralLibraryOptions']['nrOx']
        var_mods_str = ', '.join([f"UniMod:{m[0]}" for m in var_mods]) if var_mods else 'None'
        print(f"{'Variable mods':<25} {var_mods_str:<30} {f'nrOx: {nr_ox}':<30}")

        # Models
        models = oktoberfest_config['models']
        print(f"{'Intensity model':<25} {'Built-in predictor':<30} {models['intensity']:<30}")
        print(f"{'RT model':<25} {'Built-in predictor':<30} {models['irt']:<30}")

        print("\n")


def main(
    diann_config: str,
    fasta: str,
    output: str = 'oktoberfest_config.json',
    instrument: str = 'QE',
    show_comparison: bool = False,
):
    """Convert DIA-NN config to Oktoberfest config.

    Args:
        diann_config: Path to DIA-NN .config.json file
        fasta: Path to FASTA file
        output: Output path for Oktoberfest config
        instrument: Instrument type (QE, TIMSTOF, or ASTRAL)
        show_comparison: Print parameter comparison table
    """
    # Validate instrument type
    valid_instruments = ['QE', 'TIMSTOF', 'ASTRAL']
    if instrument not in valid_instruments:
        raise ValueError(f"Invalid instrument type: {instrument}. Must be one of {valid_instruments}")

    # Generate config
    oktoberfest_config = KoinaConfigAdapter.from_diann_config(
        diann_config_path=diann_config,
        fasta_path=fasta,
        instrument_type=instrument,
    )

    # Save config
    KoinaConfigAdapter.save_oktoberfest_config(
        oktoberfest_config,
        output,
    )

    # Show comparison if requested
    if show_comparison:
        KoinaConfigAdapter.print_comparison(
            diann_config,
            oktoberfest_config,
        )


import cyclopts

app = cyclopts.App()


@app.default
def cli_main(
    diann_config: str,
    fasta: str,
    output: str = 'oktoberfest_config.json',
    instrument: str = 'QE',
    show_comparison: bool = False,
):
    """Convert DIA-NN config to Oktoberfest config.

    Args:
        diann_config: Path to DIA-NN .config.json file
        fasta: Path to FASTA file
        output: Output path for Oktoberfest config
        instrument: Instrument type (QE, TIMSTOF, or ASTRAL)
        show_comparison: Print parameter comparison table
    """
    main(diann_config, fasta, output, instrument, show_comparison)


if __name__ == '__main__':
    app()
