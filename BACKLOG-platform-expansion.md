# Platform Support Expansion Backlog - 2025-08-25

## 🚨 CRITICAL UNRESOLVED ISSUES

### WSL2 Incompatibility - BLOCKING ISSUE
**Status**: ❌ **UNRESOLVED**  
**Priority**: P0 (Critical)  
**Impact**: Complete failure on WSL2 systems with large file collections

**Problem**: Script hangs unpredictably during file processing on WSL2 `/mnt/` paths
**Root Cause**: WSL2's 9p protocol has fundamental limitations that cannot be overcome

**Failed Fix Attempts**:
- ❌ Threading-based timeout mechanisms  
- ❌ Chunked processing with recovery pauses
- ❌ Single-threaded mode with delays
- ❌ Enhanced retry logic

**Current Workaround**: Users must run from Windows directly, not WSL2

## Current Status
- ✅ **Coverage**: 93.4% (240/257 DAT patterns)  
- ✅ **Good Tools Support**: 30 platform codes
- ✅ **Recent Fixes**: All critical Windows compatibility issues resolved, directory contention eliminated
- ✅ **Production Ready**: 100% validation success rate, folder-level threading architecture
- ❌ **WSL2 Support**: CRITICAL BLOCKER - high I/O error rates on Windows mounts

## Medium Priority Platform Additions

### MSX Variants (Research Required)
- **MSX TurboR** - Directory name pattern: "MSX TurboR"
  - EmulationStation support: Available via RetroArch cores (blueMSX, fMSX)
  - Proposed mapping: `msx` or dedicated `msxturbo` shortcode
  - Research needed: Confirm EmulationStation shortcode standards

- **MSX2+** - Directory name pattern: "MSX MSX2+"  
  - EmulationStation support: Available via RetroArch cores
  - Proposed mapping: `msx` or `msx2` depending on platform standards
  - Research needed: Whether separate from MSX2 or combined

### Nintendo Systems
- **Nintendo Satellaview** - Directory name pattern: "Nintendo - Satellaview"
  - EmulationStation support: Via SNES9x emulator (Satellaview is Super Famicom add-on)
  - Proposed mapping: `satellaview` or `snes` (subfolder approach)
  - Research needed: EmulationStation shortcode conventions for add-on systems

### Computer Systems  
- **NEC PC-8801** - Directory name pattern: "NEC PC-8801"
  - EmulationStation support: Available via QUASI88 RetroArch core
  - Proposed mapping: `pc88` or `pc8801`
  - Research needed: Confirm shortcode and test core compatibility

## Low Priority Platform Additions

### Generic/Ambiguous Systems
- **IBM PCjr** - Directory name pattern: "IBM PCjr"
  - EmulationStation support: Via DOS/PC emulation
  - Proposed mapping: `pc` or `pcjr`
  - Priority: Low - edge case system with limited software library

- **System** - Directory name pattern: "System (Retool)"
  - Status: Generic designation, unclear what platform this represents
  - Action needed: Research source to determine actual platform
  - Priority: Low - may be data artifact

### Excluded Systems (Keep Excluded)
These systems are intentionally excluded due to limited/no EmulationStation support:
- Vectrex (limited support) - ✅ Now supported via Good Tools mapping  
- Odyssey 2 / Videopac (limited support)
- Dragon Data systems (not supported)
- Pokitto (not supported)

## Implementation Guidelines

### For Medium Priority Items:
1. **Research EmulationStation shortcode standards** using official documentation
2. **Test RetroArch core compatibility** for computer systems
3. **Add pattern mappings** to `PLATFORM_MAPPINGS` in `dat_to_shortcode_converter.py`
4. **Update specialized handlers** if applicable (Good Tools, MAME, etc.)
5. **Test with real ROM collections** if available
6. **Update documentation** (README.md, CLAUDE.md)

### For Low Priority Items:
1. **Investigate source data** to clarify ambiguous designations
2. **Assess user demand** through community feedback
3. **Consider implementation effort vs. benefit**

## Research Resources
- EmulationStation documentation: System configuration guides
- RetroArch documentation: Core compatibility matrices  
- Community forums: RetroPie, Batocera, ArkOS user experiences
- ROM preservation communities: No-Intro, TOSEC naming conventions

## Success Metrics
- Target: 95%+ pattern coverage (244+ patterns of 257 total)
- Performance: Maintain sub-millisecond pattern matching for 90% of cases
- Quality: 100% test suite success rate maintained
- User impact: Eliminate remaining legitimate unknown platforms

## Next Steps
1. Begin with Nintendo Satellaview research (highest user demand)
2. MSX variants investigation (good EmulationStation support established)
3. Computer systems research (requires core compatibility testing)
4. Generic systems clarification (lowest priority)

---

**Last Updated:** 2025-08-25  
**Next Review:** After implementing 2-3 medium priority items or when user feedback indicates priority changes

## Recent Developments (August 2025)
- ✅ **Critical Bug Resolution**: All Windows compatibility issues resolved, including directory contention
- ✅ **Architecture Enhancement**: Implemented folder-level threading to prevent 0-byte file creation
- ✅ **Production Readiness**: Achieved 100% validation success rate across all test scenarios
- 🔍 **WSL2 Investigation**: Detailed analysis of 9p protocol limitations documented in local issues register and GitHub issue #2