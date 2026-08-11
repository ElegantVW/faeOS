# Week 1 Syllabus — Hardware Manufacturing Fundamentals
**Course:** 5-Year Doctorate-Level Hardware Manufacturing Program  
**Target:** RK3588 carrier board + custom case + immutable faeOS image  
**Schedule:** 5 days/week × 3 hrs/day (Theory 1.5h, Lab 1h, Outdoor/Study 0.5h)  
**Budget:** €1,000 tools (phased); all learning via free resources  

---

## Day 1 (Monday) — Course Orientation & Semiconductor Physics Refresher

### Theory (1.5h)
- **Course structure & goals**: 300 credits / 260 weeks / 5 product lines shipped
- **Hardware target**: RK3588 SoC (ARM Cortex-A76×4 + A55×4, Mali-G610, NPU 6 TOPS)
- **Semiconductor basics**: Si crystal structure, doping (n/p-type), bandgap, Fermi level
- **PN junction**: Depletion region, forward/reverse bias, I-V curve, diode equation
- **MOSFET physics**: MOS capacitor, threshold voltage, inversion layer, I<sub>D</sub>-V<sub>GS</sub>/V<sub>DS</sub>

**Free Resources:**
- *Semiconductor Physics* — MIT 6.007 OpenCourseWare (lecture notes, problem sets)
- *MOSFET Operation* — All About Circuits textbook (vol. 3, ch. 6)
- *RK3588 Datasheet* — Rockchip official (public, 200+ pages)

### Lab (1h)
- **LTSpice tutorial**: Install, schematic capture, DC sweep of diode & MOSFET
- Simulate: 1N4148 I-V curve, 2N7000 V<sub>GS(th)</sub> extraction, CMOS inverter VTC
- Export plots → `week1/day1_spice/` for portfolio

### Outdoor/Study (0.5h)
- Read: *The Transistor* (IEEE Milestone article, free PDF)
- Watch: Ben Eater "How Transistors Work" (YouTube, 15 min)

---

## Day 2 (Tuesday) — PCB Design Fundamentals & KiCad Mastery

### Theory (1.5h)
- **PCB stackup**: FR-4 properties, copper weight, dielectric constant, impedance control
- **Trace geometry**: Width/space for 50Ω single-ended, 90Ω/100Ω differential
- **Via types**: Through, blind, buried, microvia; aspect ratio limits
- **Design rules**: IPC-2221 (free summary), current capacity, thermal relief
- **KiCad 8 workflow**: Schematic → Footprint → PCB → DRC → Gerber/Drill/Assembly

**Free Resources:**
- *KiCad 8 Official Tutorial* (kicad.org/doc)
- *IPC-2221 Design Guide Summary* — Sierra Circuits / Eurocircuits free whitepapers
- *High-Speed PCB Design* — Rick Hartley notes (free PDF via Altium/SI-list archives)
- *RK3588 PCB Layout Guide* — Rockchip application note (request via distributor or GitHub mirrors)

### Lab (1h)
- **KiCad project**: Create `rk3588_carrier` project
- Draw: Power input (USB-C PD 5V/3A), buck converter (MP2359), LDO (AP2112 3.3V/1.8V)
- Place: RK3588 BGA footprint (19×19mm, 0.65mm pitch, 361 balls — use ultra-libarian free symbol)
- Route: DDR4 x32 (2×16-bit) — length match ±50ps, 40Ω single-ended
- Run DRC → export Gerbers → `week1/day2_kicad/`

### Outdoor/Study (0.5h)
- Read: *Right the First Time* (Lee Ritchey, Ch. 1-2 free excerpts)
- Browse: JLCPCB / PCBWay capability pages (track min 0.1mm, via 0.2mm, 4-layer €2/5pcs)

---

## Day 3 (Wednesday) — Power Electronics & RK3588 Power Tree

### Theory (1.5h)
- **RK3588 power domains**: VDD_CPU_L (0.85V), VDD_CPU_B (0.85V), VDD_GPU (0.85V), VDD_NPU (0.85V), VDD_LOGIC (0.85V), VCC_1V8, VCC_3V3, VCC_5V0, DDR_VDDQ (1.1V/1.2V)
- **PMIC**: RK806-1 (I²C, 8 bucks + 6 LDOs) — datasheet & register map
- **Buck converter design**: Synchronous vs. non-sync, inductor selection, output ripple, compensation
- **PD controller**: CH32X035 / IP2721 for USB-C 5V/3A negotiation
- **Power sequencing**: PMIC enable → domain ramps → POR → PMU firmware

**Free Resources:**
- *RK806-1 Datasheet* — Rockchip (public via GitHub mirrors)
- *Switching Regulator Design* — TI "Power Supply Design Seminar" slides (free)
- *Understanding Buck Converters* — Analog Devices AN1197 (free)
- *USB-C PD Spec* — USB-IF free download (register for free account)

### Lab (1h)
- **LTSpice**: Design 5V→0.85V/4A buck (MP2359) — choose L, C<sub>out</sub>, compensation
- Simulate: Load step 0→4A, measure overshoot/undershoot, phase margin
- **KiCad**: Add PMIC schematic page, wire I²C to RK3588, add decoupling (0201 0.1µF × 4 per ball group)
- Export BOM → `week1/day3_power/`

### Outdoor/Study (0.5h)
- Read: *PMIC Layout Guidelines* — RK806-1 app note (Rockchip GitHub)
- Calculate: Total power budget (RK3588 max ~12W, carrier board budget 15W)

---

## Day 4 (Thursday) — DDR4 Memory Interface & Signal Integrity

### Theory (1.5h)
- **DDR4 basics**: Bank groups, burst length 8, preamble, write leveling, read/write training
- **RK3588 DDR PHY**: 2×16-bit channels, up to 3200 MT/s, ODT, V<sub>REF</sub> training
- **Signal integrity**: Eye diagrams, ISI, crosstalk, SSO noise, termination (ODT vs. fly-by)
- **PCB routing**: T-topology vs. fly-by, length matching (byte lane ±10ps, CK ±5ps), layer assignment
- **Simulation**: IBIS models, HyperLynx/SIWave (free trials) or open-source (QUCS-S)

**Free Resources:**
- *DDR4 Design Guide* — Micron TN-47-01 (free PDF)
- *RK3588 DDR Layout Guide* — Rockchip app note
- *Signal Integrity Primer* — Eric Bogatin free videos (YouTube) / "Signal and Power Integrity" Ch. 1 free
- *IBIS Models* — Micron/Samsung/SK Hynix free download

### Lab (1h)
- **KiCad**: Route DDR4 Channel A (16 bits + DQS/DQS# + CK/CK# + CKE + CS + ODT)
- Constraints: 50Ω SE, 100Ω Diff, length match DQ↔DQS ±5mm, CK↔DQS ±2mm
- Place: 0402 series termination (22Ω) near RK3588, decoupling at each V<sub>DDQ</sub> ball
- **QUCS-S**: Import IBIS, simulate DDR4 read/write eye at 2400 MT/s
- Export: Constraint manager rules → `week1/day4_ddr/`

### Outdoor/Study (0.5h)
- Read: *High-Speed Digital Design* (Johnson & Graham) Ch. 3 free excerpt — transmission line basics
- Watch: Robert Feranec "DDR4 Layout" (YouTube, 30 min)

---

## Day 5 (Friday) — Bring-up Strategy & Tooling Plan

### Theory (1.5h)
- **Bring-up phases**: 
  1. Power-on (no SoC) — check rails, PMIC I²C
  2. SoC soldered — JTAG/SWD, UART0 boot ROM
  3. DDR training — RK3588 DDR PHY firmware (BL31/ATF)
  4. Storage — eMMC / SD / NVMe
  5. Display — MIPI DSI / HDMI / DP
  6. Peripherals — USB, PCIe, Ethernet, Audio
- **Debug interfaces**: JTAG (ARM DSTREAM compatible), SWD, UART (1.8V), trace (ETM/ETB)
- **Test equipment roadmap** (phased):
  - Month 1-3: USB microscope (€50), TS100 iron (€60), DMM (€30), practice kits (€50) = **€190**
  - Month 3-6: Hot-air (€110 shared), 4-ch scope (€380 shared/makerspace) = **€0 new**
  - Month 6+: VNA (€200 kit), logic analyzer (€40), thermal cam (€200 rental)
- **Version control**: Git for KiCad (diff via `kicad-cli sch/bom`), Gerber review checklist

**Free Resources:**
- *RK3588 Boot Flow* — Rockchip SDK docs (GitHub: rockchip-linux/rkbin)
- *ARM Trusted Firmware* — Porting guide (free)
- *Buildroot / Yocto* — Quick start for minimal faeOS image
- *JLCPCB SMT Assembly* — €0 setup, €8/stencil, parts at LCSC prices (BOM cost estimator)

### Lab (1h)
- **Create bring-up checklist** → `week1/day5_bringup/checklist.md`
- **Git repo init**: `rk3588-carrier` with `.gitignore` for KiCad, `docs/`, `hw/`, `sw/`
- **Schematic review checklist** (10 items): Power, DDR, Clocks, Reset, Straps, Debug, Connectors, Mounting, Silkscreen, DRC
- **Order plan**: 4-layer 1.6mm FR-4, ENIG, impedance control — quote from JLCPCB/PCBWay/AISLER

### Outdoor/Study (0.5h)
- Read: *Bringing Up a Custom Board* — Bunnie Huang blog (free)
- Join: `##hardware` on Libera.Chat, r/PrintedCircuitBoard, EEVBlog forum
- Plan: Week 2 — Schematic completion, BOM optimization, first prototype order

---

## Week 1 Deliverables

| Item | Path | Due |
|------|------|-----|
| Spice simulations (diode, MOSFET, inverter, buck) | `week1/day1_spice/` | Day 1 |
| KiCad project: power + RK3588 + DDR4 start | `week1/day2_kicad/rk3588_carrier.kicad_pro` | Day 2 |
| Buck converter design notes + sim | `week1/day3_power/buck_design.md` | Day 3 |
| DDR4 routing constraints + eye sim | `week1/day4_ddr/ddr_constraints.md` | Day 4 |
| Bring-up checklist + git repo | `week1/day5_bringup/` | Day 5 |
| **Week 1 Reflection** (1 page) | `week1/reflection.md` | End of week |

---

## Free Resource Index (Bookmark These)

| Category | Resource | Access |
|----------|----------|--------|
| Semiconductor Physics | MIT 6.007 OCW | ocw.mit.edu |
| MOSFET/Analog | All About Circuits Vol. 3 | allaboutcircuits.com/textbook |
| PCB Design | KiCad 8 Tutorial | docs.kicad.org/8.0 |
| IPC Standards | Sierra Circuits Whitepapers | sierraproto.com/resources |
| High-Speed Design | Rick Hartley Notes | si-list archives / YouTube |
| Power Electronics | TI Power Supply Seminar | ti.com/training |
| DDR4 | Micron TN-47-01 | micron.com/support |
| Signal Integrity | Eric Bogatin YouTube | youtube.com/@EricBogatin |
| RK3588 Docs | Rockchip GitHub | github.com/rockchip-linux |
| ARM Firmware | Trusted Firmware-A | trustedfirmware.org |
| Manufacturing | JLCPCB/PCBWay Capabilities | jlcpcb.com/capability |
| Community | Libera.Chat ##hardware | irc.libera.chat |

---

## Budget Tracker (Week 1)

| Item | Cost | Status |
|------|------|--------|
| USB Microscope (500x, 1080p) | €50 | Pending |
| TS100 Soldering Iron + Tips | €60 | Pending |
| Digital Multimeter (UNI-T UT61E+) | €30 | Pending |
| SMD Practice Kit (0201/0402/BGA) | €50 | Pending |
| **Subtotal (Month 1-3)** | **€190** | — |
| Hot-Air Rework (shared/makerspace) | €0 | Access arranged |
| 4-Ch Oscilloscope (shared/makerspace) | €0 | Access arranged |
| **Total New Spend** | **€190** | **Within €1,000** |

---

*Generated: 2026-08-06 | Next: Week 2 — Schematic Completion & BOM*