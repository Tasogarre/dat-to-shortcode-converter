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
from good_pattern_handler import SpecializedPatternProcessor
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue
from threading import Lock
from subcategory_handler import SubcategoryProcessor
import time
from functools import wraps
from collections import defaultdict


class PerformanceMonitor:
    """
    Performance monitoring for pattern matching operations
    Based on pyinstrument best practices for profiling function calls
    """
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.timing_data = defaultdict(list)
        self.pattern_hit_counts = defaultdict(int)
        self.cache_hits = defaultdict(int)
        self.cache_misses = defaultdict(int)
        
    def time_function(self, func_name: str):
        """Decorator to time function execution"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                result = func(*args, **kwargs)
                end_time = time.perf_counter()
                
                duration = end_time - start_time
                self.timing_data[func_name].append(duration)
                
                # Log slow operations (> 10ms)
                if duration > 0.01:
                    self.logger.debug(f"Slow {func_name}: {duration:.4f}s")
                
                return result
            return wrapper
        return decorator
    
    def record_pattern_hit(self, pattern_type: str, pattern: str = ""):
        """Record successful pattern match"""
        key = f"{pattern_type}:{pattern}" if pattern else pattern_type
        self.pattern_hit_counts[key] += 1
    
    def record_cache_hit(self, cache_type: str):
        """Record cache hit"""
        self.cache_hits[cache_type] += 1
    
    def record_cache_miss(self, cache_type: str):
        """Record cache miss"""
        self.cache_misses[cache_type] += 1
    
    def get_performance_stats(self) -> Dict[str, any]:
        """Get comprehensive performance statistics"""
        stats = {
            'timing_summary': {},
            'pattern_efficiency': {},
            'cache_efficiency': {}
        }
        
        # Timing statistics
        for func_name, times in self.timing_data.items():
            if times:
                stats['timing_summary'][func_name] = {
                    'total_calls': len(times),
                    'total_time': sum(times),
                    'avg_time': sum(times) / len(times),
                    'min_time': min(times),
                    'max_time': max(times),
                    'p95_time': sorted(times)[int(len(times) * 0.95)] if len(times) > 20 else max(times)
                }
        
        # Pattern hit efficiency
        total_hits = sum(self.pattern_hit_counts.values())
        for pattern, hits in self.pattern_hit_counts.items():
            if total_hits > 0:
                stats['pattern_efficiency'][pattern] = {
                    'hits': hits,
                    'percentage': (hits / total_hits) * 100
                }
        
        # Cache efficiency
        for cache_type in set(list(self.cache_hits.keys()) + list(self.cache_misses.keys())):
            hits = self.cache_hits[cache_type]
            misses = self.cache_misses[cache_type]
            total = hits + misses
            if total > 0:
                stats['cache_efficiency'][cache_type] = {
                    'hits': hits,
                    'misses': misses,
                    'hit_rate': (hits / total) * 100
                }
        
        return stats
    
    def log_performance_summary(self):
        """Log performance summary"""
        stats = self.get_performance_stats()
        
        self.logger.info("=== PERFORMANCE SUMMARY ===")
        
        # Function timing
        if stats['timing_summary']:
            self.logger.info("Function Performance:")
            for func_name, data in stats['timing_summary'].items():
                self.logger.info(f"  {func_name}: {data['total_calls']} calls, avg {data['avg_time']*1000:.2f}ms, total {data['total_time']:.3f}s")
        
        # Pattern efficiency
        if stats['pattern_efficiency']:
            self.logger.info("Top Pattern Matches:")
            sorted_patterns = sorted(stats['pattern_efficiency'].items(), 
                                   key=lambda x: x[1]['hits'], reverse=True)
            for pattern, data in sorted_patterns[:10]:  # Top 10
                self.logger.info(f"  {pattern}: {data['hits']} hits ({data['percentage']:.1f}%)")
        
        # Cache efficiency
        if stats['cache_efficiency']:
            self.logger.info("Cache Performance:")
            for cache_type, data in stats['cache_efficiency'].items():
                self.logger.info(f"  {cache_type}: {data['hit_rate']:.1f}% hit rate ({data['hits']}/{data['hits'] + data['misses']})")


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
    # Nintendo Systems - Enhanced patterns for consolidation (most specific first)
    r"Nintendo.*Super Nintendo.*": ("snes", "Super Nintendo Entertainment System"),
    r"Nintendo.*Super Famicom.*": ("snes", "Super Nintendo Entertainment System"),
    r"Nintendo.*Nintendo Entertainment System.*": ("nes", "Nintendo Entertainment System"),
    r"Nintendo.*Famicom.*Entertainment System.*": ("nes", "Nintendo Entertainment System"),
    r"Nintendo.*Famicom(?!\s+(Disk|&)).*": ("nes", "Nintendo Entertainment System"),
    r"Nintendo.*Family Computer(?!\s+Disk).*": ("nes", "Nintendo Entertainment System"),
    r"Nintendo.*Family Computer.*Disk.*System.*": ("fds", "Famicom Disk System"),
    r"Nintendo.*Famicom.*Disk.*System.*": ("fds", "Famicom Disk System"),
    r"Nintendo.*Game Boy(?!\s+(Color|Advance)).*": ("gb", "Game Boy"),
    r"Nintendo.*Game Boy Color.*": ("gbc", "Game Boy Color"),
    r"Nintendo.*Game Boy Advance.*": ("gba", "Game Boy Advance"),
    r"Nintendo.*Nintendo 64DD.*": ("n64dd", "Nintendo 64DD"),
    r"Nintendo.*Nintendo 64.*": ("n64", "Nintendo 64"),
    r"Nintendo.*GameCube.*": ("gc", "GameCube"),
    r"Nintendo.*Wii(?!\s+U).*": ("wii", "Wii"),
    r"Nintendo.*Wii U.*": ("wiiu", "Wii U"),
    r"Nintendo.*Nintendo DS(?!i).*": ("nds", "Nintendo DS"),
    r"Nintendo.*Nintendo DSi.*": ("nds", "Nintendo DS"),  # Consolidate DSi into DS
    r"NDS.*": ("nds", "Nintendo DS"),  # General NDS collections
    r".*Nintendo DS.*": ("nds", "Nintendo DS"),  # General Nintendo DS collections
    # General Game Boy patterns
    r".*Game Boy(?!\s+(Color|Advance)).*": ("gb", "Game Boy"),
    r".*GB(?!\s*C).*": ("gb", "Game Boy"),  # GB but not GBC
    r"Nintendo.*Nintendo 3DS.*": ("n3ds", "Nintendo 3DS"),
    r"Nintendo.*Virtual Boy.*": ("virtualboy", "Virtual Boy"),
    r"Nintendo.*Pokemon Mini.*": ("pokemini", "Pokemon Mini"),
    
    # NEW: Nintendo patterns for preprocessed names (Phase 2 enhancement)
    r"^Nintendo 64$": ("n64", "Nintendo 64"),
    r"^Nintendo Famicom Disk System$": ("fds", "Famicom Disk System"),
    r"^Nintendo Game Boy$": ("gb", "Game Boy"),
    r"^Nintendo Game Boy Color$": ("gbc", "Game Boy Color"),
    r"^Nintendo Game Boy Advance$": ("gba", "Game Boy Advance"),
    r"^Nintendo Pokemon Mini$": ("pokemini", "Pokemon Mini"),
    r"^Nintendo Virtual Boy$": ("virtualboy", "Virtual Boy"),
    r"^Nintendo DS$": ("nds", "Nintendo DS"),
    r"^Nintendo Super Famicom & Super Entertainment System$": ("snes", "Super Nintendo Entertainment System"),
    r"^Nintendo Famicom & Entertainment System$": ("nes", "Nintendo Entertainment System"),
    
    # Sega Systems - Keep genesis and megadrive separate as requested
    r"Sega.*Master System.*": ("mastersystem", "Sega Master System"),
    r"Sega.*Mark III.*": ("mastersystem", "Sega Master System"),
    r"Sega.*Mega Drive.*": ("genesis", "Sega Genesis"),  # Consolidate Mega Drive with Genesis
    r"Sega.*Genesis.*": ("genesis", "Sega Genesis"),
    r"Sega.*Game Gear.*": ("gamegear", "Sega Game Gear"),
    r"Sega.*32X.*": ("sega32x", "Sega 32X"),
    r"Sega.*Mega.?CD.*": ("segacd", "Sega CD"),
    # General Genesis/Mega Drive patterns
    r".*Genesis.*": ("genesis", "Sega Genesis"),
    r".*Mega Drive.*": ("genesis", "Sega Genesis"),
    r"Sega.*Sega CD.*": ("segacd", "Sega CD"),
    r"Sega.*Saturn.*": ("saturn", "Sega Saturn"),
    r"Sega.*Dreamcast.*": ("dreamcast", "Sega Dreamcast"),
    r"Sega.*SG-1000.*": ("sg1000", "Sega SG-1000"),  # Note: Not in EmulationStation list
    
    # NEW: Sega patterns for preprocessed names (Phase 2 enhancement)
    r"^Sega 32X$": ("sega32x", "Sega 32X"),
    r"^Sega Dreamcast$": ("dreamcast", "Sega Dreamcast"),
    r"^Sega Game Gear$": ("gamegear", "Sega Game Gear"),
    r"^Sega Mark III & Master System$": ("mastersystem", "Sega Master System"),
    r"^Sega Mega Drive & Genesis$": ("megadrive", "Sega Mega Drive"),
    r"^Sega Mega-CD & Sega CD$": ("segacd", "Sega CD"),
    r"^Sega Saturn$": ("saturn", "Sega Saturn"),
    r"^Sega Game 1000$": ("sg1000", "Sega SG-1000"),
    
    # Sony Systems
    r"Sony.*PlayStation(?!\s+(2|3|4|Portable|Vita)).*": ("psx", "PlayStation"),
    r"Sony.*PlayStation 2.*": ("ps2", "PlayStation 2"),
    r"Sony.*PlayStation 3.*": ("ps3", "PlayStation 3"),
    r"Sony.*PlayStation 4.*": ("ps4", "PlayStation 4"),
    r"Sony.*PlayStation Portable.*": ("psp", "PlayStation Portable"),
    r"Sony.*PlayStation Vita.*": ("psvita", "PlayStation Vita"),
    # General PlayStation patterns
    r".*PlayStation 1.*": ("psx", "PlayStation"),
    r".*PS1.*": ("psx", "PlayStation"),
    r".*PSX.*": ("psx", "PlayStation"),
    
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
    
    # NEW: Atari patterns for preprocessed names (Phase 2 enhancement)  
    r"^Atari 8bit$": ("atari800", "Atari 8-bit"),
    r"^Atari Lynx$": ("atarilynx", "Atari Lynx"),
    r"^Atari ST$": ("atarist", "Atari ST"),
    r"^Atari 2600 & VCS$": ("atari2600", "Atari 2600"),
    r"^Atari 5200$": ("atari5200", "Atari 5200"),
    r"^Atari 7800$": ("atari7800", "Atari 7800"),
    
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
    
    # NEW: Additional high-impact patterns for preprocessed names (Phase 2 enhancement)
    r"^3DO Interactive Multiplayer$": ("3do", "3DO Interactive Multiplayer"),
    r".*3DO.*": ("3do", "3DO Interactive Multiplayer"),
    r"^Bandai WonderSwan Color$": ("wonderswancolor", "Bandai WonderSwan Color"),
    r"^Bandai WonderSwan$": ("wonderswan", "Bandai WonderSwan"),
    r".*WonderSwan Color": ("wonderswancolor", "Bandai WonderSwan Color"),
    r".*WonderSwan": ("wonderswan", "Bandai WonderSwan"),
    r"^Coleco ColecoVision$": ("coleco", "ColecoVision"),
    r".*ColecoVision": ("coleco", "ColecoVision"),
    r"^GCE Vectrex$": ("vectrex", "GCE Vectrex"),
    r".*Vectrex": ("vectrex", "GCE Vectrex"),
    r"^Magnavox Odyssey": ("odyssey2", "Magnavox Odyssey 2"),
    r".*Odyssey.*": ("odyssey2", "Magnavox Odyssey 2"),
    r"^Mattel Intellivision$": ("intellivision", "Mattel Intellivision"),
    r".*Intellivision": ("intellivision", "Mattel Intellivision"),
    r"^NEC PC-Engine & TurboGrafx-16$": ("pcengine", "PC Engine"),
    r"^NEC SuperGrafx$": ("supergrafx", "PC Engine SuperGrafx"),
    r"^NEC PC-8801$": ("pc98", "NEC PC-98"),
    r"^SNK Neo-Geo CD$": ("neogeocd", "Neo Geo CD"),
    r"^SNK Neo-Geo Pocket Color$": ("ngpc", "Neo Geo Pocket Color"),
    r"^SNK Neo-Geo Pocket$": ("ngp", "Neo Geo Pocket"),
    r".*Neo-Geo CD": ("neogeocd", "Neo Geo CD"),
    r".*Neo-Geo Pocket Color": ("ngpc", "Neo Geo Pocket Color"),
    r".*Neo-Geo Pocket": ("ngp", "Neo Geo Pocket"),
    r"^Sony PlayStation$": ("psx", "PlayStation"),
    r"^Sony PlayStation 2$": ("ps2", "PlayStation 2"),
    r"^Sony - PlayStation Portable$": ("psp", "PlayStation Portable"),
    r"^Watara Supervision$": ("supervision", "Watara Supervision"),
    r".*Supervision": ("supervision", "Watara Supervision"),
    r"^Commodore Amiga$": ("amiga", "Commodore Amiga"),
    r".*Amiga": ("amiga", "Commodore Amiga"),
    r"^Sharp X68000$": ("x68000", "Sharp X68000"),
    r"^Sharp X1$": ("x1", "Sharp X1"),
    r".*X68000": ("x68000", "Sharp X68000"),
    r"^Tandy TRS-80.*Model I$": ("trs80", "TRS-80"),
    r"^Tandy TRS-80.*Model III$": ("trs80", "TRS-80"),
    r"^Tandy TRS-80.*Color Computer$": ("coco", "TRS-80 Color Computer"),
    r"^Tiger Gizmondo$": ("gizmondo", "Tiger Gizmondo"),
    r"^Sinclair ZX Spectrum$": ("zxspectrum", "ZX Spectrum"),
    r"^Pokitto$": ("pokitto", "Pokitto"),
    r"Pokitto.*": ("pokitto", "Pokitto"),
    r"^Dragon": ("dragon32", "Dragon Data"),
    r"Dragon.*": ("dragon32", "Dragon Data"),
    r"^Tsukuda Othello Multivision$": ("othello", "Othello Multivision"),
    
    # Arcade Systems
    r".*Arcade.*": ("arcade", "Arcade"),
    r"Neo.?Geo(?!\s+Pocket).*": ("neogeo", "Neo Geo"),
    r"FinalBurn.*Arcade.*": ("arcade", "Arcade"),
    r"MAME.*": ("arcade", "Arcade (MAME)"),
    r".*Atomiswave.*": ("atomiswave", "Atomiswave Arcade"),
    r"^Atomiswave$": ("atomiswave", "Atomiswave Arcade"),
    r".*Cannonball.*": ("cannonball", "Cannonball (OutRun Engine)"),
    r"^Cannonball$": ("cannonball", "Cannonball (OutRun Engine)"),
    
    # GoodTools patterns
    r"GoodNES.*": ("nes", "Nintendo Entertainment System"),
    r"GoodSNES.*": ("snes", "Super Nintendo Entertainment System"),
    r"GoodN64.*": ("n64", "Nintendo 64"),
    r"N64.*": ("n64", "Nintendo 64"),  # General N64 collections
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
    
    # NEW: Enhanced Good tools and FinalBurn Neo patterns (Phase 2 enhancement)
    r"GoodGBC.*": ("gbc", "Game Boy Color"),
    r"GoodGB.*": ("gb", "Game Boy"),  
    r"GoodGBA.*": ("gba", "Game Boy Advance"),
    r"GoodA26.*": ("atari2600", "Atari 2600"),
    r"GoodA78.*": ("atari7800", "Atari 7800"),
    r"GoodA52.*": ("atari5200", "Atari 5200"),
    r"GoodCOL.*": ("coleco", "ColecoVision"),
    r"GoodINTV.*": ("intellivision", "Mattel Intellivision"),
    r"Good.*": ("unknown", "Unknown Good Tool Collection"),  # Fallback for unmatched Good tools
    
    # FinalBurn Neo patterns
    r"FinalBurn Neo - NES Games": ("nes", "Nintendo Entertainment System"),
    r"FinalBurn Neo - SNES Games": ("snes", "Super Nintendo Entertainment System"),
    r"FinalBurn Neo - Genesis Games": ("genesis", "Sega Genesis"),
    r"FinalBurn Neo - Master System Games": ("mastersystem", "Sega Master System"),
    r"FinalBurn Neo - Game Gear Games": ("gamegear", "Sega Game Gear"),
    r"FinalBurn Neo - PC Engine Games": ("pcengine", "PC Engine"),
    r"FinalBurn Neo - Neo Geo Games": ("neogeo", "Neo Geo"),
    r"FinalBurn Neo - CPS Games": ("arcade", "Arcade (CPS)"),
    r"FinalBurn Neo - .*": ("arcade", "Arcade (FinalBurn Neo)"),  # Fallback for other FBN patterns
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
    # Nintendo Systems
    '.nes', '.fds', '.nsf', '.unf', '.nez',  # NES/Famicom
    '.sfc', '.smc', '.swc', '.fig', '.bsx', '.st',  # SNES + Satellaview/Sufami Turbo
    '.gb', '.gbc', '.gba', '.sgb',  # Game Boy systems
    '.n64', '.v64', '.z64', '.n64dd', '.rom',  # N64 (includes 64DD)
    '.gcm', '.iso', '.rvz', '.ciso', '.wbfs', '.wad',  # Nintendo disc systems
    '.nds', '.nde', '.srl',  # DS
    '.3ds', '.cia', '.3dsx',  # 3DS
    '.xci', '.nsp',  # Switch
    
    # Sega Systems
    '.sms', '.gg', '.sg', '.sgd',  # Sega 8-bit (Master System, Game Gear, SG-1000)
    '.md', '.gen', '.bin', '.smd',  # Genesis/Mega Drive
    '.32x',  # 32X
    
    # Sony Systems
    '.pbp', '.cso', '.ecm', '.sbi',  # PlayStation formats
    '.vpk',  # Vita
    
    # Atari Systems
    '.a26', '.a52', '.a78',  # Atari 2600/5200/7800
    '.lnx', '.lyx',  # Lynx
    '.jag', '.j64',  # Jaguar
    
    # Other Handheld Systems
    '.ws', '.wsc', '.pc2',  # WonderSwan
    '.ngp', '.ngc',  # Neo Geo Pocket
    '.sv',  # Supervision
    '.vb',  # Virtual Boy
    '.min',  # Pokemon Mini
    
    # Computer Systems
    '.pce',  # PC Engine/TurboGrafx
    '.int',  # Intellivision
    '.col',  # ColecoVision
    '.d64', '.g64', '.t64', '.prg', '.crt',  # Commodore 64
    '.adf', '.adz', '.dms', '.hdf',  # Amiga
    '.cas', '.dsk',  # MSX and other computer systems
    
    # CD-based and Disc Systems
    '.cue', '.chd', '.mds', '.ccd', '.sub', '.img',  # Disc images
    '.m3u', '.mdf', '.nrg',  # Playlists and disc images
    
    # Compressed Formats
    '.zip', '.7z', '.rar', '.tar.gz', '.gz', '.bz2',  # Compressed archives
}

class RegionalPreferenceEngine:
    """Handles regional consolidation vs separation logic"""
    
    def __init__(self, regional_mode: str = "consolidated"):
        self.regional_mode = regional_mode
        
        # Platforms that are always kept separate regardless of mode
        self.always_separate = {
            "fds": [r".*Family Computer.*Disk.*System.*", r".*Famicom.*Disk.*System.*"],
            "n64dd": [r".*Nintendo 64DD.*"],
            "segacd": [r".*Sega.*CD.*", r".*Mega.?CD.*"],
            "pcenginecd": [r".*PC Engine.*CD.*"],
            "turbografxcd": [r".*TurboGrafx.*CD.*"],
        }
        
        # Regional mapping rules
        self.regional_mappings = {
            "consolidated": {
                # Current mappings already consolidate these properly
                "nes": ["nes", "famicom"],
                "snes": ["snes", "sfc", "superfamicom"],
                "pcengine": ["pcengine", "turbografx", "tg16"],
            },
            "regional": {
                # Separate mappings for regional mode (most specific first)
                "snes": [r".*Super Nintendo.*"],
                "sfc": [r".*Super Famicom.*"],  
                "nes": [r".*Nintendo Entertainment System.*"],
                "famicom": [r".*Famicom(?!\s+(Disk|&)).*", r".*Family Computer(?!\s+Disk).*"],
                "pcengine": [r".*PC Engine(?!\s+CD).*"],
                "turbografx": [r".*TurboGrafx.*(?!\s+CD).*"],
            }
        }
    
    def get_target_platform(self, folder_name: str, detected_platform: str) -> str:
        """Determine final target platform based on regional preferences"""
        
        # Always separate significant variants first
        for platform, patterns in self.always_separate.items():
            for pattern in patterns:
                if re.search(pattern, folder_name, re.IGNORECASE):
                    return platform
        
        # Apply regional preference logic
        if self.regional_mode == "regional":
            return self._apply_regional_separation(folder_name, detected_platform)
        
        # For consolidated mode, use existing detection (already consolidates)
        return detected_platform
    
    def _apply_regional_separation(self, folder_name: str, detected_platform: str) -> str:
        """Apply regional separation rules"""
        for platform, patterns in self.regional_mappings["regional"].items():
            for pattern in patterns:
                if re.search(pattern, folder_name, re.IGNORECASE):
                    return platform
        
        return detected_platform
    
    def get_display_name(self, platform: str) -> str:
        """Get appropriate display name for platform based on regional mode"""
        display_mapping = {
            # Complete mapping from all PLATFORM_MAPPINGS entries
            "3do": "3DO Interactive Multiplayer",
            "amiga": "Commodore Amiga",
            "amstradcpc": "Amstrad CPC",
            "apple2": "Apple II",
            "arcade": "Arcade (FinalBurn Neo)",
            "atari2600": "Atari 2600",
            "atari5200": "Atari 5200",
            "atari7800": "Atari 7800",
            "atari800": "Atari 8-bit Family",
            "atarijaguar": "Atari Jaguar",
            "atarijaguarcd": "Atari Jaguar CD",
            "atarilynx": "Atari Lynx",
            "atarist": "Atari ST",
            "atarixe": "Atari XE",
            "atomiswave": "Atomiswave Arcade",
            "c64": "Commodore 64",
            "cannonball": "Cannonball (OutRun Engine)",
            "coco": "TRS-80 Color Computer",
            "coleco": "ColecoVision",
            "colecovision": "ColecoVision",
            "dragon32": "Dragon Data",
            "dreamcast": "Sega Dreamcast",
            "fds": "Famicom Disk System",
            "famicom": "Nintendo Famicom", 
            "gamegear": "Sega Game Gear",
            "gb": "Game Boy",
            "gba": "Game Boy Advance",
            "gbc": "Game Boy Color",
            "gc": "GameCube",
            "genesis": "Sega Genesis",
            "gizmondo": "Tiger Gizmondo",
            "intellivision": "Mattel Intellivision",
            "macintosh": "Apple Macintosh",
            "mastersystem": "Sega Master System",
            "megadrive": "Sega Mega Drive",
            "msx": "MSX",
            "n3ds": "Nintendo 3DS",
            "n64": "Nintendo 64",
            "n64dd": "Nintendo 64DD",
            "nds": "Nintendo DS",
            "neogeo": "Neo Geo",
            "neogeocd": "Neo Geo CD",
            "nes": "Nintendo Entertainment System",
            "ngp": "Neo Geo Pocket",
            "ngpc": "Neo Geo Pocket Color",
            "odyssey2": "Magnavox Odyssey 2",
            "othello": "Othello Multivision",
            "pc": "PC (IBM Compatible)",
            "pc98": "NEC PC-98",
            "pcengine": "PC Engine",
            "pcenginecd": "PC Engine CD",
            "pokemini": "Pokemon Mini",
            "pokitto": "Pokitto",
            "ps2": "PlayStation 2",
            "ps3": "PlayStation 3",
            "ps4": "PlayStation 4",
            "psp": "PlayStation Portable",
            "psvita": "PlayStation Vita",
            "psx": "PlayStation",
            "saturn": "Sega Saturn",
            "sega32x": "Sega 32X",
            "segacd": "Sega CD",
            "sfc": "Super Famicom",
            "sg1000": "Sega SG-1000",
            "snes": "Super Nintendo Entertainment System",
            "supergrafx": "PC Engine SuperGrafx",
            "supervision": "Watara Supervision",
            "trs80": "TRS-80",
            "turbografx": "TurboGrafx-16",
            "turbografxcd": "TurboGrafx-16 CD",
            "unknown": "Unknown Good Tool Collection",
            "vectrex": "GCE Vectrex",
            "virtualboy": "Virtual Boy",
            "wii": "Wii",
            "wiiu": "Wii U",
            "wonderswan": "Bandai WonderSwan",
            "wonderswancolor": "Bandai WonderSwan Color",
            "x1": "Sharp X1",
            "x68000": "Sharp X68000",
            "xbox": "Microsoft Xbox",
            "xbox360": "Microsoft Xbox 360",
            "zxspectrum": "ZX Spectrum",
        }
        
        if self.regional_mode == "consolidated":
            # Show consolidated names with context
            consolidated_names = {
                "nes": "Nintendo Entertainment System (includes Famicom)",
                "snes": "Super Nintendo Entertainment System (includes Super Famicom)",
                "pcengine": "PC Engine (includes TurboGrafx-16)",
            }
            return consolidated_names.get(platform, display_mapping.get(platform, platform))
        
        return display_mapping.get(platform, platform)

class PerformanceOptimizedROMProcessor:
    """Simple processor for basic ROM organization functionality"""
    
    def __init__(self, source_dir, operations_logger, progress_logger, dry_run=False):
        self.source_dir = source_dir
        self.operations_logger = operations_logger
        self.progress_logger = progress_logger
        self.dry_run = dry_run
        self.max_io_workers = 4
        self.hash_chunk_size = 65536
        self.progress_update_frequency = 100
    
    def discover_files_concurrent(self, platforms, selected_platforms):
        """Discover ROM files in selected platform directories"""
        files = []
        for platform_shortcode in selected_platforms:
            if platform_shortcode in platforms:
                platform_info = platforms[platform_shortcode]
                for source_folder in platform_info.source_folders:
                    folder_path = self.source_dir / source_folder
                    if folder_path.exists():
                        for ext in ROM_EXTENSIONS:
                            files.extend(folder_path.rglob(f"*{ext}"))
        return files
    
    def process_files_concurrent(self, all_files, target_dir, format_handler, platforms_info=None, regional_engine=None):
        """Process files with concurrent copying and real-time progress feedback"""
        import time
        from pathlib import Path
        import shutil
        from threading import Lock
        
        stats = ProcessingStats()
        stats.files_found = len(all_files)
        
        if not all_files:
            return stats
        
        # Progress tracking variables
        progress_lock = Lock()
        files_processed = 0
        files_copied = 0
        files_skipped = 0
        errors = 0
        start_time = time.perf_counter()
        current_file_name = ""
        
        def update_progress(file_name=""):
            """Update console progress display"""
            nonlocal current_file_name
            if file_name:
                current_file_name = file_name
                
            current_time = time.perf_counter()
            elapsed_time = current_time - start_time
            
            if elapsed_time > 0:
                files_per_sec = files_processed / elapsed_time
                
                if files_processed > 0:
                    estimated_total_time = (len(all_files) * elapsed_time) / files_processed
                    remaining_time = max(0, estimated_total_time - elapsed_time)
                else:
                    remaining_time = 0
                    files_per_sec = 0
                
                # Progress bar
                progress = files_processed / len(all_files) if len(all_files) > 0 else 0
                bar_length = 40
                filled_length = int(bar_length * progress)
                bar = '█' * filled_length + '░' * (bar_length - filled_length)
                
                # Format time remaining
                remaining_str = f"{remaining_time:.1f}s" if remaining_time < 60 else f"{remaining_time/60:.1f}m"
                
                # Truncate current file name if too long
                display_file = current_file_name[-50:] if len(current_file_name) > 50 else current_file_name
                
                # Update same line using carriage return
                print(f"\rProcessing: [{bar}] {files_processed}/{len(all_files)} files ({progress*100:.1f}%)", end='', flush=True)
                print(f"\nCurrent: {display_file} | {remaining_str} remaining | {files_per_sec:.1f} files/sec", end='', flush=True)
                # Move cursor back up to overwrite next time
                print("\033[F", end='', flush=True)
        
        def process_single_file(file_path):
            """Process a single file with proper platform detection and formatting"""
            nonlocal files_processed, files_copied, files_skipped, errors
            
            try:
                source_path = Path(file_path)
                
                # Find the platform this file belongs to by matching against platforms_info
                platform_shortcode = None
                source_folder_name = None
                
                if platforms_info:
                    # Find which platform this file belongs to based on source folders
                    for platform_code, platform_info in platforms_info.items():
                        for source_folder in platform_info.source_folders:
                            folder_path = Path(self.source_dir) / source_folder
                            try:
                                # Check if the file path is within this platform's source folder
                                source_path.relative_to(folder_path)
                                platform_shortcode = platform_code
                                source_folder_name = source_folder
                                break
                            except ValueError:
                                continue
                        if platform_shortcode:
                            break
                
                if not platform_shortcode:
                    # Fallback: use parent directory as platform
                    platform_shortcode = source_path.parent.name.lower()
                    source_folder_name = source_path.parent.name
                
                # Apply regional preferences if available
                if regional_engine:
                    platform_shortcode = regional_engine.get_target_platform(source_folder_name or "", platform_shortcode)
                
                # Use FormatHandler to determine target path (handles N64, NDS subfolders)
                if format_handler and source_folder_name:
                    target_platform_dir = format_handler.get_target_path(platform_shortcode, source_folder_name, target_dir)
                else:
                    target_platform_dir = target_dir / platform_shortcode
                
                # Create target directory
                target_platform_dir.mkdir(parents=True, exist_ok=True)
                target_file_path = target_platform_dir / source_path.name
                
                # Update progress with current file
                update_progress(f"{platform_shortcode}/{source_path.name}")
                
                # Copy file if not in dry run mode
                if not self.dry_run:
                    if not target_file_path.exists():
                        shutil.copy2(source_path, target_file_path)
                        with progress_lock:
                            files_copied += 1
                    else:
                        with progress_lock:
                            files_skipped += 1
                            self.operations_logger.warning(f"File already exists, skipping: {target_file_path}")
                else:
                    # Dry run mode - just simulate
                    with progress_lock:
                        files_copied += 1
                
                # Log operation
                self.operations_logger.info(f"{'[DRY RUN] ' if self.dry_run else ''}Copied: {source_path} -> {target_file_path}")
                
            except Exception as e:
                with progress_lock:
                    errors += 1
                self.operations_logger.error(f"Error processing {file_path}: {str(e)}")
                # Still update progress even on error
                update_progress()
            
            finally:
                with progress_lock:
                    files_processed += 1
        
        # Process files with threading for performance
        with ThreadPoolExecutor(max_workers=self.max_io_workers) as executor:
            futures = [executor.submit(process_single_file, file_path) for file_path in all_files]
            
            # Wait for completion
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    self.operations_logger.error(f"Thread error: {str(e)}")
                    errors += 1
        
        # Final progress update - clean display
        print(f"\rProcessing: [{'█' * 40}] {files_processed}/{len(all_files)} files (100.0%)")
        print(f"✅ Complete! Processed {files_processed} files")
        
        # Update stats
        stats.files_copied = files_copied
        stats.files_skipped_duplicate = files_skipped
        stats.errors = errors
        
        # Log final statistics
        elapsed_time = time.perf_counter() - start_time
        self.operations_logger.info(f"Processing completed in {elapsed_time:.2f} seconds")
        self.operations_logger.info(f"Copy rate: {files_copied / elapsed_time if elapsed_time > 0 else 0:.1f} files/second")
        
        return stats

class PlatformAnalyzer:
    """Analyzes directories and identifies platforms"""
    
    def __init__(self, source_dir: Path, logger: logging.Logger, regional_engine: RegionalPreferenceEngine = None, enable_subcategory_processing: bool = True):
        self.source_dir = source_dir
        self.logger = logger
        self.regional_engine = regional_engine or RegionalPreferenceEngine()
        self.enable_subcategory_processing = enable_subcategory_processing
        
        # Initialize subcategory processor if enabled
        if self.enable_subcategory_processing:
            self.subcategory_processor = SubcategoryProcessor(self.logger)
        else:
            self.subcategory_processor = None
        
        # Initialize specialized pattern processor for Good/MAME patterns
        self.specialized_processor = SpecializedPatternProcessor(self.logger)
        
        # Initialize performance monitor for optimization tracking
        self.performance_monitor = PerformanceMonitor(self.logger)
        
    def analyze_directory(self, debug_mode: bool = False, include_empty_dirs: bool = False, target_dir: Path = None) -> Tuple[Dict[str, PlatformInfo], List[str], List[str]]:
        """
        Analyze source directory and categorize all content
        
        Args:
            debug_mode: Enable detailed debug logging
            include_empty_dirs: Process directories even without ROM files
            target_dir: Target directory to avoid processing (prevents infinite loops)
        
        Returns:
            - Dict of platform shortcode -> PlatformInfo
            - List of excluded folders with reasons
            - List of unknown folders
        """
        platforms = {}
        excluded = []
        unknown = []
        
        self.logger.info(f"Analyzing directory: {self.source_dir}")
        if debug_mode:
            self.logger.info(f"Debug mode: Enabled")
            self.logger.info(f"Include empty directories: {include_empty_dirs}")
            self.logger.info(f"ROM extensions being searched: {sorted(ROM_EXTENSIONS)}")
        
        # Console progress feedback
        print(f"📁 Scanning ROM directories in: {self.source_dir}")
        
        directories_processed = 0
        directories_skipped_roms = 0
        directories_skipped_target = 0
        directories_with_roms = 0
        
        # Scan top-level directories (non-recursive to avoid game subdirectories)
        source_path = Path(self.source_dir)
        
        # First, get all top-level directories
        top_level_dirs = []
        try:
            for item in source_path.iterdir():
                if item.is_dir():
                    top_level_dirs.append(item)
        except (OSError, PermissionError) as e:
            self.logger.error(f"Error accessing source directory: {e}")
            return platforms, excluded, unknown
        
        # Process each top-level directory and count ROM files recursively within each
        for platform_dir in top_level_dirs:
            directories_processed += 1
            
            if debug_mode:
                self.logger.debug(f"Processing top-level directory: {platform_dir}")
            
            # Skip target directory to avoid loops (precise path comparison)
            if target_dir and platform_dir.resolve() == target_dir.resolve():
                directories_skipped_target += 1
                if debug_mode:
                    self.logger.debug(f"  Skipped: Target directory (exact match): {platform_dir}")
                continue
                
            # Count ROM files recursively within this platform directory
            rom_files = []
            all_extensions = set()
            
            for root, dirs, files in os.walk(platform_dir):
                for file in files:
                    all_extensions.add(Path(file).suffix.lower())
                    if Path(file).suffix.lower() in ROM_EXTENSIONS:
                        rom_files.append(file)
            
            if not rom_files and not include_empty_dirs:
                directories_skipped_roms += 1
                if debug_mode:
                    self.logger.debug(f"  Skipped: No ROM files (extensions: {sorted(all_extensions)})")
                continue
            
            # Count directories with ROM files for progress reporting
            if rom_files:
                directories_with_roms += 1
                
            folder_name = platform_dir.name
            
            if debug_mode:
                self.logger.debug(f"  Folder name: '{folder_name}'")
            
            # Check for exclusions first
            exclusion_reason = self._check_exclusions(folder_name)
            if exclusion_reason:
                excluded.append(f"{folder_name} - {exclusion_reason}")
                if debug_mode:
                    self.logger.debug(f"  Excluded: {exclusion_reason}")
                continue
                
            # Try to identify platform
            if debug_mode:
                self.logger.debug(f"  Attempting platform identification...")
            
            platform_result = self._identify_platform(folder_name, debug_mode=debug_mode)
            if platform_result:
                shortcode, display_name = platform_result
                
                if debug_mode:
                    self.logger.debug(f"  ✅ Platform identified: {shortcode} ({display_name})")
                
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
                    source_folders=current.source_folders + [str(platform_dir.relative_to(self.source_dir))]
                )
            else:
                unknown.append(folder_name)
                if debug_mode:
                    self.logger.debug(f"  ❌ No platform match found")
        
        # Console progress feedback
        print(f"✅ Analysis complete: {directories_with_roms} directories with ROM files, {len(platforms)} platforms identified")
        if directories_skipped_roms > 0 or directories_skipped_target > 0:
            empty_note = " (including root source directory)" if directories_skipped_roms == 1 else ""
            print(f"📊 Filtered: {directories_skipped_roms} empty dirs{empty_note}, {directories_skipped_target} target dirs skipped")
        
        # Log detailed summary statistics
        if debug_mode:
            self.logger.info(f"Directory analysis summary:")
            self.logger.info(f"  Total directories processed: {directories_processed}")
            self.logger.info(f"  Directories skipped (no ROM files): {directories_skipped_roms}")
            self.logger.info(f"  Directories skipped (target pattern): {directories_skipped_target}")
            self.logger.info(f"  Platforms identified: {len(platforms)}")
            self.logger.info(f"  Folders excluded: {len(excluded)}")
            self.logger.info(f"  Unknown folders: {len(unknown)}")
                
        return platforms, excluded, unknown
    
    def _check_exclusions(self, folder_name: str) -> Optional[str]:
        """Check if folder should be excluded"""
        for pattern, reason in EXCLUDED_PLATFORMS.items():
            if re.match(pattern, folder_name, re.IGNORECASE):
                return reason
        return None
    
    def _identify_platform(self, folder_name: str, debug_mode: bool = False) -> Optional[Tuple[str, str]]:
        """Identify platform from folder name using specialized and regex patterns with regional preferences"""
        original_folder_name = folder_name
        start_time = time.perf_counter()
        
        try:
            if debug_mode:
                self.logger.debug(f"    Testing folder: '{folder_name}'")
            
            # STEP 1: Try specialized patterns first (Good tools, MAME, FinalBurn Neo)
            # These have higher confidence and should be prioritized
            specialized_start = time.perf_counter()
            specialized_result, specialized_context = self.specialized_processor.process(folder_name)
            specialized_time = time.perf_counter() - specialized_start
            
            if debug_mode:
                self.logger.debug(f"    STEP 1: Specialized patterns - {'✅ Match' if specialized_result else '❌ No match'}")
            
            if specialized_result:
                shortcode, display_name = specialized_result
                
                # Apply regional preference logic even to specialized patterns
                final_platform = self.regional_engine.get_target_platform(folder_name, shortcode)
                final_display_name = self.regional_engine.get_display_name(final_platform)
                
                # Record performance metrics
                handler_used = specialized_context.get('handler_used', 'unknown')
                self.performance_monitor.record_pattern_hit(f"specialized_{handler_used}", shortcode)
                
                # Log specialized pattern matching
                confidence = specialized_context.get('confidence', 0.0)
                if debug_mode:
                    self.logger.debug(f"    Specialized match: {shortcode} ({display_name}) [Handler: {handler_used}, Confidence: {confidence:.2f}]")
                self.logger.info(f"Specialized pattern matched: '{folder_name}' -> {shortcode} ({display_name}) [Handler: {handler_used}, Confidence: {confidence:.2f}]")
                
                # Log regional mapping if applied
                if final_platform != shortcode:
                    if debug_mode:
                        self.logger.debug(f"    Regional mapping: {shortcode} -> {final_platform}")
                    self.logger.info(f"Regional mapping applied to specialized pattern: {folder_name}")
                    self.logger.info(f"  Original: {shortcode} ({display_name})")
                    self.logger.info(f"  Final: {final_platform} ({final_display_name})")
                    self.logger.info(f"  Mode: {self.regional_engine.regional_mode}")
                
                return final_platform, final_display_name
            
            # STEP 2: Apply subcategory preprocessing if enabled
            if debug_mode:
                self.logger.debug(f"    STEP 2: Subcategory preprocessing - {'Enabled' if self.subcategory_processor else 'Disabled'}")
            
            if self.subcategory_processor:
                processed_name, preprocessing_context = self.subcategory_processor.process(folder_name)
                folder_name = processed_name
                
                # Log preprocessing if changes were made
                if folder_name != original_folder_name:
                    if debug_mode:
                        self.logger.debug(f"    Preprocessed: '{original_folder_name}' → '{folder_name}'")
                    self.logger.info(f"Subcategory preprocessing: '{original_folder_name}' → '{folder_name}'")
                    for key, value in preprocessing_context.items():
                        if value and key != 'original_name':
                            self.logger.debug(f"  {key}: {value}")
                elif debug_mode:
                    self.logger.debug(f"    No preprocessing changes needed")
            
            # STEP 3: Try regular pattern matching with (potentially) preprocessed name
            if debug_mode:
                self.logger.debug(f"    STEP 3: Testing {len(PLATFORM_MAPPINGS)} regex patterns against: '{folder_name}'")
            
            regex_start = time.perf_counter()
            patterns_tested = 0
            
            for pattern_index, (pattern, (shortcode, display_name)) in enumerate(PLATFORM_MAPPINGS.items()):
                patterns_tested += 1
                if debug_mode and patterns_tested <= 5:  # Show first 5 pattern attempts
                    self.logger.debug(f"    Testing pattern {pattern_index}: {pattern}")
                
                if re.match(pattern, folder_name, re.IGNORECASE):
                    # Apply regional preference logic
                    final_platform = self.regional_engine.get_target_platform(folder_name, shortcode)
                    final_display_name = self.regional_engine.get_display_name(final_platform)
                    
                    # Record performance metrics
                    self.performance_monitor.record_pattern_hit("regular_pattern", f"{shortcode}:{pattern_index}")
                    
                    # Log regular pattern matching
                    if debug_mode:
                        self.logger.debug(f"    ✅ Pattern match #{pattern_index}: '{folder_name}' -> {shortcode} ({display_name})")
                        self.logger.debug(f"    Matching pattern: {pattern}")
                    self.logger.debug(f"Regular pattern matched: '{folder_name}' -> {shortcode} ({display_name}) [Pattern: {pattern}]")
                    
                    # Log regional mapping decisions
                    if final_platform != shortcode:
                        if debug_mode:
                            self.logger.debug(f"    Regional mapping: {shortcode} -> {final_platform}")
                        self.logger.info(f"Regional mapping applied: {folder_name}")
                        self.logger.info(f"  Original: {shortcode} ({display_name})")
                        self.logger.info(f"  Final: {final_platform} ({final_display_name})")
                        self.logger.info(f"  Mode: {self.regional_engine.regional_mode}")
                    
                    return final_platform, final_display_name
            
            # STEP 4: No pattern matched
            if debug_mode:
                self.logger.debug(f"    ❌ No regex patterns matched (tested {patterns_tested} patterns)")
            
            self.performance_monitor.record_cache_miss("platform_identification")
            return None
            
        finally:
            # Record total identification time
            total_time = time.perf_counter() - start_time
            self.performance_monitor.timing_data["_identify_platform"].append(total_time)

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
    
    def __init__(self, logger: logging.Logger, regional_engine: RegionalPreferenceEngine = None):
        self.logger = logger
        self.regional_engine = regional_engine or RegionalPreferenceEngine()
    
    def show_analysis_summary(self, platforms: Dict[str, PlatformInfo], 
                            excluded: List[str], unknown: List[str]) -> None:
        """Display comprehensive analysis summary"""
        print("\n" + "="*80)
        print("ROM COLLECTION ANALYSIS")
        print("="*80)
        print(f"🌐 Regional Mode: {self.regional_engine.regional_mode.upper()}")
        
        if self.regional_engine.regional_mode == "consolidated":
            print("📁 Regional variants will be merged (NES+Famicom→nes)")
        else:
            print("📁 Regional variants will be kept separate (NES→nes, Famicom→famicom)")
        
        print("⚠️  Significant variants always separated (FDS, N64DD, Sega CD)")
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
                 dry_run: bool = False, interactive: bool = True,
                 regional_mode: str = "consolidated", args=None):
        self.source_dir = source_dir
        self.target_dir = target_dir
        self.dry_run = dry_run
        self.interactive = interactive
        self.regional_mode = regional_mode
        
        # Initialize components
        self.comprehensive_logger = ComprehensiveLogger(dry_run)
        self.regional_engine = RegionalPreferenceEngine(regional_mode)
        # Determine subcategory processing setting
        enable_subcategory = True
        if args and hasattr(args, 'disable_subcategory_processing'):
            enable_subcategory = not args.disable_subcategory_processing
            
        self.analyzer = PlatformAnalyzer(source_dir, 
                                       self.comprehensive_logger.get_logger('analysis'),
                                       self.regional_engine,
                                       enable_subcategory)
        
        # Store args for subcategory statistics
        self.args = args
        self.selector = InteractiveSelector(
            self.comprehensive_logger.get_logger('progress'),
            self.regional_engine)
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
            # Get debug options from args
            debug_mode = self.args and hasattr(self.args, 'debug_analysis') and self.args.debug_analysis
            include_empty_dirs = self.args and hasattr(self.args, 'include_empty_dirs') and self.args.include_empty_dirs
            
            platforms, excluded, unknown = self.analyzer.analyze_directory(debug_mode=debug_mode, include_empty_dirs=include_empty_dirs, target_dir=self.target_dir)
            
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
            all_files, self.target_dir, self.format_handler, platforms, self.regional_engine
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
  
  # Regional handling examples
  python enhanced_rom_organizer.py "source" "target" --regional-mode consolidated
  python enhanced_rom_organizer.py "source" "target" --regional-mode regional

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
    parser.add_argument("--regional-mode", 
                       choices=["consolidated", "regional"], 
                       default="consolidated",
                       help="Regional variant handling: 'consolidated' merges variants (NES+Famicom→nes), 'regional' keeps separate (default: consolidated)")
    parser.add_argument("--disable-subcategory-processing", action="store_true",
                       help="Disable subcategory consolidation preprocessing (for testing compatibility)")
    parser.add_argument("--subcategory-stats", action="store_true",
                       help="Show detailed subcategory processing statistics")
    parser.add_argument("--debug-analysis", action="store_true",
                       help="Enable detailed debug logging during analysis")
    parser.add_argument("--include-empty-dirs", action="store_true",
                       help="Process directories even without ROM files (useful for DAT collections)")
    
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
            interactive=not args.no_interactive,
            regional_mode=args.regional_mode,
            args=args  # Pass args for subcategory processing options
        )
        
        if args.analyze_only:
            # Just show analysis
            # Use debug options from args
            debug_mode = args.debug_analysis if hasattr(args, 'debug_analysis') else False
            include_empty_dirs = args.include_empty_dirs if hasattr(args, 'include_empty_dirs') else False
            
            platforms, excluded, unknown = organizer.analyzer.analyze_directory(debug_mode=debug_mode, include_empty_dirs=include_empty_dirs, target_dir=organizer.target_dir)
            organizer.selector.show_analysis_summary(platforms, excluded, unknown)
            
            # Show subcategory processing statistics if requested
            if args.subcategory_stats and organizer.analyzer.subcategory_processor:
                print("\n" + "="*50)
                print("SUBCATEGORY PROCESSING STATISTICS")
                print("="*50)
                stats = organizer.analyzer.subcategory_processor.get_statistics()
                for key, value in stats.items():
                    formatted_key = key.replace('_', ' ').title()
                    print(f"{formatted_key}: {value}")
                
                # Log detailed subcategory statistics to file
                subcategory_logger = organizer.comprehensive_logger.get_logger('analysis')
                subcategory_logger.info("=== Subcategory Processing Statistics ===")
                for key, value in stats.items():
                    subcategory_logger.info(f"{key}: {value}")
                organizer.analyzer.subcategory_processor.log_statistics()
            
            print(f"\n✅ Analysis complete. Found {len(platforms)} supported platforms.")
        else:
            # Full processing
            stats = organizer.organize_roms()
            
            if stats.files_copied > 0:
                print(f"\n🎉 Success! Organized {stats.files_copied:,} files across {len(stats.selected_platforms)} platforms.")
                print(f"🌐 Regional mode: {args.regional_mode}")
            elif args.dry_run:
                print(f"\n📋 Dry run complete. Would have organized {stats.files_copied:,} files.")
                print(f"🌐 Regional mode: {args.regional_mode}")
            else:
                print(f"\n✅ Processing complete. No files needed copying.")
            
            print(f"📊 Check logs/ directory for detailed reports.")
        
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        sys.exit(1)

def test_regional_preferences():
    """Test regional preference engine with behavioral test cases"""
    
    # Test cases for regional handling
    test_cases = {
        "consolidated_mode": {
            "nes_famicom_consolidation": [
                ("Nintendo - Nintendo Entertainment System (Headerless) (Parent-Clone) (Retool)", "nes"),
                ("Nintendo - Famicom (Parent-Clone) (Retool)", "nes"),
                ("Nintendo Famicom & Entertainment System - Games - [NES] (Retool)", "nes"),
            ],
            "snes_superfamicom_consolidation": [
                ("Nintendo - Super Nintendo Entertainment System (Parent-Clone) (Retool)", "snes"),
                ("Nintendo - Super Famicom (Parent-Clone) (Retool)", "snes"),
            ],
            "always_separate": [
                ("Nintendo - Family Computer Disk System (FDS) (Parent-Clone) (Retool)", "fds"),
                ("Nintendo - Nintendo 64DD (Parent-Clone) (Retool)", "n64dd"),
                ("Sega - Sega CD (Parent-Clone) (Retool)", "segacd"),
                ("Sega - Mega CD (Parent-Clone) (Retool)", "segacd"),
            ]
        },
        
        "regional_mode": {
            "nes_famicom_separation": [
                ("Nintendo - Nintendo Entertainment System (Headerless) (Parent-Clone) (Retool)", "nes"),
                ("Nintendo - Famicom (Parent-Clone) (Retool)", "famicom"),
            ],
            "snes_superfamicom_separation": [
                ("Nintendo - Super Nintendo Entertainment System (Parent-Clone) (Retool)", "snes"),
                ("Nintendo - Super Famicom (Parent-Clone) (Retool)", "sfc"),
            ],
            "pcengine_turbografx_separation": [
                ("NEC - PC Engine (Parent-Clone) (Retool)", "pcengine"),
                ("NEC - TurboGrafx-16 (Parent-Clone) (Retool)", "turbografx"),
            ]
        }
    }
    
    print("=" * 80)
    print("REGIONAL PREFERENCE ENGINE BEHAVIORAL TESTS")
    print("=" * 80)
    
    # Test consolidated mode
    print("\nTesting Consolidated Mode...")
    consolidated_engine = RegionalPreferenceEngine("consolidated")
    consolidated_analyzer = PlatformAnalyzer(Path("test"), logging.getLogger(), consolidated_engine)
    
    total_tests = 0
    passed_tests = 0
    
    for test_name, test_cases_list in test_cases["consolidated_mode"].items():
        print(f"\n--- {test_name.replace('_', ' ').title()} ---")
        for folder_name, expected_platform in test_cases_list:
            total_tests += 1
            result = consolidated_analyzer._identify_platform(folder_name)
            actual_platform = result[0] if result else None
            
            if actual_platform == expected_platform:
                passed_tests += 1
                status = "✅"
            else:
                status = "❌"
            
            print(f"{status} {folder_name}")
            print(f"    Expected: {expected_platform}, Got: {actual_platform}")
    
    print("\n" + "="*80)
    print("Testing Regional Mode...")
    regional_engine = RegionalPreferenceEngine("regional")
    regional_analyzer = PlatformAnalyzer(Path("test"), logging.getLogger(), regional_engine)
    
    for test_name, test_cases_list in test_cases["regional_mode"].items():
        print(f"\n--- {test_name.replace('_', ' ').title()} ---")
        for folder_name, expected_platform in test_cases_list:
            total_tests += 1
            result = regional_analyzer._identify_platform(folder_name)
            actual_platform = result[0] if result else None
            
            if actual_platform == expected_platform:
                passed_tests += 1
                status = "✅"
            else:
                status = "❌"
            
            print(f"{status} {folder_name}")
            print(f"    Expected: {expected_platform}, Got: {actual_platform}")
    
    print(f"\n📊 Test Results: {passed_tests}/{total_tests} ({passed_tests/total_tests*100:.1f}%)")
    
    if passed_tests == total_tests:
        print("🎉 All regional preference tests passed!")
    else:
        print(f"⚠️  {total_tests - passed_tests} tests failed. Check implementation.")
    
    print("=" * 80)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test-regional":
        test_regional_preferences()
    else:
        main()
