#!/usr/bin/env python3
"""
Specialized pattern handling for Good tools and MAME/FinalBurn Neo collections
Handles the complex naming patterns used by these ROM management tools
"""

import re
import logging
from typing import Optional, Tuple, Dict, Any

class GoodPatternHandler:
    """
    Handles specialized patterns for GoodTools collections
    GoodTools uses abbreviated platform codes that need mapping to standard shortcodes
    """
    
    # Mapping of Good tool codes to platform shortcodes
    GOOD_TOOL_MAPPINGS = {
        'NES': ('nes', 'Nintendo Entertainment System'),
        'SNES': ('snes', 'Super Nintendo Entertainment System'), 
        'N64': ('n64', 'Nintendo 64'),
        'Gen': ('genesis', 'Sega Genesis'),
        'SMS': ('mastersystem', 'Sega Master System'),
        'GG': ('gamegear', 'Sega Game Gear'),
        '32X': ('sega32x', 'Sega 32X'),
        'MCD': ('segacd', 'Sega CD'),
        'SAT': ('saturn', 'Sega Saturn'),
        'PCE': ('pcengine', 'PC Engine'),
        'Lynx': ('atarilynx', 'Atari Lynx'),
        '5200': ('atari5200', 'Atari 5200'),
        '7800': ('atari7800', 'Atari 7800'),
        '2600': ('atari2600', 'Atari 2600'),
        'A26': ('atari2600', 'Atari 2600'),
        'A78': ('atari7800', 'Atari 7800'),
        'A52': ('atari5200', 'Atari 5200'),
        'GBC': ('gbc', 'Game Boy Color'),
        'GB': ('gb', 'Game Boy'),
        'GBA': ('gba', 'Game Boy Advance'),
        'COL': ('coleco', 'ColecoVision'),
        'INTV': ('intellivision', 'Mattel Intellivision'),
    }
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
    
    def match_good_pattern(self, folder_name: str) -> Optional[Tuple[str, str]]:
        """
        Match Good tool patterns like 'GoodNES v3.27' or 'GoodN64 (2022-01-15)'
        Returns (shortcode, display_name) tuple if matched
        """
        # Pattern for Good tool naming: Good[Platform] [version/date info]
        good_match = re.match(r'^Good([A-Z0-9]+)\b.*', folder_name, re.IGNORECASE)
        
        if good_match:
            platform_code = good_match.group(1).upper()
            
            if platform_code in self.GOOD_TOOL_MAPPINGS:
                shortcode, display_name = self.GOOD_TOOL_MAPPINGS[platform_code]
                self.logger.debug(f"Good tool matched: '{folder_name}' -> {platform_code} -> ({shortcode}, {display_name})")
                return (shortcode, display_name)
            else:
                self.logger.warning(f"Unknown Good tool platform code: {platform_code} in '{folder_name}'")
                return ("unknown", f"Good {platform_code} Collection")
        
        return None


class MAMEPatternHandler:
    """
    Handles MAME and FinalBurn Neo pattern matching
    These tools often include the target platform in their naming
    """
    
    # FinalBurn Neo platform mappings
    FINALBURN_MAPPINGS = {
        'NES Games': ('nes', 'Nintendo Entertainment System'),
        'SNES Games': ('snes', 'Super Nintendo Entertainment System'),
        'Genesis Games': ('genesis', 'Sega Genesis'),
        'Master System Games': ('mastersystem', 'Sega Master System'),
        'Game Gear Games': ('gamegear', 'Sega Game Gear'),
        'PC Engine Games': ('pcengine', 'PC Engine'),
        'Neo Geo Games': ('neogeo', 'Neo Geo'),
        'CPS Games': ('arcade', 'Arcade (CPS)'),
        'Arcade Games': ('arcade', 'Arcade'),
    }
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
    
    def match_finalburn_pattern(self, folder_name: str) -> Optional[Tuple[str, str]]:
        """
        Match FinalBurn Neo patterns like 'FinalBurn Neo - NES Games'
        Returns (shortcode, display_name) tuple if matched
        """
        fb_match = re.match(r'^FinalBurn Neo - (.+)$', folder_name, re.IGNORECASE)
        
        if fb_match:
            platform_desc = fb_match.group(1)
            
            if platform_desc in self.FINALBURN_MAPPINGS:
                shortcode, display_name = self.FINALBURN_MAPPINGS[platform_desc]
                self.logger.debug(f"FinalBurn Neo matched: '{folder_name}' -> {platform_desc} -> ({shortcode}, {display_name})")
                return (shortcode, display_name)
            else:
                # Fallback for unknown FinalBurn Neo patterns
                self.logger.info(f"Unknown FinalBurn Neo pattern: {platform_desc} in '{folder_name}', defaulting to arcade")
                return ("arcade", f"Arcade (FinalBurn Neo {platform_desc})")
        
        return None
    
    def match_mame_pattern(self, folder_name: str) -> Optional[Tuple[str, str]]:
        """
        Match MAME patterns - typically all arcade content
        Returns (shortcode, display_name) tuple if matched
        """
        if re.match(r'^MAME.*', folder_name, re.IGNORECASE):
            self.logger.debug(f"MAME pattern matched: '{folder_name}' -> arcade")
            return ("arcade", "Arcade (MAME)")
        
        return None


class SpecializedPatternProcessor:
    """
    Coordinating processor for all specialized pattern handlers
    Processes Good tools, MAME, and FinalBurn Neo patterns in priority order
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.good_handler = GoodPatternHandler(self.logger)
        self.mame_handler = MAMEPatternHandler(self.logger)
    
    def process(self, folder_name: str) -> Tuple[Optional[Tuple[str, str]], Dict[str, Any]]:
        """
        Process specialized patterns with priority:
        1. Good tools (highest priority - very specific patterns)
        2. FinalBurn Neo (medium priority - includes platform in name)  
        3. MAME (lowest priority - broad arcade catch-all)
        
        Returns ((shortcode, display_name), context) tuple
        Context includes information about which handler matched
        """
        context = {
            'handler_used': None,
            'pattern_type': None,
            'confidence': 0.0
        }
        
        # Try Good tools first (highest confidence)
        result = self.good_handler.match_good_pattern(folder_name)
        if result:
            context.update({
                'handler_used': 'good_tools',
                'pattern_type': 'good_collection',
                'confidence': 0.95
            })
            return (result, context)
        
        # Try FinalBurn Neo patterns (medium confidence)
        result = self.mame_handler.match_finalburn_pattern(folder_name)
        if result:
            context.update({
                'handler_used': 'finalburn_neo',
                'pattern_type': 'finalburn_collection',
                'confidence': 0.85
            })
            return (result, context)
        
        # Try MAME patterns (lower confidence)
        result = self.mame_handler.match_mame_pattern(folder_name)
        if result:
            context.update({
                'handler_used': 'mame',
                'pattern_type': 'mame_collection', 
                'confidence': 0.75
            })
            return (result, context)
        
        # No specialized pattern matched
        return (None, context)
    
    def get_stats(self) -> Dict[str, int]:
        """Return statistics about pattern matching"""
        return {
            'good_tools_supported': len(self.good_handler.GOOD_TOOL_MAPPINGS),
            'finalburn_mappings': len(self.mame_handler.FINALBURN_MAPPINGS),
        }


# Example usage and testing
if __name__ == "__main__":
    import logging
    
    # Configure logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Create processor
    processor = SpecializedPatternProcessor()
    
    # Test patterns
    test_patterns = [
        "GoodNES v3.27",
        "GoodN64 (2022-01-15)",
        "Good32X v1.02",
        "GoodUnknown v1.0",  # Should handle unknown codes gracefully
        "FinalBurn Neo - NES Games",
        "FinalBurn Neo - CPS Games", 
        "FinalBurn Neo - Unknown Platform",  # Should fallback to arcade
        "MAME 0.245",
        "MAME Complete Collection",
        "Regular DAT folder"  # Should not match
    ]
    
    print("=== Specialized Pattern Handler Testing ===")
    for pattern in test_patterns:
        result, context = processor.process(pattern)
        if result:
            shortcode, display_name = result
            print(f"✅ '{pattern}' -> {shortcode} ({display_name}) [Handler: {context['handler_used']}, Confidence: {context['confidence']}]")
        else:
            print(f"❌ '{pattern}' -> No match")
    
    print(f"\nStats: {processor.get_stats()}")