//! ARM7TDMI interpreter (pipeline-less, from scratch).

mod arm;
mod cpsr;
mod thumb;

pub use cpsr::Cpsr;

use crate::bus::Bus;

#[derive(Clone, Debug)]
pub struct Cpu {
    /// R0–R15; R15 is PC (points at *current* instruction for our interpreter).
    pub r: [u32; 16],
    pub cpsr: Cpsr,
    pub spsr: Cpsr,
    pub cycles: u64,
    pub halted: bool,
}

impl Default for Cpu {
    fn default() -> Self {
        Self::new()
    }
}

impl Cpu {
    pub fn new() -> Self {
        Self {
            r: [0; 16],
            cpsr: Cpsr::new_svc(),
            spsr: Cpsr::default(),
            cycles: 0,
            halted: false,
        }
    }

    pub fn pc(&self) -> u32 {
        self.r[15]
    }

    pub fn set_pc(&mut self, pc: u32) {
        self.r[15] = pc;
    }

    /// PC as seen by ARM data-processing / LDR [PC, …].
    ///
    /// After fetch we already advanced R15 to next insn (A+4). Architectural
    /// PC for the insn at A is A+8, so return R15+4.
    pub fn pc_arm_read(&self) -> u32 {
        self.r[15].wrapping_add(4)
    }

    /// PC as seen by Thumb (A+4). After fetch R15=A+2 → return R15+2.
    pub fn pc_thumb_read(&self) -> u32 {
        self.r[15].wrapping_add(2)
    }

    pub fn step(&mut self, bus: &mut Bus) -> u32 {
        if self.halted {
            return 1;
        }
        if self.cpsr.thumb {
            thumb::step(self, bus)
        } else {
            arm::step(self, bus)
        }
    }

    pub fn reg(&self, i: usize) -> u32 {
        if i == 15 {
            if self.cpsr.thumb {
                self.pc_thumb_read()
            } else {
                self.pc_arm_read()
            }
        } else {
            self.r[i]
        }
    }

    pub fn set_reg(&mut self, i: usize, v: u32) {
        if i == 15 {
            // writing PC
            let mut pc = v;
            if self.cpsr.thumb {
                pc &= !1;
                // LSB of BX sets thumb; bare MOV PC keeps mode
            } else {
                pc &= !3;
            }
            self.r[15] = pc;
        } else {
            self.r[i] = v;
        }
    }
}
