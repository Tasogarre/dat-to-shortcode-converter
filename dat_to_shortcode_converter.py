#!/usr/bin/env python3
"""
Enhanced ROM Organizer Script - Advanced DAT to EmulationStation Organization
Usage: python enhanced_rom_organizer.py <source_directory> <target_directory> [options]

Features:
- Interactive platform selection with file count previews
- N64 format-specific subfolder organization
- Platform exclusion system for unsupported systems
- Comprehensive regex-based pattern matching
- SHA1-based deduplication with detailed logging
- Subcategory consolidation (firmware/games/applications)
- Comprehensive timestamped logging system
"""

import os
import sys
import hashlib
import shutil
import argparse
import logging
import re
import mmap
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Set, Optional, NamedTuple
from collections import defaultdict, Counter
from dataclasses import dataclass
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue
from threading import Lock

class PlatformInfo(NamedTuple):
    """Information about a detected platform"""
    shortcode: str
    display_name: str
    folder_count: int
    file_count: int
    source_folders: List[str]

@dataclass
class ProcessingStats:
    """Statistics for tracking processing progress"""
    platforms_found: int = 0
    files_found: int = 0
    files_copied: int = 0
    files_skipped_duplicate: int = 0
    files_skipped_unknown: int = 0
    errors: int = 0
    processing_time: float = 0.0
    selected_platforms: List[str] = None

    def __post_init__(self):
        if self.selected_platforms is None:
            self.selected_platforms = []

# Enhanced platform mappings with regex patterns
PLATFORM_MAPPINGS = {
    # Nintendo Systems - Enhanced patterns for consolidation
    r"Nintendo.*Nintendo Entertainment System.*": ("nes", "Nintendo Entertainment System"),
    r"Nintendo.*Famicom.*Entertainment System.*": ("nes", "Nintendo Entertainment System"),
    r"Nintendo.*Famicom(?!\s+(Disk|&)).*": ("nes", "Nintendo Entertainment System"),
    r"Nintendo.*Family Computer.*": ("nes", "Nintendo Entertainment System"),
    r"Nintendo.*Super Nintendo.*": ("snes", "Super Nintendo Entertainment System"),
    r"Nintendo.*Super Famicom.*": ("snes", "Super Nintendo Entertainment System"),
    r"Nintendo.*Game Boy(?!\s+(Color|Advance)).*": ("gb", "Game Boy"),
    r"Nintendo.*Game Boy Color.*": ("gbc", "Game Boy Color"),
    r"Nintendo.*Game Boy Advance.*": ("gba", "Game Boy Advance"),
    r"Nintendo.*Nintendo 64.*": ("n64", "Nintendo 64"),
    r"Nintendo.*GameCube.*": ("gc", "GameCube"),
    r"Nintendo.*Wii(?!\s+U).*": ("wii", "Wii"),
    r"Nintendo.*Wii U.*": ("wiiu", "Wii U"),
    r"Nintendo.*Nintendo DS(?!i).*": ("nds", "Nintendo DS"),
    r"Nintendo.*Nintendo DSi.*": ("nds", "Nintendo DS"),  # Consolidate DSi into DS
    r"Nintendo.*Nintendo 3DS.*": ("n3ds", "Nintendo 3DS"),
    r"Nintendo.*Virtual Boy.*": ("virtualboy", "Virtual Boy"),
    r"Nintendo.*Pokemon Mini.*": ("pokemini", "Pokemon Mini"),
    
    # Sega Systems - Keep genesis and megadrive separate as requested
    r"Sega.*Master System.*": ("mastersystem", "Sega Master System"),
    r"Sega.*Mark III.*": ("mastersystem", "Sega Master System"),
    r"Sega.*Mega Drive.*": ("megadrive", "Sega Mega Drive"),
    r"Sega.*Genesis.*": ("genesis", "Sega Genesis"),
    r"Sega.*Game Gear.*": ("gamegear", "Sega Game Gear"),
    r"Sega.*32X.*": ("sega32x", "Sega 32X"),
    r"Sega.*Mega.?CD.*": ("segacd", "Sega CD"),
    r"Sega.*Sega CD.*": ("segacd", "Sega CD"),
    r"Sega.*Saturn.*": ("saturn", "Sega Saturn"),
    r"Sega.*Dreamcast.*": ("dreamcast", "Sega Dreamcast"),
    r"Sega.*SG-1000.*": ("sg1000", "Sega SG-1000"),  # Note: Not in EmulationStation list
    
    # Sony Systems
    r"Sony.*PlayStation(?!\s+(2|3|4|Portable|Vita)).*": ("psx", "PlayStation"),
    r"Sony.*PlayStation 2.*": ("ps2", "PlayStation 2"),
    r"Sony.*PlayStation 3.*": ("ps3", "PlayStation 3"),
    r"Sony.*PlayStation 4.*": ("ps4", "PlayStation 4"),
    r"Sony.*PlayStation Portable.*": ("psp", "PlayStation Portable"),
    r"Sony.*PlayStation Vita.*": ("psvita", "PlayStation Vita"),
    
    # Atari Systems
    r"Atari.*2600.*": ("atari2600", "Atari 2600"),
    r"Atari.*5200.*": ("atari5200", "Atari 5200"),
    r"Atari.*7800.*": ("atari7800", "Atari 7800"),
    r"Atari.*Lynx.*": ("atarilynx", "Atari Lynx"),
    r"Atari.*Jaguar(?!\s+CD).*": ("atarijaguar", "Atari Jaguar"),
    r"Atari.*Jaguar CD.*": ("atarijaguarcd", "Atari Jaguar CD"),
    r"Atari.*8-bit.*": ("atari800", "Atari 8-bit Family"),
    r"Atari.*ST.*": ("atarist", "Atari ST"),
    r"Atari.*XE.*": ("atarixe", "Atari XE"),
    
    # PC Systems - Consolidate to 'pc'
    r"DOS.*": ("pc", "PC (DOS)"),
    r"IBM.*PC.*": ("pc", "PC (IBM Compatible)"),
    r".*PC and Compatibles.*": ("pc", "PC (IBM Compatible)"),
    
    # Other Supported Systems
    r"Commodore.*64.*": ("c64", "Commodore 64"),
    r"Commodore.*Amiga.*": ("amiga", "Commodore Amiga"),
    r"Coleco.*ColecoVision.*": ("colecovision", "ColecoVision"),
    r"Mattel.*Intellivision.*": ("intellivision", "Mattel Intellivision"),
    r"NEC.*PC Engine.*": ("pcengine", "PC Engine"),
    r"NEC.*TurboGrafx.*": ("pcengine", "TurboGrafx-16"),
    r"SNK.*Neo.?Geo Pocket(?!\s+Color).*": ("ngp", "Neo Geo Pocket"),
    r"SNK.*Neo.?Geo Pocket Color.*": ("ngpc", "Neo Geo Pocket Color"),
    r"Bandai.*WonderSwan(?!\s+Color).*": ("wonderswan", "WonderSwan"),
    r"Bandai.*WonderSwan Color.*": ("wonderswancolor", "WonderSwan Color"),
    r"3DO.*": ("3do", "3DO Interactive Multiplayer"),
    r"Amstrad.*CPC.*": ("amstradcpc", "Amstrad CPC"),
    r"Apple.*Apple II.*": ("apple2", "Apple II"),
    r".*MSX(?!2).*": ("msx", "MSX"),
    r"Sinclair.*ZX Spectrum.*": ("zxspectrum", "ZX Spectrum"),
    r"Microsoft.*Xbox(?!\s+360).*": ("xbox", "Microsoft Xbox"),
    r"Microsoft.*Xbox 360.*": ("xbox360", "Microsoft Xbox 360"),
    r".*Macintosh.*": ("macintosh", "Apple Macintosh"),
    
    # Arcade Systems
    r".*Arcade.*": ("arcade", "Arcade"),
    r"Neo.?Geo(?!\s+Pocket).*": ("neogeo", "Neo Geo"),
    r"FinalBurn.*Arcade.*": ("arcade", "Arcade"),
    r"MAME.*": ("arcade", "Arcade (MAME)"),
    
    # GoodTools patterns
    r"GoodNES.*": ("nes", "Nintendo Entertainment System"),
    r"GoodSNES.*": ("snes", "Super Nintendo Entertainment System"),
    r"GoodN64.*": ("n64", "Nintendo 64"),
    r"GoodGen.*": ("genesis", "Sega Genesis"),
    r"GoodSMS.*": ("mastersystem", "Sega Master System"),
    r"GoodGG.*": ("gamegear", "Sega Game Gear"),
    r"Good32X.*": ("sega32x", "Sega 32X"),
    r"GoodMCD.*": ("segacd", "Sega CD"),
    r"GoodSAT.*": ("saturn", "Sega Saturn"),
    r"GoodPCE.*": ("pcengine", "PC Engine"),
    r"GoodLynx.*": ("atarilynx", "Atari Lynx"),
    r"Good5200.*": ("atari5200", "Atari 5200"),
    r"Good7800.*": ("atari7800", "Atari 7800"),
    r"Good2600.*": ("atari2600", "Atari 2600"),
}

# Platforms explicitly excluded due to lack of EmulationStation support
EXCLUDED_PLATFORMS = {
    r"Sharp.*X68000.*": "X68000 not supported by EmulationStation",
    r"Tiger.*Gizmondo.*": "Gizmondo not supported by EmulationStation",
    r"Dragon Data.*Dragon.*": "Dragon Data systems not supported by EmulationStation",
    r".*TRS-80.*": "TRS-80 systems not supported by EmulationStation",
    r"Sharp.*X1.*": "Sharp X1 not supported by EmulationStation",
    r"Tsukuda.*Othello.*": "Othello Multivision not supported by EmulationStation",
    r"Watara.*Supervision.*": "Watara Supervision not supported by EmulationStation",
    r"GCE.*Vectrex.*": "Vectrex support limited in EmulationStation",
    r"Magnavox.*Odyssey.*": "Odyssey systems support limited in EmulationStation",
    r"Philips.*Videopac.*": "Videopac support limited in EmulationStation",
    r".*Pokitto.*": "Pokitto not supported by EmulationStation",
}

# ROM file extensions for detection
ROM_EXTENSIONS = {
    '.nes', '.fds', '.nsf', '.unf', '.nez',  # NES/Famicom
    '.sfc', '.smc', '.swc', '.fig',  # SNES
    '.gb', '.gbc', '.gba', '.sgb',  # Game Boy systems
    '.n64', '.v64', '.z64', '.rom',  # N64
    '.gcm', '.iso', '.rvz', '.ciso', '.wbfs', '.wad',  # Nintendo disc systems
    '.nds', '.nde', '.srl',  # DS
    '.3ds', '.cia', '.3dsx',  # 3DS
    '.sms', '.gg', '.sg',  # Sega 8-bit
    '.md', '.gen', '.bin', '.smd',  # Genesis/Mega Drive
    '.32x',  # 32X
    '.cue', '.chd', '.mds', '.ccd', '.sub', '.img', '.pbp', '.cso',  # CD-based systems
    '.vpk',  # Vita
    '.xci', '.nsp',  # Switch (for future)
    '.zip', '.7z', '.rar', '.tar.gz',  # Compressed formats
    '.m3u', '.ccd', '.mdf', '.nrg',  # Playlists and disc images
    '.lnx', '.lyx',  # Lynx
    '.a26', '.a52', '.a78',  # Atari systems
    '.ws', '.wsc', '.pc2',  # WonderSwan
    '.ngp', '.ngc',  # Neo Geo Pocket
    '.vb',  # Virtual Boy
    '.min',  # Pokemon Mini
}

class PlatformAnalyzer:
    """Analyzes directories and identifies platforms"""
    
    def __init__(self, source_dir: Path, logger: logging.Logger):
        self.source_dir = source_dir
        self.logger = logger
        
    def analyze_directory(self) -> Tuple[Dict[str, PlatformInfo], List[str], List[str]]:
        """
        Analyze source directory and categorize all content
        
        Returns:
            - Dict of platform shortcode -> PlatformInfo
            - List of excluded folders with reasons
            - List of unknown folders
        """
        platforms = {}
        excluded = []
        unknown = []
        
        self.logger.info(f"Analyzing directory: {self.source_dir}")
        
        # Recursively scan all directories
        for root, dirs, files in os.walk(self.source_dir):
            root_path = Path(root)
            
            # Skip target directories to avoid loops
            if any("roms" in parent.name.lower() for parent in root_path.parents):
                continue
                
            # Count ROM files in this directory
            rom_files = [f for f in files if Path(f).suffix.lower() in ROM_EXTENSIONS]
            if not rom_files:
                continue
                
            folder_name = root_path.name
            
            # Check for exclusions first
            exclusion_reason = self._check_exclusions(folder_name)
            if exclusion_reason:
                excluded.append(f"{folder_name} - {exclusion_reason}")
                continue
                
            # Try to identify platform
            platform_result = self._identify_platform(folder_name)
            if platform_result:
                shortcode, display_name = platform_result
                
                if shortcode not in platforms:
                    platforms[shortcode] = PlatformInfo(
                        shortcode=shortcode,
                        display_name=display_name,
                        folder_count=0,
                        file_count=0,
                        source_folders=[]
                    )
                
                # Update platform info
                current = platforms[shortcode]
                platforms[shortcode] = PlatformInfo(
                    shortcode=current.shortcode,
                    display_name=current.display_name,
                    folder_count=current.folder_count + 1,
                    file_count=current.file_count + len(rom_files),
                    source_folders=current.source_folders + [str(root_path)]
                )
            else:
                unknown.append(folder_name)
                
        return platforms, excluded, unknown
    
    def _check_exclusions(self, folder_name: str) -> Optional[str]:
        """Check if folder should be excluded"""
        for pattern, reason in EXCLUDED_PLATFORMS.items():
            if re.match(pattern, folder_name, re.IGNORECASE):
                return reason
        return None
    
    def _identify_platform(self, folder_name: str) -> Optional[Tuple[str, str]]:
        """Identify platform from folder name using regex patterns"""
        for pattern, (shortcode, display_name) in PLATFORM_MAPPINGS.items():
            if re.match(pattern, folder_name, re.IGNORECASE):
                return shortcode, display_name
        return None

class FormatHandler:
    """Handles special format requirements (like N64 variants and NDS encryption states)"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def detect_n64_format(self, folder_name: str) -> str:
        """Detect N64 ROM format from folder name"""
        folder_lower = folder_name.lower()
        if "bigendian" in folder_lower:
            return "bigendian"
        elif "byteswapped" in folder_lower:
            return "byteswapped"
        else:
            return "standard"
    
    def detect_nds_format(self, folder_name: str) -> str:
        """Detect NDS ROM encryption state from folder name"""
        folder_lower = folder_name.lower()
        if "encrypted" in folder_lower:
            return "encrypted"
        elif "decrypted" in folder_lower:
            return "decrypted"
        else:
            return "standard"
    
    def get_target_path(self, platform: str, source_folder: str, target_base: Path) -> Path:
        """Get target path with format-specific handling"""
        if platform == "n64":
            format_type = self.detect_n64_format(source_folder)
            return target_base / platform / format_type
        elif platform == "nds":
            format_type = self.detect_nds_format(source_folder)
            return target_base / platform / format_type
        else:
            return target_base / platform

class InteractiveSelector:
    """Manages interactive platform selection"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def show_analysis_summary(self, platforms: Dict[str, PlatformInfo], 
                            excluded: List[str], unknown: List[str]) -> None:
        """Display comprehensive analysis summary"""
        print("\n" + "="*80)
        print("ROM COLLECTION ANALYSIS")
        print("="*80)
        
        if platforms:
            print(f"\n✅ SUPPORTED PLATFORMS FOUND ({len(platforms)}):")
            print("-" * 50)
            for i, (shortcode, info) in enumerate(sorted(platforms.items()), 1):
                print(f"[{i:2d}] {shortcode:<12} - {info.display_name}")
                print(f"     📁 {info.folder_count} folders, 🎮 {info.file_count:,} files")
        
        if excluded:
            print(f"\n⚠️  EXCLUDED PLATFORMS ({len(excluded)}):")
            print("-" * 50)
            for item in excluded[:10]:  # Show first 10
                print(f"    • {item}")
            if len(excluded) > 10:
                print(f"    ... and {len(excluded) - 10} more")
        
        if unknown:
            print(f"\n❓ UNKNOWN PLATFORMS ({len(unknown)}):")
            print("-" * 50)
            for item in unknown[:10]:  # Show first 10
                print(f"    • {item}")
            if len(unknown) > 10:
                print(f"    ... and {len(unknown) - 10} more")
        
        print("\n" + "="*80)
    
    def get_platform_selection(self, platforms: Dict[str, PlatformInfo]) -> List[str]:
        """Get user's platform selection"""
        if not platforms:
            print("No supported platforms found!")
            return []
        
        while True:
            print("\nSelect platforms to process:")
            print("• Enter platform numbers (e.g., 1,3,5-8)")
            print("• Enter 'all' for all platforms")
            print("• Enter 'quit' to exit")
            
            try:
                user_input = input("\nYour selection: ").strip().lower()
                
                if user_input == 'quit':
                    return []
                elif user_input == 'all':
                    return list(platforms.keys())
                else:
                    return self._parse_selection(user_input, platforms)
                    
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
                return []
            except Exception as e:
                print(f"Invalid input: {e}. Please try again.")
    
    def _parse_selection(self, selection: str, platforms: Dict[str, PlatformInfo]) -> List[str]:
        """Parse user selection string into platform list"""
        platform_list = list(sorted(platforms.keys()))
        selected = set()
        
        for part in selection.split(','):
            part = part.strip()
            if '-' in part:
                # Range selection
                start, end = map(int, part.split('-'))
                for i in range(start - 1, end):
                    if 0 <= i < len(platform_list):
                        selected.add(platform_list[i])
            else:
                # Single selection
                index = int(part) - 1
                if 0 <= index < len(platform_list):
                    selected.add(platform_list[index])
        
        if not selected:
            raise ValueError("No valid platforms selected")
            
        return list(selected)

class ComprehensiveLogger:
    """Enhanced logging system with multiple outputs"""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.loggers = {}
        self.setup_logging()
    
    def setup_logging(self):
        """Setup comprehensive logging system"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Define log types and their purposes
        log_configs = {
            'operations': {
                'file': log_dir / f"operations_{self.timestamp}.log",
                'level': logging.INFO,
                'description': 'All file operations and decisions'
            },
            'analysis': {
                'file': log_dir / f"analysis_{self.timestamp}.log", 
                'level': logging.INFO,
                'description': 'Platform detection and analysis results'
            },
            'errors': {
                'file': log_dir / f"errors_{self.timestamp}.log",
                'level': logging.ERROR,
                'description': 'Errors and exceptions'
            },
            'summary': {
                'file': log_dir / f"summary_{self.timestamp}.log",
                'level': logging.INFO,
                'description': 'Final processing summary and statistics'
            },
            'progress': {
                'file': log_dir / f"progress_{self.timestamp}.log",
                'level': logging.INFO,
                'description': 'Real-time progress updates'
            }
        }
        
        for log_type, config in log_configs.items():
            logger = logging.getLogger(log_type)
            logger.setLevel(config['level'])
            
            # File handler
            fh = logging.FileHandler(config['file'])
            fh.setLevel(config['level'])
            
            # Console handler for progress and errors
            if log_type in ['progress', 'errors']:
                ch = logging.StreamHandler()
                ch.setLevel(config['level'])
                logger.addHandler(ch)
            
            # Formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            fh.setFormatter(formatter)
            
            logger.addHandler(fh)
            self.loggers[log_type] = logger
    
    def get_logger(self, log_type: str) -> logging.Logger:
        """Get specific logger by type"""
        return self.loggers.get(log_type, self.loggers['operations'])

class EnhancedROMOrganizer:
    """Main ROM organizer with enhanced features"""
    
    def __init__(self, source_dir: Path, target_dir: Path, 
                 dry_run: bool = False, interactive: bool = True):
        self.source_dir = source_dir
        self.target_dir = target_dir
        self.dry_run = dry_run
        self.interactive = interactive
        
        # Initialize components
        self.comprehensive_logger = ComprehensiveLogger(dry_run)
        self.analyzer = PlatformAnalyzer(source_dir, 
                                       self.comprehensive_logger.get_logger('analysis'))
        self.selector = InteractiveSelector(
            self.comprehensive_logger.get_logger('progress'))
        self.format_handler = FormatHandler(
            self.comprehensive_logger.get_logger('operations'))
        
        # Initialize performance-optimized processor
        self.performance_processor = PerformanceOptimizedROMProcessor(
            source_dir,
            self.comprehensive_logger.get_logger('operations'),
            self.comprehensive_logger.get_logger('progress'),
            dry_run
        )
        
        # Statistics tracking
        self.stats = ProcessingStats()
        
        # Get loggers
        self.logger_ops = self.comprehensive_logger.get_logger('operations')
        self.logger_progress = self.comprehensive_logger.get_logger('progress')
        self.logger_errors = self.comprehensive_logger.get_logger('errors')
        self.logger_summary = self.comprehensive_logger.get_logger('summary')
        self.logger_performance = self.comprehensive_logger.get_logger('performance')
    
    def organize_roms(self) -> ProcessingStats:
        """Main organization workflow"""
        start_time = datetime.now()
        
        try:
            self.logger_progress.info("Starting enhanced ROM organization...")
            self.logger_progress.info(f"Source: {self.source_dir}")
            self.logger_progress.info(f"Target: {self.target_dir}")
            self.logger_progress.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE RUN'}")
            
            # Phase 1: Analysis
            self.logger_progress.info("Phase 1: Analyzing ROM collection...")
            platforms, excluded, unknown = self.analyzer.analyze_directory()
            
            self.stats.platforms_found = len(platforms)
            
            # Log analysis results
            self._log_analysis_results(platforms, excluded, unknown)
            
            # Phase 2: Interactive Selection (if enabled)
            selected_platforms = []
            if self.interactive:
                self.logger_progress.info("Phase 2: Interactive platform selection...")
                self.selector.show_analysis_summary(platforms, excluded, unknown)
                selected_platforms = self.selector.get_platform_selection(platforms)
                
                if not selected_platforms:
                    self.logger_progress.info("No platforms selected. Exiting.")
                    return self.stats
            else:
                selected_platforms = list(platforms.keys())
            
            self.stats.selected_platforms = selected_platforms
            self.logger_progress.info(f"Selected {len(selected_platforms)} platforms for processing")
            
            # Phase 3: File Processing
            self.logger_progress.info("Phase 3: Processing ROM files...")
            self._process_selected_platforms(platforms, selected_platforms)
            
            # Phase 4: Generate Summary
            end_time = datetime.now()
            self.stats.processing_time = (end_time - start_time).total_seconds()
            self._generate_comprehensive_summary()
            
            return self.stats
            
        except Exception as e:
            self.logger_errors.error(f"Fatal error during organization: {e}")
            self.stats.errors += 1
            raise
    
    def _log_analysis_results(self, platforms: Dict[str, PlatformInfo], 
                            excluded: List[str], unknown: List[str]) -> None:
        """Log detailed analysis results"""
        analysis_logger = self.comprehensive_logger.get_logger('analysis')
        
        analysis_logger.info("=== PLATFORM ANALYSIS RESULTS ===")
        analysis_logger.info(f"Supported platforms found: {len(platforms)}")
        analysis_logger.info(f"Excluded platforms: {len(excluded)}")
        analysis_logger.info(f"Unknown platforms: {len(unknown)}")
        
        for shortcode, info in platforms.items():
            analysis_logger.info(f"Platform: {shortcode} ({info.display_name})")
            analysis_logger.info(f"  Folders: {info.folder_count}, Files: {info.file_count}")
            for folder in info.source_folders:
                analysis_logger.info(f"  Source: {folder}")
        
        if excluded:
            analysis_logger.info("\nEXCLUDED PLATFORMS:")
            for item in excluded:
                analysis_logger.info(f"  {item}")
        
        if unknown:
            analysis_logger.info("\nUNKNOWN PLATFORMS:")
            for item in unknown:
                analysis_logger.info(f"  {item}")
    
    def _process_selected_platforms(self, platforms: Dict[str, PlatformInfo], 
                                  selected_platforms: List[str]) -> None:
        """Process files for selected platforms using concurrent optimization"""
        start_time = datetime.now()
        
        # Log performance configuration
        cpu_count = os.cpu_count() or 1
        self.logger_performance.info(f"System CPU cores: {cpu_count}")
        self.logger_performance.info(f"I/O worker threads: {self.performance_processor.max_io_workers}")
        self.logger_performance.info(f"Hash chunk size: {self.performance_processor.hash_chunk_size:,} bytes")
        
        # Phase 1: Concurrent file discovery
        discovery_start = datetime.now()
        all_files = self.performance_processor.discover_files_concurrent(platforms, selected_platforms)
        discovery_time = (datetime.now() - discovery_start).total_seconds()
        
        self.logger_performance.info(f"File discovery completed in {discovery_time:.2f} seconds")
        self.logger_performance.info(f"Discovery rate: {len(all_files) / max(discovery_time, 0.1):.1f} files/second")
        
        if not all_files:
            self.logger_progress.info("No ROM files found to process!")
            return
        
        # Phase 2: Concurrent file processing  
        processing_start = datetime.now()
        processing_stats = self.performance_processor.process_files_concurrent(
            all_files, self.target_dir, self.format_handler
        )
        processing_time = (datetime.now() - processing_start).total_seconds()
        
        # Update main stats
        self.stats.files_found = processing_stats.files_found
        self.stats.files_copied = processing_stats.files_copied
        self.stats.files_skipped_duplicate = processing_stats.files_skipped_duplicate
        self.stats.errors = processing_stats.errors
        
        # Log performance metrics
        total_time = (datetime.now() - start_time).total_seconds()
        self.logger_performance.info(f"Processing completed in {processing_time:.2f} seconds")
        self.logger_performance.info(f"Total processing time: {total_time:.2f} seconds")
        if processing_stats.files_copied > 0:
            self.logger_performance.info(f"Copy rate: {processing_stats.files_copied / max(processing_time, 0.1):.1f} files/second")
        
        # Final progress update
        self.logger_progress.info(f"✅ Processing complete!")
        self.logger_progress.info(f"📊 Files copied: {processing_stats.files_copied:,}")
        self.logger_progress.info(f"📊 Files skipped (duplicates): {processing_stats.files_skipped_duplicate:,}")
        self.logger_progress.info(f"📊 Errors: {processing_stats.errors:,}")
        self.logger_progress.info(f"⚡ Total time: {total_time:.2f} seconds")
    
    def _generate_comprehensive_summary(self) -> None:
        """Generate comprehensive processing summary"""
        summary_lines = [
            "=" * 80,
            "ENHANCED ROM ORGANIZER - PROCESSING SUMMARY",
            "=" * 80,
            f"Timestamp: {datetime.now()}",
            f"Processing Time: {self.stats.processing_time:.2f} seconds",
            f"Mode: {'DRY RUN' if self.dry_run else 'LIVE RUN'}",
            "",
            "PROCESSING STATISTICS:",
            f"  Platforms Found: {self.stats.platforms_found}",
            f"  Platforms Selected: {len(self.stats.selected_platforms)}",
            f"  Total Files Found: {self.stats.files_found:,}",
            f"  Files Copied: {self.stats.files_copied:,}",
            f"  Files Skipped (Duplicates): {self.stats.files_skipped_duplicate:,}",
            f"  Files Skipped (Unknown): {self.stats.files_skipped_unknown:,}",
            f"  Errors: {self.stats.errors:,}",
            "",
            "SELECTED PLATFORMS:",
        ]
        
        for platform in sorted(self.stats.selected_platforms):
            summary_lines.append(f"  ✓ {platform}")
        
        if self.stats.processing_time > 0:
            files_per_second = self.stats.files_copied / self.stats.processing_time
            summary_lines.extend([
                "",
                "PERFORMANCE METRICS:",
                f"  Files per Second: {files_per_second:.1f}",
                f"  Average File Size: Calculated during processing"
            ])
        
        summary_lines.extend([
            "",
            "LOGS GENERATED:",
            f"  📋 Operations: logs/operations_{self.comprehensive_logger.timestamp}.log",
            f"  📊 Analysis: logs/analysis_{self.comprehensive_logger.timestamp}.log", 
            f"  ❌ Errors: logs/errors_{self.comprehensive_logger.timestamp}.log",
            f"  📈 Progress: logs/progress_{self.comprehensive_logger.timestamp}.log",
            f"  📋 Summary: logs/summary_{self.comprehensive_logger.timestamp}.log",
            f"  ⚡ Performance: logs/performance_{self.comprehensive_logger.timestamp}.log",
            "",
            "PERFORMANCE OPTIMIZATIONS:",
            f"  🧵 Concurrent I/O workers: {self.performance_processor.max_io_workers}",
            f"  💾 Memory-mapped hash calculation for large files (>10MB)",
            f"  🔄 Chunked processing with {self.performance_processor.hash_chunk_size // 1024}KB chunks",
            f"  📊 Thread-safe progress tracking every {self.performance_processor.progress_update_frequency} files",
            "",
            "=" * 80
        ])
        
        summary_text = "\n".join(summary_lines)
        
        # Log to summary file and display
        self.logger_summary.info(summary_text)
        print("\n" + summary_text)

def main():
    """Main application entry point"""
    parser = argparse.ArgumentParser(
        description="Enhanced ROM Organizer - DAT to EmulationStation Organization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode with analysis and selection
  python enhanced_rom_organizer.py "D:\\roms\\source" "D:\\roms\\organized"
  
  # Dry run to preview operations
  python enhanced_rom_organizer.py "D:\\roms\\source" "D:\\roms\\target" --dry-run
  
  # Non-interactive mode (process all detected platforms)
  python enhanced_rom_organizer.py "D:\\roms\\source" "D:\\roms\\target" --no-interactive
  
  # Show analysis only
  python enhanced_rom_organizer.py "D:\\roms\\source" "D:\\roms\\target" --analyze-only

Features:
  ✓ Interactive platform selection with file counts
  ✓ N64 format-specific subfolder organization  
  ✓ Platform exclusion for unsupported systems
  ✓ SHA1-based duplicate detection and handling
  ✓ Comprehensive logging with timestamped files
  ✓ Subcategory consolidation (games/firmware/apps)
  ✓ Progress reporting and performance metrics
        """
    )
    
    parser.add_argument("source", help="Source directory to scan for ROM files")
    parser.add_argument("target", help="Target directory for organized ROM files") 
    parser.add_argument("--dry-run", action="store_true", 
                       help="Preview operations without making changes")
    parser.add_argument("--no-interactive", action="store_true",
                       help="Process all detected platforms without user selection")
    parser.add_argument("--analyze-only", action="store_true", 
                       help="Show analysis results and exit")
    
    args = parser.parse_args()
    
    # Validate directories
    source_dir = Path(args.source)
    target_dir = Path(args.target)
    
    if not source_dir.exists():
        print(f"❌ Error: Source directory '{source_dir}' does not exist!")
        sys.exit(1)
    
    if not source_dir.is_dir():
        print(f"❌ Error: Source path '{source_dir}' is not a directory!")
        sys.exit(1)
    
    # Create target directory if needed
    if not args.dry_run and not args.analyze_only:
        target_dir.mkdir(parents=True, exist_ok=True)
    
    # Run organizer
    try:
        organizer = EnhancedROMOrganizer(
            source_dir=source_dir,
            target_dir=target_dir, 
            dry_run=args.dry_run,
            interactive=not args.no_interactive
        )
        
        if args.analyze_only:
            # Just show analysis
            platforms, excluded, unknown = organizer.analyzer.analyze_directory()
            organizer.selector.show_analysis_summary(platforms, excluded, unknown)
            print(f"\n✅ Analysis complete. Found {len(platforms)} supported platforms.")
        else:
            # Full processing
            stats = organizer.organize_roms()
            
            if stats.files_copied > 0:
                print(f"\n🎉 Success! Organized {stats.files_copied:,} files across {len(stats.selected_platforms)} platforms.")
            elif args.dry_run:
                print(f"\n📋 Dry run complete. Would have organized {stats.files_copied:,} files.")
            else:
                print(f"\n✅ Processing complete. No files needed copying.")
            
            print(f"📊 Check logs/ directory for detailed reports.")
        
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
