#!/usr/bin/env python3
"""
Subcategory Consolidation Handler for DAT Pattern Processing
Implements Chain of Responsibility pattern for DAT folder name preprocessing
"""

import re
import logging
from typing import Optional, Dict, Tuple, List
from abc import ABC, abstractmethod


class ProcessingHandler(ABC):
    """Base handler class for Chain of Responsibility pattern"""
    
    def __init__(self):
        self._next_handler: Optional['ProcessingHandler'] = None
        
    def set_next(self, handler: 'ProcessingHandler') -> 'ProcessingHandler':
        """Set the next handler in the chain"""
        self._next_handler = handler
        return handler
    
    @abstractmethod
    def handle(self, folder_name: str, context: Dict) -> str:
        """Process folder name and pass to next handler if needed"""
        pass
    
    def _pass_to_next(self, folder_name: str, context: Dict) -> str:
        """Pass processing to next handler in chain"""
        if self._next_handler:
            return self._next_handler.handle(folder_name, context)
        return folder_name


class SubcategoryConsolidationHandler(ProcessingHandler):
    """Consolidates subcategory patterns like 'Platform - Games/Applications/Firmware'"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__()
        self.logger = logger or logging.getLogger(__name__)
        
        # Subcategory patterns to strip (ordered by specificity)
        self.subcategory_patterns = [
            # Multi-level subcategories (most specific first)
            r"^(.+?)\s+-\s+\w+\s+-\s+(Games|Applications|Firmware|Educational|Various)\s+-\s+\[.+?\]\s*.*$",
            r"^(.+?)\s+-\s+\w+\s+-\s+(Games|Applications|Firmware|Educational|Various)\s*.*$",
            # Format-specific subcategories  
            r"^(.+?)\s+-\s+(Games|Applications|Firmware|Educational|Compilations|Coverdisks|Samplers|Operating Systems|Demos|Various)\s+-\s+\[.+?\]\s*.*$",
            # Standard subcategories
            r"^(.+?)\s+-\s+(Games|Applications|Firmware|Educational|Compilations|Coverdisks|Samplers|Operating Systems|Demos|Various)\s*.*$",
        ]
    
    def handle(self, folder_name: str, context: Dict) -> str:
        """Consolidate subcategory patterns"""
        original_name = folder_name
        
        for pattern in self.subcategory_patterns:
            match = re.match(pattern, folder_name, re.IGNORECASE)
            if match:
                # Extract the base platform name
                base_platform = match.group(1).strip()
                
                # Log the consolidation decision
                if self.logger:
                    self.logger.debug(f"Subcategory consolidation: '{original_name}' → '{base_platform}'")
                
                # Update context for downstream handlers
                context['subcategory_consolidated'] = True
                context['original_subcategory'] = original_name
                context['consolidation_type'] = 'subcategory'
                
                return self._pass_to_next(base_platform, context)
        
        # No subcategory found, pass through unchanged
        return self._pass_to_next(folder_name, context)


class FormatIndicatorHandler(ProcessingHandler):
    """Strips format indicators like [ROM], [BIN], [GBC]"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__()
        self.logger = logger or logging.getLogger(__name__)
        
        # Format indicator patterns to remove
        self.format_patterns = [
            r"\s*-\s*\[.+?\]\s*",  # Remove " - [FORMAT]" patterns
            r"\s*\[.+?\]\s*",      # Remove "[FORMAT]" patterns
            r"\s*\(.+?\)\s*$",     # Remove trailing "(Retool)", "(Parent-Clone)" etc.
        ]
    
    def handle(self, folder_name: str, context: Dict) -> str:
        """Strip format indicators"""
        processed_name = folder_name
        
        for pattern in self.format_patterns:
            new_name = re.sub(pattern, "", processed_name)
            if new_name != processed_name:
                if self.logger:
                    self.logger.debug(f"Format indicator removed: '{processed_name}' → '{new_name.strip()}'")
                processed_name = new_name.strip()
                
                # Update context
                context['format_stripped'] = True
        
        return self._pass_to_next(processed_name, context)


class PublisherDisambiguationHandler(ProcessingHandler):
    """Handles publisher disambiguation like 'Microsoft - MSX' vs 'MSX MSX'"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__()
        self.logger = logger or logging.getLogger(__name__)
        
        # Publisher patterns to normalize (ordered by specificity)
        self.publisher_patterns = [
            # Microsoft MSX variants (most specific)
            (r"^Microsoft\s+-\s+(MSX.*)$", r"\1"),
            # Only strip publisher when it's clearly redundant
            # Keep "Nintendo - Game Boy" as is, only strip when subcategory follows
        ]
    
    def handle(self, folder_name: str, context: Dict) -> str:
        """Normalize publisher prefixes"""
        processed_name = folder_name
        
        for pattern, replacement in self.publisher_patterns:
            new_name = re.sub(pattern, replacement, processed_name, flags=re.IGNORECASE)
            if new_name != processed_name:
                if self.logger:
                    self.logger.debug(f"Publisher normalized: '{processed_name}' → '{new_name}'")
                processed_name = new_name
                
                # Update context
                context['publisher_normalized'] = True
                break
        
        return self._pass_to_next(processed_name, context)


class SubcategoryProcessor:
    """Main processor that orchestrates the subcategory consolidation chain"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        
        # Build the processing chain
        self.subcategory_handler = SubcategoryConsolidationHandler(self.logger)
        self.format_handler = FormatIndicatorHandler(self.logger)
        self.publisher_handler = PublisherDisambiguationHandler(self.logger)
        
        # Chain the handlers together
        self.subcategory_handler.set_next(self.format_handler).set_next(self.publisher_handler)
        
        # Statistics tracking
        self.stats = {
            'processed_count': 0,
            'subcategory_consolidated': 0,
            'format_stripped': 0,
            'publisher_normalized': 0,
            'unchanged': 0
        }
    
    def process(self, folder_name: str) -> Tuple[str, Dict]:
        """Process a folder name through the consolidation chain"""
        context = {
            'subcategory_consolidated': False,
            'format_stripped': False,
            'publisher_normalized': False,
            'original_name': folder_name
        }
        
        # Run through the processing chain
        processed_name = self.subcategory_handler.handle(folder_name, context)
        
        # Update statistics
        self.stats['processed_count'] += 1
        if context.get('subcategory_consolidated'):
            self.stats['subcategory_consolidated'] += 1
        if context.get('format_stripped'):
            self.stats['format_stripped'] += 1
        if context.get('publisher_normalized'):
            self.stats['publisher_normalized'] += 1
        if processed_name == folder_name:
            self.stats['unchanged'] += 1
        
        return processed_name, context
    
    def get_statistics(self) -> Dict:
        """Get processing statistics"""
        return self.stats.copy()
    
    def log_statistics(self) -> None:
        """Log processing statistics"""
        if self.logger:
            self.logger.info("=== Subcategory Processing Statistics ===")
            self.logger.info(f"Total processed: {self.stats['processed_count']}")
            self.logger.info(f"Subcategory consolidated: {self.stats['subcategory_consolidated']}")
            self.logger.info(f"Format indicators stripped: {self.stats['format_stripped']}")
            self.logger.info(f"Publishers normalized: {self.stats['publisher_normalized']}")
            self.logger.info(f"Unchanged: {self.stats['unchanged']}")


# Test function for validation
def test_subcategory_processor():
    """Test the subcategory processor with sample patterns"""
    processor = SubcategoryProcessor()
    
    # Test cases from real DAT patterns
    test_cases = [
        # Subcategory consolidation
        ("Atari 2600 & VCS - Games (Retool)", "Atari 2600 & VCS"),
        ("Nintendo Game Boy - Applications (Retool)", "Nintendo Game Boy"),
        ("Sega Mark III & Master System - Firmware (Retool)", "Sega Mark III & Master System"),
        
        # Format indicator removal
        ("Atari 8bit - Games - [BIN] (Retool)", "Atari 8bit"),
        ("Nintendo Famicom & Entertainment System - Games - [NES] (Retool)", "Nintendo Famicom & Entertainment System"),
        
        # Publisher disambiguation
        ("Microsoft - MSX (Parent-Clone) (Retool)", "MSX"),
        ("Microsoft - MSX2 (Retool)", "MSX2"),
        
        # Complex cases
        ("Bandai WonderSwan - Applications (Retool)", "Bandai WonderSwan"),
        ("3DO 3DO Interactive Multiplayer - Firmware (Retool)", "3DO 3DO Interactive Multiplayer"),
        
        # Should remain unchanged
        ("Nintendo - Nintendo Entertainment System (Retool)", "Nintendo - Nintendo Entertainment System"),
        ("Sega - Mega Drive - Genesis (Retool)", "Sega - Mega Drive - Genesis"),
    ]
    
    print("=== Subcategory Processor Test Results ===")
    for original, expected in test_cases:
        processed, context = processor.process(original)
        status = "✅ PASS" if processed == expected else "❌ FAIL"
        print(f"{status} '{original}' → '{processed}'")
        if processed != expected:
            print(f"     Expected: '{expected}'")
    
    print("\n=== Processing Statistics ===")
    stats = processor.get_statistics()
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    test_subcategory_processor()