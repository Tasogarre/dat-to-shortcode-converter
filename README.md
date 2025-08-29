# DAT to Shortcode Converter

Convert ROM collections from DAT naming conventions (No-Intro, TOSEC, GoodTools, Redump) to standardised shortcode folder structures for EmulationStation, RetroPie, ArkOS, Batocera, and other emulation frontends.

[![Python](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()
[![Version](https://img.shields.io/badge/version-0.12.9-blue)](CHANGELOG.md)
[![Status](https://img.shields.io/badge/status-production--ready-green)](CHANGELOG.md)

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

## 💖 Support This Project

If this tool has been helpful for organizing your ROM collection, consider supporting its development!

[![Buy Me A Coffee](https://img.shields.io/badge/-Buy%20me%20a%20coffee-orange?style=for-the-badge&logo=buymeacoffee&logoColor=white)](https://buymeacoffee.com/kcdworks)

Your support helps maintain and improve this tool for the retrogaming community. Every coffee counts! ☕

## ✨ Key Features

- **Industry-leading accuracy** - 97.5% platform detection across 58+ systems including all major EmulationStation platforms
- **High-performance processing** - Process thousands of files with real-time progress, memory-efficient hashing, and robust error recovery
- **Smart format handling** - Format-specific subfolders (N64 BigEndian/ByteSwapped, NDS encrypted/decrypted), duplicate prevention with SHA1 verification
- **Advanced pattern matching** - Three-tier system with specialized Good Tools, MAME, and FinalBurn Neo support

## 🎮 Supported Platforms

**Nintendo**: NES, SNES, Game Boy/Color/Advance, N64, GameCube, Wii/U, DS/3DS, Virtual Boy  
**Sega**: Master System, Genesis/Mega Drive, Game Gear, Saturn, Dreamcast  
**Sony**: PlayStation 1-4, PSP, PS Vita  
**Atari**: 2600, 5200, 7800, Lynx, 800  
**Arcade**: MAME, Neo Geo/CD, Atomiswave, FinalBurn Neo  
**Classic Computers**: Amiga, C64, MSX, PC  
**Other**: 3DO, PC Engine, WonderSwan, Vectrex, and 30+ more systems

*Plus specialized support for Good Tools collections (33 platform codes) and format-specific subfolders for N64 and NDS*

## 📦 Quick Start

**Requirements**: Python 3.7+ on Windows, Linux, or macOS

```bash
# 1. Download
git clone https://github.com/Tasogarre/dat-to-shortcode-converter.git
cd dat-to-shortcode-converter

# 2. Verify installation
python dat_to_shortcode_converter.py --help

# 3. Analyze your collection first
python dat_to_shortcode_converter.py "/path/to/dat/roms" "/path/to/output" --analyze-only
```

⚠️ **WSL2 Users**: Run from Windows directly - WSL2 has known I/O issues with large collections on Windows drives

## 🚀 Common Usage

```bash
# Interactive mode (recommended) - choose which platforms to process
python dat_to_shortcode_converter.py "/path/to/dat/roms" "/path/to/output"

# Process all platforms automatically  
python dat_to_shortcode_converter.py "/path/to/dat/roms" "/path/to/output" --no-interactive

# Preview without changes
python dat_to_shortcode_converter.py "/path/to/dat/roms" "/path/to/output" --dry-run

# Debug platform detection issues
python dat_to_shortcode_converter.py "/path/to/dat/roms" "/path/to/output" --analyze-only --debug-analysis
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

## ⚡ Performance

Expect ~65 files/second for typical collections. Large collections (50,000+ files) process in 10-20 minutes with real-time progress tracking.

*Performance varies based on file size, storage type, and antivirus software*

## 📋 Logs and Debugging

Comprehensive logs are saved to `logs/` directory for troubleshooting platform detection and file operations.

## 🔧 Advanced Options

**Key Options:**
- `--analyze-only` - Show platform analysis without processing
- `--dry-run` - Preview operations without copying files  
- `--no-interactive` - Process all platforms automatically
- `--regional-mode regional` - Keep regional variants separate (Famicom/NES)
- `--debug-analysis` - Enhanced debugging for troubleshooting

Run `python dat_to_shortcode_converter.py --help` for all options.

## ❓ Troubleshooting

### Common Issues

**"No platforms found"** - Verify ROM files are in DAT-named folders with recognized extensions (.nes, .zip, etc.). Run with `--analyze-only --debug-analysis` for detailed analysis.

**"Permission denied"** - Ensure target directory is writable and close any running emulators or ROM managers.

**WSL2 Compatibility** - Script experiences high I/O error rates on WSL2 Windows mounts (`/mnt/*`) due to 9p protocol limitations. Use Windows Command Prompt/PowerShell instead.

**Slow performance** - Use local drives, exclude ROM directories from antivirus scanning, or process smaller batches.

### Getting Help
1. Check log files in `logs/` directory
2. Run `--analyze-only --debug-analysis` for detailed platform detection
3. [Open an issue](https://github.com/Tasogarre/dat-to-shortcode-converter/issues) with log files

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. When reporting issues, include log files from `logs/` directory and examples of non-working folder names.

## ⚖️ License

MIT License - see [LICENSE](LICENSE) for details. This tool is for organizing legally owned ROM backups only.

## 🙏 Acknowledgments

Thanks to the **EmulationStation**, **RetroPie**, **No-Intro**, **TOSEC**, **GoodTools**, and **Redump** communities for establishing standards and preserving gaming history.
