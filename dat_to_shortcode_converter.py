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

# CRITICAL: Force UTF-8 encoding for all I/O operations (must be before any imports)
import sys
import io
import locale
import os

# Force UTF-8 for all I/O operations on Windows
if sys.platform == 'win32':
    # Windows-specific encoding fixes
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    os.environ['PYTHONIOENCODING'] = 'utf-8:replace'
    
    # Try to set console code page to UTF-8 (may fail in some environments)
    try:
        import subprocess
        result = subprocess.run(['chcp', '65001'], shell=True, capture_output=True, text=True)
    except:
        pass  # Not critical if this fails

# Version information - MUST be updated with every commit that changes functionality
__version__ = "0.10.0"
VERSION_DATE = "2025-08-27"
VERSION_INFO = f"DAT to Shortcode Converter v{__version__} ({VERSION_DATE})"

# Feature flags for experimental features (solopreneur rapid prototyping)
FEATURES = {
    'enhanced_terminal_display': os.getenv('ENABLE_ENHANCED_DISPLAY', '1') == '1',
    'enable_progress_save': os.getenv('ENABLE_PROGRESS_SAVE', '0') == '1',  # OFF by default
    'debug_threading': os.getenv('DEBUG_THREADING', '0') == '1'
}

import os
import sys
import hashlib
import shutil
import argparse
import logging
from logging.handlers import RotatingFileHandler
import re
import mmap
import threading
import time
import random
import signal
import uuid
import atexit
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Set, Optional, NamedTuple
from collections import defaultdict, Counter
from dataclasses import dataclass, field
import json
from good_pattern_handler import SpecializedPatternProcessor
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue
from threading import Lock, Event
from subcategory_handler import SubcategoryProcessor
from functools import wraps
from collections import defaultdict


# Global shutdown handler instance
shutdown_handler = None


class GracefulShutdownHandler:
    """Handles graceful shutdown with thread coordination and progress preservation"""
    
    def __init__(self):
        self.shutdown_event = Event()
        self.executor = None
        self.progress_state = {}
        self.completed_files = set()
        self.remaining_files = set()
        self.force_count = 0
        
    def register(self):
        """Register signal handlers for graceful shutdown"""
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        if sys.platform == 'win32':
            # Windows-specific signal
            try:
                signal.signal(signal.SIGBREAK, self.handle_shutdown)
            except AttributeError:
                pass  # SIGBREAK might not be available
        
        # Register atexit handler for cleanup
        atexit.register(self.cleanup)
    
    def handle_shutdown(self, signum, frame):
        """Gracefully handle shutdown request"""
        self.force_count += 1
        
        if self.force_count == 1:
            print("\n\n⚠️  Graceful shutdown initiated (press Ctrl+C again to force quit)...")
            
            # Set shutdown event for all threads
            self.shutdown_event.set()
            
            # Save current progress
            self.save_progress_state()
            
            # Shutdown executor with timeout
            if self.executor:
                print("   Waiting for threads to complete...")
                try:
                    self.executor.shutdown(wait=True, timeout=5.0)
                except:
                    # Force shutdown if timeout
                    self.executor.shutdown(wait=False)
            
            # Clean up temp files
            self.cleanup_temp_files()
            
            if FEATURES['enable_progress_save']:
                print("✅ Shutdown complete. Progress saved to .processing_state/resume_state.json")
            else:
                print("✅ Shutdown complete.")
            sys.exit(0)
        else:
            print("\n❌ Force quit requested. Terminating immediately...")
            sys.exit(1)
    
    def save_progress_state(self):
        """Save progress for potential resume"""
        if not FEATURES['enable_progress_save']:
            return  # Don't save unless explicitly enabled
            
        try:
            state_file = Path('.processing_state/resume_state.json')
            state_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'progress': self.progress_state,
                    'completed_files': list(self.completed_files),
                    'remaining_files': list(self.remaining_files)
                }, f, indent=2)
        except Exception as e:
            print(f"   Warning: Could not save progress state: {e}")
    
    def cleanup_temp_files(self):
        """Clean up any temporary files"""
        try:
            # Clean up .tmp files in target directories
            for temp_file in Path('.').rglob('*.tmp*'):
                try:
                    temp_file.unlink()
                except:
                    pass
        except Exception:
            pass
    
    def cleanup(self):
        """Final cleanup on exit"""
        if self.executor:
            try:
                self.executor.shutdown(wait=False)
            except:
                pass
    
    def check_shutdown(self):
        """Check if shutdown has been requested"""
        return self.shutdown_event.is_set()


class SafeFileHandler(logging.FileHandler):
    """File handler that sanitizes output for safe logging"""
    
    def __init__(self, filename, mode='a', encoding='utf-8', delay=False):
        super().__init__(filename, mode, encoding, delay)
    
    def emit(self, record):
        """Emit a record with sanitized message"""
        try:
            msg = self.format(record)
            # Replace problematic characters for logs (no Unicode arrows or emojis)
            msg = msg.replace('→', '->').replace('←', '<-').replace('↑', '^').replace('↓', 'v')
            # Remove emojis and other high Unicode characters for log files
            msg = ''.join(c if ord(c) < 128 else '?' for c in msg)
            self.stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


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
    files_replaced: int = 0  # Files that were replaced due to differences
    files_renamed_duplicates: int = 0  # Files renamed to prevent overwriting
    files_skipped_duplicate: int = 0
    files_skipped_unknown: int = 0
    errors: int = 0
    processing_time: float = 0.0
    selected_platforms: List[str] = None
    folders_created: Set[str] = field(default_factory=set)  # Track created directories

    def __post_init__(self):
        if self.selected_platforms is None:
            self.selected_platforms = []
    
    @property
    def total_unique_files(self) -> int:
        """Calculate total unique files processed (copied + renamed)"""
        return self.files_copied + self.files_renamed_duplicates

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

def is_wsl2_mount(path: Path) -> bool:
    """Check if path is on WSL2 Windows mount"""
    import platform
    
    # Only check for /mnt/ on Linux systems
    if platform.system() != 'Windows':
        return str(path).startswith('/mnt/')
    
    # Windows paths are never WSL2 mounts
    return False

def copy_file_simple_wsl2(source_path: Path, target_file_path: Path, operations_logger=None):
    """WSL2-optimized file copy with timeout and chunked processing support, returns (success, error_msg)"""
    import time
    import signal
    import threading
    
    # Timeout mechanism using threading for better WSL2 compatibility
    def copy_with_timeout(src, dst, timeout_seconds=30):
        """Copy file with timeout using threading"""
        result = {'success': False, 'error': None}
        
        def copy_thread():
            try:
                shutil.copyfile(src, dst)
                result['success'] = True
            except Exception as e:
                result['error'] = e
        
        thread = threading.Thread(target=copy_thread)
        thread.daemon = True
        thread.start()
        thread.join(timeout_seconds)
        
        if thread.is_alive():
            # Thread is still running, which means timeout occurred
            result['error'] = TimeoutError(f"Copy operation timed out after {timeout_seconds} seconds")
            return False, result['error']
            
        return result['success'], result['error']
    
    try:
        # Create target directory if needed
        target_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Log file size for debugging
        source_size = source_path.stat().st_size
        if operations_logger:
            operations_logger.debug(f"WSL2 copying file: {source_path.name} ({source_size:,} bytes)")
        
        # Attempt copy with timeout
        success, error = copy_with_timeout(source_path, target_file_path, timeout_seconds=30)
        
        if not success:
            error_msg = str(error) if error else "Unknown WSL2 copy error"
            if operations_logger:
                if isinstance(error, TimeoutError):
                    operations_logger.error(f"WSL2 copy timeout: {source_path} -> {target_file_path}: {error_msg}")
                else:
                    operations_logger.error(f"WSL2 copy failed: {source_path} -> {target_file_path}: {error_msg}")
            return False, error_msg
        
        # Increased delay for WSL2 9p protocol stability
        time.sleep(0.01)  # 10ms delay (increased from 1ms)
        
        # Verify copy was successful
        if not target_file_path.exists() or target_file_path.stat().st_size == 0:
            error_msg = f"WSL2 copy verification failed: {target_file_path}"
            if operations_logger:
                operations_logger.warning(error_msg)
            return False, error_msg
        
        # Verify file size matches
        target_size = target_file_path.stat().st_size
        if target_size != source_size:
            error_msg = f"WSL2 copy size mismatch: {source_path} ({source_size} vs {target_size})"
            if operations_logger:
                operations_logger.warning(error_msg)
            return False, error_msg
            
        if operations_logger:
            operations_logger.debug(f"WSL2 copy successful: {source_path.name} ({source_size:,} bytes)")
        return True, None
        
    except Exception as e:
        error_msg = f"WSL2 copy exception: {str(e)}"
        if operations_logger:
            operations_logger.error(f"WSL2 copy failed: {source_path} -> {target_file_path}: {error_msg}")
        return False, error_msg

def calculate_sha1(file_path, chunk_size=65536):
    """Calculate SHA1 hash with optimal method selection based on file size"""
    import mmap
    
    file_path = Path(file_path)
    
    try:
        file_size = file_path.stat().st_size
        sha1_hash = hashlib.sha1()
        
        # Use memory mapping for files larger than 100MB for efficiency
        if file_size > 100 * 1024 * 1024:  # 100MB threshold
            with open(file_path, 'rb') as f:
                # Memory-mapped reading for large files
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mmapped:
                    sha1_hash.update(mmapped)
        else:
            # Chunked reading for smaller files (better for concurrent operations)
            with open(file_path, 'rb') as f:
                while chunk := f.read(chunk_size):
                    sha1_hash.update(chunk)
        
        return sha1_hash.hexdigest()
    
    except (OSError, IOError) as e:
        # Return None if file cannot be read (file locked, missing, etc.)
        return None
    except Exception as e:
        # Return None for any other error during hash calculation
        return None

def should_copy_file(source_path, target_path, operations_logger=None):
    """Determine if file needs copying based on existence, size, and SHA1 hash comparison
    
    Returns:
        tuple: (should_copy: bool, reason: str, details: dict)
    """
    source_path = Path(source_path)
    target_path = Path(target_path)
    
    # Quick check: if target doesn't exist, definitely copy
    if not target_path.exists():
        return True, "new_file", {"action": "copy"}
    
    try:
        # Get file sizes for quick comparison
        source_size = source_path.stat().st_size
        target_size = target_path.stat().st_size
        
        # Different sizes = different files, need to copy
        if source_size != target_size:
            if operations_logger:
                operations_logger.debug(f"Size mismatch for {source_path.name}: source={source_size}, target={target_size}")
            return True, "size_mismatch", {"action": "replace", "source_size": source_size, "target_size": target_size}
        
        # Same size - need SHA1 comparison to determine if identical
        source_hash = calculate_sha1(source_path)
        target_hash = calculate_sha1(target_path)
        
        # Handle hash calculation failures
        if source_hash is None:
            if operations_logger:
                operations_logger.warning(f"Failed to calculate source hash for {source_path}")
            return True, "source_hash_failed", {"action": "copy_force"}
            
        if target_hash is None:
            if operations_logger:
                operations_logger.warning(f"Failed to calculate target hash for {target_path}")
            return True, "target_hash_failed", {"action": "replace_force"}
        
        # Compare hashes
        if source_hash == target_hash:
            if operations_logger:
                operations_logger.debug(f"Files identical (SHA1: {source_hash[:8]}...): {source_path.name}")
            return False, "identical_hash", {"action": "skip", "hash": source_hash}
        else:
            if operations_logger:
                operations_logger.debug(f"Hash mismatch for {source_path.name}: source={source_hash[:8]}..., target={target_hash[:8]}...")
            return True, "hash_mismatch", {"action": "replace", "source_hash": source_hash, "target_hash": target_hash}
    
    except Exception as e:
        # If any error occurs during comparison, err on the side of copying
        if operations_logger:
            operations_logger.warning(f"Error during file comparison for {source_path.name}: {e}")
        return True, "comparison_error", {"action": "copy_force", "error": str(e)}

def display_unified_progress(emoji: str, label: str, current: int, total: int, 
                           extra_info: str = "", rate: float = 0, eta_seconds: float = 0) -> None:
    """
    Display consistent progress bars across all stages of ROM processing
    
    Args:
        emoji: Stage emoji (🔍 for discovery, 📦 for processing, etc.)
        label: Stage label (Discovering, Processing, etc.)
        current: Current progress value
        total: Total expected value
        extra_info: Additional information to display after the progress bar
        rate: Rate of progress (files/second, etc.) - optional
        eta_seconds: Estimated time remaining in seconds - optional
    """
    # Consistent 40-character progress bar
    progress_bar_width = 40
    if total > 0:
        progress_ratio = min(current / total, 1.0)
        progress_pct = progress_ratio * 100
        filled = int(progress_bar_width * progress_ratio)
    else:
        progress_ratio = 0.0
        progress_pct = 0.0
        filled = 0
    
    bar = "█" * filled + "░" * (progress_bar_width - filled)
    
    # Base progress display
    progress_display = f"{emoji} {label}: [{bar}] {current:,}/{total:,} ({progress_pct:.1f}%)"
    
    # Add extra info if provided
    if extra_info:
        progress_display += f" | {extra_info}"
    
    # Add rate if provided
    if rate > 0:
        progress_display += f" | {rate:.1f} files/s"
    
    # Add ETA if provided
    if eta_seconds > 0:
        eta_str = f"{int(eta_seconds//60)}:{int(eta_seconds%60):02d}"
        progress_display += f" | ETA: {eta_str}"
    
    # Display with carriage return for same-line updates
    print(f"\r{progress_display}", end='', flush=True)

def count_rom_files_in_directory(directory_path: Path, rom_extensions: set = None) -> int:
    """Count ROM files in a directory recursively"""
    if rom_extensions is None:
        rom_extensions = ROM_EXTENSIONS
    
    rom_file_count = 0
    try:
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                if Path(file).suffix.lower() in rom_extensions:
                    rom_file_count += 1
    except (OSError, PermissionError):
        # If we can't access the directory, return 0
        pass
    
    return rom_file_count

def calculate_crc32(file_path: Path) -> int:
    """Fast CRC32 calculation for file verification"""
    import zlib
    crc = 0
    with open(file_path, 'rb') as f:
        while chunk := f.read(65536):  # 64KB chunks
            crc = zlib.crc32(chunk, crc)
    return crc & 0xffffffff  # Ensure positive value

def copy_file_with_verification(source_path: Path, target_path: Path, operations_logger=None) -> tuple[bool, str]:
    """Direct copy with CRC32 verification - no temp files"""
    import time
    import platform
    
    try:
        # Ensure target directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Direct copy with no temp files
        shutil.copy2(source_path, target_path)
        
        # Windows AV compatibility: brief pause after creation
        if platform.system() == 'Windows':
            time.sleep(0.05)  # 50ms for AV scan completion
        
        # Quick CRC32 verification
        source_crc = calculate_crc32(source_path)
        target_crc = calculate_crc32(target_path)
        
        if source_crc != target_crc:
            # Remove failed copy and report
            if target_path.exists():
                target_path.unlink()
            return False, f"CRC mismatch: {source_crc:08X} != {target_crc:08X}"
            
        return True, f"CRC: {source_crc:08X}"
        
    except Exception as e:
        # Cleanup any partial copy
        if target_path.exists():
            try:
                target_path.unlink()
            except:
                pass
        return False, str(e)

def copy_file_with_retry(source_path: Path, target_path: Path, operations_logger=None, max_retries: int = 3) -> tuple[bool, str]:
    """Copy file with retry logic and CRC verification"""
    import time
    
    delays = [0.1, 0.3, 0.7]  # Exponential backoff
    
    for attempt in range(max_retries):
        success, info = copy_file_with_verification(source_path, target_path, operations_logger)
        
        if success:
            if operations_logger:
                operations_logger.debug(f"Copy successful on attempt {attempt + 1}: {source_path.name} - {info}")
            return True, info
            
        # Log the attempt failure
        if operations_logger:
            operations_logger.warning(f"Copy attempt {attempt + 1}/{max_retries} failed: {source_path.name} - {info}")
            
        # Retry with exponential backoff
        if attempt < max_retries - 1:
            delay = delays[min(attempt, len(delays) - 1)]
            time.sleep(delay)
    
    # All attempts failed
    error_msg = f"Failed after {max_retries} attempts: {info}"
    if operations_logger:
        operations_logger.error(f"Copy permanently failed: {source_path.name} - {error_msg}")
    return False, error_msg

def copy_file_atomic(source_path, target_file_path, operations_logger=None, max_retries=3):
    """Legacy wrapper for backward compatibility"""
    success, info = copy_file_with_retry(Path(source_path), Path(target_file_path), operations_logger, max_retries)
    if success:
        return True, None
    else:
        return False, info

# WSL2 compatibility function (keeping for legacy)
def copy_file_atomic_wsl2_legacy(source_path, target_file_path, operations_logger=None, max_retries=3):
    """WSL2-optimized file copy with timeout and chunked processing support, returns (success, error_msg)"""
    import time
    import platform
    
    source_path = Path(source_path)
    target_file_path = Path(target_file_path)
    is_windows = platform.system() == 'Windows'
    
    # Windows-specific retry delays (more conservative)
    if is_windows:
        retry_delays = [0.1, 0.3, 0.6]  # Shorter delays since we avoid temp files
    else:
        retry_delays = [0.05, 0.1, 0.2]  # Faster for Unix-like systems
    
    # WSL2 detection: if either source or target is on Windows mount, use simple copy
    if is_wsl2_mount(source_path) or is_wsl2_mount(target_file_path):
        if operations_logger:
            operations_logger.debug(f"WSL2 mount detected, using simple copy: {source_path}")
        
        # Use WSL2-optimized copy with longer delays
        for attempt in range(min(max_retries, 2)):  # Limit to 2 attempts for WSL2
            success, error_msg = copy_file_simple_wsl2(source_path, target_file_path, operations_logger)
            if success:
                return True, None
            
            if attempt < 1:  # Only retry once
                if operations_logger:
                    operations_logger.warning(f"WSL2 copy attempt {attempt + 1} failed, retrying: {source_path}")
                time.sleep(1.0 + (attempt * 2.0))  # 1s, then 3s delay
        
        # All WSL2 attempts failed
        error_msg = f"All WSL2 copy attempts failed: {source_path}"
        if operations_logger:
            operations_logger.error(error_msg)
        return False, error_msg
    
    # Direct copy without temp files to avoid antivirus interference
    last_error = None
    source_size = None
    
    try:
        source_size = source_path.stat().st_size
    except Exception as e:
        return False, f"Cannot read source file: {e}"
    
    for attempt in range(max_retries):
        # Use the new CRC-based verification method
        success, info = copy_file_with_verification(source_path, target_file_path, operations_logger)
        
        if success:
            return True, None
            
        # Log the attempt failure
        if operations_logger:
            operations_logger.warning(f"Copy attempt {attempt + 1}/{max_retries} failed: {source_path} - {info}")
            
        # Retry with exponential backoff
        if attempt < max_retries - 1:
            delay = retry_delays[min(attempt, len(retry_delays) - 1)]
            time.sleep(delay)
        else:
            last_error = info
            break
    
    # All attempts failed
    error_msg = f"Failed to copy after {max_retries} attempts: {last_error}"
    return False, error_msg

class ModernTerminalDisplay:
    """Professional multi-panel terminal display with complete transparency"""
    
    def __init__(self):
        self.stats = {
            'total_directories_found': 0,
            'directories_with_roms': 0,
            'empty_directories': 0,
            'total_files_discovered': 0,
            'rom_files': 0,
            'non_rom_files': 0,
            'supported_platforms': 0,
            'excluded_platforms': 0,
            'unknown_platforms': 0,
            'files_to_process': 0,
            'files_excluded': 0,
            'files_unknown': 0,
            'files_copied': 0,
            'files_renamed': 0,
            'files_skipped': 0,
            'files_failed': 0,
            'retries': 0,
            'current_platform': '',
            'current_file': '',
            'processing_time': 0,
            'avg_rate': 0
        }
        self.platform_progress = {}
        self.activity_log = []
        self.last_update = 0
        self.update_interval = 0.1  # 100ms refresh rate
        self.display_lines = 0  # Track how many lines we've drawn
        
    def show_header(self, source_dir: str, target_dir: str, mode: str, regional_mode: str, threads: int):
        """Show fixed header section"""
        print("=" * 80)
        print(VERSION_INFO)
        print("=" * 80)
        print(f"Source: {source_dir}")
        print(f"Target: {target_dir}")
        print(f"Mode: {mode} | Regional: {regional_mode} | Threads: {threads}")
        print("=" * 80)
        print()
        
    def show_phase_discovery(self, non_rom_extensions=None):
        """Show Phase 1 discovery results"""
        print("PHASE 1: DISCOVERY & ANALYSIS")
        print("-" * 80)
        print("Directory Scan:")
        print(f"  ✓ Total directories found:        {self.stats['total_directories_found']:,}")
        print(f"  ✓ Directories with ROM files:     {self.stats['directories_with_roms']:,}  ({self.stats['directories_with_roms']/max(1,self.stats['total_directories_found'])*100:.1f}%)")
        print(f"  ✓ Empty directories skipped:       {self.stats['empty_directories']:,}  ({self.stats['empty_directories']/max(1,self.stats['total_directories_found'])*100:.1f}%)")
        print()
        print("File Discovery:")
        print(f"  ✓ Total files discovered:      {self.stats['total_files_discovered']:,}")
        print(f"  ✓ ROM files (supported ext):   {self.stats['rom_files']:,}  ({self.stats['rom_files']/max(1,self.stats['total_files_discovered'])*100:.1f}%)")
        print(f"  ✓ Files in excluded/unknown:    {self.stats['non_rom_files']:,}  ({self.stats['non_rom_files']/max(1,self.stats['total_files_discovered'])*100:.1f}%) - These ARE ROM files, just not in supported platforms")
        
        # Show non-ROM file type breakdown if available
        if non_rom_extensions and self.stats['non_rom_files'] > 0:
            print(f"      File types: ", end="")
            top_extensions = non_rom_extensions.most_common(5)
            parts = []
            for extension, count in top_extensions:
                display_ext = extension if extension else "[no ext]"
                parts.append(f"{display_ext}: {count:,}")
            print(", ".join(parts))
            if len(non_rom_extensions) > 5:
                remaining = sum(non_rom_extensions.values()) - sum(count for _, count in top_extensions)
                print(f"      + {len(non_rom_extensions)-5} more types ({remaining:,} files)")
        print()
        print("Platform Analysis:")
        total_platforms = self.stats['supported_platforms'] + self.stats['excluded_platforms'] + self.stats['unknown_platforms']
        print(f"  ✓ Supported platforms:             {self.stats['supported_platforms']:,}  ({self.stats['supported_platforms']/max(1,total_platforms)*100:.1f}%) → {self.stats['files_to_process']:,} files")
        print(f"  ✓ Excluded platforms:              {self.stats['excluded_platforms']:,}  ({self.stats['excluded_platforms']/max(1,total_platforms)*100:.1f}%) → {self.stats['files_excluded']:,} files")
        print(f"  ✓ Unknown platforms:               {self.stats['unknown_platforms']:,}  ({self.stats['unknown_platforms']/max(1,total_platforms)*100:.1f}%) → {self.stats['files_unknown']:,} files")
        print(f"  ✓ Directories analyzed:           {total_platforms:,}  (100%)")
        print()
        
    def show_phase_selection(self, platforms_to_process: int):
        """Show Phase 2 selection summary"""
        print("PHASE 2: SELECTION SUMMARY")
        print("-" * 80)
        print("✓ Processing: ALL SUPPORTED PLATFORMS")
        print(f"  • Platforms to process:            {platforms_to_process:,}")
        print(f"  • Files to process:            {self.stats['files_to_process']:,}")
        print(f"  • Folders to process:             {self.stats['directories_with_roms']:,}")
        estimated_time = self.stats['files_to_process'] / 2500 if self.stats['files_to_process'] > 0 else 0
        print(f"  • Estimated time:            ~{int(estimated_time)} sec @ 2,500 files/s")
        print()
        print("✗ Not Processing:")
        print(f"  • Excluded platform files:      {self.stats['files_excluded']:,} (will remain in source)")
        print(f"  • Unknown platform files:         {self.stats['files_unknown']:,} (will remain in source)")
        print(f"  • Files in excluded/unknown:   {self.stats['non_rom_files']:,} (will remain in source - these are ROM files in unsupported platforms)")
        print()
        
    def start_processing_phase(self):
        """Initialize processing phase display"""
        print("PHASE 3: PROCESSING [Live Updates]")
        print("=" * 80)
        print()
        self.display_lines = 0
        
    def update_live_progress(self, **kwargs):
        """Update live processing display"""
        # Rate limiting
        now = time.time()
        if now - self.last_update < self.update_interval:
            return
        self.last_update = now
        
        # Clear previous display if we've drawn lines before
        if self.display_lines > 0:
            print('\033[2J\033[H', end='')  # Clear screen and move to top
            
        lines = []
        
        # Overall Progress Panel
        lines.append("┌─ OVERALL PROGRESS ───────────────────────────────────────────────────────┐")
        current = kwargs.get('current', 0)
        total = kwargs.get('total', 0)
        rate = kwargs.get('rate', 0)
        eta = kwargs.get('eta_seconds', 0)
        
        if total > 0:
            progress_pct = (current / total) * 100
            bar_width = 30
            filled = int((current / total) * bar_width)
            bar = "█" * filled + "░" * (bar_width - filled)
            eta_str = f"{int(eta//60):02d}:{int(eta%60):02d}" if eta > 0 else "--:--"
            elapsed = kwargs.get('elapsed', 0)
            elapsed_str = f"{int(elapsed//60):02d}:{int(elapsed%60):02d}"
            
            lines.append(f"│ {bar} {progress_pct:5.1f}% │ {current:,}/{total:,} │ Rate: {rate:,.0f}/s  │")
            lines.append(f"│ Time: {elapsed_str} elapsed │ {eta_str} remaining │ Average: {self.stats['avg_rate']:,.0f} files/s        │")
        else:
            lines.append("│ Initializing...                                                          │")
            lines.append("│                                                                          │")
            
        lines.append("└──────────────────────────────────────────────────────────────────────────┘")
        lines.append("")
        
        # File Accounting Panel
        lines.append("┌─ FILE ACCOUNTING ────────────────────────────────────────────────────────┐")
        lines.append(f"│ Input:  {self.stats['files_to_process']:,} files selected for processing                            │")
        processed = self.stats['files_copied'] + self.stats['files_renamed']
        lines.append(f"│ Output: {processed:,} processed → {self.stats['files_copied']:,} copied + {self.stats['files_renamed']:,} renamed (duplicates)       │")
        lines.append(f"│ Status: ✓ {self.stats['files_copied']:,} success │ ⟲ {self.stats['retries']:,} retried │ ⚠ {self.stats['files_skipped']:,} skipped │ ✗ {self.stats['files_failed']:,} failed    │")
        lines.append("└──────────────────────────────────────────────────────────────────────────┘")
        lines.append("")
        
        # Platform Status Panel (show top 5 active platforms)
        lines.append("┌─ PLATFORM STATUS ────────────────────────────────────────────────────────┐")
        platform_display_count = 0
        for platform, progress in sorted(self.platform_progress.items(), key=lambda x: x[1]['current'], reverse=True):
            if platform_display_count >= 5:
                break
            platform_display_count += 1
            
            p = progress
            if p['total'] > 0:
                pct = (p['current'] / p['total']) * 100
                bar_width = 20
                filled = int((p['current'] / p['total']) * bar_width)
                bar = "█" * filled + "░" * (bar_width - filled)
                
                if p['current'] >= p['total']:
                    status_icon = "✓"
                    status_text = "complete"
                elif p['current'] > 0:
                    status_icon = "⟳"
                    status_text = "processing"
                else:
                    status_icon = "○"
                    status_text = "queued"
                    
                error_info = f" {p['errors']} errors" if p['errors'] > 0 else " all copied"
                lines.append(f"│ {status_icon} {platform:<11} [{bar}] {pct:3.0f}% │ {p['current']:,}/{p['total']:,} │{error_info:>11} │")
            platform_display_count += 1
            
        lines.append("└──────────────────────────────────────────────────────────────────────────┘")
        lines.append("")
        
        # Recent Activity Panel
        lines.append("┌─ RECENT ACTIVITY ────────────────────────────────────────────────────────┐")
        for activity in self.activity_log[-4:]:  # Show last 4 activities
            lines.append(f"│ {activity:<76} │")
        # Fill empty lines if needed
        for _ in range(4 - len(self.activity_log[-4:])):
            lines.append("│" + " " * 76 + "│")
        lines.append("└──────────────────────────────────────────────────────────────────────────┘")
        lines.append("")
        lines.append("[Press CTRL+C to pause, Q to quit, V for verbose mode, L to view log]")
        
        # Print all lines
        for line in lines:
            print(line)
            
        self.display_lines = len(lines)
        
    def add_activity(self, timestamp: str, file_name: str, action: str, details: str = ""):
        """Add activity to the log"""
        icon = "✓" if action == "copied" else "⟲" if action == "retry" else "✗"
        activity = f"{icon} {timestamp} {file_name:<30} → {action}"
        if details:
            activity += f" ({details})"
        
        self.activity_log.append(activity)
        # Keep only recent activities (max 20)
        if len(self.activity_log) > 20:
            self.activity_log = self.activity_log[-20:]
            
    def update_platform_progress(self, platform: str, current: int, total: int, errors: int = 0):
        """Update progress for a specific platform"""
        self.platform_progress[platform] = {
            'current': current,
            'total': total,
            'errors': errors
        }
        
    def show_final_summary(self):
        """Display comprehensive final summary"""
        print("\n")
        print("PHASE 4: VERIFICATION SUMMARY")
        print("=" * 80)
        print("Final Statistics:")
        print(f"  ✓ Files successfully copied:     {self.stats['files_copied']:,}  ({self.stats['files_copied']/max(1,self.stats['files_to_process'])*100:.2f}%)")
        print(f"  ✓ Files renamed (duplicates):         {self.stats['files_renamed']:,}  ({self.stats['files_renamed']/max(1,self.stats['files_to_process'])*100:.2f}%)")
        print(f"  ✗ Files failed:                       {self.stats['files_failed']:,}  ({self.stats['files_failed']/max(1,self.stats['files_to_process'])*100:.2f}%)")
        print()
        print("Verification:")
        print(f"  ✓ Source files processed:        {self.stats['files_to_process']:,}")
        print(f"  ✓ Target files created:          {self.stats['files_copied'] + self.stats['files_renamed']:,}  [Checksum verified]")
        completion_pct = ((self.stats['files_copied'] + self.stats['files_renamed']) / max(1, self.stats['files_to_process'])) * 100
        print(f"  ✓ Processing completion:           {completion_pct:.1f}%  (Files successfully processed)")
        print()
        print("Performance:")
        print(f"  • Total time:                  {self.stats['processing_time']:.1f} sec")
        print(f"  • Average speed:            {self.stats['avg_rate']:,} files/s")
        print()
        
        # Final validation check
        if self.stats['files_failed'] > 0:
            print("⚠️  WARNING: Some files failed to copy! Check errors log for details.")
        elif completion_pct == 100.0:
            print("🎉 SUCCESS: All files copied successfully with 100% integrity!")
        print("=" * 80)


# Global display instance
progress_display = ModernTerminalDisplay()




def extract_folder_hint(folder_name: str) -> Optional[str]:
    """Extract a short, meaningful identifier from folder name
    
    Examples:
    - "NES-1" -> "1"
    - "NES-USA" -> "USA"  
    - "Nintendo Entertainment System (Europe)" -> "Europe"
    - "NES (Alt)" -> "Alt"
    - "NES_v2" -> "v2"
    
    Returns:
        Short identifier (max 8 chars) or None if no meaningful hint found
    """
    import re
    
    # Clean input
    folder_name = folder_name.strip()
    
    # Try to extract patterns in order of preference
    patterns = [
        (r'-(\w{1,8})$', 'suffix_dash'),           # Suffix after dash: NES-1 -> "1"
        (r'_(\w{1,8})$', 'suffix_underscore'),     # Suffix after underscore: NES_v2 -> "v2"
        (r'\(([^)]{1,8})\)', 'parentheses'),       # Short text in parens: (Alt) -> "Alt"
        (r'\[([^\]]{1,8})\]', 'brackets'),         # Short text in brackets: [USA] -> "USA"
        (r'(?:^|\s)v(\d+)', 'version'),            # Version numbers: v2 -> "2"
        (r'(?:^|\s)(\d{1,3})$', 'trailing_number'), # Trailing numbers: NES 2 -> "2"
        (r'(?:^|\s)(\w{2,4})(?:\s|$)', 'short_word'), # Short meaningful words
    ]
    
    for pattern, pattern_type in patterns:
        match = re.search(pattern, folder_name, re.IGNORECASE)
        if match:
            hint = match.group(1).strip()
            # Filter out common words and ensure reasonable length
            if (hint.lower() not in ['the', 'and', 'or', 'of', 'in', 'at', 'to', 'for'] 
                and len(hint) >= 1 and len(hint) <= 8):
                return hint
    
    # No meaningful hint found
    return None

def get_unique_target_path(
    source_path: Path,
    target_dir: Path, 
    platform: str,
    source_folder_name: str,
    existing_paths: Set[str],
    operations_logger
) -> Tuple[Path, Optional[str]]:
    """Generate collision-free target path with intelligent duplicate handling
    
    Args:
        source_path: Source file path
        target_dir: Base target directory
        platform: Target platform shortcode
        source_folder_name: Name of source folder (for hint extraction)
        existing_paths: Set of target paths already claimed
        operations_logger: Logger for debugging
    
    Returns:
        Tuple of (unique_target_path, rename_reason)
        rename_reason can be:
        - None: Original name used
        - "skip_identical": File is truly identical, should skip
        - "renamed_with_hint_X": Renamed using folder hint
        - "renamed_with_number_X": Renamed with numbered suffix
        - "error_too_many_duplicates": Unable to find unique name
    """
    filename = source_path.name
    stem = source_path.stem  # Filename without extension
    suffix = source_path.suffix  # Extension including dot
    
    base_target = target_dir / platform / filename
    base_target_str = str(base_target)
    
    # First file with this name - use as-is
    if (base_target_str not in existing_paths and not base_target.exists()):
        return base_target, None
    
    # Path collision detected - check if truly identical via SHA1
    if base_target.exists():
        try:
            source_hash = calculate_sha1(source_path)
            target_hash = calculate_sha1(base_target)
            if source_hash and target_hash and source_hash == target_hash:
                operations_logger.debug(f"Truly identical file detected via SHA1: {filename}")
                return base_target, "skip_identical"
        except Exception as e:
            operations_logger.warning(f"SHA1 comparison failed for {filename}: {e}")
    
    # Different file with same name - need unique name
    operations_logger.info(f"Filename collision detected for: {filename} (from {source_folder_name})")
    
    # Strategy 1: Try using source folder hint
    folder_hint = extract_folder_hint(source_folder_name) if source_folder_name else None
    if folder_hint:
        unique_name = f"{stem} ({folder_hint}){suffix}"
        unique_path = target_dir / platform / unique_name
        unique_path_str = str(unique_path)
        
        if (unique_path_str not in existing_paths and not unique_path.exists()):
            operations_logger.info(f"Using folder hint for rename: {filename} -> {unique_name}")
            return unique_path, f"renamed_with_hint_{folder_hint}"
    
    # Strategy 2: Fall back to numbered suffix (2), (3), etc.
    counter = 2
    while counter < 100:
        unique_name = f"{stem} ({counter}){suffix}"
        unique_path = target_dir / platform / unique_name
        unique_path_str = str(unique_path)
        
        if (unique_path_str not in existing_paths and not unique_path.exists()):
            operations_logger.info(f"Using numbered suffix for rename: {filename} -> {unique_name}")
            return unique_path, f"renamed_with_number_{counter}"
        counter += 1
    
    # Should never reach here - emergency fallback
    operations_logger.error(f"Unable to find unique name for {filename} after 99 attempts")
    return base_target, "error_too_many_duplicates"

def count_files_in_directory(target_dir: Path) -> int:
    """Count actual ROM files in target directory for validation"""
    if not target_dir.exists():
        return 0
    
    count = 0
    for ext in ROM_EXTENSIONS:
        count += len(list(target_dir.rglob(f"*{ext}")))
    return count

class PerformanceOptimizedROMProcessor:
    """Simple processor for basic ROM organization functionality"""
    
    def __init__(self, source_dir, operations_logger, progress_logger, dry_run=False, max_workers=None):
        import platform
        
        self.source_dir = source_dir
        self.operations_logger = operations_logger
        self.progress_logger = progress_logger
        self.logger_errors = operations_logger  # Fix AttributeError - use operations_logger for errors
        self.dry_run = dry_run
        
        # Platform-aware thread defaults
        if max_workers is not None:
            self.max_io_workers = max_workers
        else:
            is_windows = platform.system() == 'Windows'
            if is_windows:
                self.max_io_workers = 3  # Updated from 2 based on user testing
            else:
                self.max_io_workers = 4  # More aggressive for Unix-like systems
        
        self.hash_chunk_size = 65536
        self.progress_update_frequency = 100
        
        # Log platform and threading configuration
        platform_name = platform.system()
        self.operations_logger.info(f"Platform: {platform_name}, Thread workers: {self.max_io_workers}")
    
    def discover_files_concurrent(self, platforms, selected_platforms):
        """Discover ROM files in selected platform directories with comprehensive counting"""
        import time
        
        files = []
        total_files_discovered = 0  # Track ALL files for complete statistics
        non_rom_extensions = Counter()  # Track non-ROM file extensions for transparency
        total_platforms = len(selected_platforms)
        processed_platforms = 0
        start_time = time.perf_counter()
        last_update_time = time.perf_counter()  # Track last progress update separately
        
        for platform_shortcode in selected_platforms:
            if platform_shortcode in platforms:
                platform_info = platforms[platform_shortcode]
                
                # Track folders within this platform
                total_folders = len(platform_info.source_folders)
                processed_folders = 0
                
                for source_folder in platform_info.source_folders:
                    folder_path = self.source_dir / source_folder
                    if folder_path.exists():
                        # Count ALL files for complete statistics
                        for file_path in folder_path.rglob("*"):
                            if file_path.is_file():
                                total_files_discovered += 1
                                extension = file_path.suffix.lower()
                                # Only add ROM files to processing list
                                if extension in ROM_EXTENSIONS:
                                    files.append(file_path)
                                else:
                                    # Track non-ROM file extensions for transparency
                                    non_rom_extensions[extension] += 1
                    
                    processed_folders += 1
                    
                    # Update progress every folder for small collections or every few folders for large ones
                    current_time = time.perf_counter()
                    
                    # Show progress for each platform completion or periodically
                    if processed_folders == total_folders or current_time - last_update_time > 0.5:
                        last_update_time = current_time  # Update last update time, not start time
                        extra_info = f"{len(files):,} files found"
                        display_unified_progress(
                            emoji="🔍",
                            label="Discovering", 
                            current=processed_platforms,
                            total=total_platforms,
                            extra_info=extra_info
                        )
            
            processed_platforms += 1
            
            # Final update for this platform
            extra_info = f"{len(files):,} files found"
            display_unified_progress(
                emoji="🔍",
                label="Discovering", 
                current=processed_platforms,
                total=total_platforms,
                extra_info=extra_info
            )
        
        # Final progress update showing comprehensive statistics
        non_rom_files = total_files_discovered - len(files)
        display_unified_progress(
            emoji="🔍",
            label="Discovering", 
            current=total_platforms,
            total=total_platforms,
            extra_info=f"{len(files):,} ROM files + {non_rom_files:,} other files = {total_files_discovered:,} total"
        )
        print()  # Clear the progress line
        
        # Log comprehensive file discovery statistics
        self.operations_logger.info(f"COMPREHENSIVE FILE DISCOVERY STATISTICS:")
        self.operations_logger.info(f"  Total files discovered (recursive): {total_files_discovered:,}")
        self.operations_logger.info(f"  ROM files (will process): {len(files):,}")
        self.operations_logger.info(f"  Non-ROM files (skipped): {non_rom_files:,}")
        self.operations_logger.info(f"  ROM file percentage: {(len(files) / max(total_files_discovered, 1)) * 100:.1f}%")
        
        # Log non-ROM file type breakdown for transparency
        if non_rom_extensions:
            self.operations_logger.info(f"NON-ROM FILE TYPE BREAKDOWN:")
            # Sort by count (descending) and show top 10
            top_extensions = non_rom_extensions.most_common(10)
            for extension, count in top_extensions:
                display_ext = extension if extension else "[no extension]"
                self.operations_logger.info(f"  {display_ext}: {count:,} files")
            if len(non_rom_extensions) > 10:
                remaining = sum(non_rom_extensions.values()) - sum(count for _, count in top_extensions)
                self.operations_logger.info(f"  [Other extensions]: {remaining:,} files")
        
        # Store comprehensive statistics for later use
        self.total_files_discovered = total_files_discovered
        self.non_rom_extensions = non_rom_extensions
        return files
    
    def process_files_concurrent(self, all_files, target_dir, format_handler, platforms_info=None, regional_engine=None):
        """Process files with folder-level threading to eliminate directory contention"""
        import time
        from pathlib import Path
        import shutil
        import tempfile
        from threading import Lock
        from collections import defaultdict
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        stats = ProcessingStats()
        stats.files_found = len(all_files)
        
        if not all_files:
            return stats
            
        # Progress tracking variables (thread-safe)
        progress_lock = Lock()
        files_processed = 0
        files_copied = 0
        files_replaced = 0
        files_skipped = 0
        files_renamed = 0  # Track renamed duplicates globally
        errors = 0
        start_time = time.perf_counter()
        current_file_name = ""
        
        # Group files by source folder to prevent directory contention
        files_by_folder = defaultdict(list)
        for file_path in all_files:
            source_folder = Path(file_path).parent
            files_by_folder[source_folder].append(file_path)
            
        self.operations_logger.info(f"Folder-level threading: Processing {len(files_by_folder)} folders with {len(all_files)} total files")
        
        def update_progress(file_name=""):
            """Thread-safe progress display using unified format"""
            nonlocal current_file_name
            if file_name:
                current_file_name = file_name
                
            current_time = time.perf_counter()
            elapsed_time = current_time - start_time
            
            if elapsed_time > 0:
                files_per_sec = files_processed / elapsed_time
                
                if files_processed > 0:
                    estimated_total_time = (len(all_files) * elapsed_time) / files_processed
                    eta_seconds = max(0, estimated_total_time - elapsed_time)
                else:
                    eta_seconds = 0
                    files_per_sec = 0
                
                # Use unified progress display
                display_unified_progress(
                    emoji="📦",
                    label="Processing", 
                    current=files_processed,
                    total=len(all_files),
                    rate=files_per_sec,
                    eta_seconds=eta_seconds
                )
        
        def process_folder_files(folder_path, folder_files):
            """Process all files from a single folder sequentially (eliminates directory contention)"""
            nonlocal files_processed, files_copied, files_replaced, files_skipped, files_renamed, errors
            folder_copied = 0
            folder_replaced = 0
            folder_skipped = 0 
            folder_errors = 0
            folder_renamed = 0  # New counter for renamed duplicates
            
            # Track target paths being created to prevent collisions
            target_paths_in_batch = set()
            
            self.operations_logger.info(f"Processing folder: {folder_path} with {len(folder_files)} files")
            
            for file_path in folder_files:
                try:
                    source_path = Path(file_path)
                    
                    # Find platform for this file
                    platform_shortcode = None
                    source_folder_name = None
                    
                    if platforms_info:
                        # Find which platform this file belongs to
                        for platform_code, platform_info in platforms_info.items():
                            for source_folder in platform_info.source_folders:
                                folder_path_check = Path(self.source_dir) / source_folder
                                try:
                                    source_path.relative_to(folder_path_check)
                                    platform_shortcode = platform_code
                                    source_folder_name = source_folder
                                    break
                                except ValueError:
                                    continue
                            if platform_shortcode:
                                break
                    
                    if not platform_shortcode:
                        platform_shortcode = source_path.parent.name.lower()
                        source_folder_name = source_path.parent.name
                    
                    # Apply regional preferences
                    if regional_engine:
                        platform_shortcode = regional_engine.get_target_platform(source_folder_name or "", platform_shortcode)
                    
                    # Get base target directory (with format handling)
                    if format_handler and source_folder_name:
                        target_platform_dir = format_handler.get_target_path(platform_shortcode, source_folder_name, target_dir)
                    else:
                        target_platform_dir = target_dir / platform_shortcode
                    
                    # Get unique target path (prevents filename collisions)
                    target_file_path, rename_reason = get_unique_target_path(
                        source_path,
                        target_dir,
                        platform_shortcode,
                        source_folder_name,
                        target_paths_in_batch,
                        self.operations_logger
                    )
                    
                    # Track this target path to prevent future collisions
                    target_paths_in_batch.add(str(target_file_path))
                    
                    # Handle rename reasons from unique path generation
                    if rename_reason == "skip_identical":
                        folder_skipped += 1
                        self.operations_logger.debug(f"Skipping truly identical file: {source_path.name}")
                        continue
                    elif rename_reason and rename_reason.startswith("renamed_"):
                        folder_renamed += 1
                        # Log the rename decision
                        if "hint_" in rename_reason:
                            hint = rename_reason.split("hint_")[1]
                            self.operations_logger.info(f"Prevented overwrite: {source_path.name} -> {target_file_path.name} (hint: {hint})")
                        elif "number_" in rename_reason:
                            number = rename_reason.split("number_")[1]
                            self.operations_logger.info(f"Prevented overwrite: {source_path.name} -> {target_file_path.name} (#{number})")
                    
                    # Update progress display
                    update_progress(f"{platform_shortcode}/{target_file_path.name}")
                    
                    # Smart file copy with SHA1 verification
                    if not self.dry_run:
                        # Check if we need to copy using SHA1 comparison
                        should_copy, reason, details = should_copy_file(source_path, target_file_path, self.operations_logger)
                        
                        if should_copy:
                            # Log the reason for copying
                            if reason == "new_file":
                                self.operations_logger.debug(f"Copying new file: {target_file_path.name}")
                            elif reason in ["size_mismatch", "hash_mismatch"]:
                                self.operations_logger.info(f"Replacing different file: {target_file_path.name} (reason: {reason})")
                            else:
                                self.operations_logger.debug(f"Copying file: {target_file_path.name} (reason: {reason})")
                            
                            # Check for shutdown request
                            if shutdown_handler and shutdown_handler.check_shutdown():
                                self.operations_logger.info("Shutdown requested, stopping processing")
                                return
                            
                            # Use improved atomic copy method with proper timing
                            success, error_msg = copy_file_atomic(source_path, target_file_path, self.operations_logger)
                            if error_msg and "identical" in error_msg:
                                folder_skipped += 1
                                success = False  # Don't count as copied
                            elif error_msg and "replaced" in error_msg:
                                folder_replaced += 1
                                success = True
                            
                            if success:
                                # Track folder creation
                                folder_dir_str = str(target_file_path.parent)
                                if folder_dir_str not in stats.folders_created:
                                    stats.folders_created.add(folder_dir_str)
                                
                                # Count based on rename status - FIXED: Don't double-count renamed files
                                if rename_reason and rename_reason.startswith("renamed_"):
                                    # This is a renamed duplicate, already counted in folder_renamed - don't double-count
                                    pass  # Renamed files already counted at line 1313, don't count again as copied
                                elif reason == "new_file":
                                    folder_copied += 1
                                else:
                                    folder_replaced += 1
                                self.operations_logger.debug(f"Successfully copied: {source_path.name}")
                                # Log file size for verification
                                try:
                                    target_size = target_file_path.stat().st_size
                                    self.operations_logger.debug(f"Copy verified: {target_size:,} bytes written")
                                except Exception:
                                    pass
                            else:
                                folder_errors += 1
                                self.logger_errors.error(f"Failed to copy {source_path.name}: {error_msg}")
                                # Log detailed failure for debugging
                                self.logger_errors.debug(f"Copy failure: {source_path} -> {target_file_path}")
                        else:
                            # File is identical, skip it
                            folder_skipped += 1
                            if reason == "identical_hash":
                                hash_preview = details.get("hash", "unknown")[:8]
                                self.operations_logger.debug(f"Skipped identical file: {source_path.name} (SHA1: {hash_preview}...)")
                            else:
                                self.operations_logger.debug(f"Skipped file: {source_path.name} (reason: {reason})")
                    else:
                        # Dry run mode
                        if rename_reason and rename_reason.startswith("renamed_"):
                            folder_renamed += 1
                            self.operations_logger.debug(f"[DRY RUN] Would rename: {source_path} -> {target_file_path}")
                        else:
                            folder_copied += 1
                            self.operations_logger.debug(f"[DRY RUN] Would copy: {source_path} -> {target_file_path}")
                        
                except Exception as e:
                    folder_errors += 1
                    self.logger_errors.error(f"Error processing {file_path}: {str(e)}")
                
                finally:
                    # Update global counters thread-safely
                    with progress_lock:
                        files_processed += 1
                        
            # Update global stats for this folder
            with progress_lock:
                files_copied += folder_copied
                files_replaced += folder_replaced
                files_skipped += folder_skipped
                files_renamed += folder_renamed
                errors += folder_errors
                
            self.operations_logger.info(f"Completed folder {folder_path}: {folder_copied} copied, {folder_replaced} replaced, {folder_renamed} renamed, {folder_skipped} skipped, {folder_errors} errors")
        
        # Process folders with one thread per folder (eliminates directory contention)
        max_workers = min(self.max_io_workers, len(files_by_folder))
        self.operations_logger.info(f"Using {max_workers} threads for {len(files_by_folder)} folders")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Register executor with shutdown handler for proper cleanup
            if shutdown_handler:
                shutdown_handler.executor = executor
            
            # Submit one folder per thread
            futures = []
            for folder_path, folder_files in files_by_folder.items():
                future = executor.submit(process_folder_files, folder_path, folder_files)
                futures.append(future)
            
            # Wait for all folders to complete
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    with progress_lock:
                        errors += 1
                    self.logger_errors.error(f"Thread error: {str(e)}")
        
        # Final progress display with newline
        display_unified_progress(
            emoji="📦",
            label="Processing", 
            current=files_processed,
            total=len(all_files),
            rate=files_processed / (time.perf_counter() - start_time) if (time.perf_counter() - start_time) > 0 else 0,
            eta_seconds=0
        )
        print(f"\n✅ Multi-threaded processing complete: {files_processed:,} files processed")
        print(f"   📋 Results: {files_copied:,} copied, {files_replaced:,} replaced, {files_renamed:,} renamed, {files_skipped:,} skipped, {errors:,} errors")
        
        # Update stats
        stats.files_copied = files_copied
        stats.files_replaced = files_replaced
        stats.files_renamed_duplicates = files_renamed
        stats.files_skipped_duplicate = files_skipped
        stats.errors = errors
        
        # Log final statistics
        elapsed_time = time.perf_counter() - start_time
        self.operations_logger.info(f"Processing completed in {elapsed_time:.2f} seconds")
        self.operations_logger.info(f"Copy rate: {files_copied / elapsed_time if elapsed_time > 0 else 0:.1f} files/second")
        self.operations_logger.info(f"Folder-level threading: Processed {len(files_by_folder)} folders with {max_workers} threads")
        
        return stats

class AsyncFileCopyEngine:
    """Adaptive file copying engine that automatically optimizes for filesystem type"""
    
    def __init__(self, operations_logger, errors_logger, progress_logger, dry_run=False):
        self.operations_logger = operations_logger
        self.errors_logger = errors_logger
        self.progress_logger = progress_logger
        self.dry_run = dry_run
        
        # Environment detection
        self.is_wsl2 = self._detect_wsl2()
        self.strategy = self._select_strategy()
        
        # Strategy-specific configuration
        self.max_workers = self.strategy.get('max_workers', 4)
        self.retry_config = self.strategy.get('retry_config', {})
        
        # Logging
        self.operations_logger.info(f"AsyncFileCopyEngine initialized with {self.strategy['name']} strategy")
        self.operations_logger.debug(f"WSL2 DEBUG - Selected strategy: {self.strategy}")
    
    def _detect_wsl2(self) -> bool:
        """Detect WSL2 environment"""
        import platform
        import os
        
        # First check if we're on Windows (not WSL)
        if platform.system() == 'Windows':
            return False
        
        # Then check for WSL2 on Linux
        try:
            if os.path.exists('/proc/version'):
                with open('/proc/version', 'r') as f:
                    version_content = f.read().lower()
                    return 'microsoft' in version_content
        except Exception:
            pass
        
        return False
    
    def _is_windows_mount(self, path: Path) -> bool:
        """Check if path is Windows mount in WSL"""
        return str(path).startswith('/mnt/')
    
    def _select_strategy(self) -> dict:
        """Select appropriate copying strategy based on environment"""
        if self.is_wsl2:
            return {
                'name': 'WSL2SingleThreadStrategy',
                'max_workers': 1,  # Single-threaded for WSL2 Windows mounts
                'retry_config': {
                    'max_attempts': 2,
                    'base_delay': 1.0,
                    'exponential_base': 3.0,
                    'jitter': True
                },
                'description': 'Single-threaded strategy optimized for WSL2 9p protocol limitations'
            }
        else:
            return {
                'name': 'HighConcurrencyStrategy', 
                'max_workers': 8,
                'retry_config': {
                    'max_attempts': 3,
                    'base_delay': 0.1,
                    'exponential_base': 2.0,
                    'jitter': False
                },
                'description': 'High-concurrency strategy for native Linux filesystems'
            }
    
    def copy_files_adaptive(self, files_by_folder, platforms, target_dir, update_progress_callback) -> ProcessingStats:
        """Adaptive file copying with filesystem-aware optimization"""
        stats = ProcessingStats()
        start_time = time.perf_counter()
        
        self.operations_logger.info(f"Starting adaptive file copying with {self.strategy['name']}")
        self.operations_logger.debug(f"WSL2 DEBUG - Processing {len(files_by_folder)} folders with {self.max_workers} workers")
        
        if self.is_wsl2 and any(self._is_windows_mount(Path(folder)) for folder in files_by_folder.keys()):
            self.operations_logger.warning("WSL2 + Windows mount detected - Using single-threaded strategy to prevent I/O errors")
        
        # Use single-threaded processing for WSL2 to avoid 9p protocol issues
        if self.max_workers == 1:
            return self._process_single_threaded(files_by_folder, platforms, target_dir, update_progress_callback)
        else:
            return self._process_concurrent(files_by_folder, platforms, target_dir, update_progress_callback)
    
    def _calculate_progress_update_frequency(self, total_files: int) -> int:
        """Calculate appropriate progress update frequency based on file count"""
        if total_files < 1000:
            return 10  # Update every 10 files for small collections
        elif total_files < 10000:
            return 100  # Update every 100 files for medium collections
        elif total_files < 50000:
            return 500  # Update every 500 files for large collections
        else:
            return 1000  # Update every 1000 files for very large collections
    
    def _process_single_threaded(self, files_by_folder, platforms, target_dir, update_progress_callback) -> ProcessingStats:
        """Single-threaded processing optimized for WSL2 with chunked recovery"""
        import time
        import os
        
        stats = ProcessingStats()
        total_files = sum(len(files) for files in files_by_folder.values())
        
        self.operations_logger.info("Using single-threaded processing for WSL2 compatibility")
        self.operations_logger.info(f"Processing {total_files} files across {len(files_by_folder)} folders")
        
        # Calculate appropriate update frequency
        update_frequency = self._calculate_progress_update_frequency(total_files)
        
        # Chunked processing configuration for WSL2 stability
        chunk_size = 1000  # Process 1000 files at a time
        recovery_pause = 5.0  # 5-second pause between chunks
        
        processed_files = 0
        start_time = time.perf_counter()
        last_update_time = start_time
        last_chunk_time = start_time
        
        # Track target paths globally to prevent collisions across chunks
        global_target_paths = set()
        
        # User feedback about processing mode
        print(f"📦 Starting WSL2-optimized chunked processing ({total_files:,} files)...", flush=True)
        self.operations_logger.info(f"Using chunked processing: {chunk_size} files per chunk with {recovery_pause}s recovery pauses")
        
        # Convert files to a flat list for chunked processing
        all_files = []
        for folder_path, files in files_by_folder.items():
            for file_info in files:
                all_files.append(file_info)
        
        # Process files in chunks
        for chunk_start in range(0, len(all_files), chunk_size):
            chunk_end = min(chunk_start + chunk_size, len(all_files))
            chunk_files = all_files[chunk_start:chunk_end]
            
            self.operations_logger.info(f"Processing chunk {chunk_start//chunk_size + 1}: files {chunk_start+1}-{chunk_end}")
            
            # Process current chunk
            for file_info in chunk_files:
                source_path = file_info['path']
                platform_shortcode = file_info['platform']
                source_folder_name = file_info.get('source_folder', source_path.parent.name)
                
                # Determine target path with duplicate handling
                if platform_shortcode in platforms:
                    # Get unique target path to prevent filename collisions
                    target_file_path, rename_reason = get_unique_target_path(
                        source_path,
                        target_dir,
                        platform_shortcode,
                        source_folder_name,
                        global_target_paths,
                        self.operations_logger
                    )
                    
                    # Track this target path to prevent future collisions
                    global_target_paths.add(str(target_file_path))
                    
                    # Handle rename reasons
                    if rename_reason == "skip_identical":
                        stats.files_skipped_duplicate += 1
                        self.operations_logger.debug(f"Skipping truly identical file: {source_path.name}")
                        processed_files += 1
                        continue
                    elif rename_reason and rename_reason.startswith("renamed_"):
                        stats.files_renamed_duplicates += 1
                        # Log the rename decision
                        if "hint_" in rename_reason:
                            hint = rename_reason.split("hint_")[1]
                            self.operations_logger.info(f"Prevented overwrite: {source_path.name} -> {target_file_path.name} (hint: {hint})")
                        elif "number_" in rename_reason:
                            number = rename_reason.split("number_")[1]
                            self.operations_logger.info(f"Prevented overwrite: {source_path.name} -> {target_file_path.name} (#{number})")
                    
                    # Update progress display with final filename
                    if update_progress_callback:
                        update_progress_callback(f"{platform_shortcode}/{target_file_path.name}")
                    
                    # Perform copy with retry logic
                    success = self._copy_with_retry(source_path, target_file_path)
                    
                    if success:
                        stats.files_copied += 1
                    else:
                        stats.errors += 1
                        
                processed_files += 1
                
                # Progress update with unified display function
                current_time = time.perf_counter()
                if processed_files % update_frequency == 0 or processed_files == total_files:
                    elapsed_time = current_time - start_time
                    
                    if elapsed_time > 0:
                        files_per_sec = processed_files / elapsed_time
                        eta_seconds = (total_files - processed_files) / files_per_sec if files_per_sec > 0 else 0
                    else:
                        files_per_sec = 0
                        eta_seconds = 0
                    
                    # Use unified progress display
                    display_unified_progress(
                        emoji="📦",
                        label="Processing", 
                        current=processed_files,
                        total=total_files,
                        rate=files_per_sec,
                        eta_seconds=eta_seconds
                    )
                    
                    last_update_time = current_time
            
            # WSL2 Recovery pause between chunks (except for the last chunk)
            if chunk_end < len(all_files):
                chunk_processing_time = time.perf_counter() - last_chunk_time
                self.operations_logger.info(f"Chunk {chunk_start//chunk_size + 1} completed in {chunk_processing_time:.1f}s")
                
                print(f"\n⏸️  Recovery pause ({recovery_pause}s) - letting WSL2's 9p protocol recover...", flush=True)
                self.operations_logger.info(f"Recovery pause: {recovery_pause}s to prevent 9p protocol saturation")
                
                # Perform filesystem sync to ensure all operations are committed
                try:
                    os.sync()
                except:
                    pass  # sync() may not be available on all systems
                
                time.sleep(recovery_pause)
                last_chunk_time = time.perf_counter()
                
                print(f"▶️  Resuming processing... ({processed_files:,}/{total_files:,} files completed)", flush=True)
        
        # Final progress update with newline
        print(f"\n✅ WSL2-optimized chunked processing complete: {processed_files:,} files processed")
        self.operations_logger.info(f"Total processing completed: {processed_files:,} files, {stats.files_copied} successful, {stats.errors} errors")
        return stats
    
    def _process_concurrent(self, files_by_folder, platforms, target_dir, update_progress_callback) -> ProcessingStats:
        """Concurrent processing for native filesystems"""
        import time
        from pathlib import Path
        from threading import Lock
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        stats = ProcessingStats()
        
        # Flatten files from folder structure and extract paths
        all_files = []
        for folder_files in files_by_folder.values():
            for file_info in folder_files:
                if isinstance(file_info, dict):
                    all_files.append(file_info['path'])
                else:
                    all_files.append(file_info)
            
        stats.files_found = len(all_files)
        
        if not all_files:
            return stats
            
        self.operations_logger.info(f"Using concurrent processing with {self.max_workers} workers")
        self.operations_logger.info(f"Processing {len(all_files)} files across {len(files_by_folder)} folders")
        
        # Progress tracking variables (thread-safe)
        progress_lock = Lock()
        files_processed = 0
        files_copied = 0
        files_skipped = 0
        errors = 0
        start_time = time.perf_counter()
        
        def update_progress_threadsafe():
            """Thread-safe progress display"""
            current_time = time.perf_counter()
            elapsed_time = current_time - start_time
            
            if elapsed_time > 0 and files_processed > 0:
                files_per_sec = files_processed / elapsed_time
                estimated_total_time = (len(all_files) * elapsed_time) / files_processed
                eta_seconds = max(0, estimated_total_time - elapsed_time)
            else:
                files_per_sec = 0
                eta_seconds = 0
            
            # Use unified progress display
            display_unified_progress(
                emoji="📦",
                label="Processing", 
                current=files_processed,
                total=len(all_files),
                rate=files_per_sec,
                eta_seconds=eta_seconds
            )
        
        def process_folder_files(folder_path, folder_files):
            """Process all files from a single folder sequentially"""
            nonlocal files_processed, files_copied, files_skipped, errors
            folder_copied = 0
            folder_skipped = 0 
            folder_errors = 0
            
            self.operations_logger.info(f"Processing folder: {folder_path} with {len(folder_files)} files")
            
            for file_info in folder_files:
                try:
                    # Handle dict structure from _group_files_by_folder
                    if isinstance(file_info, dict):
                        source_path = Path(file_info['path'])
                        platform_shortcode = file_info['platform']
                        source_folder_name = source_path.parent.name
                    else:
                        source_path = Path(file_info)
                        platform_shortcode = None
                        source_folder_name = None
                    
                    # If platform wasn't found in dict, fall back to detection logic
                    if not platform_shortcode and platforms:
                        # Find which platform this file belongs to
                        for platform_code, platform_info in platforms.items():
                            for source_folder in platform_info.source_folders:
                                # Use the file's parent directory to match platform
                                try:
                                    if str(source_path.parent).endswith(source_folder) or source_folder in str(source_path):
                                        platform_shortcode = platform_code
                                        source_folder_name = source_folder
                                        break
                                except ValueError:
                                    continue
                            if platform_shortcode:
                                break
                    
                    if not platform_shortcode:
                        platform_shortcode = source_path.parent.name.lower()
                        source_folder_name = source_path.parent.name
                    
                    # Determine target path
                    target_platform_dir = target_dir / platform_shortcode
                    target_file_path = target_platform_dir / source_path.name
                    
                    # Create target directory if needed
                    target_platform_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Copy file
                    if not self.dry_run:
                        if not target_file_path.exists():
                            success = self._copy_with_retry(source_path, target_file_path)
                            if success:
                                folder_copied += 1
                                self.operations_logger.debug(f"Successfully copied: {source_path} -> {target_file_path}")
                            else:
                                folder_errors += 1
                                self.errors_logger.error(f"Failed to copy: {source_path}")
                        else:
                            folder_skipped += 1
                            self.operations_logger.debug(f"File already exists, skipping: {target_file_path}")
                    else:
                        # Dry run mode
                        folder_copied += 1
                        self.operations_logger.debug(f"[DRY RUN] Would copy: {source_path} -> {target_file_path}")
                        
                except Exception as e:
                    folder_errors += 1
                    self.errors_logger.error(f"Error processing {source_path}: {str(e)}")
                
                finally:
                    # Update global counters thread-safely
                    with progress_lock:
                        files_processed += 1
                        if files_processed % 50 == 0:  # Update progress every 50 files
                            update_progress_threadsafe()
                            
            # Update global stats for this folder
            with progress_lock:
                files_copied += folder_copied
                files_skipped += folder_skipped
                errors += folder_errors
        
        # Process folders concurrently
        with ThreadPoolExecutor(max_workers=min(len(files_by_folder), self.max_workers)) as executor:
            # Submit all folder processing tasks
            future_to_folder = {}
            for folder_path, folder_files in files_by_folder.items():
                future = executor.submit(process_folder_files, folder_path, folder_files)
                future_to_folder[future] = folder_path
            
            # Wait for completion and handle any exceptions
            for future in as_completed(future_to_folder):
                folder_path = future_to_folder[future]
                try:
                    future.result()  # This will raise any exception that occurred
                except Exception as e:
                    with progress_lock:
                        errors += 1
                    self.errors_logger.error(f"Thread error processing {folder_path}: {str(e)}")
        
        # Final progress update
        with progress_lock:
            update_progress_threadsafe()
            stats.files_copied = files_copied
            stats.files_skipped_duplicate = files_skipped
            stats.errors = errors
        
        print()  # Add newline after progress
        return stats
    
    def _copy_with_retry(self, source_path: Path, target_path: Path, max_retries: int = 3) -> bool:
        """Copy file with retry logic avoiding temp files to prevent antivirus interference"""
        
        # Ensure target directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        for attempt in range(max_retries):
            # Use the new CRC-based verification method
            success, info = copy_file_with_verification(source_path, target_path, self.operations_logger)
            
            if success:
                return True
                
            # Log retry attempts as warnings, not errors
            if attempt < max_retries - 1:
                self.operations_logger.warning(f"Copy attempt {attempt + 1}/{max_retries} failed: {source_path.name} - {info}")
                delay = 0.1 * (2 ** attempt)
                time.sleep(delay)
            else:
                # Only log final failure as error after all retries exhausted
                self.errors_logger.error(f"FINAL FAILURE after {max_retries} attempts: {source_path.name} - {info}")
                return False
                    
        return False

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
        
    def analyze_directory(self, debug_mode: bool = False, include_empty_dirs: bool = False, target_dir: Path = None) -> Tuple[Dict[str, PlatformInfo], Dict[str, Tuple[str, int]], List[str], Dict[str, int]]:
        """
        Analyze source directory and categorize all content
        
        Args:
            debug_mode: Enable detailed debug logging
            include_empty_dirs: Process directories even without ROM files
            target_dir: Target directory to avoid processing (prevents infinite loops)
        
        Returns:
            - Dict of platform shortcode -> PlatformInfo
            - Dict of excluded folders: folder_name -> (reason, file_count)
            - List of unknown folders
            - Dict of directory statistics
        """
        platforms = {}
        excluded = {}
        unknown = []
        
        self.logger.info(f"Analyzing directory: {self.source_dir}")
        if debug_mode:
            self.logger.info(f"Debug mode: Enabled")
            self.logger.info(f"Include empty directories: {include_empty_dirs}")
            self.logger.info(f"ROM extensions being searched: {sorted(ROM_EXTENSIONS)}")
        
        # Console progress feedback
        print(f"📁 Scanning ROM directories in: {self.source_dir}")
        
        # Update progress display with initial stats
        progress_display.stats['excluded'] = 0
        progress_display.stats['unknown'] = 0
        progress_display.stats['analyzed'] = 0
        
        directories_processed = 0
        directories_skipped_roms = 0
        directories_skipped_target = 0
        directories_with_roms = 0
        
        # Track all file extensions for transparency about non-ROM files
        all_file_extensions = Counter()
        total_files_analyzed = 0
        
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
            directory_stats = {
                'total_processed': 0,
                'directories_with_roms': 0, 
                'empty_directories': 0
            }
            return platforms, excluded, unknown, directory_stats
        
        # Process each top-level directory and count ROM files recursively within each
        total_dirs = len(top_level_dirs)
        for idx, platform_dir in enumerate(top_level_dirs):
            directories_processed += 1
            
            # Update analysis progress display
            if FEATURES['enhanced_terminal_display']:
                print(f"\r📊 Analyzing: [{idx+1}/{total_dirs}] - ✅ {len(platforms)} platforms, ⚠️ {len(excluded)} excluded, ❓ {len(unknown)} unknown", end='', flush=True)
            
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
                    extension = Path(file).suffix.lower()
                    all_extensions.add(extension)
                    # Track all files for global transparency
                    all_file_extensions[extension] += 1
                    total_files_analyzed += 1
                    
                    if extension in ROM_EXTENSIONS:
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
                # Validation: ensure we store integer count, not list
                file_count = len(rom_files)
                if debug_mode and not isinstance(file_count, int):
                    self.logger.error(f"ERROR: len(rom_files) returned {type(file_count)}, not int: {file_count}")
                if debug_mode and not isinstance(rom_files, list):
                    self.logger.error(f"ERROR: rom_files is {type(rom_files)}, not list: {rom_files}")
                
                excluded[folder_name] = (exclusion_reason, file_count)
                progress_display.stats['excluded'] = len(excluded)
                if debug_mode:
                    self.logger.debug(f"  Excluded: {exclusion_reason} ({file_count} files)")
                continue
                
            # Try to identify platform
            if debug_mode:
                self.logger.debug(f"  Attempting platform identification...")
            
            platform_result = self._identify_platform(folder_name, debug_mode=debug_mode)
            if platform_result:
                shortcode, display_name = platform_result
                
                if debug_mode:
                    self.logger.debug(f"  [OK] Platform identified: {shortcode} ({display_name})")
                
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
                progress_display.stats['analyzed'] = len(platforms)
            else:
                unknown.append(folder_name)
                progress_display.stats['unknown'] = len(unknown)
                if debug_mode:
                    self.logger.debug(f"  [X] No platform match found")
        
        # Console progress feedback
        if FEATURES['enhanced_terminal_display']:
            print()  # Clear the progress line
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
        
        # Log comprehensive file extension analysis
        rom_files_found = sum(all_file_extensions[ext] for ext in all_file_extensions if ext in ROM_EXTENSIONS)
        non_rom_files_found = total_files_analyzed - rom_files_found
        
        self.logger.info(f"COMPREHENSIVE FILE EXTENSION ANALYSIS:")
        self.logger.info(f"  Total files analyzed: {total_files_analyzed:,}")
        self.logger.info(f"  ROM files (recognized extensions): {rom_files_found:,}")
        self.logger.info(f"  Non-ROM files: {non_rom_files_found:,}")
        
        if debug_mode:
            print(f"\nDEBUG: FILE EXTENSION ANALYSIS")
            print(f"DEBUG: Total files analyzed: {total_files_analyzed:,}")
            print(f"DEBUG: ROM files found: {rom_files_found:,}")
            print(f"DEBUG: Non-ROM files found: {non_rom_files_found:,}")
        
        if all_file_extensions:
            self.logger.info(f"FILE EXTENSION BREAKDOWN (Top 20):")
            # Sort by count (descending)
            top_extensions = all_file_extensions.most_common(20)
            for extension, count in top_extensions:
                display_ext = extension if extension else "[no extension]"
                is_rom = "ROM" if extension in ROM_EXTENSIONS else "NON-ROM"
                self.logger.info(f"  {display_ext}: {count:,} files ({is_rom})")
                
            if debug_mode:
                print(f"DEBUG: Top file extensions found:")
                for i, (extension, count) in enumerate(top_extensions[:10]):
                    display_ext = extension if extension else "[no ext]"
                    is_rom = "ROM" if extension in ROM_EXTENSIONS else "non-ROM"
                    print(f"       {i+1:2d}. {display_ext}: {count:,} ({is_rom})")
        
        # Create directory statistics summary
        directory_stats = {
            'total_processed': directories_processed,
            'directories_with_roms': directories_with_roms,
            'empty_directories': directories_skipped_roms,
            'target_directories_skipped': directories_skipped_target
        }
                
        return platforms, excluded, unknown, directory_stats
    
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
                self.logger.debug(f"    STEP 1: Specialized patterns - {'[OK] Match' if specialized_result else '[X] No match'}")
            
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
                        self.logger.debug(f"    Preprocessed: '{original_folder_name}' -> '{folder_name}'")
                    self.logger.info(f"Subcategory preprocessing: '{original_folder_name}' -> '{folder_name}'")
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
                        self.logger.debug(f"    [OK] Pattern match #{pattern_index}: '{folder_name}' -> {shortcode} ({display_name})")
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
                self.logger.debug(f"    [X] No regex patterns matched (tested {patterns_tested} patterns)")
            
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
                            excluded: Dict[str, Tuple[str, int]], unknown: List[str], unknown_files: int = 0) -> None:
        """Display comprehensive analysis summary"""
        print("\n" + "="*80)
        print("ROM COLLECTION ANALYSIS")
        print("="*80)
        print(f"🌐 Regional Mode: {self.regional_engine.regional_mode.upper()}")
        
        if self.regional_engine.regional_mode == "consolidated":
            print("📁 Regional variants will be merged (NES+Famicom->nes)")
        else:
            print("📁 Regional variants will be kept separate (NES->nes, Famicom->famicom)")
        
        print("⚠️  Significant variants always separated (FDS, N64DD, Sega CD)")
        print("="*80)
        
        if platforms:
            total_supported_files = sum(info.file_count for info in platforms.values())
            print(f"\n✅ SUPPORTED PLATFORMS FOUND ({len(platforms)}):")
            print("-" * 50)
            print(f"     🎮 Total supported files: {total_supported_files:,}")
            print()
            for i, (shortcode, info) in enumerate(sorted(platforms.items()), 1):
                print(f"[{i:2d}] {shortcode:<12} - {info.display_name}")
                print(f"     📁 {info.folder_count} folders, 🎮 {info.file_count:,} files")
        
        if excluded:
            print(f"\n⚠️  EXCLUDED PLATFORMS ({len(excluded)}):")
            print("-" * 50)
            total_excluded_files = sum(file_count for reason, file_count in excluded.values())
            print(f"     🎮 Total excluded files: {total_excluded_files:,}")
            print()
            items_shown = list(excluded.items())[:10]  # Show first 10
            for folder_name, (reason, file_count) in items_shown:
                print(f"    • {folder_name} - {reason}")
                if file_count > 0:
                    print(f"      🎮 {file_count:,} files")
            if len(excluded) > 10:
                print(f"    ... and {len(excluded) - 10} more")
        
        if unknown:
            print(f"\n❓ UNKNOWN PLATFORMS ({len(unknown)}):")
            print("-" * 50)
            print(f"     🎮 Total unknown files: {unknown_files:,}")
            print()
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
    
    def __init__(self, dry_run: bool = False, debug: bool = False):
        self.dry_run = dry_run
        self.debug = debug
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.loggers = {}
        self.setup_logging()
    
    def setup_logging(self):
        """Setup comprehensive logging system"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Define log types and their purposes
        # Use DEBUG level for comprehensive logging when debug flag is enabled
        default_level = logging.DEBUG if self.debug else logging.INFO
        error_level = logging.DEBUG if self.debug else logging.ERROR
        
        log_configs = {
            'operations': {
                'file': log_dir / f"operations_{self.timestamp}.log",
                'level': default_level,
                'description': 'All file operations and decisions'
            },
            'analysis': {
                'file': log_dir / f"analysis_{self.timestamp}.log", 
                'level': default_level,
                'description': 'Platform detection and analysis results'
            },
            'errors': {
                'file': log_dir / f"errors_{self.timestamp}.log",
                'level': error_level,
                'description': 'Errors and exceptions'
            },
            'summary': {
                'file': log_dir / f"summary_{self.timestamp}.log",
                'level': default_level,
                'description': 'Final processing summary and statistics'
            },
            'progress': {
                'file': log_dir / f"progress_{self.timestamp}.log",
                'level': default_level,
                'description': 'Real-time progress updates'
            }
        }
        
        for log_type, config in log_configs.items():
            logger = logging.getLogger(log_type)
            logger.setLevel(config['level'])
            
            # Use SafeFileHandler for sanitized output (no rotation for simplicity)
            # Could extend SafeFileHandler to support rotation if needed
            fh = SafeFileHandler(config['file'], encoding='utf-8')
            fh.setLevel(config['level'])
            
            # All logging goes to files only - console controlled by ModernTerminalDisplay
            
            # Formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            fh.setFormatter(formatter)
            
            logger.addHandler(fh)
            self.loggers[log_type] = logger
            
            # Write enhanced header with context to each log file
            self._write_log_header(logger, log_type, config['description'])
    
    def _write_log_header(self, logger: logging.Logger, log_type: str, description: str):
        """Write enhanced header with version and context to log file"""
        # Define log type display names
        log_type_names = {
            'operations': 'OPERATIONS',
            'analysis': 'PLATFORM ANALYSIS', 
            'errors': 'ERRORS & EXCEPTIONS',
            'progress': 'PROGRESS TRACKING',
            'summary': 'SUMMARY REPORT',
            'performance': 'PERFORMANCE METRICS'
        }
        
        log_display_name = log_type_names.get(log_type, log_type.upper())
        header = f"""================================================================================
LOG TYPE: {log_display_name}
Version: {__version__} | Date: {VERSION_DATE}
Timestamp: {datetime.now().isoformat()}
Description: {description}
================================================================================"""
        
        # Write header directly to log (without timestamp prefix)
        for handler in logger.handlers:
            if isinstance(handler, (logging.FileHandler, SafeFileHandler)):
                # Write raw header without formatter
                handler.stream.write(header + '\n')
                handler.stream.flush()
    
    def get_logger(self, log_type: str) -> logging.Logger:
        """Get specific logger by type"""
        return self.loggers.get(log_type, self.loggers['operations'])

def check_version_consistency(logger=None):
    """Check if version has been updated with code changes - non-blocking validation"""
    try:
        script_path = Path(__file__)
        script_mtime = datetime.fromtimestamp(script_path.stat().st_mtime)
        version_date_obj = datetime.strptime(VERSION_DATE, "%Y-%m-%d")
        
        # Check if file was modified after version date
        if script_mtime.date() > version_date_obj.date():
            warning_msg = f"⚠️  VERSION CHECK: Script modified ({script_mtime.date()}) after version date ({VERSION_DATE})"
            if logger:
                logger.warning(warning_msg)
            else:
                print(warning_msg)
                print(f"   Consider updating version from {__version__} if functionality changed")
                
    except Exception:
        # Non-critical - don't block execution if version check fails
        pass

class EnhancedROMOrganizer:
    """Main ROM organizer with enhanced features"""
    
    def __init__(self, source_dir: Path, target_dir: Path, 
                 dry_run: bool = False, interactive: bool = True,
                 regional_mode: str = "consolidated", debug: bool = False, args=None):
        self.source_dir = source_dir
        self.target_dir = target_dir
        self.dry_run = dry_run
        self.interactive = interactive
        self.regional_mode = regional_mode
        
        # Extract concurrency settings from args
        self.max_workers = getattr(args, 'threads', None) if args else None
        self.verify_copies = getattr(args, 'verify_copies', False) if args else False
        self.skip_identical = getattr(args, 'skip_identical', True) if args else True
        
        # Initialize components
        self.comprehensive_logger = ComprehensiveLogger(dry_run, debug)
        
        # Run version consistency check (non-blocking)
        check_version_consistency(self.comprehensive_logger.get_logger('operations'))
        
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
        
        # Initialize adaptive file copy engine (replaces PerformanceOptimizedROMProcessor)
        self.async_copy_engine = AsyncFileCopyEngine(
            self.comprehensive_logger.get_logger('operations'),
            self.comprehensive_logger.get_logger('errors'),
            self.comprehensive_logger.get_logger('progress'),
            dry_run
        )
        
        # Keep legacy processor for file discovery (will be migrated in future)
        self.performance_processor = PerformanceOptimizedROMProcessor(
            source_dir,
            self.comprehensive_logger.get_logger('operations'),
            self.comprehensive_logger.get_logger('progress'),
            dry_run,
            max_workers=getattr(self, 'max_workers', None)  # Use max_workers if provided
        )
        
        # Statistics tracking
        self.stats = ProcessingStats()
        
        # Get loggers
        self.logger_ops = self.comprehensive_logger.get_logger('operations')
        self.logger_progress = self.comprehensive_logger.get_logger('progress')
        self.logger_errors = self.comprehensive_logger.get_logger('errors')
        self.logger_summary = self.comprehensive_logger.get_logger('summary')
        self.logger_performance = self.comprehensive_logger.get_logger('performance')
        
        # WSL2 Environment Detection for debugging
        self._detect_and_log_environment()
    
    def _detect_and_log_environment(self):
        """Detect and log environment information for WSL2 diagnostics"""
        import platform
        import os
        
        try:
            system_name = platform.system()
            self.logger_ops.debug(f"Environment DEBUG - Platform system: {system_name}")
            
            # Check for WSL2 environment
            is_wsl2 = False
            version_info = "N/A"
            
            if system_name == 'Windows':
                self.logger_ops.info("Windows environment detected - will use multi-threaded file operations")
                is_wsl2 = False
            elif system_name == 'Linux':
                # Check if it's WSL2 on Linux
                if os.path.exists('/proc/version'):
                    with open('/proc/version', 'r') as f:
                        version_info = f.read().lower()
                        is_wsl2 = 'microsoft' in version_info
                        
                if is_wsl2:
                    self.logger_ops.info("WSL2 environment detected - will use single-threaded file operations for /mnt/* paths")
                    self.logger_ops.debug("WSL2 DEBUG - WSL2 uses 9p protocol for Windows mounts which has concurrency limitations")
                else:
                    self.logger_ops.info("Linux environment detected - will use multi-threaded file operations")
            
            self.logger_ops.debug(f"Environment DEBUG - Kernel version: {version_info}")
            self.logger_ops.debug(f"Environment DEBUG - Is WSL2: {is_wsl2}")
            
            # Check source directory mount type (only relevant for WSL2)
            source_str = str(self.source_dir)
            is_windows_mount = source_str.startswith('/mnt/') if system_name == 'Linux' else False
            self.logger_ops.debug(f"Environment DEBUG - Source directory: {source_str}")
            self.logger_ops.debug(f"Environment DEBUG - Is Windows mount (/mnt/*): {is_windows_mount}")
            
            if is_wsl2 and is_windows_mount:
                self.logger_ops.warning("WSL2 + Windows mount detected - This may cause I/O errors with concurrent operations")
                
        except Exception as e:
            self.logger_ops.debug(f"Environment DEBUG - Could not detect environment: {str(e)}")
    
    def _group_files_by_folder(self, all_files: List[Path], platforms: Dict) -> Dict:
        """Group files by their parent folder for adaptive processing"""
        files_by_folder = defaultdict(list)
        
        # Group files by parent directory and identify platforms
        for file_path in all_files:
            # Find which platform this file belongs to
            platform_shortcode = None
            for shortcode, platform_info in platforms.items():
                for source_folder in platform_info.source_folders:
                    if str(source_folder) in str(file_path.parent):
                        platform_shortcode = shortcode
                        break
                if platform_shortcode:
                    break
            
            if platform_shortcode:
                folder_key = str(file_path.parent)
                files_by_folder[folder_key].append({
                    'path': file_path,
                    'platform': platform_shortcode
                })
                
        self.logger_ops.debug(f"WSL2 DEBUG - Grouped {len(all_files)} files into {len(files_by_folder)} folders")
        return files_by_folder
    
    def organize_roms(self) -> ProcessingStats:
        """Main organization workflow"""
        start_time = datetime.now()
        
        try:
            # Initialize modern terminal display
            mode = "DRY RUN" if self.dry_run else "LIVE RUN"
            regional_mode = "SEPARATE" if self.regional_mode == 'regional' else "CONSOLIDATED"
            threads = getattr(self.args, 'threads', 4) if self.args else 4
            
            # Show header with configuration
            progress_display.show_header(
                str(self.source_dir), 
                str(self.target_dir), 
                mode, 
                regional_mode, 
                threads
            )
            
            # Log to file only (no console output)
            self.logger_progress.info("Starting enhanced ROM organization...")
            self.logger_progress.info(f"Source: {self.source_dir}")
            self.logger_progress.info(f"Target: {self.target_dir}")
            self.logger_progress.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE RUN'}")
            
            # Phase 1: Analysis (log only)
            # Get debug options from args
            debug_mode = self.args and hasattr(self.args, 'debug_analysis') and self.args.debug_analysis
            include_empty_dirs = self.args and hasattr(self.args, 'include_empty_dirs') and self.args.include_empty_dirs
            
            platforms, excluded, unknown, directory_stats = self.analyzer.analyze_directory(debug_mode=debug_mode, include_empty_dirs=include_empty_dirs, target_dir=self.target_dir)
            
            self.stats.platforms_found = len(platforms)
            
            # Update display with discovery results
            rom_files = sum(info.file_count for info in platforms.values())
            
            # Count actual ROM files in excluded and unknown directories
            excluded_files = 0
            if excluded:
                try:
                    # Safe unpacking with type checking
                    excluded_files = 0
                    for folder_name, value in excluded.items():
                        if isinstance(value, tuple) and len(value) == 2:
                            reason, file_count = value
                            if isinstance(file_count, int):
                                excluded_files += file_count
                            elif hasattr(file_count, '__len__'):  # If it's accidentally a list
                                excluded_files += len(file_count)
                                if debug_mode:
                                    print(f"DEBUG: WARNING - {folder_name} had list instead of int: {file_count}")
                            else:
                                if debug_mode:
                                    print(f"DEBUG: ERROR - {folder_name} has invalid file_count type: {type(file_count)}")
                        else:
                            if debug_mode:
                                print(f"DEBUG: ERROR - {folder_name} has invalid structure: {value}")
                except Exception as e:
                    if debug_mode:
                        print(f"DEBUG: ERROR unpacking excluded: {e}")
                        print(f"DEBUG: excluded contents: {excluded}")
                    excluded_files = 0
            
            # Calculate unknown files count with comprehensive debugging (same as analyze-only path)
            unknown_files = 0
            if unknown:
                debug_mode = getattr(self.args, 'debug_analysis', False) if hasattr(self, 'args') else False
                
                if debug_mode:
                    print(f"\nDEBUG: UNKNOWN FILES COUNT ANALYSIS (Interactive Mode)")
                    print(f"DEBUG: Found {len(unknown)} unknown folders to analyze...")
                    print(f"DEBUG: Source directory: {self.source_dir}")
                    print(f"DEBUG: ROM extensions: {sorted(list(ROM_EXTENSIONS))}")
                    
                self.analyzer.logger.info(f"UNKNOWN FILES COUNT DEBUGGING (Interactive Mode):")
                self.analyzer.logger.info(f"  Unknown folders to check: {len(unknown)}")
                self.analyzer.logger.info(f"  Source directory: {self.source_dir}")
                
                for unknown_folder in unknown:
                    unknown_dir_path = self.source_dir / unknown_folder
                    
                    # Log path construction details
                    self.analyzer.logger.info(f"  Checking folder: '{unknown_folder}'")
                    self.analyzer.logger.info(f"    Constructed path: {unknown_dir_path}")
                    self.analyzer.logger.info(f"    Path exists: {unknown_dir_path.exists()}")
                    
                    if unknown_dir_path.exists():
                        # Count files with detailed logging
                        all_files = []
                        rom_files = []
                        extensions_found = set()
                        
                        try:
                            for root, dirs, files in os.walk(unknown_dir_path):
                                for file in files:
                                    all_files.append(file)
                                    extension = Path(file).suffix.lower()
                                    extensions_found.add(extension)
                                    if extension in ROM_EXTENSIONS:
                                        rom_files.append(file)
                        except Exception as e:
                            self.analyzer.logger.error(f"    Error walking directory: {e}")
                            continue
                        
                        folder_count = len(rom_files)
                        unknown_files += folder_count
                        
                        # Log detailed results
                        self.analyzer.logger.info(f"    Total files: {len(all_files)}")
                        self.analyzer.logger.info(f"    ROM files: {folder_count}")
                        self.analyzer.logger.info(f"    Extensions found: {sorted(extensions_found)}")
                        
                        if debug_mode:
                            print(f"DEBUG: '{unknown_folder}'")
                            print(f"       Path: {unknown_dir_path}")
                            print(f"       Exists: {unknown_dir_path.exists()}")
                            print(f"       Total files: {len(all_files)}")
                            print(f"       ROM files: {folder_count}")
                            print(f"       Extensions: {sorted(extensions_found)}")
                            if folder_count != len(all_files):
                                non_rom_extensions = extensions_found - ROM_EXTENSIONS
                                print(f"       Non-ROM extensions: {sorted(non_rom_extensions)}")
                    else:
                        self.analyzer.logger.warning(f"    WARNING: Path does not exist!")
                        if debug_mode:
                            print(f"DEBUG: '{unknown_folder}' -> PATH DOES NOT EXIST!")
                
                self.analyzer.logger.info(f"TOTAL UNKNOWN FILES COUNTED (Interactive): {unknown_files}")
                if debug_mode:
                    print(f"DEBUG: TOTAL unknown files counted: {unknown_files}")
                    if unknown_files == 0 and len(unknown) > 0:
                        print(f"DEBUG: WARNING - Found {len(unknown)} unknown folders but 0 ROM files!")
                        print(f"DEBUG: This suggests either path issues or non-ROM file extensions")
            
            # DEBUG: Type checking before stats update to identify the list concatenation error
            debug_mode = getattr(self.args, 'debug_analysis', False) if hasattr(self, 'args') else False
            if debug_mode:
                print(f"\nDEBUG: TYPE ANALYSIS BEFORE STATS UPDATE")
                print(f"DEBUG: Type of rom_files: {type(rom_files).__name__}, value: {rom_files}")
                print(f"DEBUG: Type of excluded_files: {type(excluded_files).__name__}, value: {excluded_files}")
                print(f"DEBUG: Type of unknown_files: {type(unknown_files).__name__}, value: {unknown_files}")
                
                # Check if excluded_files is somehow a list
                if not isinstance(excluded_files, int):
                    print(f"ERROR: excluded_files is not an int! It's {type(excluded_files)}")
                    print(f"ERROR: excluded dict structure check:")
                    for folder, value in excluded.items():
                        print(f"    {folder}: {value} (type: {type(value)})")
                        if isinstance(value, tuple) and len(value) == 2:
                            print(f"      reason: {value[0]} (type: {type(value[0])})")
                            print(f"      file_count: {value[1]} (type: {type(value[1])})")
                    # Fallback to prevent crash
                    excluded_files = 0
                    print(f"DEBUG: Set excluded_files to 0 as fallback")
            
            progress_display.stats.update({
                'supported_platforms': len(platforms),
                'excluded_platforms': len(excluded),
                'unknown_platforms': len(unknown),
                'files_to_process': rom_files,
                'files_excluded': excluded_files,
                'files_unknown': unknown_files,
                'rom_files': rom_files,
                'non_rom_files': excluded_files + unknown_files,
                'total_files_discovered': rom_files + excluded_files + unknown_files,
                'total_directories_found': directory_stats['total_processed'],
                'directories_with_roms': directory_stats['directories_with_roms'],
                'empty_directories': directory_stats['empty_directories']
            })
            
            # Show discovery results
            # Note: Non-ROM extensions data is only available after file discovery (Phase 3)
            # For Phase 1 analysis, we show basic counts without file type breakdown
            progress_display.show_phase_discovery()
            
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
            
            # Show selection summary
            progress_display.show_phase_selection(len(selected_platforms))
            
            # Initialize platform progress tracking
            for platform in selected_platforms:
                progress_display.update_platform_progress(platform, 0, platforms[platform].file_count, 0)
            
            # Phase 3: File Processing
            progress_display.start_processing_phase()
            self.logger_progress.info("Phase 3: Processing ROM files...")
            self._process_selected_platforms(platforms, selected_platforms)
            
            # Phase 4: Generate Summary
            end_time = datetime.now()
            self.stats.processing_time = (end_time - start_time).total_seconds()
            
            # Update display with final statistics
            progress_display.stats['processing_time'] = self.stats.processing_time
            progress_display.stats['avg_rate'] = self.stats.total_unique_files / max(self.stats.processing_time, 0.1)
            progress_display.stats['files_to_process'] = self.stats.files_found
            progress_display.stats['files_copied'] = self.stats.files_copied
            progress_display.stats['files_renamed'] = self.stats.files_renamed_duplicates
            progress_display.stats['files_skipped'] = self.stats.files_skipped_duplicate
            progress_display.stats['files_failed'] = self.stats.errors
            progress_display.show_final_summary()
            
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
        
        # Update display stats for processing phase
        total_expected_files = sum(platforms[p].file_count for p in selected_platforms if p in platforms)
        
        # Log performance configuration
        cpu_count = os.cpu_count() or 1
        self.logger_performance.info(f"System CPU cores: {cpu_count}")
        self.logger_performance.info(f"I/O worker threads: {self.performance_processor.max_io_workers}")
        self.logger_performance.info(f"Hash chunk size: {self.performance_processor.hash_chunk_size:,} bytes")
        
        # Phase 1: Concurrent file discovery
        discovery_start = datetime.now()
        all_files = self.performance_processor.discover_files_concurrent(platforms, selected_platforms)
        discovery_time = (datetime.now() - discovery_start).total_seconds()
        
        # Log discovery completion (no console output)
        self.logger_performance.info(f"File discovery completed in {discovery_time:.2f} seconds")
        self.logger_performance.info(f"Discovery rate: {len(all_files) / max(discovery_time, 0.1):.1f} files/second")
        
        if not all_files:
            print("ℹ️  No ROM files found to process!")
            self.logger_progress.info("No ROM files found to process!")
            return
        
        # Phase 2: Adaptive file processing using AsyncFileCopyEngine
        processing_start = datetime.now()
        
        # Convert file list to folder-grouped structure for adaptive processing
        files_by_folder = self._group_files_by_folder(all_files, platforms)
        
        # Simple progress callback compatible with current AsyncFileCopyEngine
        processed_count = 0
        def progress_callback(file_desc):
            # Extract info from file description like "platform/filename"
            nonlocal processed_count
            processed_count += 1
            
            # Add to activity log
            timestamp = datetime.now().strftime("%H:%M:%S")
            progress_display.add_activity(timestamp, file_desc, "copied", "")
            
            # Update live progress
            elapsed = (datetime.now() - processing_start).total_seconds()
            rate = processed_count / max(elapsed, 0.1)
            eta = (len(all_files) - processed_count) / max(rate, 0.1)
            
            # Update average rate
            progress_display.stats['avg_rate'] = rate
            
            # Update display every 50 files to avoid flickering
            if processed_count % 50 == 0 or processed_count == len(all_files):
                progress_display.update_live_progress(
                    current=processed_count,
                    total=len(all_files),
                    rate=rate,
                    eta_seconds=eta,
                    elapsed=elapsed
                )
        
        processing_stats = self.async_copy_engine.copy_files_adaptive(
            files_by_folder, platforms, self.target_dir, progress_callback
        )
        processing_time = (datetime.now() - processing_start).total_seconds()
        
        # Update main stats (AsyncFileCopyEngine returns simplified stats)
        self.stats.files_found = len(all_files)
        self.stats.files_copied = processing_stats.files_copied
        self.stats.files_renamed_duplicates = processing_stats.files_renamed_duplicates
        self.stats.files_skipped_duplicate = processing_stats.files_skipped_duplicate
        self.stats.errors = processing_stats.errors
        
        # Update display stats with processing results
        progress_display.stats.update({
            'files_copied': processing_stats.files_copied,
            'files_renamed': getattr(processing_stats, 'files_renamed_duplicates', 0),
            'files_skipped': processing_stats.files_skipped_duplicate,
            'files_failed': processing_stats.errors,
            'processing_time': processing_time
        })
        
        # Log performance metrics
        total_time = (datetime.now() - start_time).total_seconds()
        self.logger_performance.info(f"Processing completed in {processing_time:.2f} seconds")
        self.logger_performance.info(f"Total processing time: {total_time:.2f} seconds")
        if processing_stats.files_copied > 0:
            self.logger_performance.info(f"Copy rate: {processing_stats.files_copied / max(processing_time, 0.1):.1f} files/second")
        
        # Final progress update
        self.logger_progress.info(f"[OK] Processing complete!")
        self.logger_progress.info(f"[STATS] Files copied: {processing_stats.files_copied:,}")
        self.logger_progress.info(f"[STATS] Files renamed (duplicates): {processing_stats.files_renamed_duplicates:,}")
        self.logger_progress.info(f"[STATS] Files replaced: {processing_stats.files_replaced:,}")
        self.logger_progress.info(f"[STATS] Files skipped (duplicates): {processing_stats.files_skipped_duplicate:,}")
        self.logger_progress.info(f"[STATS] Total unique files: {processing_stats.total_unique_files:,}")
        self.logger_progress.info(f"[STATS] Errors: {processing_stats.errors:,}")
        self.logger_progress.info(f"[TIME] Total time: {total_time:.2f} seconds")
    
    def _generate_comprehensive_summary(self) -> None:
        """Generate comprehensive processing summary"""
        summary_lines = [
            "=" * 80,
            "🎮 ENHANCED ROM ORGANIZER - PROCESSING SUMMARY 🎮",
            "=" * 80,
            f"📅 Timestamp: {datetime.now()}",
            f"⏱️  Processing Time: {self.stats.processing_time:.2f} seconds",
            f"🔧 Mode: {'DRY RUN' if self.dry_run else 'LIVE RUN'}",
            "",
            "📊 PROCESSING STATISTICS:",
            f"  🎯 Platforms Found: {self.stats.platforms_found}",
            f"  ✅ Platforms Selected: {len(self.stats.selected_platforms)}",
            "",
            "🔍 FILE DISCOVERY (Comprehensive):",
            f"  📁 Total Files Discovered: {getattr(self.performance_processor, 'total_files_discovered', 'N/A'):,}",
            f"  🎮 ROM Files (Processed): {self.stats.files_found:,}",
            f"  📄 Non-ROM Files (Skipped): {getattr(self.performance_processor, 'total_files_discovered', self.stats.files_found) - self.stats.files_found:,}" if hasattr(self.performance_processor, 'total_files_discovered') else "  📄 Non-ROM Files (Skipped): N/A",
            "",
            "✨ PROCESSING RESULTS:",
            f"  📥 Files Copied (New): {self.stats.files_copied:,}",
            f"  🔄 Files Renamed (Duplicates): {self.stats.files_renamed_duplicates:,}",
            f"  ♻️  Files Replaced: {self.stats.files_replaced:,}",
            f"  ⏭️  Files Skipped (Identical): {self.stats.files_skipped_duplicate:,}",
            f"  ❓ Files Skipped (Unknown): {self.stats.files_skipped_unknown:,}",
            f"  🎯 Total Unique Files: {self.stats.total_unique_files:,}",
            f"  📂 Folders Created: {len(self.stats.folders_created) if hasattr(self.stats, 'folders_created') else 'N/A'}",
            f"  ❌ Errors: {self.stats.errors:,}",
            "",
            "🎮 SELECTED PLATFORMS:",
        ]
        
        for platform in sorted(self.stats.selected_platforms):
            summary_lines.append(f"  ✅ {platform}")
        
        # Add duplicate handling section if any duplicates were renamed
        if self.stats.files_renamed_duplicates > 0:
            summary_lines.extend([
                "",
                "🔄 DUPLICATE FILENAME HANDLING:",
                f"  🛡️  Files Renamed to Prevent Overwrites: {self.stats.files_renamed_duplicates:,}",
                f"  📝 Naming Pattern: filename (n).ext or filename (hint).ext",
                f"  📋 Check operations log for specific rename decisions",
                f"  ⚠️  Data Loss Prevented: {self.stats.files_renamed_duplicates:,} files would have been overwritten!"
            ])
        
        if self.stats.processing_time > 0:
            files_per_second = self.stats.files_copied / self.stats.processing_time
            summary_lines.extend([
                "",
                "⚡ PERFORMANCE METRICS:",
                f"  🚀 Files per Second: {files_per_second:.1f}",
                f"  📊 Average File Size: Calculated during processing"
            ])
        
        summary_lines.extend([
            "",
            "📄 LOGS GENERATED:",
            f"  📝 [LOG] Operations: logs/operations_{self.comprehensive_logger.timestamp}.log",
            f"  📈 [STATS] Analysis: logs/analysis_{self.comprehensive_logger.timestamp}.log", 
            f"  🚨 [ERRORS] Errors: logs/errors_{self.comprehensive_logger.timestamp}.log",
            f"  📊 [PROGRESS] Progress: logs/progress_{self.comprehensive_logger.timestamp}.log",
            f"  📋 [LOG] Summary: logs/summary_{self.comprehensive_logger.timestamp}.log",
            f"  ⚡ [PERF] Performance: logs/performance_{self.comprehensive_logger.timestamp}.log",
            "",
            "🔧 PERFORMANCE OPTIMIZATIONS:",
            f"  🧵 [THREAD] Concurrent I/O workers: {self.performance_processor.max_io_workers}",
            f"  💾 [MEM] Memory-mapped hash calculation for large files (>10MB)",
            f"  🔄 [CYCLE] Chunked processing with {self.performance_processor.hash_chunk_size // 1024}KB chunks",
            f"  📊 [STATS] Thread-safe progress tracking every {self.performance_processor.progress_update_frequency} files",
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
    
    # Version argument (outputs version and exits)
    parser.add_argument('--version', '-v', 
                       action='version', 
                       version=f'%(prog)s {__version__} ({VERSION_DATE})')
    
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
                       help="Regional variant handling: 'consolidated' merges variants (NES+Famicom->nes), 'regional' keeps separate (default: consolidated)")
    parser.add_argument("--disable-subcategory-processing", action="store_true",
                       help="Disable subcategory consolidation preprocessing (for testing compatibility)")
    parser.add_argument("--subcategory-stats", action="store_true",
                       help="Show detailed subcategory processing statistics")
    parser.add_argument("--debug", action="store_true",
                       help="Enable comprehensive DEBUG logging for all components (file I/O, threading, WSL2 diagnostics)")
    parser.add_argument("--debug-analysis", action="store_true",
                       help="Enable detailed debug logging during analysis")
    parser.add_argument("--include-empty-dirs", action="store_true",
                       help="Process directories even without ROM files (useful for DAT collections)")
    
    # New concurrency and verification options
    parser.add_argument("--threads", type=int, choices=range(1, 9), metavar="[1-8]",
                       help="Number of concurrent threads (1-8). Default: 2 on Windows, 4 on Linux")
    parser.add_argument("--verify-copies", action="store_true",
                       help="Verify copied files with SHA1 hash after copying (adds overhead)")
    parser.add_argument("--skip-identical", action="store_true", default=True,
                       help="Skip files with identical SHA1 hashes (default: enabled)")
    parser.add_argument("--no-skip-identical", action="store_false", dest="skip_identical",
                       help="Always copy files even if SHA1 hashes match (force overwrite)")
    
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
    
    # Initialize global shutdown handler
    global shutdown_handler
    shutdown_handler = GracefulShutdownHandler()
    shutdown_handler.register()
    
    # Run organizer
    try:
        organizer = EnhancedROMOrganizer(
            source_dir=source_dir,
            target_dir=target_dir, 
            dry_run=args.dry_run,
            interactive=not args.no_interactive,
            regional_mode=args.regional_mode,
            debug=args.debug,
            args=args  # Pass args for subcategory processing options
        )
        
        # Pass shutdown handler to processor
        if hasattr(organizer, 'processor'):
            organizer.processor.shutdown_handler = shutdown_handler
        
        if args.analyze_only:
            # Just show analysis
            # Use debug options from args
            debug_mode = args.debug_analysis if hasattr(args, 'debug_analysis') else False
            include_empty_dirs = args.include_empty_dirs if hasattr(args, 'include_empty_dirs') else False
            
            platforms, excluded, unknown, directory_stats = organizer.analyzer.analyze_directory(debug_mode=debug_mode, include_empty_dirs=include_empty_dirs, target_dir=organizer.target_dir)
            
            # Calculate unknown files count with comprehensive debugging
            unknown_files_count = 0
            if unknown:
                if debug_mode:
                    print(f"\nDEBUG: UNKNOWN FILES COUNT ANALYSIS")
                    print(f"DEBUG: Found {len(unknown)} unknown folders to analyze...")
                    print(f"DEBUG: Source directory: {organizer.source_dir}")
                    print(f"DEBUG: ROM extensions: {sorted(list(ROM_EXTENSIONS))}")
                    
                analyzer.logger.info(f"UNKNOWN FILES COUNT DEBUGGING:")
                analyzer.logger.info(f"  Unknown folders to check: {len(unknown)}")
                analyzer.logger.info(f"  Source directory: {organizer.source_dir}")
                
                for unknown_folder in unknown:
                    unknown_dir_path = organizer.source_dir / unknown_folder
                    
                    # Log path construction details
                    analyzer.logger.info(f"  Checking folder: '{unknown_folder}'")
                    analyzer.logger.info(f"    Constructed path: {unknown_dir_path}")
                    analyzer.logger.info(f"    Path exists: {unknown_dir_path.exists()}")
                    
                    if unknown_dir_path.exists():
                        # Count files with detailed logging
                        all_files = []
                        rom_files = []
                        extensions_found = set()
                        
                        try:
                            for root, dirs, files in os.walk(unknown_dir_path):
                                for file in files:
                                    all_files.append(file)
                                    extension = Path(file).suffix.lower()
                                    extensions_found.add(extension)
                                    if extension in ROM_EXTENSIONS:
                                        rom_files.append(file)
                        except Exception as e:
                            analyzer.logger.error(f"    Error walking directory: {e}")
                            continue
                        
                        folder_count = len(rom_files)
                        unknown_files_count += folder_count
                        
                        # Log detailed results
                        analyzer.logger.info(f"    Total files: {len(all_files)}")
                        analyzer.logger.info(f"    ROM files: {folder_count}")
                        analyzer.logger.info(f"    Extensions found: {sorted(extensions_found)}")
                        
                        if debug_mode:
                            print(f"DEBUG: '{unknown_folder}'")
                            print(f"       Path: {unknown_dir_path}")
                            print(f"       Exists: {unknown_dir_path.exists()}")
                            print(f"       Total files: {len(all_files)}")
                            print(f"       ROM files: {folder_count}")
                            print(f"       Extensions: {sorted(extensions_found)}")
                            if folder_count != len(all_files):
                                non_rom_extensions = extensions_found - ROM_EXTENSIONS
                                print(f"       Non-ROM extensions: {sorted(non_rom_extensions)}")
                    else:
                        analyzer.logger.warning(f"    WARNING: Path does not exist!")
                        if debug_mode:
                            print(f"DEBUG: '{unknown_folder}' -> PATH DOES NOT EXIST!")
                
                analyzer.logger.info(f"TOTAL UNKNOWN FILES COUNTED: {unknown_files_count}")
                if debug_mode:
                    print(f"DEBUG: TOTAL unknown files counted: {unknown_files_count}")
                    if unknown_files_count == 0 and len(unknown) > 0:
                        print(f"DEBUG: WARNING - Found {len(unknown)} unknown folders but 0 ROM files!")
                        print(f"DEBUG: This suggests either path issues or non-ROM file extensions")
            
            organizer.selector.show_analysis_summary(platforms, excluded, unknown, unknown_files_count)
            
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
            
            # Calculate comprehensive statistics
            unique_files_processed = stats.total_unique_files
            
            if unique_files_processed > 0:
                print(f"\n🎉 Success! Processing Complete")
                
                # FIXED: Log final success statistics to summary log
                organizer.logger_summary.info("🎉 SUCCESS: ROM Processing Complete")
                organizer.logger_summary.info(f"📊 Final File Statistics:")
                organizer.logger_summary.info(f"   📄 New files copied: {stats.files_copied:,}")
                
                print(f"\n📊 File Statistics:")
                print(f"   📁 Total files discovered: {stats.files_found:,}")
                print(f"   ⏭️  Files skipped (identical): {stats.files_skipped_duplicate:,}")
                print(f"   📄 New files copied: {stats.files_copied:,}")
                if stats.files_renamed_duplicates > 0:
                    print(f"   📝 Duplicates renamed: {stats.files_renamed_duplicates:,} (prevented overwrites!)")
                    organizer.logger_summary.info(f"   📝 Duplicates renamed: {stats.files_renamed_duplicates:,} (prevented overwrites!)")
                if stats.files_replaced > 0:
                    print(f"   🔄 Files replaced (updates): {stats.files_replaced:,}")
                    organizer.logger_summary.info(f"   🔄 Files replaced (updates): {stats.files_replaced:,}")
                print(f"   ✅ Unique files copied: {unique_files_processed:,}")
                
                # Log comprehensive statistics
                organizer.logger_summary.info(f"   [DIR] Total files discovered: {stats.files_found:,}")
                organizer.logger_summary.info(f"   [SKIP] Files skipped (identical): {stats.files_skipped_duplicate:,}")
                if stats.files_replaced > 0:
                    organizer.logger_summary.info(f"   🔄 Files replaced (updates): {stats.files_replaced:,}")
                organizer.logger_summary.info(f"   [OK] Unique files copied: {unique_files_processed:,}")
                
                # Validation check (only if not dry run)
                if not args.dry_run:
                    try:
                        actual_files_in_target = count_files_in_directory(target_dir)
                        print(f"   📁 Files in target directory: {actual_files_in_target:,}")
                        if actual_files_in_target != unique_files_processed:
                            print(f"   ⚠️  WARNING: Count mismatch!")
                            print(f"      Expected: {unique_files_processed:,}")
                            print(f"      Found: {actual_files_in_target:,}")
                            # FIXED: Log critical count mismatch warning to summary log
                            organizer.logger_summary.warning(f"[WARNING] CRITICAL: File count mismatch detected!")
                            organizer.logger_summary.warning(f"Expected files processed: {unique_files_processed:,}")
                            organizer.logger_summary.warning(f"Actual files in target: {actual_files_in_target:,}")
                            organizer.logger_summary.warning(f"Discrepancy: {unique_files_processed - actual_files_in_target:,} files missing")
                    except Exception:
                        pass  # Don't fail on validation
                
                print(f"\n📂 Organization Statistics:")
                if hasattr(stats, 'folders_created'):
                    print(f"   🗂️  Folders created: {len(stats.folders_created)}")
                print(f"   🎮 Platforms organized: {len(stats.selected_platforms)}")
                print(f"   🌐 Regional mode: {args.regional_mode}")
                
            elif args.dry_run:
                print(f"\n📋 Dry run complete")
                print(f"   📄 Would copy: {stats.files_copied:,} files")
                if stats.files_renamed_duplicates > 0:
                    print(f"   📝 Would rename: {stats.files_renamed_duplicates:,} duplicates")
                print(f"   🌐 Regional mode: {args.regional_mode}")
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
