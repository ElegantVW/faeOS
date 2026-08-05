//! Human policy language → structured rules.

use anyhow::{bail, Context, Result};
use std::net::IpAddr;
use std::str::FromStr;

#[derive(Debug, Clone)]
pub struct Policy {
    pub table: String,
    pub family: Family,
    pub default_input: Verdict,
    pub default_output: Verdict,
    pub default_forward: Verdict,
    pub rules: Vec<Rule>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Family {
    Inet,
    Ip,
    Ip6,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Verdict {
    Accept,
    Drop,
}

#[derive(Debug, Clone)]
pub enum Rule {
    AllowLo,
    AllowEstablished,
    AllowIn {
        proto: Proto,
        port: u16,
        from: Option<IpAddr>,
    },
    AllowOut {
        proto: Proto,
        port: u16,
    },
    DenyIn {
        proto: Proto,
        port: u16,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Proto {
    Tcp,
    Udp,
}

impl Default for Policy {
    fn default() -> Self {
        Self {
            table: "bulwark".into(),
            family: Family::Inet,
            default_input: Verdict::Drop,
            default_output: Verdict::Accept,
            default_forward: Verdict::Drop,
            rules: vec![Rule::AllowLo, Rule::AllowEstablished],
        }
    }
}

pub fn parse_policy(text: &str) -> Result<Policy> {
    let mut p = Policy::default();
    p.rules.clear();
    for (lineno, raw) in text.lines().enumerate() {
        let line = raw.split('#').next().unwrap_or("").trim();
        if line.is_empty() {
            continue;
        }
        let lower = line.to_ascii_lowercase();
        let parts: Vec<&str> = lower.split_whitespace().collect();
        if parts.is_empty() {
            continue;
        }
        match parts[0] {
            "table" => {
                if parts.len() >= 2 {
                    p.table = parts[1].to_string();
                }
            }
            "family" => {
                if parts.len() >= 2 {
                    p.family = match parts[1] {
                        "inet" => Family::Inet,
                        "ip" => Family::Ip,
                        "ip6" => Family::Ip6,
                        o => bail!("line {}: unknown family {o}", lineno + 1),
                    };
                }
            }
            "default" => {
                if parts.len() >= 3 {
                    let v = parse_verdict(parts[2])?;
                    match parts[1] {
                        "input" => p.default_input = v,
                        "output" => p.default_output = v,
                        "forward" => p.default_forward = v,
                        o => bail!("line {}: unknown chain {o}", lineno + 1),
                    }
                }
            }
            "allow" => {
                if parts.len() >= 2 && parts[1] == "lo" {
                    p.rules.push(Rule::AllowLo);
                } else if parts.len() >= 2 && parts[1] == "established" {
                    p.rules.push(Rule::AllowEstablished);
                } else if parts.len() >= 4 && parts[1] == "in" {
                    let proto = parse_proto(parts[2])?;
                    let port: u16 = parts[3]
                        .parse()
                        .with_context(|| format!("line {}: bad port", lineno + 1))?;
                    let mut from = None;
                    if parts.len() >= 6 && parts[4] == "from" {
                        from = Some(
                            IpAddr::from_str(parts[5])
                                .with_context(|| format!("line {}: bad from addr", lineno + 1))?,
                        );
                    }
                    p.rules.push(Rule::AllowIn { proto, port, from });
                } else if parts.len() >= 4 && parts[1] == "out" {
                    let proto = parse_proto(parts[2])?;
                    let port: u16 = parts[3].parse().context("bad port")?;
                    p.rules.push(Rule::AllowOut { proto, port });
                } else {
                    bail!("line {}: bad allow syntax", lineno + 1);
                }
            }
            "deny" => {
                if parts.len() >= 4 && parts[1] == "in" {
                    let proto = parse_proto(parts[2])?;
                    let port: u16 = parts[3].parse().context("bad port")?;
                    p.rules.push(Rule::DenyIn { proto, port });
                } else {
                    bail!("line {}: bad deny syntax", lineno + 1);
                }
            }
            other => bail!("line {}: unknown keyword {other}", lineno + 1),
        }
    }
    if p.rules.is_empty() {
        p.rules.push(Rule::AllowLo);
        p.rules.push(Rule::AllowEstablished);
    }
    Ok(p)
}

fn parse_verdict(s: &str) -> Result<Verdict> {
    match s {
        "accept" | "allow" => Ok(Verdict::Accept),
        "drop" | "deny" | "reject" => Ok(Verdict::Drop),
        o => bail!("unknown verdict {o}"),
    }
}

fn parse_proto(s: &str) -> Result<Proto> {
    match s {
        "tcp" => Ok(Proto::Tcp),
        "udp" => Ok(Proto::Udp),
        o => bail!("unknown proto {o}"),
    }
}

pub fn policy_summary(p: &Policy) -> String {
    let mut s = format!(
        "table {} family {:?}\n  input={:?} output={:?} forward={:?}\n  {} rule(s)\n",
        p.table,
        p.family,
        p.default_input,
        p.default_output,
        p.default_forward,
        p.rules.len()
    );
    for r in &p.rules {
        s.push_str(&format!("  - {r:?}\n"));
    }
    s
}
