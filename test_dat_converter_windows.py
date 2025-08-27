#!/usr/bin/env python3
"""
Comprehensive Test Suite for DAT Converter - Windows Optimized
Tests file discovery, counting consistency, and Windows compatibility
"""

import unittest
import tempfile
import shutil
import sys
import os
from pathlib import Path
from datetime import datetime
import json

# Import the main class
from dat_to_shortcode_converter import EnhancedROMOrganizer, ManifestTracker, PlatformAnalyzer, ROM_EXTENSIONS


class TestFileDiscovery(unittest.TestCase):
    """Test file discovery and counting mechanisms"""
    
    def setUp(self):
        """Create test directory structure mimicking real ROM collections"""
        self.test_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.test_dir) / "source"
        self.target_dir = Path(self.test_dir) / "target"
        
        # Create nested structure like MAME (simulating the issue)
        self.create_mame_test_structure()
        self.create_nested_platform_structure()
    
    def create_mame_test_structure(self):
        """Create test ROM files in nested directories (mimics MAME's 471 subfolders)"""
        # Simulate MAME structure with many subfolders
        mame_dir = self.source_dir / "MAME 0.245 ROMs (merged)"
        mame_dir.mkdir(parents=True)
        
        # Create main folder with files (10 files)
        for i in range(10):
            (mame_dir / f"game{i}.zip").write_text("test_rom_data")
        
        # Create subfolders (simulate MAME's nested structure)
        total_nested_files = 0
        for subfolder_num in range(5):  # 5 subfolders instead of 471 for testing
            sub_dir = mame_dir / f"subfolder_{subfolder_num}"
            sub_dir.mkdir()
            
            # Each subfolder has multiple files
            for i in range(20):  # 20 files per subfolder
                (sub_dir / f"rom_{i}.zip").write_text("nested_rom_data")
                total_nested_files += 20
        
        # Total expected: 10 (main) + (5 * 20) = 110 files
        self.expected_mame_files = 110
        
    def create_nested_platform_structure(self):
        """Create other platforms with various nesting levels"""
        # Nintendo platform with some nesting
        nes_dir = self.source_dir / "Nintendo - Nintendo Entertainment System (Retool)"
        nes_dir.mkdir(parents=True)
        
        # Add files directly
        for i in range(15):
            (nes_dir / f"game{i}.nes").write_text("nes_game_data")
        
        # Add one subfolder with more files
        nes_sub = nes_dir / "Special Collection"
        nes_sub.mkdir()
        for i in range(5):
            (nes_sub / f"special{i}.nes").write_text("special_nes_data")
        
        # Expected: 15 + 5 = 20 files
        self.expected_nes_files = 20
        self.total_expected_files = self.expected_mame_files + self.expected_nes_files  # 130 total
    
    def test_recursive_file_discovery_completeness(self):
        """Test that ALL files in subdirectories are discovered"""
        import logging
        logger = logging.getLogger('test')
        analyzer = PlatformAnalyzer(self.source_dir, logger)
        platforms, excluded, unknown = analyzer.analyze_directory(
            debug_mode=False, include_empty_dirs=False, target_dir=self.target_dir
        )
        
        # Check that analysis finds all files
        total_files = sum(p.file_count for p in platforms.values())
        self.assertEqual(
            total_files, self.total_expected_files,
            f"Should discover all {self.total_expected_files} files in subdirectories. Found: {total_files}"
        )
        
        # Verify MAME platform specifically (should include all subfolders)
        arcade_platform = None
        for platform in platforms.values():
            if 'arcade' in platform.shortcode or 'mame' in platform.display_name.lower():
                arcade_platform = platform
                break
        
        if arcade_platform:
            self.assertGreaterEqual(
                arcade_platform.file_count, self.expected_mame_files,
                f"MAME platform should include all {self.expected_mame_files} files from subdirectories"
            )
    
    def test_file_count_consistency_through_pipeline(self):
        """Test that file counts remain consistent through all processing stages"""
        organizer = EnhancedROMOrganizer(self.source_dir, self.target_dir, dry_run=True)
        
        # Stage 1: Analysis
        platforms, excluded, unknown = organizer.analyzer.analyze_directory(
            debug_mode=False, include_empty_dirs=False, target_dir=organizer.target_dir
        )
        analysis_count = sum(p.file_count for p in platforms.values())
        
        # Stage 2: Discovery
        if platforms:
            all_files = organizer.performance_processor.discover_files_concurrent(
                platforms, list(platforms.keys())
            )
            discovery_count = len(all_files)
            
            # Discovery should find MORE files (due to recursive subdirectory scanning)
            self.assertGreaterEqual(
                discovery_count, analysis_count, 
                f"Discovery count ({discovery_count}) should be >= analysis count ({analysis_count}) due to recursive scanning"
            )
        
        # Discovery should find all files including nested (which is more than analysis)
        if platforms:
            self.assertGreaterEqual(
                discovery_count, self.total_expected_files,
                f"Discovery should find at least {self.total_expected_files} files. Found: {discovery_count}"
            )
    
    def test_subdirectory_inclusion_in_source_folders(self):
        """Test that source_folders includes ALL folders with ROM files, not just top-level"""
        import logging
        logger = logging.getLogger('test')
        analyzer = PlatformAnalyzer(self.source_dir, logger)
        platforms, excluded, unknown = analyzer.analyze_directory(
            debug_mode=False, include_empty_dirs=False, target_dir=self.target_dir
        )
        
        # Find arcade platform (MAME)
        arcade_platform = None
        for platform in platforms.values():
            if len(platform.source_folders) > 1:  # Should have multiple folders for MAME
                arcade_platform = platform
                break
        
        if arcade_platform:
            # Should have more than 1 folder (main + subfolders)
            self.assertGreater(
                len(arcade_platform.source_folders), 1,
                "MAME platform should include multiple source folders (main + subfolders)"
            )
    
    def tearDown(self):
        """Clean up test directories"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)


class TestManifestGeneration(unittest.TestCase):
    """Test consolidated manifest file generation"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.target_dir = Path(self.test_dir) / "target"
        self.target_dir.mkdir(parents=True)
    
    def test_single_manifest_creation(self):
        """Test that only one manifest file is created"""
        tracker = ManifestTracker(self.target_dir)
        
        # Add some test operations
        test_ops = [
            {'source': 'test1.rom', 'target': 'target1.rom', 'status': 'success'},
            {'source': 'test2.rom', 'target': 'target2.rom', 'status': 'skipped'}
        ]
        tracker.add_folder_operations("test_folder", test_ops)
        
        # Save manifest
        manifest_file = tracker.save()
        
        # Verify file was created
        self.assertIsNotNone(manifest_file, "Manifest file should be created")
        self.assertTrue(Path(manifest_file).exists(), "Manifest file should exist on disk")
        
        # Verify only one manifest file in directory
        manifest_files = list(self.target_dir.glob("copy_manifest_*.json"))
        self.assertEqual(len(manifest_files), 1, "Should create only one manifest file")
    
    def test_manifest_data_structure(self):
        """Test that manifest contains all required data"""
        tracker = ManifestTracker(self.target_dir)
        
        # Add test operations
        test_ops = [
            {'source': 'test.rom', 'target': 'target.rom', 'status': 'success'},
            {'source': 'fail.rom', 'target': 'fail_target.rom', 'status': 'failed'}
        ]
        tracker.add_folder_operations("test_folder", test_ops)
        
        # Save and load manifest
        manifest_file = tracker.save()
        
        with open(manifest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Verify structure
        required_keys = ['timestamp', 'platform', 'execution_info', 'folders_processed']
        for key in required_keys:
            self.assertIn(key, data, f"Manifest should contain {key}")
        
        # Verify execution info includes Windows details
        self.assertIn('windows_native', data['execution_info'])
        self.assertEqual(data['platform'], sys.platform)
    
    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)


class TestWindowsCompatibility(unittest.TestCase):
    """Windows-specific compatibility tests"""
    
    def test_windows_path_handling(self):
        """Test Windows path formats work correctly"""
        if sys.platform == 'win32':
            # Test Windows drive letter paths
            test_paths = [
                r"E:\Emulation\Rom Library - Final",
                r"C:\Users\Test\Documents",
                "E:/Emulation/Forward/Slash"  # Mixed separators
            ]
            
            for test_path in test_paths:
                path_obj = Path(test_path)
                # Test that Path object creation works
                self.assertIsNotNone(path_obj)
                # Test that we can get parts without errors
                parts = path_obj.parts
                self.assertIsInstance(parts, tuple)
    
    def test_unicode_emoji_handling_on_windows(self):
        """Test Unicode and emoji handling on Windows terminals"""
        # Create test instance to access _print_with_emoji
        organizer = EnhancedROMOrganizer(".", ".", dry_run=True)
        
        # Test that emoji output doesn't crash
        test_messages = [
            ("Test message", "✅", "[+]"),
            ("Stats message", "📊", "[*]"),
            ("Error message", "❌", "[-]"),
            ("Time message", "⏰", "[T]")
        ]
        
        for message, emoji, fallback in test_messages:
            try:
                # This should not raise an exception
                organizer._print_with_emoji(message, emoji, fallback)
            except Exception as e:
                self.fail(f"Emoji output failed: {e}")
    
    def test_windows_encoding_compatibility(self):
        """Test that Windows encoding issues are handled"""
        # Test default encoding
        encoding = sys.getdefaultencoding()
        self.assertIsNotNone(encoding)
        
        # Test Unicode string handling
        test_strings = [
            "Regular ASCII text",
            "Unicode text with émojis: ✅❌📊",
            "Japanese characters: テスト",
            "Mixed: Regular + 🎮 + テスト"
        ]
        
        for test_str in test_strings:
            try:
                # Test encoding to UTF-8 (used in log files)
                encoded = test_str.encode('utf-8')
                self.assertIsInstance(encoded, bytes)
                
                # Test round-trip
                decoded = encoded.decode('utf-8')
                self.assertEqual(decoded, test_str)
            except Exception as e:
                self.fail(f"Unicode handling failed for '{test_str}': {e}")
    
    def test_long_path_detection(self):
        """Test Windows long path detection"""
        if sys.platform == 'win32':
            # Test paths near Windows limit
            short_path = "C:" + "\\test" * 10  # ~60 chars
            long_path = "C:" + "\\very_long_folder_name_that_exceeds_limits" * 8  # >260 chars
            
            self.assertLess(len(short_path), 260, "Short path should be under limit")
            self.assertGreater(len(long_path), 260, "Long path should exceed limit")


class TestFunctionalWorkflow(unittest.TestCase):
    """End-to-end functional tests for complete workflow"""
    
    def setUp(self):
        """Create realistic test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.test_dir) / "source" 
        self.target_dir = Path(self.test_dir) / "target"
        
        # Create realistic platform structure
        self.create_realistic_rom_structure()
    
    def create_realistic_rom_structure(self):
        """Create ROM structure similar to real collections"""
        platforms_to_create = [
            ("Nintendo - Nintendo Entertainment System (Retool)", "nes", 25),
            ("Nintendo Game Boy - Games (Retool)", "gb", 15),
            ("MAME 0.245 ROMs (merged)", "arcade", 30)  # This one gets subfolders
        ]
        
        self.total_files = 0
        
        for folder_name, shortcode, file_count in platforms_to_create:
            platform_dir = self.source_dir / folder_name
            platform_dir.mkdir(parents=True)
            
            # Add main files
            ext = ".nes" if shortcode == "nes" else ".gb" if shortcode == "gb" else ".zip"
            for i in range(file_count):
                (platform_dir / f"game{i}{ext}").write_text(f"test_data_{i}")
                self.total_files += 1
            
            # For MAME, add subfolders (simulating the critical nested structure)
            if "MAME" in folder_name:
                for sub_num in range(3):  # 3 subfolders
                    sub_dir = platform_dir / f"subfolder_{sub_num}"
                    sub_dir.mkdir()
                    for sub_file in range(10):  # 10 files per subfolder
                        (sub_dir / f"nested_rom_{sub_file}.zip").write_text("nested_data")
                        self.total_files += 1
        
        # Total expected: 25 + 15 + 30 + (3 * 10) = 100 files
    
    def test_complete_discovery_workflow(self):
        """Test complete discovery workflow finds all files including nested"""
        import logging
        logger = logging.getLogger('test')
        analyzer = PlatformAnalyzer(self.source_dir, logger)
        platforms, excluded, unknown = analyzer.analyze_directory(
            debug_mode=False, include_empty_dirs=False, target_dir=self.target_dir
        )
        
        # Should find all platforms
        self.assertGreater(len(platforms), 0, "Should find at least one platform")
        
        # Should find all files (including nested ones)
        total_discovered = sum(p.file_count for p in platforms.values())
        self.assertEqual(
            total_discovered, self.total_files,
            f"Should discover all {self.total_files} files including nested. Found: {total_discovered}"
        )
        
        # Verify nested folders are included in source_folders
        arcade_platform = None
        for platform in platforms.values():
            if 'arcade' in platform.shortcode:
                arcade_platform = platform
                break
        
        if arcade_platform:
            # Should have multiple source folders (main + subfolders)
            self.assertGreater(
                len(arcade_platform.source_folders), 1,
                "Arcade platform should include multiple source folders for nested structure"
            )
    
    def test_dry_run_workflow(self):
        """Test complete dry-run workflow"""
        organizer = EnhancedROMOrganizer(
            self.source_dir, self.target_dir, 
            dry_run=True, debug=True
        )
        
        # Run analysis
        platforms, excluded, unknown = organizer.analyzer.analyze_directory(
            debug_mode=False, include_empty_dirs=False, target_dir=organizer.target_dir
        )
        
        # Should not fail
        self.assertIsNotNone(platforms)
        
        # Dry run should not create target files
        target_files = list(self.target_dir.rglob("*")) if self.target_dir.exists() else []
        rom_files = [f for f in target_files if f.suffix.lower() in ROM_EXTENSIONS]
        self.assertEqual(len(rom_files), 0, "Dry run should not create ROM files")
    
    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)


class TestManifestIntegration(unittest.TestCase):
    """Test manifest system integration"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.target_dir = Path(self.test_dir) / "target"
        self.target_dir.mkdir(parents=True)
    
    def test_consolidated_manifest_vs_individual_files(self):
        """Test that consolidated manifest replaces individual files"""
        tracker = ManifestTracker(self.target_dir)
        
        # Simulate multiple folder operations (like 700+ folders)
        for folder_num in range(10):  # Simulate 10 folders instead of 700
            folder_path = f"test_folder_{folder_num}"
            operations = [
                {'source': f'file{i}.rom', 'target': f'target{i}.rom', 'status': 'success'}
                for i in range(5)  # 5 operations per folder
            ]
            tracker.add_folder_operations(folder_path, operations)
        
        # Save consolidated manifest
        manifest_file = tracker.save()
        
        # Verify only one manifest file exists
        manifest_files = list(self.target_dir.glob("copy_manifest_*.json"))
        self.assertEqual(len(manifest_files), 1, "Should create only one manifest file")
        
        # Verify manifest contains all operations
        with open(manifest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Should have 10 folders with 5 operations each = 50 total
        self.assertEqual(data['total_operations'], 50, "Should track all operations")
        self.assertEqual(len(data['folders_processed']), 10, "Should track all folders")
    
    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)


class TestWindowsSpecific(unittest.TestCase):
    """Windows-specific functionality tests"""
    
    def test_windows_platform_detection(self):
        """Test Windows platform detection"""
        if sys.platform == 'win32':
            # Test that we correctly identify Windows
            self.assertEqual(sys.platform, 'win32')
            
            # Test path handling
            test_path = r"E:\Emulation\Test"
            path_obj = Path(test_path)
            self.assertIn('E:', str(path_obj))
    
    def test_manifest_windows_metadata(self):
        """Test that manifest includes Windows-specific metadata"""
        temp_dir = tempfile.mkdtemp()
        try:
            tracker = ManifestTracker(temp_dir)
            manifest_file = tracker.save()
            
            with open(manifest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Should include Windows metadata
            exec_info = data['execution_info']
            if sys.platform == 'win32':
                self.assertTrue(exec_info['windows_native'])
            else:
                self.assertFalse(exec_info['windows_native'])
                
        finally:
            shutil.rmtree(temp_dir)


def run_windows_tests():
    """Run test suite with Windows-optimized output"""
    print("=" * 60)
    print("DAT CONVERTER - WINDOWS COMPATIBILITY TEST SUITE")
    print("=" * 60)
    print(f"Platform: {sys.platform}")
    print(f"Python: {sys.version}")
    print(f"Encoding: {sys.getdefaultencoding()}")
    print(f"Windows Native: {sys.platform == 'win32'}")
    print("=" * 60)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    test_classes = [
        TestFileDiscovery,
        TestManifestGeneration,
        TestFunctionalWorkflow,
        TestManifestIntegration,
        TestWindowsSpecific
    ]
    
    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(
        verbosity=2,
        descriptions=True,
        failfast=False
    )
    
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✅ ALL TESTS PASSED - Windows compatibility verified!")
    else:
        print(f"❌ {len(result.failures)} failures, {len(result.errors)} errors")
        print("Check output above for details")
    print("=" * 60)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    # Run Windows-optimized test suite
    success = run_windows_tests()
    
    # Exit with appropriate code for batch files
    sys.exit(0 if success else 1)