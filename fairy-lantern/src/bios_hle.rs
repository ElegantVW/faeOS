//! High-level BIOS SWI emulation (no real BIOS binary required).

use crate::bus::Bus;
use crate::cpu::Cpu;

/// ARM SWI: GBA BIOS uses the low 8 bits of the 24-bit comment field.
pub fn swi_arm(cpu: &mut Cpu, bus: &mut Bus, op: u32) {
    dispatch(cpu, bus, (op & 0xFF) as u8);
}

/// Thumb SWI: low 8 bits.
pub fn swi_thumb(cpu: &mut Cpu, bus: &mut Bus, op: u32) {
    dispatch(cpu, bus, (op & 0xFF) as u8);
}

fn dispatch(cpu: &mut Cpu, bus: &mut Bus, num: u8) {
    match num {
        0x01 => register_ram_reset(cpu, bus),
        0x02 => {
            // Halt — wait for IRQ; mark as soft wait for vblank
            bus.halt_wait = true;
        }
        0x04 => intr_wait(cpu, bus),
        0x05 => {
            // VBlankIntrWait: r0=1, r1=1 then IntrWait
            cpu.r[0] = 1;
            cpu.r[1] = 1;
            intr_wait(cpu, bus);
        }
        0x06 => div(cpu),
        0x07 => div_arm(cpu),
        0x08 => {
            // Sqrt r0 = isqrt(r0)
            let v = cpu.r[0] as u64;
            cpu.r[0] = (v as f64).sqrt() as u32;
        }
        0x0B => cpu_set(cpu, bus),
        0x0C => cpu_fast_set(cpu, bus),
        0x11 => lz77_uncomp(cpu, bus, false),
        0x12 => lz77_uncomp(cpu, bus, true),
        0x13 => { /* HuffUnComp stub */ }
        0x14 => rl_uncomp(cpu, bus, false),
        0x15 => rl_uncomp(cpu, bus, true),
        0x00 => soft_reset(cpu, bus),
        _ => {
            // unknown SWI — nop
        }
    }
}

fn soft_reset(cpu: &mut Cpu, bus: &mut Bus) {
    // Jump to ROM entry
    cpu.cpsr.thumb = false;
    cpu.cpsr.mode = 0x1F;
    cpu.r[13] = 0x0300_7F00;
    cpu.set_pc(0x0800_0000);
    let _ = bus;
}

fn register_ram_reset(cpu: &mut Cpu, bus: &mut Bus) {
    let flags = cpu.r[0];
    if flags & 0x01 != 0 {
        bus.ewram.fill(0);
    }
    if flags & 0x02 != 0 {
        bus.iwram.fill(0);
    }
    if flags & 0x04 != 0 {
        bus.pal.fill(0);
    }
    if flags & 0x08 != 0 {
        bus.vram.fill(0);
    }
    if flags & 0x10 != 0 {
        bus.oam.fill(0);
    }
    if flags & 0x20 != 0 {
        // clear SIO, sound, timers partially — clear IO range
        for i in 0x60..0xB0 {
            if i < bus.io.len() {
                bus.io[i] = 0;
            }
        }
    }
    if flags & 0x40 != 0 {
        for i in 0x00..0x60 {
            if i < bus.io.len() {
                bus.io[i] = 0;
            }
        }
    }
    // always clear some regs
    if flags & 0x80 != 0 {
        for r in cpu.r.iter_mut().take(12) {
            *r = 0;
        }
    }
}

fn intr_wait(cpu: &mut Cpu, bus: &mut Bus) {
    // r0: 0 = return if already set, 1 = discard current and wait
    // r1: interrupt flags to wait for
    let discard = cpu.r[0] != 0;
    let mask = (cpu.r[1] & 0xFFFF) as u16;
    if discard {
        let if_ = bus.read16(0x0400_0202);
        bus.write16_raw(0x0400_0202, if_ & !mask);
    }
    // Ask emu loop to run until these IRQs fire (at least VBlank)
    bus.intr_wait_mask = if mask == 0 { 1 } else { mask }; // default VBlank
    bus.halt_wait = true;
}

fn div(cpu: &mut Cpu) {
    let num = cpu.r[0] as i32;
    let den = cpu.r[1] as i32;
    if den == 0 {
        cpu.r[0] = 0;
        cpu.r[1] = 0;
        cpu.r[3] = 0;
        return;
    }
    let q = num / den;
    let r = num % den;
    cpu.r[0] = q as u32;
    cpu.r[1] = r as u32;
    cpu.r[3] = q.unsigned_abs();
}

fn div_arm(cpu: &mut Cpu) {
    // r1 / r0 → r0=quot r1=rem r3=abs(quot)  (swapped args vs Div)
    let num = cpu.r[1] as i32;
    let den = cpu.r[0] as i32;
    if den == 0 {
        return;
    }
    let q = num / den;
    let r = num % den;
    cpu.r[0] = q as u32;
    cpu.r[1] = r as u32;
    cpu.r[3] = q.unsigned_abs();
}

fn cpu_set(cpu: &mut Cpu, bus: &mut Bus) {
    let src = cpu.r[0];
    let dst = cpu.r[1];
    let ctrl = cpu.r[2];
    let count = ctrl & 0x001F_FFFF;
    let fixed = ctrl & (1 << 24) != 0;
    let word = ctrl & (1 << 26) != 0;
    let mut s = src;
    let mut d = dst;
    if word {
        for _ in 0..count {
            let v = if fixed {
                bus.read32(src)
            } else {
                let v = bus.read32(s);
                s = s.wrapping_add(4);
                v
            };
            bus.write32(d, v);
            d = d.wrapping_add(4);
        }
    } else {
        for _ in 0..count {
            let v = if fixed {
                bus.read16(src) as u32
            } else {
                let v = bus.read16(s) as u32;
                s = s.wrapping_add(2);
                v
            };
            bus.write16(d, v as u16);
            d = d.wrapping_add(2);
        }
    }
}

fn cpu_fast_set(cpu: &mut Cpu, bus: &mut Bus) {
    let src = cpu.r[0];
    let dst = cpu.r[1];
    let ctrl = cpu.r[2];
    let count = ctrl & 0x001F_FFFF; // 32-bit words
    let fill = ctrl & (1 << 24) != 0;
    let mut s = src;
    let mut d = dst;
    // rounds up to multiple of 8 words in real BIOS; we honor count
    for _ in 0..count {
        let v = if fill {
            bus.read32(src)
        } else {
            let v = bus.read32(s);
            s = s.wrapping_add(4);
            v
        };
        bus.write32(d, v);
        d = d.wrapping_add(4);
    }
}

fn lz77_uncomp(cpu: &mut Cpu, bus: &mut Bus, to_vram: bool) {
    let src = cpu.r[0];
    let dst = cpu.r[1];
    let header = bus.read32(src);
    let size = header & 0x00FF_FFFF;
    let mut s = src.wrapping_add(4);
    let mut d = dst;
    let mut written = 0u32;
    while written < size {
        let flags = bus.read8(s);
        s = s.wrapping_add(1);
        for bit in (0..8).rev() {
            if written >= size {
                break;
            }
            if flags & (1 << bit) != 0 {
                // compressed: 2-byte block
                let b0 = bus.read8(s) as u32;
                let b1 = bus.read8(s.wrapping_add(1)) as u32;
                s = s.wrapping_add(2);
                let disp = ((b0 & 0xF) << 8) | b1;
                let n = ((b0 >> 4) + 3) as u32;
                for _ in 0..n {
                    if written >= size {
                        break;
                    }
                    let v = bus.read8(d.wrapping_sub(disp + 1));
                    write_decomp(bus, d, v, to_vram);
                    d = d.wrapping_add(1);
                    written += 1;
                }
            } else {
                let v = bus.read8(s);
                s = s.wrapping_add(1);
                write_decomp(bus, d, v, to_vram);
                d = d.wrapping_add(1);
                written += 1;
            }
        }
    }
}

fn write_decomp(bus: &mut Bus, addr: u32, val: u8, to_vram: bool) {
    if to_vram {
        // VRAM prefers 16-bit; still allow byte via read-mod-write
        let a = addr & !1;
        let cur = bus.read16(a);
        let v = if addr & 1 == 0 {
            (cur & 0xFF00) | val as u16
        } else {
            (cur & 0x00FF) | ((val as u16) << 8)
        };
        bus.write16(a, v);
    } else {
        bus.write8(addr, val);
    }
}

fn rl_uncomp(cpu: &mut Cpu, bus: &mut Bus, to_vram: bool) {
    let src = cpu.r[0];
    let dst = cpu.r[1];
    let header = bus.read32(src);
    let size = header & 0x00FF_FFFF;
    let mut s = src.wrapping_add(4);
    let mut d = dst;
    let mut written = 0u32;
    while written < size {
        let flag = bus.read8(s);
        s = s.wrapping_add(1);
        if flag & 0x80 != 0 {
            let n = (flag & 0x7F) as u32 + 3;
            let b = bus.read8(s);
            s = s.wrapping_add(1);
            for _ in 0..n {
                if written >= size {
                    break;
                }
                write_decomp(bus, d, b, to_vram);
                d = d.wrapping_add(1);
                written += 1;
            }
        } else {
            let n = (flag & 0x7F) as u32 + 1;
            for _ in 0..n {
                if written >= size {
                    break;
                }
                let b = bus.read8(s);
                s = s.wrapping_add(1);
                write_decomp(bus, d, b, to_vram);
                d = d.wrapping_add(1);
                written += 1;
            }
        }
    }
}
