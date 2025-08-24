# Enhanced ROM Organizer - User Guide & Testing Procedures

## Table of Contents
1. [Overview & Features](#overview--features)
2. [Installation & Setup](#installation--setup)
3. [Usage Examples](#usage-examples)
4. [Performance Optimization Features](#performance-optimization-features)
5. [Testing Procedures](#testing-procedures)
6. [Understanding Output](#understanding-output)
7. [Troubleshooting](#troubleshooting)
8. [Advanced Configuration](#advanced-configuration)

---

## Overview & Features

The Enhanced ROM Organizer is a high-performance Python script designed to organize ROM collections from various DAT naming conventions (No-Intro, TOSEC, GoodTools, Redump) into EmulationStation-compatible folder structures with advanced concurrent processing capabilities.

### 🎯 **Key Features**
- **Interactive Platform Selection**: Choose which systems to process with file count previews
- **N64 Format Handling**: Separate subfolders for BigEndian/ByteSwapped/Standard formats
- **NDS Encryption Handling**: Separate subfolders for Encrypted/Decrypted/Standard formats ✨ **NEW**
- **Concurrent Processing**: Multi-threaded file discovery, hash calculation, and copying ✨ **NEW**
- **Optimized Hash Calculation**: Memory-mapped SHA1 for large files, buffered I/O for smaller files ✨ **NEW**
- **SHA1 Deduplication**: Intelligent duplicate detection and handling
- **Platform Exclusion**: Automatically excludes unsupported systems with clear reasoning
- **Comprehensive Logging**: 6 separate log files with detailed operation tracking ✨ **NEW**
- **Subcategory Consolidation**: Merges games/firmware/applications folders into single platforms
- **Real-time Progress Reporting**: Thread-safe progress updates during processing ✨ **NEW**
- **Performance Metrics**: Detailed timing and throughput analysis ✨ **NEW**
- **Dry Run Mode**: Preview operations before execution

### 🚀 **Performance Optimizations** ✨ **NEW**
- **Concurrent File Discovery**: Multi-threaded directory traversal
- **Parallel Hash Calculation**: Optimized SHA1 computation with memory-mapping for large files
- **Thread Pool Management**: Adaptive worker pools based on CPU cores
- **Memory Efficiency**: Chunked processing to handle large collections without memory issues
- **I/O Optimization**: Buffered reading and optimized copy operations
- **Progress Batching**: Efficient progress reporting to minimize overhead

### 🎮 **Supported Platforms**
The script maps to all official EmulationStation platforms:
- **Nintendo**: NES, SNES, GB/GBC/GBA, N64 (with format subfolders), GC, Wii/WiiU, DS/3DS (with encryption subfolders ✨)
- **Sega**: Master System, Genesis, Mega Drive, Game Gear, 32X, CD, Saturn, Dreamcast  
- **Sony**: PlayStation 1-4, PSP, PS Vita
- **Atari**: 2600, 5200, 7800, 800, ST, XE, Lynx, Jaguar
- **Others**: 3DO, Amiga, C64, ColecoVision, Intellivision, MSX, Neo Geo, PC Engine, WonderSwan, Arcade

---

## Installation & Setup

### Prerequisites
- **Python 3.7+** (uses only standard library - no external dependencies)
- **Windows/Linux/macOS** compatible
- **Sufficient disk space** for copied ROMs

### Installation Steps

1. **Download the script:**
   ```bash
   # Save as: enhanced_rom_organizer.py
   ```

2. **Verify Python installation:**
   ```bash
   python --version
   # Should show Python 3.7 or higher
   ```

3. **Test the script:**
   ```bash
   python enhanced_rom_organizer.py --help
   ```

4. **Create directory structure:**
   ```
   your_roms_project/
   ├── enhanced_rom_organizer.py
   ├── source_roms/          # Your DAT-organized ROMs
   ├── organized_roms/       # Target for organized ROMs  
   └── logs/                 # Auto-created for log files
   ```

---

---

## Performance Optimization Features

### 🚀 **Designed for Large Collections**
This enhanced version is specifically optimized for processing 50,000+ ROM files efficiently:

#### **Concurrent Processing Architecture**
- **Multi-threaded File Discovery**: Scans multiple directories simultaneously
- **Parallel Hash Calculation**: Calculates SHA1 hashes concurrently for multiple files
- **Concurrent File Operations**: Copies multiple files simultaneously with thread safety
- **Adaptive Thread Pools**: Automatically adjusts worker threads based on CPU cores

#### **Memory-Optimized Hash Calculation**
```
File Size < 10MB  → Buffered reading with optimized chunk sizes
File Size ≥ 10MB  → Memory-mapped file access for maximum performance
Chunk Size        → 1MB blocks for optimal I/O throughput
```

#### **Smart Resource Management**
- **CPU Utilization**: `min(32, CPU_cores * 4)` I/O worker threads
- **Memory Efficiency**: Processes files in batches to prevent memory exhaustion  
- **Progress Optimization**: Batched updates every 50 files to minimize overhead
- **Error Isolation**: Individual file failures don't stop the entire process

#### **Performance Monitoring**
```
📊 Real-time metrics during processing:
  - Discovery rate (files/second)
  - Processing rate (files/second)  
  - Copy throughput (files/second)
  - Memory usage patterns
  - Thread utilization stats
```

### 📁 **Enhanced Format Handling**

#### **N64 ROM Organization** 
```
target/
└── n64/
    ├── bigendian/     # BigEndian format ROMs
    ├── byteswapped/   # ByteSwapped format ROMs  
    └── standard/      # Standard format ROMs
```

#### **Nintendo DS Organization** ✨ **NEW**
```
target/
└── nds/
    ├── encrypted/     # Encrypted DS ROMs (retail format)
    ├── decrypted/     # Decrypted DS ROMs (emulator-ready)
    └── standard/      # Standard/unknown encryption state
```

### ⚡ **Expected Performance Improvements**

For a 50,000 ROM collection:
- **File Discovery**: ~10-30x faster through concurrent directory traversal
- **Hash Calculation**: ~3-5x faster with memory-mapped I/O for large files
- **Overall Processing**: ~5-15x faster depending on hardware and file sizes
- **Progress Visibility**: Real-time updates prevent "hanging" perception

### 🔧 **Hardware Recommendations**

**Optimal Performance:**
- **CPU**: 8+ cores with high single-thread performance
- **RAM**: 16GB+ (8GB minimum)  
- **Storage**: SSD for both source and target (NVMe preferred)
- **Network**: Local storage preferred over network drives

**Minimum Requirements:**  
- **CPU**: 4 cores
- **RAM**: 8GB
- **Storage**: Any (performance will vary)

---

## Usage Examples

### 🔍 **1. Analysis Mode (Recommended First Step)**
```bash
# Analyze your ROM collection without making changes
python enhanced_rom_organizer.py "D:\roms\source" "D:\roms\target" --analyze-only
```

**What this does:**
- Scans your entire source directory
- Identifies supported platforms with file counts
- Shows excluded platforms with reasons
- Lists unknown/unsupported folders
- **No files are modified**

### 🧪 **2. Dry Run Mode (Preview Operations)**
```bash  
# Preview what would happen without copying files
python enhanced_rom_organizer.py "D:\roms\source" "D:\roms\target" --dry-run
```

**What this does:**
- Complete interactive workflow
- Shows all operations that would occur
- Generates logs showing intended actions
- **No files are copied**

### 🎮 **3. Interactive Mode (Recommended)**
```bash
# Full interactive processing with platform selection
python enhanced_rom_organizer.py "D:\roms\source" "D:\roms\target"
```

**What this does:**
- Analyzes your collection
- Presents interactive menu
- Lets you select specific platforms
- Processes only selected platforms
- **Copies files with full deduplication**

### ⚡ **4. Batch Mode (Process All)**
```bash
# Process all supported platforms automatically
python enhanced_rom_organizer.py "D:\roms\source" "D:\roms\target" --no-interactive
```

**What this does:**
- Processes ALL supported platforms found
- No user interaction required
- Suitable for automation/scripts

### 📁 **5. In-Place Organization**
```bash
# Organize within same directory structure
python enhanced_rom_organizer.py "D:\roms" "D:\roms\organized" 
```

---

## Testing Procedures

### 🧪 **Phase 1: Initial Validation Testing**

#### **Test 1: Environment Verification**
```bash
# 1. Test script syntax and dependencies
python -m py_compile enhanced_rom_organizer.py
python enhanced_rom_organizer.py --help

# Expected: No errors, help text displays
```

#### **Test 2: Directory Analysis** 
```bash
# 2. Test with your actual ROM collection
python enhanced_rom_organizer.py "your_source_path" "test_target" --analyze-only

# Expected Results:
# - Shows supported platforms with file counts  
# - Lists excluded platforms with reasons
# - No errors in console output
# - Analysis log created in logs/ folder
```

#### **Test 3: Platform & Format Detection Validation**
Create a test directory structure to verify platform detection and format handling:
```
test_roms/
├── Nintendo - Nintendo Entertainment System (Headerless) (Parent-Clone) (Retool)/
│   ├── game1.nes
│   └── game2.zip
├── Nintendo - Nintendo 64 (BigEndian) (Parent-Clone) (Retool)/  
│   └── game1.n64
├── Nintendo - Nintendo DS (Encrypted) (Parent-Clone) (Retool)/
│   └── game1.nds
├── Nintendo - Nintendo DS (Decrypted) (Parent-Clone) (Retool)/
│   └── game2.nds
├── Sega - Mega Drive - Genesis (Parent-Clone) (Retool)/
│   └── game1.md
└── Sharp - X68000 (Retool)/
    └── game1.dim
```

Run analysis:
```bash
python enhanced_rom_organizer.py "test_roms" "test_target" --analyze-only
```

**Expected Results:**
- `NES` folder detected → maps to `nes` platform
- `N64 BigEndian` folder detected → maps to `n64` platform  
- `DS Encrypted` folder detected → maps to `nds` platform (encrypted subfolder)
- `DS Decrypted` folder detected → maps to `nds` platform (decrypted subfolder)
- `Genesis` folder detected → maps to `genesis` platform
- `Sharp X68000` folder excluded with reason

### 🎯 **Phase 2: Functionality Testing**

#### **Test 4: Dry Run Validation**
```bash
# Test dry run with small dataset
python enhanced_rom_organizer.py "test_roms" "test_target" --dry-run
```

**Validation Checklist:**
- [ ] Interactive menu displays correctly with file counts
- [ ] Platform selection works (try 1,3 and 1-3 formats)
- [ ] N64 format detection works (should show BigEndian subfolder)
- [ ] NDS format detection works (should show Encrypted/Decrypted subfolders) ✨ **NEW**
- [ ] "WOULD COPY" messages appear in logs
- [ ] No actual files copied
- [ ] All 6 log files created with timestamps (including performance.log) ✨ **NEW**
- [ ] Performance metrics logged (discovery rate, processing threads) ✨ **NEW**
- [ ] Concurrent processing messages appear in progress log ✨ **NEW**

#### **Test 5: Small-Scale Live Testing**
```bash  
# Process a small collection (10-50 files) in live mode
python enhanced_rom_organizer.py "test_roms" "test_target"
```

**Validation Checklist:**
- [ ] Files copied to correct platform folders
- [ ] N64 files go to `/n64/bigendian/` subfolder
- [ ] SHA1 deduplication works (copy same file twice - second should be skipped)
- [ ] Progress updates appear during processing
- [ ] Final summary shows correct statistics
- [ ] Target directory structure matches expectations:
  ```
  test_target/
  ├── nes/
  │   ├── game1.nes
  │   └── game2.zip
  ├── n64/
  │   └── bigendian/
  │       └── game1.n64
  └── genesis/
      └── game1.md
  ```

### 📊 **Phase 3: Performance & Scale Testing**

#### **Test 6: Deduplication Accuracy**
Create duplicate test files:
```bash
# Create identical files with same name in different source folders
mkdir -p "test_dupes/Nintendo - Nintendo Entertainment System (1)" 
mkdir -p "test_dupes/Nintendo - Nintendo Entertainment System (2)"
cp "test_file.nes" "test_dupes/Nintendo - Nintendo Entertainment System (1)/"
cp "test_file.nes" "test_dupes/Nintendo - Nintendo Entertainment System (2)/"
```

Run processing:
```bash
python enhanced_rom_organizer.py "test_dupes" "test_target_dupes" --dry-run
```

**Expected Results:**
- First file: "WOULD COPY"  
- Second file: "WOULD SKIP (duplicate)"
- SHA1 hashes calculated and compared
- Deduplication logged correctly

#### **Test 7: Large Collection Testing** (Optional)
```bash
# Test with larger collection (1000+ files)
python enhanced_rom_organizer.py "large_collection" "large_target" --dry-run

# Monitor for:
# - Memory usage stays reasonable
# - Progress updates every 50-100 files  
# - Performance metrics in final summary
# - No memory leaks or crashes
```

### 🔧 **Phase 4: Edge Case Testing**

#### **Test 8: Error Handling**
```bash
# Test various error conditions:

# 1. Non-existent source directory
python enhanced_rom_organizer.py "fake_path" "test_target"
# Expected: Clear error message, graceful exit

# 2. Permission issues (create read-only folder)  
# Expected: Error logged, operation continues with other files

# 3. Interrupt handling (Ctrl+C during processing)
# Expected: Clean cancellation message
```

#### **Test 9: Special Characters & Long Paths**
Test with folders containing:
- Special characters: `Nintendo - Game Boy (Misc & Unlicensed)`
- Long paths (>255 characters on Windows)
- Unicode characters in filenames

#### **Test 10: Platform Consolidation**
Create test structure for consolidation:
```
test_consolidation/
├── Nintendo Famicom & Entertainment System - Games - [NES] (Retool)/
├── Nintendo Famicom & Entertainment System - Firmware (Retool)/
└── Nintendo Famicom & Entertainment System - Applications - [NES] (Retool)/
```

**Expected Result:** All three folders should consolidate to single `nes` platform.

---

## Understanding Output

### 📋 **Log Files Explanation**

The script generates 5 timestamped log files in the `logs/` directory:

1. **`operations_YYYYMMDD_HHMMSS.log`**
   - Every file copy, skip, or rename operation
   - SHA1 hash calculations and comparisons
   - Target path decisions

2. **`analysis_YYYYMMDD_HHMMSS.log`**  
   - Platform detection results
   - Folder categorization decisions
   - Exclusion reasoning

3. **`errors_YYYYMMDD_HHMMSS.log`**
   - File system errors
   - Permission issues
   - Hash calculation failures

4. **`progress_YYYYMMDD_HHMMSS.log`**
   - Real-time processing updates
   - Performance metrics
   - Phase completion notifications

5. **`summary_YYYYMMDD_HHMMSS.log`**
   - Final statistics and summary
   - Processing performance metrics
   - Complete operation overview

### 🎯 **Interactive Menu Guide**

When running in interactive mode, you'll see:

```
ROM COLLECTION ANALYSIS
================================================================================

✅ SUPPORTED PLATFORMS FOUND (12):
--------------------------------------------------
[ 1] nes          - Nintendo Entertainment System
     📁 3 folders, 🎮 1,247 files
[ 2] snes         - Super Nintendo Entertainment System  
     📁 2 folders, 🎮 892 files
[ 3] n64          - Nintendo 64
     📁 2 folders, 🎮 234 files
...

⚠️  EXCLUDED PLATFORMS (5):
--------------------------------------------------
    • Sharp - X68000 (Retool) - X68000 not supported by EmulationStation
    • Tiger - Gizmondo (Retool) - Gizmondo not supported by EmulationStation
...

❓ UNKNOWN PLATFORMS (2):  
--------------------------------------------------
    • Custom ROM Set
    • Homebrew Collection
...

Select platforms to process:
• Enter platform numbers (e.g., 1,3,5-8)
• Enter 'all' for all platforms
• Enter 'quit' to exit

Your selection: 
```

**Selection Examples:**
- `1` → Process only NES
- `1,3,5` → Process NES, N64, and platform 5
- `1-5` → Process platforms 1 through 5
- `all` → Process all supported platforms
- `quit` → Exit without processing

---

## Troubleshooting

### ❌ **Common Issues & Solutions**

#### **Issue: "No platforms found"**
**Causes:**
- ROM files not in recognized folders
- Incorrect source directory path
- No ROM files with recognized extensions

**Solutions:**
```bash
# 1. Verify source path is correct
ls "your_source_path"

# 2. Check for ROM file extensions
find "your_source_path" -name "*.nes" -o -name "*.zip" | head -10

# 3. Run analysis to see what's detected
python enhanced_rom_organizer.py "source" "target" --analyze-only
```

#### **Issue: "Permission denied" errors**
**Causes:**
- Read-only source files
- Target directory permissions
- Files in use by other applications

**Solutions:**
```bash
# 1. Check file permissions
ls -la "your_rom_file"

# 2. Ensure target directory is writable
mkdir -p "target_test" && touch "target_test/test" && rm "target_test/test"

# 3. Close any running emulators or ROM managers
```

#### **Issue: Script runs slowly**
**Causes:**
- Large files requiring SHA1 calculation
- Network drives
- Antivirus scanning

**Solutions:**
- Use local drives when possible
- Exclude ROM directories from real-time antivirus scanning
- Process smaller batches if needed

#### **Issue: Interactive menu not working**  
**Causes:**
- Running in non-interactive environment
- Input redirection issues

**Solutions:**
```bash
# Use non-interactive mode
python enhanced_rom_organizer.py "source" "target" --no-interactive

# Or use batch processing with predefined selections
```

### 🔍 **Debugging Steps**

1. **Enable verbose logging:**
   Check all 5 log files for detailed error information

2. **Test with minimal dataset:**  
   Create a simple test folder with 1-2 ROMs to isolate issues

3. **Verify platform detection:**
   ```bash
   python enhanced_rom_organizer.py "source" "target" --analyze-only 2>&1 | grep -i "error"
   ```

4. **Check Python environment:**
   ```bash
   python --version
   python -c "import hashlib, pathlib, argparse, re; print('All imports successful')"
   ```

---

## Advanced Configuration

### 🔧 **Customizing Platform Mappings**

To add custom platform mappings, edit the `PLATFORM_MAPPINGS` dictionary:

```python
# Add custom pattern (around line 80)
PLATFORM_MAPPINGS = {
    # ... existing mappings ...
    r"Custom.*Collection.*": ("custom", "Custom Platform"),
    r"Homebrew.*Nintendo.*": ("nes", "Nintendo Entertainment System"),
}
```

### 📁 **Custom Exclusions**

To exclude additional platforms:

```python
# Add to EXCLUDED_PLATFORMS dictionary (around line 150)  
EXCLUDED_PLATFORMS = {
    # ... existing exclusions ...
    r"Custom.*Exclude.*": "Custom exclusion reason",
}
```

### ⚙️ **Performance Tuning**

For very large collections:

1. **Adjust progress reporting frequency:**
   ```python
   # Change line ~750: if processed_files % 50 == 0:
   if processed_files % 100 == 0:  # Report every 100 files
   ```

2. **Modify SHA1 chunk size:**
   ```python
   # Change line ~850: for chunk in iter(lambda: f.read(8192), b""):
   for chunk in iter(lambda: f.read(65536), b""):  # Use 64KB chunks
   ```

### 🎯 **Automation Integration**

For automated workflows:

```bash
#!/bin/bash
# Automated ROM organization script

SOURCE_DIR="/path/to/source/roms"
TARGET_DIR="/path/to/organized/roms"
LOG_DIR="/path/to/logs"

# Run organization
python enhanced_rom_organizer.py "$SOURCE_DIR" "$TARGET_DIR" --no-interactive

# Check results
if [ $? -eq 0 ]; then
    echo "ROM organization completed successfully"
    # Move logs to permanent location
    mkdir -p "$LOG_DIR/$(date +%Y%m%d)"
    mv logs/* "$LOG_DIR/$(date +%Y%m%d)/"
else
    echo "ROM organization failed"
    exit 1
fi
```

---

## Final Testing Checklist

Before using with your full ROM collection:

- [ ] **Analysis mode works** with your directory structure
- [ ] **Dry run shows expected results** for a test subset  
- [ ] **Platform detection accuracy** ≥95% for your naming conventions
- [ ] **N64 format handling** creates correct subfolders
- [ ] **Deduplication works** correctly with identical files
- [ ] **Interactive selection** responds properly to various input formats
- [ ] **Progress reporting** provides useful updates during processing
- [ ] **Error handling** gracefully manages issues without crashing
- [ ] **Log files contain** detailed information for troubleshooting
- [ ] **Performance is acceptable** for your collection size

## Success Criteria

✅ **The enhanced ROM organizer is ready for production use when:**
- All platform mappings work correctly for your collection
- Interactive selection provides clear, accurate information  
- File operations complete reliably with comprehensive logging
- Performance meets your requirements for collection size
- Error handling prevents data loss and provides clear feedback

---

*For additional support or feature requests, consult the comprehensive logs generated by the script for detailed operational information.*