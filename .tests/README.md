# Testing Directory

This directory contains all test files, test data, and debugging scripts for the DAT to Shortcode Converter project.

## Directory Structure

```
.tests/
├── README.md           # This file
├── scripts/            # Test scripts and debugging tools
│   ├── test_*.py      # Unit and integration test scripts
│   ├── debug_*.py     # Debug and analysis scripts
│   └── analyze_*.py   # Coverage and pattern analysis tools
└── data/              # Test data and sample files
    └── test-dat-collection/  # Sample ROM collections for testing
```

## Usage Guidelines

### Test Scripts (`scripts/`)
- **Unit tests**: `test_*.py` - Test specific functionality
- **Integration tests**: `test_*_workflow.py` - Test complete workflows
- **Debug tools**: `debug_*.py` - Diagnostic and troubleshooting scripts
- **Analysis tools**: `analyze_*.py` - Pattern coverage and performance analysis

### Test Data (`data/`)
- **Sample collections**: Minimal ROM files and folder structures for testing
- **Reference data**: Expected outputs and pattern mappings
- **Mock data**: Generated test cases for edge case validation

## Running Tests

All test scripts should be run from the project root directory:

```bash
# Run individual test
python .tests/scripts/test_platform_detection.py

# Run analysis tools
python .tests/scripts/analyze_enhanced_coverage.py

# Debug specific functionality
python .tests/scripts/debug_n64_detection.py
```

## Development Notes

- This directory is excluded from version control via `.gitignore`
- Test data should be minimal and focused on specific test cases
- All testing artifacts should be placed here to keep the root directory clean
- Tests should not require external dependencies beyond Python standard library

## Test Categories

1. **Pattern Matching Tests**: Validate DAT folder name recognition
2. **File Organization Tests**: Verify correct target directory structure
3. **Performance Tests**: Measure processing speed and memory usage
4. **WSL2 Compatibility Tests**: Validate filesystem-specific behavior
5. **Regional Handling Tests**: Test consolidated vs regional modes
6. **Error Recovery Tests**: Validate timeout and retry mechanisms