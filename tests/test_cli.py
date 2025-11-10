#!/usr/bin/env python3
"""
Test suite for CLI commands.
"""

import unittest
import os
import tempfile
import shutil
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from diann_runner.cli import library_search, quantification_refinement, final_quantification, all_stages, create_config


class TestCLI(unittest.TestCase):
    """Test CLI entry points."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp(prefix='diann_cli_test_')
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
    
    def tearDown(self):
        """Clean up."""
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_library_search(self):
        """Test library-search command."""
        library_search(
            fasta=Path('/test/db.fasta'),
            output_dir=Path('out_A'),
            workunit_id='TEST001',
            var_mods=['35,15.994915,M'],
            threads=32,
        )
        
        self.assertTrue(os.path.exists('step_A_library_search.sh'))
        with open('step_A_library_search.sh') as f:
            content = f.read()
            self.assertIn('--fasta-search', content)
            self.assertIn('TEST001', content)
            self.assertIn('--threads 32', content)
        
        # Check that config JSON was created
        config_path = 'out_A_libA/TEST001_predicted.speclib.config.json'
        self.assertTrue(os.path.exists(config_path), f"Config file not found: {config_path}")
        
        # Verify config contains expected parameters
        import json
        with open(config_path) as f:
            config = json.load(f)
            self.assertEqual(config['workunit_id'], 'TEST001')
            self.assertEqual(config['threads'], 32)
            self.assertEqual(config['var_mods'], [['35', '15.994915', 'M']])
    
    def test_quantification_refinement(self):
        """Test quantification-refinement command."""
        # First run library_search to create config
        library_search(
            fasta=Path('/test/db.fasta'),
            output_dir=Path('out_A'),
            workunit_id='TEST002',
            var_mods=['35,15.994915,M'],
            threads=16,
        )
        
        config_path = Path('out_A_libA/TEST002_predicted.speclib.config.json')
        self.assertTrue(config_path.exists())
        
        # Now run quantification_refinement with config
        quantification_refinement(
            config=config_path,
            predicted_lib=Path('out_A_libA/TEST002_predicted.speclib'),
            raw_files=[Path('sample1.mzML'), Path('sample2.mzML')],
        )
        
        self.assertTrue(os.path.exists('step_B_quantification_refinement.sh'))
        with open('step_B_quantification_refinement.sh') as f:
            content = f.read()
            self.assertIn('sample1.mzML', content)
            self.assertIn('sample2.mzML', content)
            self.assertIn('TEST002', content)
        
        # Check that config JSON was created for step B
        config_b_path = 'out_A_quantB/TEST002_refined.speclib.config.json'
        self.assertTrue(os.path.exists(config_b_path))
    
    def test_final_quantification(self):
        """Test final-quantification command."""
        # First run library_search and quantification_refinement to create configs
        library_search(
            fasta=Path('/test/db.fasta'),
            output_dir=Path('out_A'),
            workunit_id='TEST003',
            var_mods=['35,15.994915,M'],
            threads=16,
        )
        
        config_a_path = Path('out_A_libA/TEST003_predicted.speclib.config.json')
        quantification_refinement(
            config=config_a_path,
            predicted_lib=Path('out_A_libA/TEST003_predicted.speclib'),
            raw_files=[Path('sample1.mzML')],
        )
        
        # Now run final_quantification with config from step B
        config_b_path = Path('out_A_quantB/TEST003_refined.speclib.config.json')
        self.assertTrue(config_b_path.exists())
        
        final_quantification(
            config=config_b_path,
            refined_lib=Path('out_A_quantB/TEST003_refined.speclib'),
            raw_files=[Path('sample1.mzML')],
        )
        
        self.assertTrue(os.path.exists('step_C_final_quantification.sh'))
        with open('step_C_final_quantification.sh') as f:
            content = f.read()
            self.assertIn('refined.speclib', content)
            self.assertIn('TEST003', content)
        
        # Check that config JSON was created for step C
        config_c_path = 'out_A_quantC/TEST003_reportC.tsv.config.json'
        self.assertTrue(os.path.exists(config_c_path))
    
    def test_all_stages(self):
        """Test all-stages command."""
        all_stages(
            fasta=Path('/test/db.fasta'),
            raw_files=[Path('sample1.mzML'), Path('sample2.mzML')],
            workunit_id='TEST004',
            var_mods=['35,15.994915,M', '21,79.966331,STY'],
        )
        
        # Check all three scripts were created
        self.assertTrue(os.path.exists('step_A_library_search.sh'))
        self.assertTrue(os.path.exists('step_B_quantification_refinement.sh'))
        self.assertTrue(os.path.exists('step_C_final_quantification.sh'))
        
        # Verify workunit ID in all
        for script in ['step_A_library_search.sh', 'step_B_quantification_refinement.sh', 'step_C_final_quantification.sh']:
            with open(script) as f:
                content = f.read()
                self.assertIn('TEST004', content)
    
    def test_create_config(self):
        """Test create-config command."""
        import json
        
        config_file = Path('test_config.json')
        
        # Create config with custom parameters
        create_config(
            output=config_file,
            workunit_id='TEST_CONFIG',
            var_mods=['35,15.994915,M', '21,79.966331,STY'],
            threads=32,
            qvalue=0.05,
            unimod4=False,
            met_excision=True,
        )
        
        # Verify config file was created
        self.assertTrue(config_file.exists())
        
        # Load and verify contents
        with open(config_file) as f:
            config = json.load(f)
        
        # Check all expected parameters
        self.assertEqual(config['workunit_id'], 'TEST_CONFIG')
        self.assertEqual(config['threads'], 32)
        self.assertEqual(config['qvalue'], 0.05)
        self.assertEqual(config['var_mods'], [['35', '15.994915', 'M'], ['21', '79.966331', 'STY']])
        self.assertEqual(config['unimod4'], False)
        self.assertEqual(config['met_excision'], True)
        
        # Check that all 22 parameters are present
        expected_keys = [
            'workunit_id', 'output_base_dir', 'var_mods', 'diann_bin', 'threads', 'qvalue',
            'min_pep_len', 'max_pep_len', 'min_pr_charge', 'max_pr_charge', 'min_pr_mz', 
            'max_pr_mz', 'missed_cleavages', 'cut', 'mass_acc', 'mass_acc_ms1', 'verbose',
            'pg_level', 'is_dda', 'temp_dir_base', 'unimod4', 'met_excision'
        ]
        for key in expected_keys:
            self.assertIn(key, config, f"Missing key: {key}")
        
        # Now test using this config with library_search
        library_search(
            fasta=Path('/test/db.fasta'),
            config_defaults=config_file,
        )
        
        # Verify the generated script uses config parameters
        self.assertTrue(os.path.exists('step_A_library_search.sh'))
        with open('step_A_library_search.sh') as f:
            content = f.read()
            self.assertIn('TEST_CONFIG', content)
            self.assertIn('--threads 32', content)
            # unimod4 should be disabled
            self.assertNotIn('--unimod4', content)
            # met_excision should be enabled
            self.assertIn('--met-excision', content)


if __name__ == '__main__':
    unittest.main()

