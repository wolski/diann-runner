#!/usr/bin/env python3
"""
diann_workflow.py - Generate three-stage DIA-NN analysis shell scripts.

This module provides a class-based approach to generate shell scripts for DIA-NN's
three-stage workflow: library generation, quantification with refinement,
and final quantification.

Usage:
    from diann_workflow import DiannWorkflow
    
    # Define variable modifications
    var_mods = [
        ('35', '15.994915', 'M'),  # Oxidation
    ]
    
    # Initialize workflow with shared parameters
    workflow = DiannWorkflow(
        workunit_id='WU12345',
        output_base_dir='out-DIANN',
        var_mods=var_mods,
        threads=64,
        qvalue=0.01,
        is_dda=False  # Set True for DDA data
    )
    
    # Generate all scripts (simple case - same files for B and C)
    workflow.generate_all_scripts(
        fasta_path='/path/to/db.fasta',
        raw_files_step_b=['sample1.mzML', 'sample2.mzML'],
        raw_files_step_c=None  # Defaults to same as step_b
    )
    
    # Or generate scripts individually for maximum flexibility:
    workflow.generate_step_a_library(
        fasta_path='/path/to/db.fasta'
    )
    
    workflow.generate_step_b_quantification_with_refinement(
        raw_files=['subset1.mzML', 'subset2.mzML'],  # Fast library building
        quantify=False  # Skip quantification, only build refined library
    )
    
    workflow.generate_step_c_final_quantification(
        raw_files=['all1.mzML', 'all2.mzML', 'all3.mzML', 'all4.mzML']  # Full set
    )
"""

import os
from pathlib import Path
from typing import List, Tuple, Dict


class DiannWorkflow:
    """
    Manages three-stage DIA-NN workflow script generation.
    
    The three stages are:
    1. Step A: Generate predicted library from FASTA
    2. Step B: Quantify with predicted library + generate refined library
    3. Step C: Final quantification with refined library
    """
    
    def __init__(
        self,
        workunit_id: str,
        output_base_dir: str = 'out-DIANN',
        var_mods: List[Tuple[str, str, str]] = None,
        diann_bin: str = 'diann-docker',
        threads: int = 64,
        qvalue: float = 0.01,
        min_pep_len: int = 6,
        max_pep_len: int = 30,
        min_pr_charge: int = 2,
        max_pr_charge: int = 3,
        min_pr_mz: int = 400,
        max_pr_mz: int = 1500,
        missed_cleavages: int = 1,
        cut: str = 'K*,R*',
        mass_acc: int = 20,
        mass_acc_ms1: int = 15,
        verbose: int = 1,
        pg_level: int = 0,
        is_dda: bool = False,
        temp_dir_base: str = 'temp-DIANN',
        unimod4: bool = True,
        met_excision: bool = True
    ):
        """
        Initialize DIA-NN workflow with shared parameters across all steps.
        
        Args:
            workunit_id: Workunit ID for naming outputs
            output_base_dir: Base directory for all outputs
            var_mods: List of (unimod_id, mass_delta, residues) tuples for variable modifications
            diann_bin: Path to DIA-NN binary executable
            threads: Number of threads to use
            qvalue: FDR threshold (default 0.01 = 1%)
            min_pep_len: Minimum peptide length
            max_pep_len: Maximum peptide length
            min_pr_charge: Minimum precursor charge
            max_pr_charge: Maximum precursor charge
            min_pr_mz: Minimum precursor m/z
            max_pr_mz: Maximum precursor m/z
            missed_cleavages: Maximum number of missed cleavages
            cut: Protease specificity (e.g., 'K*,R*' for trypsin)
            mass_acc: MS2 mass accuracy (ppm)
            mass_acc_ms1: MS1 mass accuracy (ppm)
            verbose: Verbosity level
            pg_level: Protein grouping level (0 = genes, 1 = protein names, 2 = protein IDs)
            is_dda: True for DDA data, False for DIA data
            temp_dir_base: Base name for temporary directories
            unimod4: Enable Carbamidomethyl (C) fixed modification
            met_excision: Enable N-terminal methionine excision
        """
        # Core identifiers
        self.workunit_id = workunit_id
        self.output_base_dir = output_base_dir
        self.diann_bin = diann_bin
        self.temp_dir_base = temp_dir_base
        
        # Variable modifications
        self.var_mods = var_mods if var_mods is not None else []
        
        # DIA-NN parameters (shared across all steps)
        self.threads = threads
        self.qvalue = qvalue
        self.min_pep_len = min_pep_len
        self.max_pep_len = max_pep_len
        self.min_pr_charge = min_pr_charge
        self.max_pr_charge = max_pr_charge
        self.min_pr_mz = min_pr_mz
        self.max_pr_mz = max_pr_mz
        self.missed_cleavages = missed_cleavages
        self.cut = cut
        self.mass_acc = mass_acc
        self.mass_acc_ms1 = mass_acc_ms1
        self.verbose = verbose
        self.pg_level = pg_level
        self.is_dda = is_dda
        self.unimod4 = unimod4
        self.met_excision = met_excision
        
        # Derived paths
        self.lib_dir = f"{output_base_dir}_libA"
        self.quant_b_dir = f"{output_base_dir}_quantB"
        self.quant_c_dir = f"{output_base_dir}_quantC"
    
    def to_config_dict(self) -> dict:
        """
        Serialize workflow parameters to a dictionary for JSON storage.
        
        Returns:
            Dictionary containing all workflow configuration parameters
        """
        return {
            'workunit_id': self.workunit_id,
            'output_base_dir': self.output_base_dir,
            'diann_bin': self.diann_bin,
            'temp_dir_base': self.temp_dir_base,
            'var_mods': self.var_mods,
            'threads': self.threads,
            'qvalue': self.qvalue,
            'min_pep_len': self.min_pep_len,
            'max_pep_len': self.max_pep_len,
            'min_pr_charge': self.min_pr_charge,
            'max_pr_charge': self.max_pr_charge,
            'min_pr_mz': self.min_pr_mz,
            'max_pr_mz': self.max_pr_mz,
            'missed_cleavages': self.missed_cleavages,
            'cut': self.cut,
            'mass_acc': self.mass_acc,
            'mass_acc_ms1': self.mass_acc_ms1,
            'verbose': self.verbose,
            'pg_level': self.pg_level,
            'is_dda': self.is_dda,
            'unimod4': self.unimod4,
            'met_excision': self.met_excision,
        }
    
    def save_config(self, output_path: str) -> str:
        """
        Save workflow configuration to JSON file.
        
        Args:
            output_path: Base path for the output file (without .config.json extension)
        
        Returns:
            Path to the created config JSON file
        """
        import json
        from pathlib import Path
        
        config_path = f"{output_path}.config.json"
        
        # Ensure the directory exists
        config_dir = Path(config_path).parent
        config_dir.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w') as f:
            json.dump(self.to_config_dict(), f, indent=2)
        return config_path
    
    @classmethod
    def from_config_file(cls, config_path: str) -> 'DiannWorkflow':
        """
        Load workflow from a config JSON file.
        
        Args:
            config_path: Path to the .config.json file
        
        Returns:
            DiannWorkflow instance initialized with parameters from config
        """
        import json
        with open(config_path, 'r') as f:
            config = json.load(f)
        return cls(**config)
    
    def _build_common_params(self) -> List[str]:
        """
        Build common DIA-NN parameters shared across all steps.
        
        Returns:
            List of command line argument strings for truly common parameters
        """
        params = []
        
        # Basic parameters
        params.append(f"--threads {self.threads}")
        params.append(f"--qvalue {self.qvalue}")
        params.append(f"--cut '{self.cut}'")
        params.append(f"--min-pep-len {self.min_pep_len}")
        params.append(f"--max-pep-len {self.max_pep_len}")
        params.append(f"--min-pr-charge {self.min_pr_charge}")
        params.append(f"--max-pr-charge {self.max_pr_charge}")
        params.append(f"--min-pr-mz {self.min_pr_mz}")
        params.append(f"--max-pr-mz {self.max_pr_mz}")
        params.append(f"--missed-cleavages {self.missed_cleavages}")
        params.append(f"--mass-acc {self.mass_acc}")
        params.append(f"--mass-acc-ms1 {self.mass_acc_ms1}")
        params.append(f"--verbose {self.verbose}")
        
        # Variable modifications
        if self.var_mods:
            params.append(f"--var-mods {len(self.var_mods)}")
            for unimod_id, mass_delta, residues in self.var_mods:
                params.append(f"--var-mod UniMod:{unimod_id},{mass_delta},{residues}")
        
        # Fixed modifications (optional)
        if self.met_excision:
            params.append("--met-excision")
        if self.unimod4:
            params.append("--unimod4")
        
        return params
    
    def _write_shell_script(
        self,
        script_path: str,
        commands: List[str],
        temp_dirs: List[str],
        output_dirs: List[str],
        log_file: str = None
    ) -> None:
        """
        Write a shell script with proper headers and directory creation.
        
        Args:
            script_path: Path to output shell script
            commands: List of command strings to execute
            temp_dirs: List of temp directories to create
            output_dirs: List of output directories to create
            log_file: Optional log file for tee redirection
        """
        lines = ['#!/bin/bash', 'set -ex', '']
        
        # Create directories
        all_dirs = temp_dirs + output_dirs
        if all_dirs:
            mkdir_cmd = 'mkdir -p ' + ' '.join(f'"{d}"' for d in all_dirs)
            lines.append(mkdir_cmd)
            lines.append('')
        
        # Add commands
        cmd_str = ' \\\n  '.join(commands)
        
        # Add log redirection if specified
        if log_file:
            cmd_str += f' \\\n  | tee "{log_file}"'
        
        lines.append(cmd_str)
        lines.append('')
        
        # Write file
        Path(script_path).write_text('\n'.join(lines))
        
        # Make executable
        os.chmod(script_path, 0o755)
        
        print(f"Generated: {script_path}")
    
    def generate_step_a_library(
        self,
        fasta_path: str,
        script_name: str = 'step_A_library_search.sh'
    ) -> str:
        """
        Generate Step A: Predicted library generation from FASTA.
        
        This step:
        - Takes only FASTA as input (NO raw files)
        - Uses deep learning predictor
        - Generates predicted spectral library
        
        Args:
            fasta_path: Path to FASTA database (only needed for Step A)
            script_name: Name of output shell script
            
        Returns:
            Path to generated shell script
        """
        temp_dir = f"{self.temp_dir_base}_libA"
        predicted_lib = f"{self.lib_dir}/{self.workunit_id}_predicted.speclib"
        
        # Build command
        cmd = [f'"{self.diann_bin}"']
        
        # FASTA search mode
        cmd.append("--fasta-search")
        cmd.append(f'--fasta "{fasta_path}"')
        
        # Common parameters
        cmd.extend(self._build_common_params())
        
        # Step A specific flags
        cmd.append("--predictor")
        cmd.append("--gen-spec-lib")
        
        # Output and temp
        cmd.append(f'--out-lib "{predicted_lib}"')
        cmd.append(f'--temp "{temp_dir}"')
        
        self._write_shell_script(
            script_path=script_name,
            commands=cmd,
            temp_dirs=[temp_dir],
            output_dirs=[self.lib_dir],
            log_file=f"{self.lib_dir}/diann_libA.log.txt"
        )
        
        # Save config alongside the predicted library
        config_path = self.save_config(predicted_lib)
        print(f"Saved workflow config: {config_path}")
        
        return script_name
    
    def generate_step_b_quantification_with_refinement(
        self,
        raw_files: List[str],
        predicted_lib_path: str = None,
        quantify: bool = True,
        script_name: str = 'step_B_quantification_refinement.sh'
    ) -> str:
        """
        Generate Step B: Quantification using predicted library + generate refined library.
        
        This step:
        - Uses predicted library from Step A
        - Processes raw files
        - Generates refined empirical library
        - Uses --reanalyse for MBR (match between runs)
        - Optionally generates quantification matrices
        
        Args:
            raw_files: List of raw/mzML files to process (can be subset for faster library building)
            predicted_lib_path: Path to predicted library from Step A 
                               (defaults to standard location)
            quantify: If True, generate quantification matrices; if False, only build library
            script_name: Name of output shell script
            
        Returns:
            Path to generated shell script
        """
        # Use default path if not provided
        if predicted_lib_path is None:
            predicted_lib_path = f"{self.lib_dir}/{self.workunit_id}_predicted.speclib"
        
        temp_dir = f"{self.temp_dir_base}_quantB"
        output_file = f"{self.quant_b_dir}/{self.workunit_id}_reportB.tsv"
        refined_lib = f"{self.quant_b_dir}/{self.workunit_id}_refined.speclib"
        log_file = f"{self.quant_b_dir}/diann_quantB.log.txt"
        
        # Build command
        cmd = [f'"{self.diann_bin}"']
        
        # Library (NOT --fasta-search here!)
        cmd.append(f'--lib "{predicted_lib_path}"')
        
        # Raw files
        for f in raw_files:
            cmd.append(f"--f {f}")
        
        # Common parameters
        cmd.extend(self._build_common_params())
        
        # Step B specific flags
        if quantify:
            cmd.append("--matrices")
            cmd.append(f"--pg-level {self.pg_level}")
        
        cmd.append("--reanalyse")
        cmd.append("--gen-spec-lib")
        
        # DDA mode if specified
        if self.is_dda:
            cmd.append("--dda")
        
        # Output files
        cmd.append(f'--out "{output_file}"')
        cmd.append(f'--out-lib "{refined_lib}"')
        cmd.append("--out-lib-copy")
        cmd.append(f'--temp "{temp_dir}"')
        
        self._write_shell_script(
            script_path=script_name,
            commands=cmd,
            temp_dirs=[temp_dir],
            output_dirs=[self.quant_b_dir],
            log_file=log_file
        )
        
        # Save config alongside the refined library
        config_path = self.save_config(refined_lib)
        print(f"Saved workflow config: {config_path}")
        
        return script_name
    
    def generate_step_c_final_quantification(
        self,
        raw_files: List[str],
        refined_lib_path: str = None,
        use_quant: bool = True,
        save_library: bool = True,
        script_name: str = 'step_C_final_quantification.sh'
    ) -> str:
        """
        Generate Step C: Final quantification using refined library.
        
        This step:
        - Uses refined library from Step B
        - Re-processes raw files (can be different/larger set than Step B)
        - Optionally uses --use-quant to reuse .quant files from Step B
        - Produces final quantification results
        
        Args:
            raw_files: List of raw/mzML files to process (can include more files than Step B)
            refined_lib_path: Path to refined library from Step B
                             (defaults to standard location)
            use_quant: If True, reuse existing .quant files for files that were in Step B
                      (default True). Files without .quant files will be processed normally.
            save_library: If True, save output library (default True). Set False to skip
                         library writing if not needed.
            script_name: Name of output shell script
            
        Returns:
            Path to generated shell script
        """
        # Use default path if not provided
        if refined_lib_path is None:
            refined_lib_path = f"{self.quant_b_dir}/{self.workunit_id}_refined.speclib"
        
        temp_dir = f"{self.temp_dir_base}_quantC"
        output_file = f"{self.quant_c_dir}/{self.workunit_id}_reportC.tsv"
        output_lib = f"{self.quant_c_dir}/{self.workunit_id}_final.speclib"
        log_file = f"{self.quant_c_dir}/diann_quantC.log.txt"
        
        # Build command
        cmd = [f'"{self.diann_bin}"']
        
        # Library (refined from Step B)
        cmd.append(f'--lib "{refined_lib_path}"')
        
        # Raw files
        for f in raw_files:
            cmd.append(f"--f {f}")
        
        # Common parameters
        cmd.extend(self._build_common_params())
        
        # Step C specific flags
        cmd.append("--matrices")
        
        # Optional: reuse .quant files from Step B
        # Note: Files not in Step B will be processed from scratch (safe)
        if use_quant:
            cmd.append("--use-quant")
        
        cmd.append("--reanalyse")
        cmd.append(f"--pg-level {self.pg_level}")
        
        # DDA mode if specified
        if self.is_dda:
            cmd.append("--dda")
        
        # Output files
        cmd.append(f'--out "{output_file}"')
        
        # Optional: save output library
        if save_library:
            cmd.append(f'--out-lib "{output_lib}"')
            cmd.append("--out-lib-copy")
        
        cmd.append(f'--temp "{temp_dir}"')
        
        self._write_shell_script(
            script_path=script_name,
            commands=cmd,
            temp_dirs=[temp_dir],
            output_dirs=[self.quant_c_dir],
            log_file=log_file
        )
        
        # Save config alongside the final report
        config_path = self.save_config(output_file)
        print(f"Saved workflow config: {config_path}")
        
        return script_name
    
    def generate_all_scripts(
        self,
        fasta_path: str,
        raw_files_step_b: List[str],
        raw_files_step_c: List[str] = None,
        quantify_step_b: bool = True,
        use_quant_step_c: bool = True,
        save_library_step_c: bool = True
    ) -> Dict[str, str]:
        """
        Generate all three workflow scripts.
        
        Args:
            fasta_path: Path to FASTA database for Step A
            raw_files_step_b: Raw files to use in Step B (can be subset for faster library building)
            raw_files_step_c: Raw files to use in Step C (defaults to same as Step B if not specified)
            quantify_step_b: If True, Step B generates quantification; if False, only builds library
            use_quant_step_c: If True, Step C reuses .quant files from Step B (default True).
                             Files not in Step B will be processed from scratch.
            save_library_step_c: If True, Step C saves output library (default True)
        
        Returns:
            Dictionary mapping step names to script paths
        """
        # Default to same files if not specified
        if raw_files_step_c is None:
            raw_files_step_c = raw_files_step_b
        
        print("Generating DIA-NN three-stage workflow scripts...")
        print()
        
        scripts = {
            'step_a': self.generate_step_a_library(fasta_path=fasta_path),
            'step_b': self.generate_step_b_quantification_with_refinement(
                raw_files=raw_files_step_b,
                quantify=quantify_step_b
            ),
            'step_c': self.generate_step_c_final_quantification(
                raw_files=raw_files_step_c,
                use_quant=use_quant_step_c,
                save_library=save_library_step_c
            )
        }
        
        predicted_lib = f"{self.lib_dir}/{self.workunit_id}_predicted.speclib"
        refined_lib = f"{self.quant_b_dir}/{self.workunit_id}_refined.speclib"
        
        print()
        print("Generated scripts:")
        print(f"  1. {scripts['step_a']} - Generate predicted library from FASTA")
        print(f"  2. {scripts['step_b']} - {'Quantify + refine' if quantify_step_b else 'Build refined'} library ({len(raw_files_step_b)} files)")
        print(f"  3. {scripts['step_c']} - Final quantification ({len(raw_files_step_c)} files)")
        print()
        print("Run them in order:")
        for step in ['step_a', 'step_b', 'step_c']:
            print(f"  bash {scripts[step]}")
        print()
        print("Key outputs:")
        print(f"  - Predicted library: {predicted_lib}")
        print(f"  - Refined library:   {refined_lib}")
        print(f"  - Step B results:    {self.quant_b_dir}/{self.workunit_id}_reportB.tsv")
        print(f"  - Final results:     {self.quant_c_dir}/{self.workunit_id}_reportC.tsv")
        
        return scripts


def main():
    """
    Example usage demonstrating the three-stage workflow with flexible file lists.
    """
    # Variable modifications
    var_mods = [
        ('35', '15.994915', 'M'),  # Oxidation of Methionine
    ]
    
    # Initialize workflow with shared parameters only
    workflow = DiannWorkflow(
        workunit_id='WU336182',
        output_base_dir='out-DIANN',
        var_mods=var_mods,
        diann_bin='/usr/diann/diann-2.3.0/diann-linux',
        threads=64,
        qvalue=0.01,
        is_dda=False,  # Set to True if analyzing DDA data
    )
    
    # Example 1: Simple workflow - same files for all steps
    print("=" * 60)
    print("Example 1: Standard workflow - same files for B and C")
    print("=" * 60)
    
    all_files = [
        '24P64-plasma05.mzML',
        '24P64-plasma01.mzML',
        '24P64-plasma16.mzML',
        '24P64-plasma09.mzML',
    ]
    
    workflow.generate_all_scripts(
        fasta_path='/misc/fasta/fgcz_10116_1spg_rat_20240418.fasta',
        raw_files_step_b=all_files,
        raw_files_step_c=all_files,  # Same files (can omit, this is default)
        quantify_step_b=True
    )
    
    # Example 2: Fast library building - subset in B, all files in C
    print("\n" + "=" * 60)
    print("Example 2: Fast library building strategy")
    print("=" * 60)
    
    # Use just 2 files to build refined library quickly
    subset_files = [
        '24P64-plasma05.mzML',
        '24P64-plasma01.mzML',
    ]
    
    # Then quantify all files with the refined library
    all_files_extended = [
        '24P64-plasma05.mzML',
        '24P64-plasma01.mzML',
        '24P64-plasma16.mzML',
        '24P64-plasma09.mzML',
        '24P64-plasma11.mzML',
        '24P64-plasma22.mzML',
    ]
    
    workflow.generate_all_scripts(
        fasta_path='/misc/fasta/fgcz_10116_1spg_rat_20240418.fasta',
        raw_files_step_b=subset_files,      # Fast library building
        raw_files_step_c=all_files_extended, # Full quantification
        quantify_step_b=False  # Skip quantification in B, just build library
    )
    
    # Example 3: Manual individual step generation for maximum flexibility
    print("\n" + "=" * 60)
    print("Example 3: Manual step-by-step generation")
    print("=" * 60)
    
    # Step A: Generate library
    workflow.generate_step_a_library(
        fasta_path='/misc/fasta/fgcz_10116_1spg_rat_20240418.fasta'
    )
    
    # Step B: Refine library with subset
    workflow.generate_step_b_quantification_with_refinement(
        raw_files=subset_files,
        quantify=False  # Just library building, no quantification
    )
    
    # Step C: Full quantification with all files
    workflow.generate_step_c_final_quantification(
        raw_files=all_files_extended
    )


if __name__ == '__main__':
    main()
