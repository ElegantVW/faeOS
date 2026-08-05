//! DMA channels 0–3 (immediate transfers on enable).

use crate::bus::Bus;

/// Called when a DMAxCNT_H write enables the channel (bit 15).
pub fn try_start(bus: &mut Bus, ch: usize) {
    if ch > 3 {
        return;
    }
    let base = 0x0400_00B0 + ch as u32 * 12;
    let sad = bus.read32(base);
    let dad = bus.read32(base + 4);
    let cnt_l = bus.read16(base + 8) as u32;
    let cnt_h = bus.read16(base + 10);
    if cnt_h & 0x8000 == 0 {
        return;
    }
    let mut count = cnt_l & 0xFFFF;
    if count == 0 {
        count = if ch == 3 { 0x10000 } else { 0x4000 };
    }
    let word = cnt_h & (1 << 10) != 0; // 32-bit
    let src_adj = (cnt_h >> 7) & 3; // 0=inc 1=dec 2=fixed 3=prohib
    let dst_adj = (cnt_h >> 5) & 3;
    let mut src = sad;
    let mut dst = dad;

    for _ in 0..count {
        if word {
            let v = bus.read32(src & !3);
            bus.write32(dst & !3, v);
            src = adj(src, src_adj, 4);
            dst = adj(dst, dst_adj, 4);
        } else {
            let v = bus.read16(src & !1);
            bus.write16(dst & !1, v);
            src = adj(src, src_adj, 2);
            dst = adj(dst, dst_adj, 2);
        }
    }

    // clear enable unless repeat
    if cnt_h & (1 << 9) == 0 {
        bus.write16_raw(base + 10, cnt_h & !0x8000);
    }
    // IRQ on end
    if cnt_h & (1 << 14) != 0 {
        let bit = match ch {
            0 => crate::irq::IRQ_DMA0,
            1 => crate::irq::IRQ_DMA1,
            2 => crate::irq::IRQ_DMA2,
            _ => crate::irq::IRQ_DMA3,
        };
        crate::irq::raise(bus, bit);
    }
}

fn adj(addr: u32, mode: u16, step: u32) -> u32 {
    match mode {
        0 => addr.wrapping_add(step),
        1 => addr.wrapping_sub(step),
        2 => addr,
        _ => addr.wrapping_add(step),
    }
}
