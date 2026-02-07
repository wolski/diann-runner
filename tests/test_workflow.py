#!/usr/bin/env python3
"""
test.py - Comprehensive test suite for diann_workflow.py

Run with:
    python3 test.py
    python3 test.py -v  # Verbose output
"""

import unittest
import os
import tempfile
import shutil
from pathlib import Path
from diann_runner.workflow import DiannWorkflow


class TestDiannWorkflow(unittest.TestCase):
    """Test suite for DiannWorkflow class."""
    
    def setUp(self):
        """Set up test fixtures before each test."""
        # Create temporary directory for test outputs
        self.test_dir = tempfile.mkdtemp(prefix='diann_test_')
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
        
        # Test parameters
        self.fasta_path = '/test/database.fasta'
        self.raw_files = ['sample1.mzML', 'sample2.mzML', 'sample3.mzML']
        self.var_mods = [('35', '15.994915', 'M')]
        
        # Create workflow instance
        self.workflow = DiannWorkflow(
            workunit_id='TEST001',
            output_base_dir='test-out',
            var_mods=self.var_mods,
            threads=32,
            qvalue=0.01,
        )
    
    def tearDown(self):
        """Clean up after each test."""
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def read_script(self, script_path):
        """Read and return script content."""
        with open(script_path, 'r') as f:
            return f.read()
    
    def test_init_basic(self):
        """Test basic initialization of DiannWorkflow."""
        self.assertEqual(self.workflow.workunit_id, 'TEST001')
        self.assertEqual(self.workflow.output_base_dir, 'test-out')
        self.assertEqual(self.workflow.threads, 32)
        self.assertEqual(self.workflow.qvalue, 0.01)
        self.assertEqual(len(self.workflow.var_mods), 1)
    
    def test_init_defaults(self):
        """Test initialization with default values."""
        workflow = DiannWorkflow(workunit_id='TEST002')
        self.assertEqual(workflow.threads, 64)
        self.assertEqual(workflow.qvalue, 0.01)
        self.assertEqual(workflow.var_mods, ())
        self.assertEqual(workflow.is_dda, False)
    
    def test_step_a_generation(self):
        """Test Step A script generation."""
        script_path = self.workflow.generate_step_a_library(
            fasta_paths=self.fasta_path,
            script_name='test_step_a.sh'
        )
        
        # Check script exists
        self.assertTrue(os.path.exists(script_path))
        self.assertTrue(os.path.isfile(script_path))
        
        # Check script is executable
        self.assertTrue(os.access(script_path, os.X_OK))
        
        # Check content
        content = self.read_script(script_path)
        self.assertIn('#!/bin/bash', content)
        self.assertIn('--fasta-search', content)
        self.assertIn(self.fasta_path, content)
        self.assertIn('--predictor', content)
        self.assertIn('--gen-spec-lib', content)
        self.assertIn('--threads 32', content)
        self.assertIn('--qvalue 0.01', content)
        self.assertIn('--var-mods 1', content)
        self.assertIn('UniMod:35,15.994915,M', content)
        
        # Should NOT have these flags in Step A
        self.assertNotIn('--reanalyse', content)
        self.assertNotIn('--use-quant', content)
        self.assertNotIn('--matrices', content)
    
    def test_step_b_generation_with_quantification(self):
        """Test Step B script generation with quantification enabled."""
        script_path = self.workflow.generate_step_b_quantification_with_refinement(
            raw_files=self.raw_files,
            quantify=True,
            script_name='test_step_b.sh'
        )

        # Check script exists
        self.assertTrue(os.path.exists(script_path))

        # Check content
        content = self.read_script(script_path)
        self.assertIn('#!/bin/bash', content)
        self.assertIn('--lib', content)
        self.assertIn('report-lib.predicted.speclib', content)
        
        # Check all raw files are present
        for raw_file in self.raw_files:
            self.assertIn(raw_file, content)
        
        # Check Step B specific flags
        self.assertIn('--reanalyse', content)
        self.assertIn('--gen-spec-lib', content)
        self.assertIn('--out-lib', content)
        self.assertIn('_report-lib.parquet', content)
        self.assertIn('--matrices', content)  # Because quantify=True
        self.assertIn('--pg-level', content)   # Because quantify=True
        
        # Should NOT have these
        self.assertNotIn('--fasta-search', content)
        self.assertNotIn('--predictor', content)
        self.assertNotIn('--use-quant', content)  # Only in Step C
    
    def test_step_b_generation_without_quantification(self):
        """Test Step B script generation with quantification disabled."""
        script_path = self.workflow.generate_step_b_quantification_with_refinement(
            raw_files=self.raw_files,
            quantify=False,  # Disable quantification
            script_name='test_step_b_no_quant.sh'
        )
        
        content = self.read_script(script_path)
        
        # Should have library building flags
        self.assertIn('--reanalyse', content)
        self.assertIn('--gen-spec-lib', content)
        
        # Should NOT have quantification flags
        self.assertNotIn('--matrices', content)
        self.assertNotIn('--pg-level', content)
    
    def test_step_c_generation(self):
        """Test Step C script generation."""
        script_path = self.workflow.generate_step_c_final_quantification(
            raw_files=self.raw_files,
            script_name='test_step_c.sh'
        )

        # Check script exists
        self.assertTrue(os.path.exists(script_path))

        # Check content
        content = self.read_script(script_path)
        self.assertIn('#!/bin/bash', content)
        self.assertIn('--lib', content)
        self.assertIn('report-lib.parquet', content)
        
        # Check Step C specific flags
        self.assertIn('--matrices', content)
        self.assertIn('--use-quant', content)  # Critical for Step C!
        self.assertIn('--reanalyse', content)
        self.assertIn('--pg-level', content)
        self.assertIn('--gen-spec-lib', content)  # Step C generates library by default (save_library=True)
        self.assertIn('--out-lib', content)
        self.assertIn('_report-lib.parquet', content)

        # Should NOT have these
        self.assertNotIn('--fasta-search', content)
        self.assertNotIn('--predictor', content)
    
    def test_different_files_b_vs_c(self):
        """Test using different file lists for Steps B and C."""
        files_b = ['sample1.mzML', 'sample2.mzML']
        files_c = ['sample1.mzML', 'sample2.mzML', 'sample3.mzML', 'sample4.mzML']
        
        # Generate Step B with subset
        script_b = self.workflow.generate_step_b_quantification_with_refinement(
            raw_files=files_b,
            script_name='test_b_subset.sh'
        )
        
        # Generate Step C with full set
        script_c = self.workflow.generate_step_c_final_quantification(
            raw_files=files_c,
            script_name='test_c_full.sh'
        )
        
        content_b = self.read_script(script_b)
        content_c = self.read_script(script_c)
        
        # Check Step B only has 2 files
        self.assertIn('sample1.mzML', content_b)
        self.assertIn('sample2.mzML', content_b)
        self.assertNotIn('sample3.mzML', content_b)
        self.assertNotIn('sample4.mzML', content_b)
        
        # Check Step C has all 4 files
        self.assertIn('sample1.mzML', content_c)
        self.assertIn('sample2.mzML', content_c)
        self.assertIn('sample3.mzML', content_c)
        self.assertIn('sample4.mzML', content_c)
    
    def test_generate_all_scripts(self):
        """Test generating all three scripts at once."""
        scripts = self.workflow.generate_all_scripts(
            fasta_paths=self.fasta_path,
            raw_files_step_b=self.raw_files[:2],  # Subset
            raw_files_step_c=self.raw_files,      # Full set
            quantify_step_b=False
        )
        
        # Check all three scripts are returned
        self.assertIn('step_a', scripts)
        self.assertIn('step_b', scripts)
        self.assertIn('step_c', scripts)
        
        # Check all files exist
        for script_path in scripts.values():
            self.assertTrue(os.path.exists(script_path))
            self.assertTrue(os.access(script_path, os.X_OK))
    
    def test_custom_library_paths(self):
        """Test using custom library paths."""
        custom_predicted = '/custom/path/my_predicted.speclib'
        custom_refined = '/custom/path/my_refined.speclib'
        
        script_b = self.workflow.generate_step_b_quantification_with_refinement(
            raw_files=self.raw_files,
            predicted_lib_path=custom_predicted,
            script_name='test_custom_b.sh'
        )
        
        script_c = self.workflow.generate_step_c_final_quantification(
            raw_files=self.raw_files,
            refined_lib_path=custom_refined,
            script_name='test_custom_c.sh'
        )
        
        content_b = self.read_script(script_b)
        content_c = self.read_script(script_c)
        
        self.assertIn(custom_predicted, content_b)
        self.assertIn(custom_refined, content_c)
    
    def test_variable_modifications(self):
        """Test handling of multiple variable modifications."""
        multi_mods = [
            ('35', '15.994915', 'M'),  # Oxidation
            ('21', '79.966331', 'STY'),  # Phosphorylation
        ]
        
        workflow = DiannWorkflow(
            workunit_id='TEST_MODS',
            var_mods=multi_mods
        )
        
        script_path = workflow.generate_step_a_library(
            fasta_paths=self.fasta_path,
            script_name='test_multi_mods.sh'
        )
        
        content = self.read_script(script_path)
        self.assertIn('--var-mods 2', content)
        self.assertIn('UniMod:35,15.994915,M', content)
        self.assertIn('UniMod:21,79.966331,STY', content)
    
    def test_no_variable_modifications(self):
        """Test handling of no variable modifications."""
        workflow = DiannWorkflow(
            workunit_id='TEST_NO_MODS',
            var_mods=[]  # No modifications
        )
        
        script_path = workflow.generate_step_a_library(
            fasta_paths=self.fasta_path,
            script_name='test_no_mods.sh'
        )
        
        content = self.read_script(script_path)
        self.assertNotIn('--var-mods', content)
        self.assertNotIn('UniMod:', content)
    
    def test_dda_mode(self):
        """Test DDA mode flag."""
        workflow = DiannWorkflow(
            workunit_id='TEST_DDA',
            is_dda=True  # Enable DDA mode
        )
        
        script_b = workflow.generate_step_b_quantification_with_refinement(
            raw_files=self.raw_files,
            script_name='test_dda_b.sh'
        )
        
        script_c = workflow.generate_step_c_final_quantification(
            raw_files=self.raw_files,
            script_name='test_dda_c.sh'
        )
        
        content_b = self.read_script(script_b)
        content_c = self.read_script(script_c)
        
        # DDA flag should be in Steps B and C
        self.assertIn('--dda', content_b)
        self.assertIn('--dda', content_c)
        
        # But not in Step A (library generation doesn't need it)
        script_a = workflow.generate_step_a_library(
            fasta_paths=self.fasta_path,
            script_name='test_dda_a.sh'
        )
        content_a = self.read_script(script_a)
        self.assertNotIn('--dda', content_a)
    
    def test_common_params_in_all_steps(self):
        """Test that common parameters appear in all steps."""
        script_a = self.workflow.generate_step_a_library(
            fasta_paths=self.fasta_path,
            script_name='test_common_a.sh'
        )
        script_b = self.workflow.generate_step_b_quantification_with_refinement(
            raw_files=self.raw_files,
            script_name='test_common_b.sh'
        )
        script_c = self.workflow.generate_step_c_final_quantification(
            raw_files=self.raw_files,
            script_name='test_common_c.sh'
        )
        
        common_flags = [
            '--threads 32',
            '--qvalue 0.01',
            "--cut 'K*,R*'",
            '--min-pep-len 6',
            '--max-pep-len 30',
            '--min-fr-mz 200',
            '--max-fr-mz 1800',
            '--met-excision',
            '--unimod4',
        ]
        
        for script in [script_a, script_b, script_c]:
            content = self.read_script(script)
            for flag in common_flags:
                self.assertIn(flag, content)
    
    def test_output_directories_created(self):
        """Test that output directory declarations are in scripts."""
        script_a = self.workflow.generate_step_a_library(
            fasta_paths=self.fasta_path,
            script_name='test_dirs_a.sh'
        )
        
        content = self.read_script(script_a)
        self.assertIn('mkdir -p', content)
        self.assertIn('test-out_libA', content)
    
    def test_log_files(self):
        """Test that log files are properly configured in all steps."""
        script_a = self.workflow.generate_step_a_library(
            fasta_paths=self.fasta_path,
            script_name='test_log_a.sh'
        )
        script_b = self.workflow.generate_step_b_quantification_with_refinement(
            raw_files=self.raw_files,
            script_name='test_log_b.sh'
        )
        script_c = self.workflow.generate_step_c_final_quantification(
            raw_files=self.raw_files,
            script_name='test_log_c.sh'
        )

        content_a = self.read_script(script_a)
        content_b = self.read_script(script_b)
        content_c = self.read_script(script_c)

        # All steps should have tee redirection now
        self.assertIn('| tee', content_a)
        self.assertIn('diann_libA.log.txt', content_a)

        self.assertIn('| tee', content_b)
        self.assertIn('diann_quantB.log.txt', content_b)

        self.assertIn('| tee', content_c)
        self.assertIn('diann_quantC.log.txt', content_c)
    
    def test_protein_grouping_levels(self):
        """Test different protein grouping levels."""
        for pg_level in [0, 1, 2]:
            workflow = DiannWorkflow(
                workunit_id=f'TEST_PG{pg_level}',
                pg_level=pg_level
            )
            
            script_c = workflow.generate_step_c_final_quantification(
                raw_files=self.raw_files,
                script_name=f'test_pg{pg_level}.sh'
            )
            
            content = self.read_script(script_c)
            self.assertIn(f'--pg-level {pg_level}', content)
    
    def test_script_names_customization(self):
        """Test custom script naming."""
        custom_name = 'my_custom_script.sh'
        script_path = self.workflow.generate_step_a_library(
            fasta_paths=self.fasta_path,
            script_name=custom_name
        )
        
        self.assertEqual(script_path, custom_name)
        self.assertTrue(os.path.exists(custom_name))
    
    def test_workunit_id_in_outputs(self):
        """Test that workunit ID appears in output file paths."""
        script_b = self.workflow.generate_step_b_quantification_with_refinement(
            raw_files=self.raw_files,
            script_name='test_wu_b.sh'
        )

        content = self.read_script(script_b)
        self.assertIn('TEST001', content)
        self.assertIn('TEST001_report.parquet', content)
        self.assertIn('TEST001_report-lib', content)


    def test_single_step_generation(self):
        """Test single-step script generation (library prediction + quantification)."""
        script_path = self.workflow.generate_single_step(
            fasta_paths=self.fasta_path,
            raw_files=self.raw_files,
            script_name='test_single_step.sh'
        )

        # Check script exists
        self.assertTrue(os.path.exists(script_path))
        self.assertTrue(os.access(script_path, os.X_OK))

        content = self.read_script(script_path)

        # Check single-step specific flags
        self.assertIn('--lib\n', content.replace(' \\\n', '\n'))  # bare --lib (no path)
        self.assertIn('--fasta-search', content)
        self.assertIn('--predictor', content)
        self.assertIn('--out-lib', content)
        self.assertIn('_report-lib.parquet', content)  # DIA-NN 2.3.2 uses parquet for libraries
        self.assertIn('--gen-spec-lib', content)
        self.assertIn('--matrices', content)
        self.assertIn('--rt-profiling', content)
        self.assertIn(self.fasta_path, content)

        # Check all raw files are present
        for raw_file in self.raw_files:
            self.assertIn(raw_file, content)

        # Check common params
        self.assertIn('--threads 32', content)
        self.assertIn('--qvalue 0.01', content)
        self.assertIn('UniMod:35,15.994915,M', content)

        # Should NOT have these flags
        self.assertNotIn('--reannotate', content)
        self.assertNotIn('--use-quant', content)

        # Output should go to quantB directory
        self.assertIn('test-out_quantB', content)

    def test_single_step_with_multiple_fastas(self):
        """Test single-step with multiple FASTA files."""
        fasta_paths = ['/test/db1.fasta', '/test/db2.fasta']
        script_path = self.workflow.generate_single_step(
            fasta_paths=fasta_paths,
            raw_files=self.raw_files,
            script_name='test_single_multi_fasta.sh'
        )

        content = self.read_script(script_path)
        for fp in fasta_paths:
            self.assertIn(fp, content)

    def test_scan_window_parameter(self):
        """Test that scan_window parameter is correctly added to script."""
        # Case 1: scan_window = 0 (default/auto) -> should NOT be in script
        workflow_auto = DiannWorkflow(
            workunit_id='TEST_SW_0',
            scan_window=0
        )
        script_auto = workflow_auto.generate_step_b_quantification_with_refinement(
            raw_files=self.raw_files,
            script_name='test_sw_0.sh'
        )
        content_auto = self.read_script(script_auto)
        self.assertNotIn('--scan-window', content_auto)

        # Case 2: scan_window = 'AUTO' (explicit auto) -> should NOT be in script
        workflow_explicit_auto = DiannWorkflow(
            workunit_id='TEST_SW_AUTO',
            scan_window='AUTO'
        )
        script_explicit_auto = workflow_explicit_auto.generate_step_b_quantification_with_refinement(
            raw_files=self.raw_files,
            script_name='test_sw_explicit_auto.sh'
        )
        content_explicit_auto = self.read_script(script_explicit_auto)
        self.assertNotIn('--scan-window', content_explicit_auto)
        
        # Case 3: scan_window = 8 -> SHOULD be in script
        workflow_set = DiannWorkflow(
            workunit_id='TEST_SW_SET',
            scan_window=8
        )
        script_set = workflow_set.generate_step_b_quantification_with_refinement(
            raw_files=self.raw_files,
            script_name='test_sw_set.sh'
        )
        content_set = self.read_script(script_set)
        self.assertIn('--scan-window 8', content_set)

class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp(prefix='diann_edge_test_')
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
    
    def tearDown(self):
        """Clean up."""
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_empty_raw_files_list(self):
        """Test behavior with empty raw files list."""
        workflow = DiannWorkflow(workunit_id='TEST_EMPTY')
        
        # Should still generate script, even if no files
        script = workflow.generate_step_b_quantification_with_refinement(
            raw_files=[],
            script_name='test_empty.sh'
        )
        
        self.assertTrue(os.path.exists(script))
    
    def test_single_raw_file(self):
        """Test with single raw file."""
        workflow = DiannWorkflow(workunit_id='TEST_SINGLE')
        
        script = workflow.generate_step_b_quantification_with_refinement(
            raw_files=['single.mzML'],
            script_name='test_single.sh'
        )
        
        with open(script, 'r') as f:
            content = f.read()
        
        self.assertIn('single.mzML', content)
        self.assertEqual(content.count('--f'), 1)
    
    def test_many_raw_files(self):
        """Test with many raw files."""
        workflow = DiannWorkflow(workunit_id='TEST_MANY')
        
        many_files = [f'sample{i:03d}.mzML' for i in range(100)]
        
        script = workflow.generate_step_c_final_quantification(
            raw_files=many_files,
            script_name='test_many.sh'
        )
        
        with open(script, 'r') as f:
            content = f.read()
        
        # Check a few files are present
        self.assertIn('sample000.mzML', content)
        self.assertIn('sample050.mzML', content)
        self.assertIn('sample099.mzML', content)
        
        # Should have 100 --f flags
        self.assertEqual(content.count('--f sample'), 100)


def run_tests():
    """Run the test suite with nice output."""
    print("=" * 70)
    print("DIA-NN Workflow Test Suite")
    print("=" * 70)
    print()
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all tests
    suite.addTests(loader.loadTestsFromTestCase(TestDiannWorkflow))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print()
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("=" * 70)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
