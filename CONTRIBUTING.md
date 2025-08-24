# Contributing to DAT to Shortcode Converter

Thank you for your interest in contributing to the DAT to Shortcode Converter! This document provides guidelines for contributing to the project.

## 🎯 How to Contribute

We welcome contributions in several forms:
- **Bug reports** and feature requests
- **Platform mapping improvements** for better DAT recognition
- **Performance optimizations** for large collections
- **Documentation** and examples
- **Code improvements** and testing

## 🐛 Reporting Issues

### Before Submitting an Issue
1. **Search existing issues** to avoid duplicates
2. **Test with the latest version** of the script
3. **Run analysis mode** first: `python dat_to_shortcode_converter.py "source" "target" --analyze-only`
4. **Try a dry run** to gather more information: `--dry-run`

### Bug Report Template
When reporting bugs, please include:

```markdown
**Description**
A clear description of the issue.

**Steps to Reproduce**
1. Command used: `python dat_to_shortcode_converter.py ...`
2. Source directory structure (sanitized example)
3. Expected behavior vs actual behavior

**Environment**
- OS: [Windows/Linux/macOS + version]
- Python version: [output of `python --version`]
- Script version/commit hash

**Logs**
Attach relevant log files from the `logs/` directory:
- `analysis_*.log` (for platform detection issues)
- `errors_*.log` (for runtime errors)
- `operations_*.log` (for file operation issues)

**Additional Context**
- Collection size (approximate number of files)
- DAT source (No-Intro, TOSEC, GoodTools, Redump)
- Any custom folder naming patterns
```

## 🔧 Contributing Code

### Setting Up Development Environment

1. **Fork the repository**
   ```bash
   git clone https://github.com/Tasogarre/dat-to-shortcode-converter.git
   cd dat-to-shortcode-converter
   ```

2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Test your changes**
   ```bash
   # Test with a small collection first
   python dat_to_shortcode_converter.py "test_data" "test_output" --analyze-only
   ```

### Code Style Guidelines

#### Python Standards
- **PEP 8 compliance** for code formatting
- **Type hints** for function parameters and returns
- **Docstrings** for classes and complex functions
- **Clear variable names** that explain their purpose

#### Architecture Principles
- **Single responsibility** - Each class/function has one clear purpose
- **Error handling** - Graceful degradation with clear error messages
- **Logging** - Comprehensive logging for debugging and user feedback
- **Thread safety** - All concurrent operations must be thread-safe

#### Example Code Style
```python
def detect_platform_format(self, folder_name: str, platform: str) -> str:
    """
    Detect format-specific subfolder requirements for a platform.
    
    Args:
        folder_name: Source folder name to analyze
        platform: Target platform shortcode
        
    Returns:
        Format specifier (e.g., 'bigendian', 'encrypted', 'standard')
    """
    folder_lower = folder_name.lower()
    
    if platform == "n64":
        if "bigendian" in folder_lower:
            return "bigendian"
        elif "byteswapped" in folder_lower:
            return "byteswapped"
        else:
            return "standard"
    
    return "standard"
```

### Testing Guidelines

#### Manual Testing Requirements
Before submitting a PR, test with:

1. **Analysis mode** on various DAT folder structures
2. **Dry run mode** to verify intended operations
3. **Small live test** (10-50 files) to verify copying works
4. **Platform detection accuracy** for your changes
5. **Error handling** with invalid inputs

#### Test Data Structure
Create test folders that match these patterns:
```
test_data/
├── Nintendo - Nintendo Entertainment System (Headerless) (Parent-Clone) (Retool)/
├── Nintendo - Nintendo 64 (BigEndian) (Parent-Clone) (Retool)/
├── Nintendo - Nintendo DS (Encrypted) (Parent-Clone) (Retool)/
├── Sega - Mega Drive - Genesis (Parent-Clone) (Retool)/
├── Unknown Platform That Should Be Ignored/
└── Sharp - X68000 (Retool)/  # Should be excluded
```

## 🎮 Adding Platform Support

### Platform Mapping Guidelines

Platforms must be supported by EmulationStation. Check the [official platform list](https://github.com/Aloshi/EmulationStation/blob/master/es-app/src/PlatformId.cpp) before adding new mappings.

#### Adding New Platform Regex
1. **Add to `PLATFORM_MAPPINGS`** dictionary:
   ```python
   r"Your.*Platform.*Pattern.*": ("shortcode", "Display Name"),
   ```

2. **Follow naming conventions**:
   - Use **lowercase shortcodes** matching EmulationStation
   - Use **descriptive display names** for user interface
   - Create **specific patterns** to avoid false matches

#### Example Platform Addition
```python
# Add to PLATFORM_MAPPINGS around line 80
r"Bandai.*Playdia.*": ("playdia", "Bandai Playdia"),
r"Commodore.*VIC-20.*": ("vic20", "Commodore VIC-20"),
```

#### Testing New Platforms
1. Create test folders with your new naming patterns
2. Run analysis mode to verify detection
3. Test with dry run to verify target mapping
4. Verify the shortcode exists in EmulationStation's supported platforms

### Exclusion Guidelines

If a platform should be excluded (not supported by EmulationStation):

```python
# Add to EXCLUDED_PLATFORMS around line 150
r"Your.*Unsupported.*Platform.*": "Clear reason why it's not supported",
```

## 🚀 Performance Contributions

### Areas for Optimization
- **Hash calculation** improvements
- **Concurrent processing** enhancements  
- **Memory usage** optimizations for very large collections
- **Progress reporting** efficiency improvements

### Performance Testing
When submitting performance improvements:
1. **Benchmark before and after** with timing data
2. **Test with large collections** (1000+ files)
3. **Monitor memory usage** during processing
4. **Verify thread safety** in concurrent operations

### Profiling Guidelines
```bash
# Profile your changes
python -m cProfile -o profile.stats dat_to_shortcode_converter.py "source" "target" --dry-run

# Analyze with:
python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('tottime').print_stats(20)"
```

## 📝 Pull Request Process

### Before Submitting
- [ ] **Test thoroughly** with various DAT folder structures
- [ ] **Run analysis mode** to verify platform detection
- [ ] **Check for regressions** in existing functionality
- [ ] **Update comments** and docstrings as needed
- [ ] **Follow code style guidelines**

### Pull Request Template
```markdown
**Description**
Brief description of changes and motivation.

**Type of Change**
- [ ] Bug fix
- [ ] New platform support
- [ ] Performance improvement  
- [ ] Documentation update
- [ ] Code refactoring

**Testing**
- [ ] Tested with analysis mode
- [ ] Tested with dry run
- [ ] Tested with live processing (small collection)
- [ ] Verified no regressions in existing platforms

**Platform Changes** (if applicable)
- New platforms added: [list]
- Regex patterns modified: [list]
- EmulationStation compatibility verified: [yes/no]

**Performance Impact** (if applicable)
- Benchmark results: [before/after timing]
- Memory usage impact: [description]
- Large collection testing: [results]
```

### Review Process
1. **Automated checks** will run for basic validation
2. **Manual review** by maintainers
3. **Testing** with various DAT collections  
4. **Discussion** if changes need refinement
5. **Merge** once approved

## 🤝 Community Guidelines

### Communication
- **Be respectful** and constructive in discussions
- **Stay on topic** for issues and PRs
- **Provide context** when reporting problems
- **Help others** when you can share knowledge

### Code of Conduct
- **Inclusive environment** - welcome all contributors
- **Professional interaction** - focus on technical merit
- **Collaborative spirit** - work together toward common goals
- **Respect different perspectives** on implementation approaches

## 📖 Resources

### Understanding the Codebase
- **Main conversion logic**: `EnhancedROMOrganizer` class
- **Platform detection**: `PlatformAnalyzer` class
- **Performance optimization**: `PerformanceOptimizedROMProcessor` class
- **Format handling**: `FormatHandler` class (N64, NDS subfolders)

### External References
- [EmulationStation Platform IDs](https://github.com/Aloshi/EmulationStation/blob/master/es-app/src/PlatformId.cpp)
- [No-Intro DAT Standards](https://datomatic.no-intro.org/)
- [TOSEC Naming Convention](https://www.tosecdev.org/)
- [Python PEP 8 Style Guide](https://pep8.org/)

## ❓ Questions?

- **Check existing issues** first
- **Open a discussion** for general questions
- **Contact maintainers** for complex technical questions

Thank you for contributing to the DAT to Shortcode Converter! 🎮
