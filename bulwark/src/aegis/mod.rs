//! Aegis — policy DSL + apply via our netlink nf_tables code.

pub mod policy;
pub mod apply;

pub use apply::{
    aegis_available, apply_policy, apply_policy_text, flush_bulwark, load_bundled_profile,
    AegisApplyResult,
};
pub use policy::{parse_policy, policy_summary, Family, Policy, Rule};
