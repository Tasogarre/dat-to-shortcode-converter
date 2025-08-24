# DAT to Shortcode Converter - Claude Development Guide

For general project information, see [README.md](README.md).

## Project Overview

This is a Python ROM collection management tool that converts DAT naming conventions (No-Intro, TOSEC, GoodTools, Redump) to standardized shortcode folder structures for emulation frontends like EmulationStation, RetroPie, and Batocera.

**Key characteristics:**
- Single main script: `dat_to_shortcode_converter.py` (800 lines)
- Uses only Python standard library (no external dependencies)
- Supports 40+ gaming platforms with regex-based pattern matching
- Designed for large collections (50,000+ ROM files)
- Comprehensive logging system (6 different log files)

## Development Environment

**Python Version:** Requires Python 3.7+ (tested with Python 3.13.7)
**Dependencies:** None (uses only standard library)
**Testing:** No existing test framework (behavioral testing recommended)

## Current CLI Interface

```bash
# Basic usage patterns
python dat_to_shortcode_converter.py <source_dir> <target_dir> [options]

# Available options
--analyze-only      # Show platform detection analysis and exit
--dry-run          # Preview operations without copying files  
--no-interactive   # Process all platforms without user selection
--help             # Show help message
```

## Development Workflow

### Testing Strategy

**Current state:** No existing test framework
**Recommended approach:** Behavioral testing focused on file organization outcomes

**Test categories to implement:**
- Platform detection accuracy (DAT folder name → shortcode mapping)
- Regional handling logic (consolidated vs regional modes) 
- Format-specific subfolder creation (N64, NDS variants)
- File organization verification (correct target paths)
- CLI argument processing

**Testing commands:**
```bash
# Always test with analysis mode first
python dat_to_shortcode_converter.py "test_source" "test_target" --analyze-only

# Use dry-run for validation without file operations
python dat_to_shortcode_converter.py "test_source" "test_target" --dry-run
```

### Pre-commit Workflow

**CRITICAL: Always run these checks before committing:**

1. **Syntax validation**: `python -m py_compile dat_to_shortcode_converter.py`
2. **Help command test**: `python dat_to_shortcode_converter.py --help`
3. **Dry-run validation**: Test with sample DAT folders if available
4. **Log verification**: Check that logs/ directory functionality works
5. **CLI argument validation**: Test all argument combinations

### Quality Requirements

**All functionality must work without external dependencies** - The tool's strength is its simplicity and portability.

**Behavioral testing focus:**
- ✅ Test that DAT folders map to correct shortcodes
- ✅ Test that file organization produces expected directory structures  
- ✅ Test that regional preferences work as expected
- ❌ Don't test internal function names or implementation details
- ❌ Don't test file structure or import statements

## Architecture Overview

### Core Classes
- `PlatformInfo`: Platform detection results
- `ProcessingStats`: Progress tracking and metrics
- `EnhancedROMOrganizer`: Main orchestration class
- `PlatformAnalyzer`: DAT folder pattern matching
- `InteractiveSelector`: User interface for platform selection
- `PerformanceOptimizedROMProcessor`: File operations with threading

### Pattern Matching System
- **Regex-based platform detection** using `PLATFORM_MAPPINGS` dictionary
- **Consolidation rules** for regional variants (Famicom→NES, Super Famicom→SNES)
- **Format-specific handling** for N64 BigEndian/ByteSwapped, NDS Encrypted/Decrypted
- **Subcategory consolidation** merges Games/Firmware/Applications folders

## Implementation Context

### Current Enhancement Plan
The project is implementing **regional handling preferences** to allow users to choose between:
- **Consolidated mode** (default): Famicom+NES → nes/, Super Famicom+SNES → snes/
- **Regional mode**: Keep regional variants separate
- **Always separated**: Significant hardware variants (FDS, N64DD, Sega CD) regardless of mode

### Key Development Patterns

**Platform Detection:**
```python
# Follows this pattern throughout codebase
PLATFORM_MAPPINGS = {
    r"Nintendo.*Nintendo Entertainment System.*": ("nes", "Nintendo Entertainment System"),
    r"Nintendo.*Famicom(?!\s+(Disk|&)).*": ("nes", "Nintendo Entertainment System"),
    # ...extensive regex patterns
}
```

**Logging Architecture:**
```python
# Six different log categories
- operations_*.log    # File operations and decisions
- analysis_*.log      # Platform detection results
- progress_*.log      # Real-time processing updates  
- errors_*.log        # Errors and exceptions
- summary_*.log       # Final statistics
- performance_*.log   # Performance metrics
```

**Threading for Performance:**
- Concurrent file discovery with `ThreadPoolExecutor`
- Memory-mapped SHA1 calculation for large files
- Thread-safe progress tracking with locks

## Regional Handling Implementation (In Progress)

### New CLI Argument
```bash
--regional-mode {consolidated,regional}  # Default: consolidated
```

### Implementation Requirements
- `RegionalPreferenceEngine` class for consolidation logic
- Enhanced pattern matching with regional awareness
- Updated display names based on regional mode
- Comprehensive logging of regional decisions

### Validation Requirements
- Test both consolidated and regional modes
- Verify significant variants always separate (FDS, N64DD, etc.)
- Confirm existing platform mappings still work
- Performance impact assessment

## Performance Considerations

**Design goals:**
- Handle 50,000+ ROM files efficiently
- Concurrent processing with thread safety
- Memory-efficient hashing for large files
- Progress reporting without performance impact

**Optimization patterns used:**
- ThreadPoolExecutor for I/O-bound operations
- Memory-mapped file access for large files
- Caching of platform detection results
- Batch processing for file operations

## File Organization Patterns

### Current Output Structure
```
target/
├── nes/
├── snes/ 
├── n64/
│   ├── bigendian/
│   ├── byteswapped/
│   └── standard/
├── nds/
│   ├── encrypted/
│   ├── decrypted/
│   └── standard/
└── [other platforms]/
```

### Supported Format Variants
- **N64**: BigEndian, ByteSwapped, Standard
- **NDS**: Encrypted, Decrypted, Standard  
- **Future**: PSP PSN/PSX2PSP variants planned

## Troubleshooting Common Issues

### Platform Detection Issues
1. Run analysis mode: `--analyze-only`
2. Check `analysis_*.log` for detection results
3. Verify DAT folder naming matches expected patterns
4. Test regex patterns against actual folder names

### Performance Issues  
1. Check `performance_*.log` for bottlenecks
2. Monitor thread utilization in logs
3. Consider processing smaller batches
4. Exclude from antivirus real-time scanning

### File Operation Errors
1. Check `errors_*.log` for specific errors
2. Verify target directory permissions
3. Ensure source files aren't locked by other processes
4. Test with dry-run mode first

## Development Notes

### When Adding New Platforms
1. Add regex patterns to `PLATFORM_MAPPINGS`
2. Test with actual DAT folder names
3. Consider regional variants and consolidation
4. Update platform count in documentation
5. Add to behavioral test cases

### When Modifying Regional Logic
1. Preserve backward compatibility
2. Test both consolidated and regional modes
3. Verify "always separate" variants stay separate
4. Update display names appropriately
5. Log all regional mapping decisions

### Code Style Guidelines
- Follow existing regex pattern style in `PLATFORM_MAPPINGS`
- Use comprehensive logging for debugging
- Maintain thread safety for concurrent operations
- Preserve single-file architecture (no external deps)
- Use descriptive variable names matching existing patterns

---

**Key principle:** This tool succeeds because it's simple, portable, and handles edge cases well. Maintain that simplicity while adding powerful features.