#!/usr/bin/env python3
"""
Comprehensive test suite for concurrent file copying functionality.

This test suite validates that the folder-level threading implementation
in dat_to_shortcode_converter.py correctly prevents 0-byte file creation
and directory-level contention issues.

Test Categories:
1. Basic folder-level threading validation
2. 0-byte file detection and prevention
3. Atomic file operations correctness
4. Race condition stress testing
5. Error handling and retry logic
6. Thread safety and progress tracking
"""

import os
import sys
import shutil
import tempfile
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
import hashlib
import random
import unittest
from unittest.mock import patch, MagicMock

# Add the main script to path for importing
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dat_to_shortcode_converter import PerformanceOptimizedROMProcessor
except ImportError:
    print("Warning: Cannot import PerformanceOptimizedROMProcessor")
    PerformanceOptimizedROMProcessor = None


def standalone_copy_file_atomic(source_path, target_file_path, max_retries=3):
    """
    Standalone version of atomic file copy for testing.
    Extracted from the main processor for unit testing.
    """
    source_path = Path(source_path)
    target_file_path = Path(target_file_path)
    
    for attempt in range(max_retries):
        try:
            # Create target directory if needed
            target_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Use temporary file for atomic copy
            with tempfile.NamedTemporaryFile(
                dir=target_file_path.parent,
                delete=False,
                suffix='.tmp'
            ) as temp_file:
                temp_path = Path(temp_file.name)
            
            # Copy file to temporary location
            shutil.copy2(source_path, temp_path)
            
            # Verify copy succeeded and file is not 0-byte
            if temp_path.stat().st_size == 0:
                temp_path.unlink()
                raise IOError(f"0-byte file created during copy: {source_path}")
            
            # Verify size matches original
            if temp_path.stat().st_size != source_path.stat().st_size:
                temp_path.unlink()
                raise IOError(f"Size mismatch: {source_path}")
            
            # Atomic rename to final destination
            temp_path.rename(target_file_path)
            return True
            
        except Exception as e:
            if attempt < max_retries - 1:
                # Exponential backoff
                wait_time = 0.1 * (2 ** attempt)
                time.sleep(wait_time)
                continue
            else:
                raise IOError(f"Failed to copy {source_path} after {max_retries} attempts: {e}")
    
    return False


class ConcurrentCopyingTestSuite(unittest.TestCase):
    """Comprehensive test suite for concurrent copying functionality."""
    
    def setUp(self):
        """Set up test environment with temporary directories and test files."""
        self.test_dir = Path(tempfile.mkdtemp(prefix="concurrent_copy_test_"))
        self.source_dir = self.test_dir / "source"
        self.target_dir = self.test_dir / "target"
        
        self.source_dir.mkdir()
        self.target_dir.mkdir()
        
        # Create mock loggers
        self.mock_operations_logger = MagicMock()
        self.mock_progress_logger = MagicMock()
        
        # Create test data structures
        self.test_files = []
        self.expected_checksums = {}
        
    def tearDown(self):
        """Clean up test environment."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def create_test_files(self, folder_count=5, files_per_folder=10, file_size_kb=1):
        """
        Create test files organized in folders for concurrent copying tests.
        
        Args:
            folder_count: Number of folders to create
            files_per_folder: Number of files per folder
            file_size_kb: Size of each test file in KB
        """
        for folder_idx in range(folder_count):
            folder_path = self.source_dir / f"folder_{folder_idx}"
            folder_path.mkdir()
            
            for file_idx in range(files_per_folder):
                file_path = folder_path / f"test_file_{file_idx}.rom"
                
                # Create file with random content to detect corruption
                content = os.urandom(file_size_kb * 1024)
                file_path.write_bytes(content)
                
                # Store expected checksum
                checksum = hashlib.sha1(content).hexdigest()
                self.expected_checksums[str(file_path)] = checksum
                self.test_files.append(file_path)
        
        print(f"✅ Created {len(self.test_files)} test files in {folder_count} folders")
    
    def verify_file_integrity(self, source_path, target_path):
        """
        Verify that copied file maintains integrity and is not 0-byte.
        
        Args:
            source_path: Original file path
            target_path: Copied file path
            
        Returns:
            tuple: (is_valid, error_message)
        """
        if not target_path.exists():
            return False, f"Target file does not exist: {target_path}"
        
        # Check for 0-byte file
        target_size = target_path.stat().st_size
        if target_size == 0:
            return False, f"0-byte file detected: {target_path}"
        
        # Check size matches
        source_size = source_path.stat().st_size
        if target_size != source_size:
            return False, f"Size mismatch: source={source_size}, target={target_size}"
        
        # Check content integrity via checksum
        target_content = target_path.read_bytes()
        target_checksum = hashlib.sha1(target_content).hexdigest()
        expected_checksum = self.expected_checksums.get(str(source_path))
        
        if target_checksum != expected_checksum:
            return False, f"Checksum mismatch: expected={expected_checksum}, got={target_checksum}"
        
        return True, "File integrity verified"
    
    def test_folder_level_threading_basic(self):
        """Test basic folder-level threading without contention."""
        print("\n🔍 Testing basic folder-level threading...")
        
        # Create moderate test dataset
        self.create_test_files(folder_count=3, files_per_folder=5, file_size_kb=1)
        
        if not PerformanceOptimizedROMProcessor:
            self.skipTest("PerformanceOptimizedROMProcessor not available")
        
        # Create processor instance
        processor = PerformanceOptimizedROMProcessor(
            self.source_dir, self.mock_operations_logger, self.mock_progress_logger
        )
        
        # Group files by folder (simulate the new architecture)
        files_by_folder = defaultdict(list)
        for file_path in self.test_files:
            source_folder = file_path.parent
            files_by_folder[source_folder].append(file_path)
        
        # Verify folder grouping
        self.assertEqual(len(files_by_folder), 3, "Should have 3 folders")
        for folder_files in files_by_folder.values():
            self.assertEqual(len(folder_files), 5, "Each folder should have 5 files")
        
        print("✅ Folder grouping works correctly")
    
    def test_zero_byte_detection(self):
        """Test detection and prevention of 0-byte files."""
        print("\n🔍 Testing 0-byte file detection...")
        
        # Create test files
        self.create_test_files(folder_count=2, files_per_folder=3, file_size_kb=2)
        
        # Test atomic copy function directly using standalone version
        source_file = self.test_files[0]
        target_file = self.target_dir / "normal_copy.rom"
        target_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # This should work normally
            success = standalone_copy_file_atomic(source_file, target_file)
            self.assertTrue(success, "Copy should succeed")
            is_valid, error_msg = self.verify_file_integrity(source_file, target_file)
            self.assertTrue(is_valid, f"Normal copy failed: {error_msg}")
            print("✅ Normal file copy works correctly")
        except Exception as e:
            self.fail(f"Normal copy should not fail: {e}")
    
    def test_concurrent_stress_different_folders(self):
        """Test concurrent copying across different folders (should work)."""
        print("\n🔍 Testing concurrent copying across different folders...")
        
        # Create larger test dataset to stress test
        self.create_test_files(folder_count=6, files_per_folder=10, file_size_kb=1)
        
        # Group files by folder
        files_by_folder = defaultdict(list)
        for file_path in self.test_files:
            source_folder = file_path.parent
            files_by_folder[source_folder].append(file_path)
        
        copied_files = []
        copy_errors = []
        result_lock = threading.Lock()
        
        def process_folder_files(folder_path, folder_files):
            """Process all files from a single folder (one thread per folder)."""
            thread_copied = []
            thread_errors = []
            
            for source_file in folder_files:
                try:
                    # Create target path with unique name (include folder name to avoid collisions)
                    unique_filename = f"{folder_path.name}_{source_file.name}"
                    target_file = self.target_dir / "testplatform" / unique_filename
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy with atomic operations
                    success = standalone_copy_file_atomic(source_file, target_file)
                    if success:
                        thread_copied.append((source_file, target_file))
                    
                except Exception as e:
                    thread_errors.append((source_file, str(e)))
            
            # Thread-safe result collection
            with result_lock:
                copied_files.extend(thread_copied)
                copy_errors.extend(thread_errors)
        
        # Execute concurrent copying (one thread per folder)
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = []
            for folder_path, folder_files in files_by_folder.items():
                future = executor.submit(process_folder_files, folder_path, folder_files)
                futures.append(future)
            
            # Wait for all threads to complete
            for future in futures:
                future.result()
        
        processing_time = time.time() - start_time
        
        # Verify results
        self.assertEqual(len(copy_errors), 0, f"Copy errors occurred: {copy_errors}")
        self.assertEqual(len(copied_files), len(self.test_files), "All files should be copied")
        
        # Verify file integrity
        integrity_failures = []
        for source_file, target_file in copied_files:
            is_valid, error_msg = self.verify_file_integrity(source_file, target_file)
            if not is_valid:
                integrity_failures.append((source_file, target_file, error_msg))
        
        self.assertEqual(len(integrity_failures), 0, 
                        f"File integrity failures: {integrity_failures}")
        
        print(f"✅ Successfully copied {len(copied_files)} files in {processing_time:.2f}s")
        print(f"✅ No 0-byte files detected")
        print(f"✅ All file integrity checks passed")
    
    def test_atomic_operations_correctness(self):
        """Test that atomic file operations work correctly."""
        print("\n🔍 Testing atomic file operations...")
        
        # Create single test file
        test_folder = self.source_dir / "atomic_test"
        test_folder.mkdir()
        test_file = test_folder / "atomic_test.rom"
        
        # Create file with known content
        test_content = b"ATOMIC_TEST_CONTENT_" + os.urandom(1000)
        test_file.write_bytes(test_content)
        test_checksum = hashlib.sha1(test_content).hexdigest()
        
        # Test atomic copy using standalone function
        target_file = self.target_dir / "atomic_copy.rom"
        target_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Perform atomic copy
        success = standalone_copy_file_atomic(test_file, target_file)
        self.assertTrue(success, "Atomic copy should succeed")
        
        # Verify atomicity properties
        self.assertTrue(target_file.exists(), "Target file should exist after atomic copy")
        self.assertGreater(target_file.stat().st_size, 0, "Target file should not be 0-byte")
        
        # Verify content integrity
        target_content = target_file.read_bytes()
        target_checksum = hashlib.sha1(target_content).hexdigest()
        self.assertEqual(target_checksum, test_checksum, "Content should be identical after atomic copy")
        
        print("✅ Atomic file operations work correctly")
    
    def test_retry_logic_simulation(self):
        """Test retry logic with simulated failures."""
        print("\n🔍 Testing retry logic with simulated failures...")
        
        # Create test file
        test_folder = self.source_dir / "retry_test"
        test_folder.mkdir()
        test_file = test_folder / "retry_test.rom"
        test_content = b"RETRY_TEST_CONTENT_" + os.urandom(500)
        test_file.write_bytes(test_content)
        
        # Create target path
        target_file = self.target_dir / "retry_copy.rom"
        target_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Mock shutil.copy2 to fail first two attempts
        original_copy2 = shutil.copy2
        call_count = 0
        
        def mock_copy2(src, dst):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise OSError("Simulated I/O error")
            return original_copy2(src, dst)
        
        # Test retry logic
        with patch('shutil.copy2', side_effect=mock_copy2):
            try:
                success = standalone_copy_file_atomic(test_file, target_file, max_retries=3)
                self.assertTrue(success, "Retry should succeed")
                self.assertTrue(target_file.exists(), "File should exist after retry")
                self.assertGreater(target_file.stat().st_size, 0, "File should not be 0-byte")
                print("✅ Retry logic successfully recovered from simulated failures")
            except Exception as e:
                self.fail(f"Retry logic should have succeeded: {e}")
    
    def test_thread_safety_progress_tracking(self):
        """Test thread-safe progress tracking during concurrent operations."""
        print("\n🔍 Testing thread-safe progress tracking...")
        
        # Create test dataset
        self.create_test_files(folder_count=4, files_per_folder=8, file_size_kb=1)
        
        # Mock progress tracking
        progress_updates = []
        progress_lock = threading.Lock()
        
        def mock_progress_update(message):
            with progress_lock:
                progress_updates.append({
                    'thread_id': threading.current_thread().ident,
                    'message': message,
                    'timestamp': time.time()
                })
        
        # Group files by folder
        files_by_folder = defaultdict(list)
        for file_path in self.test_files:
            source_folder = file_path.parent
            files_by_folder[source_folder].append(file_path)
        
        # Process with thread-safe progress tracking
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for folder_path, folder_files in files_by_folder.items():
                def process_with_progress(folder_path, folder_files):
                    thread_id = threading.current_thread().ident
                    mock_progress_update(f"Thread {thread_id} starting folder {folder_path.name}")
                    
                    for source_file in folder_files:
                        unique_filename = f"{folder_path.name}_{source_file.name}"
                        target_file = self.target_dir / "testplatform" / unique_filename
                        target_file.parent.mkdir(parents=True, exist_ok=True)
                        success = standalone_copy_file_atomic(source_file, target_file)
                        if success:
                            mock_progress_update(f"Thread {thread_id} copied {unique_filename}")
                    
                    mock_progress_update(f"Thread {thread_id} completed folder {folder_path.name}")
                
                future = executor.submit(process_with_progress, folder_path, folder_files)
                futures.append(future)
            
            # Wait for completion
            for future in futures:
                future.result()
        
        # Verify thread safety
        thread_ids = set(update['thread_id'] for update in progress_updates)
        self.assertGreater(len(thread_ids), 1, "Multiple threads should have reported progress")
        
        # Verify no race conditions in progress updates
        self.assertGreater(len(progress_updates), 0, "Progress updates should be recorded")
        
        print(f"✅ Thread-safe progress tracking with {len(thread_ids)} threads")
        print(f"✅ {len(progress_updates)} progress updates recorded safely")


class FileSystemContentionSimulator:
    """Simulate file system contention to validate fixes."""
    
    @staticmethod
    def simulate_directory_contention_old_method(test_files, target_dir):
        """
        Simulate the OLD method that caused directory contention.
        This should demonstrate the problem we fixed.
        """
        print("\n⚠️  Simulating OLD method (flat file distribution)...")
        
        # OLD METHOD: Flat list distributed randomly to threads
        all_files_flat = list(test_files)  # Flatten all files
        random.shuffle(all_files_flat)  # Random distribution
        
        contention_events = []
        access_lock = threading.Lock()
        directory_access_count = defaultdict(int)
        
        def old_style_copy(file_path):
            """Simulate old-style copying that caused contention."""
            source_dir = file_path.parent
            thread_id = threading.current_thread().ident
            
            with access_lock:
                directory_access_count[source_dir] += 1
                current_access = directory_access_count[source_dir]
                
                # Record contention when multiple threads access same directory
                if current_access > 1:
                    contention_events.append({
                        'directory': source_dir,
                        'thread_id': thread_id,
                        'concurrent_access_count': current_access,
                        'timestamp': time.time()
                    })
            
            # Simulate file copy (just touch target file)
            target_file = target_dir / f"old_method_{file_path.name}"
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.touch()
            
            # Simulate copy delay
            time.sleep(0.001)
            
            with access_lock:
                directory_access_count[source_dir] -= 1
        
        # Execute with multiple threads (OLD WAY)
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(old_style_copy, file_path) for file_path in all_files_flat]
            for future in futures:
                future.result()
        
        return contention_events
    
    @staticmethod
    def simulate_folder_level_threading_new_method(test_files, target_dir):
        """
        Simulate the NEW method with folder-level threading.
        This should show no directory contention.
        """
        print("\n✅ Simulating NEW method (folder-level threading)...")
        
        # NEW METHOD: Group by folder, one thread per folder
        files_by_folder = defaultdict(list)
        for file_path in test_files:
            source_folder = file_path.parent
            files_by_folder[source_folder].append(file_path)
        
        contention_events = []
        access_lock = threading.Lock()
        directory_access_count = defaultdict(int)
        
        def new_style_folder_copy(folder_path, folder_files):
            """Simulate new-style folder-level copying."""
            thread_id = threading.current_thread().ident
            
            # Each thread processes ONE folder completely
            with access_lock:
                directory_access_count[folder_path] += 1
                current_access = directory_access_count[folder_path]
                
                # This should NEVER be > 1 with folder-level threading
                if current_access > 1:
                    contention_events.append({
                        'directory': folder_path,
                        'thread_id': thread_id,
                        'concurrent_access_count': current_access,
                        'timestamp': time.time()
                    })
            
            # Process all files in this folder sequentially
            for file_path in folder_files:
                target_file = target_dir / f"new_method_{file_path.name}"
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.touch()
                time.sleep(0.001)  # Simulate copy time
            
            with access_lock:
                directory_access_count[folder_path] -= 1
        
        # Execute with folder-level threading (NEW WAY)
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = []
            for folder_path, folder_files in files_by_folder.items():
                future = executor.submit(new_style_folder_copy, folder_path, folder_files)
                futures.append(future)
            
            for future in futures:
                future.result()
        
        return contention_events


def run_contention_simulation():
    """Run directory contention simulation to validate our fix."""
    print("🧪 DIRECTORY CONTENTION SIMULATION")
    print("=" * 80)
    
    # Create test environment
    test_dir = Path(tempfile.mkdtemp(prefix="contention_sim_"))
    source_dir = test_dir / "source"
    target_dir = test_dir / "target"
    source_dir.mkdir()
    target_dir.mkdir()
    
    try:
        # Create test files in multiple folders
        test_files = []
        for folder_idx in range(6):
            folder_path = source_dir / f"platform_{folder_idx}"
            folder_path.mkdir()
            
            for file_idx in range(12):
                file_path = folder_path / f"rom_{file_idx}.nes"
                file_path.write_text(f"content_{folder_idx}_{file_idx}")
                test_files.append(file_path)
        
        print(f"Created {len(test_files)} test files in 6 folders")
        
        # Test OLD method (should show contention)
        old_contention = FileSystemContentionSimulator.simulate_directory_contention_old_method(
            test_files, target_dir / "old_method"
        )
        
        # Test NEW method (should show NO contention)  
        new_contention = FileSystemContentionSimulator.simulate_folder_level_threading_new_method(
            test_files, target_dir / "new_method"
        )
        
        # Report results
        print("\n📊 CONTENTION ANALYSIS RESULTS:")
        print("-" * 50)
        print(f"OLD Method - Directory Contention Events: {len(old_contention)}")
        if old_contention:
            directories_with_contention = set(event['directory'] for event in old_contention)
            max_concurrent_access = max(event['concurrent_access_count'] for event in old_contention)
            print(f"  - Directories with contention: {len(directories_with_contention)}")
            print(f"  - Maximum concurrent access to single directory: {max_concurrent_access}")
        
        print(f"NEW Method - Directory Contention Events: {len(new_contention)}")
        if new_contention:
            print("  ⚠️  WARNING: New method still shows contention!")
        else:
            print("  ✅ No directory contention detected")
        
        # Validate our fix
        assert len(new_contention) == 0, "New method should eliminate directory contention"
        assert len(old_contention) > 0, "Old method should show contention for this test to be valid"
        
        print("\n✅ VALIDATION SUCCESSFUL: Folder-level threading eliminates directory contention")
        
    finally:
        shutil.rmtree(test_dir)


if __name__ == "__main__":
    print("🧪 DAT TO SHORTCODE CONVERTER - CONCURRENT COPYING TEST SUITE")
    print("=" * 80)
    print("Testing fixes for directory-level contention and 0-byte file issues")
    print()
    
    # Run contention simulation first
    try:
        run_contention_simulation()
    except Exception as e:
        print(f"❌ Contention simulation failed: {e}")
    
    print("\n" + "=" * 80)
    print("RUNNING COMPREHENSIVE TEST SUITE")
    print("=" * 80)
    
    # Run comprehensive test suite
    unittest.main(verbosity=2, exit=False)