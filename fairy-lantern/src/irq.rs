//! Interrupt controller (IME / IE / IF) + CPU IRQ entry.

use crate::bus::Bus;
use crate::cpu::Cpu;

pub const IRQ_VBLANK: u16 = 1 << 0;
pub const IRQ_HBLANK: u16 = 1 << 1;
pub const IRQ_VCOUNTER: u16 = 1 << 2;
pub const IRQ_TIMER0: u16 = 1 << 3;
pub const IRQ_TIMER1: u16 = 1 << 4;
pub const IRQ_TIMER2: u16 = 1 << 5;
pub const IRQ_TIMER3: u16 = 1 << 6;
pub const IRQ_DMA0: u16 = 1 << 8;
pub const IRQ_DMA1: u16 = 1 << 9;
pub const IRQ_DMA2: u16 = 1 << 10;
pub const IRQ_DMA3: u16 = 1 << 11;
pub const IRQ_KEYPAD: u16 = 1 << 12;

/// Raise a hardware IRQ source (sets IF bit).
pub fn raise(bus: &mut Bus, bit: u16) {
    let if_ = bus.read16(0x0400_0202) | bit;
    bus.write16_raw(0x0400_0202, if_);
}

/// After each CPU step: if pending and enabled, enter IRQ.
pub fn check(cpu: &mut Cpu, bus: &mut Bus) {
    if cpu.cpsr.irq_disable {
        return;
    }
    let ime = bus.read16(0x0400_0208) & 1;
    if ime == 0 {
        return;
    }
    let ie = bus.read16(0x0400_0200);
    let if_ = bus.read16(0x0400_0202);
    if ie & if_ == 0 {
        return;
    }
    enter_irq(cpu);
}

fn enter_irq(cpu: &mut Cpu) {
    // Bank SPSR_irq / R13_irq / R14_irq simplified: only track spsr + lr
    cpu.spsr = cpu.cpsr;
    cpu.cpsr.mode = 0x12; // IRQ
    cpu.cpsr.irq_disable = true;
    cpu.cpsr.thumb = false;
    // LR_irq = address of next insn + 4 (ARM ref: PC+4 of aborted)
    let lr = if cpu.spsr.thumb {
        cpu.r[15].wrapping_add(2)
    } else {
        cpu.r[15].wrapping_add(4)
    };
    cpu.r[14] = lr;
    cpu.r[15] = 0x0000_0018;
}
