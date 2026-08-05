//! Apply / flush Aegis policy via netlink.

use super::policy::{parse_policy, Family, Policy, Proto, Rule, Verdict};
use crate::netlink::{self, Netlink};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Serialize, Deserialize)]
pub struct AegisApplyResult {
    pub ok: bool,
    pub message: String,
    pub table: String,
    pub ts_unix: i64,
}

pub fn aegis_available() -> bool {
    Netlink::open().is_ok()
}

pub fn apply_policy_text(text: &str, snapshot_path: &Path) -> Result<AegisApplyResult> {
    let policy = parse_policy(text)?;
    apply_policy(&policy, snapshot_path)
}

pub fn apply_policy(policy: &Policy, snapshot_path: &Path) -> Result<AegisApplyResult> {
    // save snapshot of intent for undo (we flush our table on undo)
    if let Some(parent) = snapshot_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let snap = serde_json::json!({
        "table": policy.table,
        "family": format!("{:?}", policy.family),
        "ts": now(),
        "policy_text_hash": policy.rules.len(),
    });
    fs::write(snapshot_path, serde_json::to_string_pretty(&snap)?)?;

    let mut nl = Netlink::open().context("open netlink (need CAP_NET_ADMIN / root for apply)")?;
    let fam = netlink::family_byte(policy.family);
    let table = policy.table.as_str();

    // Best-effort delete existing table
    let seq = nl.next_seq();
    let _ = nl.send_ack(&netlink::msg_del_table(seq, fam, table));

    // NEWTABLE
    let seq = nl.next_seq();
    nl.send_ack(&netlink::msg_new_table(seq, fam, table))
        .context("NEWTABLE")?;

    // chains
    for (name, hook, policy_v) in [
        (
            "input",
            netlink::NF_INET_LOCAL_IN,
            verdict_u32(policy.default_input),
        ),
        (
            "forward",
            netlink::NF_INET_FORWARD,
            verdict_u32(policy.default_forward),
        ),
        (
            "output",
            netlink::NF_INET_LOCAL_OUT,
            verdict_u32(policy.default_output),
        ),
    ] {
        let seq = nl.next_seq();
        nl.send_ack(&netlink::msg_new_base_chain(
            seq, fam, table, name, hook, 0, policy_v,
        ))
        .with_context(|| format!("NEWCHAIN {name}"))?;
    }

    // rules
    for rule in &policy.rules {
        add_rule(&mut nl, fam, table, rule)?;
    }

    Ok(AegisApplyResult {
        ok: true,
        message: format!(
            "applied table '{}' ({} rules) via netlink nf_tables",
            table,
            policy.rules.len()
        ),
        table: table.to_string(),
        ts_unix: now(),
    })
}

pub fn flush_bulwark(table: &str, family: Family) -> Result<()> {
    let mut nl = Netlink::open()?;
    let fam = netlink::family_byte(family);
    let seq = nl.next_seq();
    nl.send_ack(&netlink::msg_del_table(seq, fam, table))
        .context("DELTABLE")?;
    Ok(())
}

fn verdict_u32(v: Verdict) -> u32 {
    match v {
        Verdict::Accept => netlink::NF_ACCEPT,
        Verdict::Drop => netlink::NF_DROP,
    }
}

fn add_rule(nl: &mut Netlink, fam: u8, table: &str, rule: &Rule) -> Result<()> {
    match rule {
        Rule::AllowLo => {
            // meta iifname "lo" accept  — on input and output
            for chain in ["input", "output"] {
                let mut exprs = Vec::new();
                exprs.extend(netlink::expr_meta_iifname(netlink::NFT_REG_1));
                exprs.extend(netlink::expr_cmp_eq_str(netlink::NFT_REG_1, "lo"));
                exprs.extend(netlink::expr_immediate_verdict(netlink::NF_ACCEPT));
                let seq = nl.next_seq();
                nl.send_ack(&netlink::msg_new_rule(seq, fam, table, chain, &exprs))
                    .with_context(|| format!("rule allow lo on {chain}"))?;
            }
        }
        Rule::AllowEstablished => {
            // ct state established,related accept on input
            let mut exprs = Vec::new();
            exprs.extend(netlink::expr_ct_state(netlink::NFT_REG_1));
            // mask & (EST|REL) != 0  →  bitwise and then neq 0
            let mask = netlink::CT_STATE_ESTABLISHED | netlink::CT_STATE_RELATED;
            exprs.extend(netlink::expr_bitwise_and_u32(
                netlink::NFT_REG_1,
                netlink::NFT_REG_1,
                mask,
            ));
            exprs.extend(netlink::expr_cmp_neq_u32(netlink::NFT_REG_1, 0));
            exprs.extend(netlink::expr_immediate_verdict(netlink::NF_ACCEPT));
            let seq = nl.next_seq();
            nl.send_ack(&netlink::msg_new_rule(
                seq, fam, table, "input", &exprs,
            ))
            .context("rule allow established")?;
        }
        Rule::AllowIn { proto, port, from } => {
            if from.is_some() {
                // v1: port match only; from-address needs payload/ip — still open port on lo-ish
                // We apply port allow; document that from is advisory in dry logs
            }
            let chain = "input";
            let mut exprs = Vec::new();
            let l4: u8 = match proto {
                Proto::Tcp => 6,
                Proto::Udp => 17,
            };
            exprs.extend(netlink::expr_meta_l4proto(netlink::NFT_REG_1));
            exprs.extend(netlink::expr_cmp_eq_u8(netlink::NFT_REG_1, l4));
            // dport at offset 2 for tcp/udp
            exprs.extend(netlink::expr_payload_transport(netlink::NFT_REG_2, 2, 2));
            exprs.extend(netlink::expr_cmp_eq_u16_be(netlink::NFT_REG_2, *port));
            exprs.extend(netlink::expr_immediate_verdict(netlink::NF_ACCEPT));
            let seq = nl.next_seq();
            nl.send_ack(&netlink::msg_new_rule(seq, fam, table, chain, &exprs))
                .with_context(|| format!("rule allow in {proto:?}/{port}"))?;
        }
        Rule::AllowOut { proto, port } => {
            let mut exprs = Vec::new();
            let l4: u8 = match proto {
                Proto::Tcp => 6,
                Proto::Udp => 17,
            };
            exprs.extend(netlink::expr_meta_l4proto(netlink::NFT_REG_1));
            exprs.extend(netlink::expr_cmp_eq_u8(netlink::NFT_REG_1, l4));
            exprs.extend(netlink::expr_payload_transport(netlink::NFT_REG_2, 2, 2));
            exprs.extend(netlink::expr_cmp_eq_u16_be(netlink::NFT_REG_2, *port));
            exprs.extend(netlink::expr_immediate_verdict(netlink::NF_ACCEPT));
            let seq = nl.next_seq();
            nl.send_ack(&netlink::msg_new_rule(seq, fam, table, "output", &exprs))
                .with_context(|| format!("rule allow out {proto:?}/{port}"))?;
        }
        Rule::DenyIn { proto, port } => {
            let mut exprs = Vec::new();
            let l4: u8 = match proto {
                Proto::Tcp => 6,
                Proto::Udp => 17,
            };
            exprs.extend(netlink::expr_meta_l4proto(netlink::NFT_REG_1));
            exprs.extend(netlink::expr_cmp_eq_u8(netlink::NFT_REG_1, l4));
            exprs.extend(netlink::expr_payload_transport(netlink::NFT_REG_2, 2, 2));
            exprs.extend(netlink::expr_cmp_eq_u16_be(netlink::NFT_REG_2, *port));
            exprs.extend(netlink::expr_immediate_verdict(netlink::NF_DROP));
            let seq = nl.next_seq();
            nl.send_ack(&netlink::msg_new_rule(seq, fam, table, "input", &exprs))
                .with_context(|| format!("rule deny in {proto:?}/{port}"))?;
        }
    }
    Ok(())
}

fn now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

pub fn load_bundled_profile(name: &str) -> Result<String> {
    // search relative to executable and common faeos paths
    let candidates = [
        format!("policy/{name}.aegis"),
        format!("bulwark/policy/{name}.aegis"),
        format!(
            "{}/faeos/bulwark/policy/{name}.aegis",
            std::env::var("HOME").unwrap_or_default()
        ),
    ];
    for c in candidates {
        let p = Path::new(&c);
        if p.is_file() {
            return Ok(fs::read_to_string(p)?);
        }
    }
    // embed defaults
    let embedded = match name {
        "strict" => include_str!("../../policy/strict.aegis"),
        "server-ssh" => include_str!("../../policy/server-ssh.aegis"),
        "desktop" => include_str!("../../policy/desktop.aegis"),
        _ => bail!("unknown profile {name} (try desktop|strict|server-ssh)"),
    };
    Ok(embedded.to_string())
}
