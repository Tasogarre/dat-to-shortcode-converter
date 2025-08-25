## Question: Organising Retro Game ROMs in Consolidated vs Region-Separated Structures

### Executive Summary
Provide flexible, rule-based heuristics that let you toggle between:
1. **Consolidated structure**: Group closely related hardware and regional variants into one platform folder (e.g., `nes` includes NES + Famicom).
2. **Region-separated structure**: Separate into distinct folders for each regional or hardware variant (e.g., `nes`, `famicom`, `fds`).
3. **Always** use standardised emulator shortcode folder structures and names that work for EmulationStation, RetroPie, ArkOS, Batocera, and other emulation frontends.

These rules balance frontend compatibility (RetroArch, ArkOS) and collector-grade organisation without country-level subfolders.

***

## 1. Heuristics for Grouping vs Splitting

| Decision Factor               | Consolidated Structure                          | Region-Separated Structure                                        |
|-------------------------------|-------------------------------------------------|--------------------------------------------------------------------|
| Hardware Core & BIOS          | Single folder if same BIOS requirement.         | Split if different BIOS (e.g., PC-Engine vs TurboGrafx-16 BIOS).  |
| Form Factor (Cartridge vs Disk) | Merge if frontend treats them identically.     | Split if metadata scraper needs distinct extension (e.g., `.nes` vs `.fds`). |
| Regional Revision              | Merge if ROM header region byte is interchangeable across emulators. | Split if region locks (e.g., NTSC-J Famicom vs NTSC-U NES) affect compatibility. |
| Naming Conventions             | Consolidate based on core emulator system name. | Use original console branding (e.g., `famicom`, `sfc`). |

***

## 2. Practical Rules and Examples

These are non-exhaustive and used for illustration.

### 2.1. NES & Famicom
- **Consolidated** (`nes` folder) when:
  - Cartridge systems can be consolidated into a single folder without hardware issues.
- **Separate** when:
  - You have Famicom Disk System `.fds` images: use `fds` to ensure the FDS BIOS loads correctly.
  - Precise metadata needed: use `nes` for cartridges, `famicom` for Nippon-only releases.

### 2.2. SNES & Super Famicom
- **Consolidated** (`snes` folder) when:
  - Using bsnes/higan core that ignores region header differences.
  - You don’t require split cover-art sets.
- **Separate** when:
  - Collector focus: `snes` vs `sfc` to maintain Japanese vs Western branding.
  - Region-locked DSP-1/2 co-processor games: separate to prevent loading incorrect region patch.

### 2.3. Other Popular Variants
- **PC-Engine & TurboGrafx-16**
  - Consolidate as `pcengine` if using a universal core and common BIOS.
  - Split into `pcengine` (HuCard) vs `pcenginecd` for CD titles.
- **Game Boy / Game Boy Color / Game Boy Advance**
  - Consolidate all into their respective `gb`, `gbc`, `gba` folders in all scenarios.
- **Mega Drive & Genesis**
  - Consolidate under `genesis` if using a unified core.
  - Split into `genesis` vs `megadrive` only if you require separate art or region tags.

***

## 3. Common Pitfalls and Edge Cases

1. **Homebrew vs Official**
   - For any folders that mention `homebrew`, `hacks` (or `hack`), `prototypes` or similar, separate them into a dedicated `…-homebrew` (or equivalent such as `hacks` etc.) variant folder.

***

## 4. Implementation Strategy

1. **Rule Definition File**
   - Maintain a separate JSON/YAML config file with platform entries:
     ```yaml
     nes:
       consolidate: true
       variants:
         - famicom
     ```
2. **Toggle Flags**
   - `--consolidated` vs `--separate` to build target directory.

***