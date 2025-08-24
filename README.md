# DAT to Shortcode Converter

Convert ROM collections from DAT naming conventions (No-Intro, TOSEC, GoodTools, Redump) to standardised shortcode folder structures for EmulationStation, RetroPie, ArkOS, Batocera, and other emulation frontends.

[![Python](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()

## 🎯 What This Tool Does

Bridges the gap between ROM preservation collections and emulation frontends by converting verbose DAT folder names to clean, standardised shortcode structures.

### Before (DAT Naming):
```
├── Nintendo - Nintendo Entertainment System (Headerless) (Parent-Clone) (Retool)/
├── Nintendo - Super Nintendo Entertainment System (Headerless) (Parent-Clone) (Retool)/
├── Nintendo - Nintendo 64 (BigEndian) (Parent-Clone) (Retool)/
├── Sega - Mega Drive - Genesis (Parent-Clone) (Retool)/
└── Sony - PlayStation (Parent-Clone) (Retool)/
```

### After (Shortcode Structure):
```
├── nes/
├── snes/
├── n64/
│   └── bigendian/
├── genesis/
└── psx/
```

## ✨ Key Features

### 🚀 **High-Performance Processing**
- **Concurrent file discovery** - Multi-threaded directory scanning
- **Parallel hash calculation** - Memory-mapped SHA1 for files >10MB
- **Optimized for large collections** - Tested with 50,000+ ROM files
- **Real-time progress tracking** - Thread-safe progress updates

### 🎮 **Smart Platform Handling**
- **40+ supported platforms** - All major EmulationStation systems
- **Format-specific organization** - N64 BigEndian/ByteSwapped subfolders
- **NDS encryption handling** - Separate encrypted/decrypted subfolders
- **Platform consolidation** - Merges firmware/games/applications folders

### 🔧 **Advanced Features**
- **SHA1-based deduplication** - Intelligent duplicate detection
- **Interactive platform selection** - Choose which systems to process
- **Comprehensive logging** - 6 detailed log files with timestamps
- **Dry run mode** - Preview operations before execution
- **Exclusion system** - Automatically excludes unsupported platforms

## 🎮 Supported Platforms

### Nintendo Systems
- **NES/Famicom** → `nes`
- **SNES/Super Famicom** → `snes`
- **Game Boy/Color/Advance** → `gb`, `gbc`, `gba`
- **Nintendo 64** → `n64` (with format subfolders)
- **GameCube** → `gc`
- **Wii/Wii U** → `wii`, `wiiu`
- **DS/3DS** → `nds`, `n3ds` (with encryption subfolders)

### Sega Systems
- **Master System** → `mastersystem`
- **Genesis/Mega Drive** → `genesis`, `megadrive`
- **Game Gear** → `gamegear`
- **Saturn/Dreamcast** → `saturn`, `dreamcast`

### Sony Systems
- **PlayStation 1-4** → `psx`, `ps2`, `ps3`, `ps4`
- **PSP/PS Vita** → `psp`, `psvita`

### Other Systems
- **Atari systems** → `atari2600`, `atari5200`, `atari7800`, `atarilynx`
- **Arcade** → `arcade`, `neogeo`
- **PC Engine** → `pcengine`
- **3DO, Amiga, C64** → `3do`, `amiga`, `c64`
- [Full platform list (EmulationStation)](https://github.com/Aloshi/EmulationStation/blob/master/es-app/src/PlatformId.cpp)

## 📦 Installation

### Requirements
- **Python 3.7+** (uses only standard library)
- **Operating System**: Windows, Linux, or macOS
- **Disk space**: Sufficient for ROM collection duplication

### Download
```bash
# Clone the repository
git clone https://github.com/Tasogarre/dat-to-shortcode-converter.git
cd dat-to-shortcode-converter

# Or download the script directly
wget https://raw.githubusercontent.com/Tasogarre/dat-to-shortcode-converter/main/dat_to_shortcode_converter.py
```

### Verify Installation
```bash
python dat_to_shortcode_converter.py --help
```

## 🚀 Usage

### 1. 📊 Analysis Mode (Recommended First Step)
```bash
# Analyze your collection without making changes
python dat_to_shortcode_converter.py "/path/to/dat/roms" "/path/to/output" --analyze-only
```

### 2. 🧪 Dry Run Mode (Preview Operations)
```bash
# Preview what would happen
python dat_to_shortcode_converter.py "/path/to/dat/roms" "/path/to/output" --dry-run
```

### 3. 🎮 Interactive Mode (Recommended)
```bash
# Full interactive processing
python dat_to_shortcode_converter.py "/path/to/dat/roms" "/path/to/output"
```

### 4. ⚡ Batch Mode (Process All)
```bash
# Process all supported platforms automatically
python dat_to_shortcode_converter.py "/path/to/dat/roms" "/path/to/output" --no-interactive
```

## 🎯 Interactive Selection Example

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

Select platforms to process:
• Enter platform numbers (e.g., 1,3,5-8)
• Enter 'all' for all platforms
• Enter 'quit' to exit

Your selection: 1,3
```

## 📁 Output Structure Examples

### Standard Platform
```
output/
└── nes/
    ├── Super Mario Bros.nes
    ├── The Legend of Zelda.nes
    └── Metroid.zip
```

### N64 with Format Subfolders
```
output/
└── n64/
    ├── bigendian/
    │   ├── Super Mario 64.n64
    │   └── GoldenEye 007.z64
    ├── byteswapped/
    │   └── Paper Mario.v64
    └── standard/
        └── Mario Kart 64.rom
```

### Nintendo DS with Encryption Subfolders
```
output/
└── nds/
    ├── encrypted/
    │   ├── Pokemon Diamond.nds
    │   └── New Super Mario Bros.nds
    ├── decrypted/
    │   └── Mario Kart DS.nds
    └── standard/
        └── Brain Age.nds
```

## ⚡ Performance Metrics

For large collections, expect significant performance improvements:

| Collection Size | Processing Time | Files/Second |
|----------------|-----------------|-------------|
| 1,000 files    | ~30 seconds     | ~33/sec     |
| 10,000 files   | ~4 minutes      | ~42/sec     |
| 50,000+ files  | ~15 minutes     | ~55/sec     |

*Performance varies based on hardware, file sizes, and storage type*

## 📋 Logging Output

The converter generates comprehensive logs in the `logs/` directory:

- **`operations_*.log`** - All file operations and decisions
- **`analysis_*.log`** - Platform detection and categorization
- **`progress_*.log`** - Real-time processing updates
- **`errors_*.log`** - Errors and exceptions
- **`summary_*.log`** - Final statistics and performance metrics
- **`performance_*.log`** - Detailed performance analysis

## 🔧 Advanced Options

```bash
# Custom usage examples
python dat_to_shortcode_converter.py [SOURCE] [TARGET] [OPTIONS]

Options:
  --analyze-only      Show analysis results and exit
  --dry-run          Preview operations without copying files
  --no-interactive   Process all platforms without user selection
  -h, --help         Show help message
```

## ❓ Troubleshooting

### Common Issues

**"No platforms found"**
- Verify ROM files are in DAT-named folders
- Check that ROM files have recognized extensions (.nes, .zip, etc.)
- Run with `--analyze-only` to see what's detected

**"Permission denied" errors**
- Ensure target directory is writable
- Close any running emulators or ROM managers
- Check file permissions on source ROMs

**Slow performance**
- Use local drives instead of network storage
- Exclude ROM directories from antivirus real-time scanning
- Consider processing smaller batches for very large collections

### Getting Help

1. Check the generated log files in `logs/` directory
2. Run with `--analyze-only` to diagnose platform detection
3. Test with a small subset of ROMs first
4. [Open an issue](https://github.com/Tasogarre/dat-to-shortcode-converter/issues) with log files attached

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Adding Platform Support
1. Add regex patterns to `PLATFORM_MAPPINGS`
2. Update `SUPPORTED_PLATFORMS.md` documentation
3. Add test cases for new platforms
4. Submit a pull request

### Reporting Issues
- Include log files from `logs/` directory
- Specify your operating system and Python version
- Provide examples of folder names that aren't working

## ⚖️ License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **EmulationStation** and **RetroPie** communities for establishing shortcode standards
- **No-Intro**, **TOSEC**, **GoodTools**, and **Redump** teams for ROM preservation
- ROM management tools like **RomVault** and **igir** for inspiration
- The broader retrogaming community for feedback and testing

---

## 🎮 Ready to Convert Your Collection?

1. **Start with analysis**: `python dat_to_shortcode_converter.py "source" "target" --analyze-only`
2. **Try a dry run**: `python dat_to_shortcode_converter.py "source" "target" --dry-run`  
3. **Process your ROMs**: `python dat_to_shortcode_converter.py "source" "target"`

**Questions?** Check our [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines or [open an issue](https://github.com/Tasogarre/dat-to-shortcode-converter/issues)!
