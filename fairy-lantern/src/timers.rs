//! Four GBA timers — methods on Bus via free functions.

use crate::bus::Bus;
use crate::irq;

#[derive(Clone, Debug)]
pub struct Timers {
    pub counter: [u32; 4],
    pub reload: [u16; 4],
}

impl Default for Timers {
    fn default() -> Self {
        Self::new()
    }
}

impl Timers {
    pub fn new() -> Self {
        Self {
            counter: [0; 4],
            reload: [0; 4],
        }
    }

    pub fn on_write_reload(&mut self, idx: usize, val: u16) {
        if idx < 4 {
            self.reload[idx] = val;
            self.counter[idx] = val as u32;
        }
    }
}

/// Advance timers by approx CPU cycles. `t` is bus.timers state; `bus` for ctrl regs + IRQ.
pub fn step(t: &mut Timers, bus: &mut Bus, cycles: u32) {
    for i in 0..4 {
        let ctrl = bus.read16(0x0400_0102 + i as u32 * 4);
        if ctrl & 0x80 == 0 {
            continue;
        }
        if i > 0 && ctrl & 0x4 != 0 {
            continue;
        }
        let presc = match ctrl & 3 {
            0 => 1u32,
            1 => 64,
            2 => 256,
            _ => 1024,
        };
        let add = cycles / presc.max(1);
        if add == 0 {
            continue;
        }
        let before = t.counter[i] & 0xFFFF;
        let sum = before + add;
        if sum > 0xFFFF {
            t.counter[i] = t.reload[i] as u32;
            bus.write16_raw(0x0400_0100 + i as u32 * 4, t.reload[i]);
            if ctrl & 0x40 != 0 {
                let bit = match i {
                    0 => irq::IRQ_TIMER0,
                    1 => irq::IRQ_TIMER1,
                    2 => irq::IRQ_TIMER2,
                    _ => irq::IRQ_TIMER3,
                };
                irq::raise(bus, bit);
            }
            if i + 1 < 4 {
                let nctrl = bus.read16(0x0400_0102 + (i as u32 + 1) * 4);
                if nctrl & 0x80 != 0 && nctrl & 0x4 != 0 {
                    let nc = (t.counter[i + 1] & 0xFFFF) + 1;
                    if nc > 0xFFFF {
                        t.counter[i + 1] = t.reload[i + 1] as u32;
                        if nctrl & 0x40 != 0 {
                            let bit = match i + 1 {
                                1 => irq::IRQ_TIMER1,
                                2 => irq::IRQ_TIMER2,
                                _ => irq::IRQ_TIMER3,
                            };
                            irq::raise(bus, bit);
                        }
                    } else {
                        t.counter[i + 1] = nc;
                    }
                }
            }
        } else {
            t.counter[i] = sum;
        }
    }
}
