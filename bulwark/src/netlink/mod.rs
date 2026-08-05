//! Raw NETLINK_NETFILTER helpers (no libmnl/libnftnl/nft binary).

#![allow(dead_code)]

use anyhow::{bail, Context, Result};
use libc::{c_int, c_void, sockaddr_nl, socket, AF_NETLINK, SOCK_RAW};
use std::io;
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::ptr;

pub const NETLINK_NETFILTER: c_int = 12;
pub const NFNL_SUBSYS_NFTABLES: u16 = 10;

// nf_tables message types
pub const NFT_MSG_NEWTABLE: u16 = 0;
pub const NFT_MSG_GETTABLE: u16 = 1;
pub const NFT_MSG_DELTABLE: u16 = 2;
pub const NFT_MSG_NEWCHAIN: u16 = 3;
pub const NFT_MSG_GETCHAIN: u16 = 4;
pub const NFT_MSG_DELCHAIN: u16 = 5;
pub const NFT_MSG_NEWRULE: u16 = 6;
pub const NFT_MSG_GETRULE: u16 = 7;
pub const NFT_MSG_DELRULE: u16 = 8;

// nfgenmsg
// nfnl_batch
pub const NFNL_MSG_BATCH_BEGIN: u16 = 16; // NLMSG_MIN_TYPE
pub const NFNL_MSG_BATCH_END: u16 = 17;

// nft attributes (subset)
pub const NFTA_TABLE_NAME: u16 = 1;
pub const NFTA_TABLE_FLAGS: u16 = 2;

pub const NFTA_CHAIN_TABLE: u16 = 1;
pub const NFTA_CHAIN_HANDLE: u16 = 2;
pub const NFTA_CHAIN_NAME: u16 = 3;
pub const NFTA_CHAIN_HOOK: u16 = 4;
pub const NFTA_CHAIN_POLICY: u16 = 5;
pub const NFTA_CHAIN_TYPE: u16 = 7;
pub const NFTA_CHAIN_PRIORITY: u16 = 8; // inside nested hook? actually NFTA_HOOK_*

pub const NFTA_HOOK_HOOKNUM: u16 = 1;
pub const NFTA_HOOK_PRIORITY: u16 = 2;

pub const NFTA_RULE_TABLE: u16 = 1;
pub const NFTA_RULE_CHAIN: u16 = 2;
pub const NFTA_RULE_EXPRESSIONS: u16 = 4;

pub const NFTA_LIST_ELEM: u16 = 1;

pub const NFTA_EXPR_NAME: u16 = 1;
pub const NFTA_EXPR_DATA: u16 = 2;

// meta
pub const NFTA_META_KEY: u16 = 1;
pub const NFTA_META_DREG: u16 = 2;
pub const NFT_META_L4PROTO: u32 = 15;
pub const NFT_META_IIFTYPE: u32 = 3; // actually check - use iifname via meta
pub const NFT_META_IIFNAME: u32 = 5;

// cmp
pub const NFTA_CMP_SREG: u16 = 1;
pub const NFTA_CMP_OP: u16 = 2;
pub const NFTA_CMP_DATA: u16 = 3;
pub const NFT_CMP_EQ: u32 = 0;

// payload
pub const NFTA_PAYLOAD_DREG: u16 = 1;
pub const NFTA_PAYLOAD_BASE: u16 = 2;
pub const NFTA_PAYLOAD_OFFSET: u16 = 3;
pub const NFTA_PAYLOAD_LEN: u16 = 4;
pub const NFT_PAYLOAD_TRANSPORT_HEADER: u32 = 2;

// immediate / verdict
pub const NFTA_IMMEDIATE_DREG: u16 = 1;
pub const NFTA_IMMEDIATE_DATA: u16 = 2;
pub const NFTA_DATA_VALUE: u16 = 1;
pub const NFTA_DATA_VERDICT: u16 = 2;
pub const NFTA_VERDICT_CODE: u16 = 1;
pub const NFT_RETURN: u32 = 0xffffffff; // -1
pub const NFT_GOTO: u32 = 0xfffffffe;
pub const NFT_JUMP: u32 = 0xfffffffd;
pub const NFT_BREAK: u32 = 0xfffffffc;
pub const NFT_CONTINUE: i32 = -5; // not used
// standard verdicts in xt: NF_DROP=0 NF_ACCEPT=1
pub const NF_DROP: u32 = 0;
pub const NF_ACCEPT: u32 = 1;

// ct
pub const NFTA_CT_KEY: u16 = 1;
pub const NFTA_CT_DREG: u16 = 2;
pub const NFT_CT_STATE: u32 = 2;
// state bits ESTABLISHED|RELATED
pub const CT_STATE_ESTABLISHED: u32 = 2;
pub const CT_STATE_RELATED: u32 = 4;

// bitwise for ct state mask match - simplify with cmp on state register after ct load

// registers
pub const NFT_REG_VERDICT: u32 = 0;
pub const NFT_REG_1: u32 = 1;
pub const NFT_REG_2: u32 = 2;

// hooks
pub const NF_INET_LOCAL_IN: u32 = 1;
pub const NF_INET_LOCAL_OUT: u32 = 3;
pub const NF_INET_FORWARD: u32 = 2;

// family
pub const NFPROTO_INET: u8 = 1;
pub const NFPROTO_IPV4: u8 = 2;
pub const NFPROTO_IPV6: u8 = 10;

// nlmsg flags
pub const NLM_F_REQUEST: u16 = 0x01;
pub const NLM_F_ACK: u16 = 0x04;
pub const NLM_F_CREATE: u16 = 0x400;
pub const NLM_F_EXCL: u16 = 0x200;
pub const NLM_F_REPLACE: u16 = 0x100;
pub const NLM_F_APPEND: u16 = 0x800;

pub const NLMSG_ERROR: u16 = 0x2;
pub const NLMSG_DONE: u16 = 0x3;

pub const NLA_F_NESTED: u16 = 0x8000;
pub const NLA_F_NET_BYTEORDER: u16 = 0x4000;

#[repr(C)]
#[derive(Clone, Copy)]
pub struct Nlmsghdr {
    pub nlmsg_len: u32,
    pub nlmsg_type: u16,
    pub nlmsg_flags: u16,
    pub nlmsg_seq: u32,
    pub nlmsg_pid: u32,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct Nfgenmsg {
    pub nfgen_family: u8,
    pub version: u8,
    pub res_id: u16, // BE
}

pub struct Netlink {
    fd: OwnedFd,
    seq: u32,
}

impl Netlink {
    pub fn open() -> Result<Self> {
        let fd = unsafe { socket(AF_NETLINK, SOCK_RAW, NETLINK_NETFILTER) };
        if fd < 0 {
            return Err(io::Error::last_os_error()).context("socket(NETLINK_NETFILTER)");
        }
        let fd = unsafe { OwnedFd::from_raw_fd(fd) };
        // bind
        let mut addr: sockaddr_nl = unsafe { mem::zeroed() };
        addr.nl_family = AF_NETLINK as u16;
        let rc = unsafe {
            libc::bind(
                fd.as_raw_fd(),
                &addr as *const _ as *const libc::sockaddr,
                mem::size_of::<sockaddr_nl>() as u32,
            )
        };
        if rc < 0 {
            return Err(io::Error::last_os_error()).context("bind netlink");
        }
        Ok(Self { fd, seq: 1 })
    }

    pub fn send_ack(&mut self, msg: &[u8]) -> Result<()> {
        let fd = self.fd.as_raw_fd();
        let n = unsafe { libc::send(fd, msg.as_ptr() as *const c_void, msg.len(), 0) };
        if n < 0 {
            return Err(io::Error::last_os_error()).context("netlink send");
        }
        // read ACK
        let mut buf = vec![0u8; 8192];
        let n = unsafe { libc::recv(fd, buf.as_mut_ptr() as *mut c_void, buf.len(), 0) };
        if n < 0 {
            return Err(io::Error::last_os_error()).context("netlink recv");
        }
        let n = n as usize;
        parse_ack(&buf[..n])
    }

    pub fn next_seq(&mut self) -> u32 {
        let s = self.seq;
        self.seq = self.seq.wrapping_add(1);
        s
    }
}

pub fn nft_msg_type(msg: u16) -> u16 {
    (NFNL_SUBSYS_NFTABLES << 8) | msg
}

pub fn nlmsg(seq: u32, msg_type: u16, flags: u16, family: u8, payload: &[u8]) -> Vec<u8> {
    let hdr_len = mem::size_of::<Nlmsghdr>() + mem::size_of::<Nfgenmsg>();
    let total = align4(hdr_len + payload.len());
    let mut buf = vec![0u8; total];
    let nl = Nlmsghdr {
        nlmsg_len: total as u32,
        nlmsg_type: msg_type,
        nlmsg_flags: flags | NLM_F_REQUEST | NLM_F_ACK,
        nlmsg_seq: seq,
        nlmsg_pid: 0,
    };
    // safety: write header
    unsafe {
        ptr::copy_nonoverlapping(
            &nl as *const _ as *const u8,
            buf.as_mut_ptr(),
            mem::size_of::<Nlmsghdr>(),
        );
    }
    let gen = Nfgenmsg {
        nfgen_family: family,
        version: 0, // NFNETLINK_V0
        res_id: 0u16.to_be(),
    };
    unsafe {
        ptr::copy_nonoverlapping(
            &gen as *const _ as *const u8,
            buf.as_mut_ptr().add(mem::size_of::<Nlmsghdr>()),
            mem::size_of::<Nfgenmsg>(),
        );
    }
    let off = mem::size_of::<Nlmsghdr>() + mem::size_of::<Nfgenmsg>();
    buf[off..off + payload.len()].copy_from_slice(payload);
    buf
}

pub fn align4(n: usize) -> usize {
    (n + 3) & !3
}

pub fn nla_put_str(attr_type: u16, s: &str) -> Vec<u8> {
    let mut body = s.as_bytes().to_vec();
    body.push(0);
    nla_put(attr_type, &body)
}

pub fn nla_put_u32(attr_type: u16, v: u32) -> Vec<u8> {
    nla_put(attr_type, &v.to_ne_bytes())
}

pub fn nla_put_u16(attr_type: u16, v: u16) -> Vec<u8> {
    nla_put(attr_type, &v.to_ne_bytes())
}

pub fn nla_put_u8(attr_type: u16, v: u8) -> Vec<u8> {
    nla_put(attr_type, &[v])
}

pub fn nla_put(attr_type: u16, data: &[u8]) -> Vec<u8> {
    let len = 4 + data.len();
    let total = align4(len);
    let mut buf = vec![0u8; total];
    buf[0..2].copy_from_slice(&(len as u16).to_ne_bytes());
    buf[2..4].copy_from_slice(&attr_type.to_ne_bytes());
    buf[4..4 + data.len()].copy_from_slice(data);
    buf
}

pub fn nla_nested(attr_type: u16, children: &[u8]) -> Vec<u8> {
    nla_put(attr_type | NLA_F_NESTED, children)
}

fn parse_ack(buf: &[u8]) -> Result<()> {
    if buf.len() < mem::size_of::<Nlmsghdr>() {
        bail!("short netlink reply");
    }
    let mut off = 0;
    while off + mem::size_of::<Nlmsghdr>() <= buf.len() {
        let hdr = unsafe { &*(buf.as_ptr().add(off) as *const Nlmsghdr) };
        let len = hdr.nlmsg_len as usize;
        if len < mem::size_of::<Nlmsghdr>() || off + len > buf.len() {
            break;
        }
        if hdr.nlmsg_type == NLMSG_ERROR {
            // struct nlmsgerr { int error; struct nlmsghdr msg; }
            let err_off = off + mem::size_of::<Nlmsghdr>();
            if err_off + 4 <= buf.len() {
                let mut ebytes = [0u8; 4];
                ebytes.copy_from_slice(&buf[err_off..err_off + 4]);
                let err = i32::from_ne_bytes(ebytes);
                if err != 0 {
                    let e = io::Error::from_raw_os_error(-err);
                    return Err(e).context("nf_tables netlink NACK");
                }
            }
            return Ok(());
        }
        if hdr.nlmsg_type == NLMSG_DONE {
            return Ok(());
        }
        off += align4(len);
    }
    // some kernels return empty success
    Ok(())
}

/// Build NEWTABLE message payload attributes.
pub fn msg_new_table(seq: u32, family: u8, name: &str) -> Vec<u8> {
    let mut payload = Vec::new();
    payload.extend(nla_put_str(NFTA_TABLE_NAME, name));
    nlmsg(
        seq,
        nft_msg_type(NFT_MSG_NEWTABLE),
        NLM_F_CREATE | NLM_F_ACK,
        family,
        &payload,
    )
}

pub fn msg_del_table(seq: u32, family: u8, name: &str) -> Vec<u8> {
    let mut payload = Vec::new();
    payload.extend(nla_put_str(NFTA_TABLE_NAME, name));
    nlmsg(
        seq,
        nft_msg_type(NFT_MSG_DELTABLE),
        NLM_F_ACK,
        family,
        &payload,
    )
}

pub fn msg_new_base_chain(
    seq: u32,
    family: u8,
    table: &str,
    chain: &str,
    hooknum: u32,
    priority: i32,
    policy: u32,
) -> Vec<u8> {
    let mut payload = Vec::new();
    payload.extend(nla_put_str(NFTA_CHAIN_TABLE, table));
    payload.extend(nla_put_str(NFTA_CHAIN_NAME, chain));
    payload.extend(nla_put_str(NFTA_CHAIN_TYPE, "filter"));
    // nested hook
    let mut hook = Vec::new();
    hook.extend(nla_put_u32(NFTA_HOOK_HOOKNUM, hooknum));
    hook.extend(nla_put_u32(NFTA_HOOK_PRIORITY, priority as u32));
    payload.extend(nla_nested(NFTA_CHAIN_HOOK, &hook));
    payload.extend(nla_put_u32(NFTA_CHAIN_POLICY, policy));
    nlmsg(
        seq,
        nft_msg_type(NFT_MSG_NEWCHAIN),
        NLM_F_CREATE | NLM_F_ACK,
        family,
        &payload,
    )
}

/// Expression list builder helpers for simple rules.
pub fn expr_meta_l4proto(reg: u32) -> Vec<u8> {
    let mut data = Vec::new();
    data.extend(nla_put_u32(NFTA_META_DREG, reg));
    data.extend(nla_put_u32(NFTA_META_KEY, NFT_META_L4PROTO));
    expr("meta", &data)
}

pub fn expr_cmp_eq_u8(reg: u32, val: u8) -> Vec<u8> {
    let mut data = Vec::new();
    data.extend(nla_put_u32(NFTA_CMP_SREG, reg));
    data.extend(nla_put_u32(NFTA_CMP_OP, NFT_CMP_EQ));
    // nested data value
    let mut d = Vec::new();
    d.extend(nla_put(NFTA_DATA_VALUE, &[val]));
    data.extend(nla_nested(NFTA_CMP_DATA, &d));
    expr("cmp", &data)
}

pub fn expr_cmp_eq_u16_be(reg: u32, val: u16) -> Vec<u8> {
    let mut data = Vec::new();
    data.extend(nla_put_u32(NFTA_CMP_SREG, reg));
    data.extend(nla_put_u32(NFTA_CMP_OP, NFT_CMP_EQ));
    let be = val.to_be_bytes();
    let mut d = Vec::new();
    d.extend(nla_put(NFTA_DATA_VALUE, &be));
    data.extend(nla_nested(NFTA_CMP_DATA, &d));
    expr("cmp", &data)
}

pub fn expr_payload_transport(reg: u32, offset: u32, len: u32) -> Vec<u8> {
    let mut data = Vec::new();
    data.extend(nla_put_u32(NFTA_PAYLOAD_DREG, reg));
    data.extend(nla_put_u32(NFTA_PAYLOAD_BASE, NFT_PAYLOAD_TRANSPORT_HEADER));
    data.extend(nla_put_u32(NFTA_PAYLOAD_OFFSET, offset));
    data.extend(nla_put_u32(NFTA_PAYLOAD_LEN, len));
    expr("payload", &data)
}

pub fn expr_immediate_verdict(code: u32) -> Vec<u8> {
    let mut data = Vec::new();
    data.extend(nla_put_u32(NFTA_IMMEDIATE_DREG, NFT_REG_VERDICT));
    let mut verd = Vec::new();
    verd.extend(nla_put_u32(NFTA_VERDICT_CODE, code));
    let mut d = Vec::new();
    d.extend(nla_nested(NFTA_DATA_VERDICT, &verd));
    data.extend(nla_nested(NFTA_IMMEDIATE_DATA, &d));
    expr("immediate", &data)
}

pub fn expr_meta_iifname(reg: u32) -> Vec<u8> {
    let mut data = Vec::new();
    data.extend(nla_put_u32(NFTA_META_DREG, reg));
    data.extend(nla_put_u32(NFTA_META_KEY, NFT_META_IIFNAME));
    expr("meta", &data)
}

pub fn expr_cmp_eq_str(reg: u32, s: &str) -> Vec<u8> {
    let mut data = Vec::new();
    data.extend(nla_put_u32(NFTA_CMP_SREG, reg));
    data.extend(nla_put_u32(NFTA_CMP_OP, NFT_CMP_EQ));
    let mut raw = s.as_bytes().to_vec();
    // IFNAMSIZ pad
    raw.resize(16, 0);
    let mut d = Vec::new();
    d.extend(nla_put(NFTA_DATA_VALUE, &raw));
    data.extend(nla_nested(NFTA_CMP_DATA, &d));
    expr("cmp", &data)
}

pub fn expr_ct_state(reg: u32) -> Vec<u8> {
    let mut data = Vec::new();
    data.extend(nla_put_u32(NFTA_CT_DREG, reg));
    data.extend(nla_put_u32(NFTA_CT_KEY, NFT_CT_STATE));
    expr("ct", &data)
}

/// bitwise: dreg = sreg & mask  then cmp — use bitwise expr
pub const NFTA_BITWISE_SREG: u16 = 1;
pub const NFTA_BITWISE_DREG: u16 = 2;
pub const NFTA_BITWISE_LEN: u16 = 3;
pub const NFTA_BITWISE_MASK: u16 = 4;
pub const NFTA_BITWISE_XOR: u16 = 5;

pub fn expr_bitwise_and_u32(sreg: u32, dreg: u32, mask: u32) -> Vec<u8> {
    let mut data = Vec::new();
    data.extend(nla_put_u32(NFTA_BITWISE_SREG, sreg));
    data.extend(nla_put_u32(NFTA_BITWISE_DREG, dreg));
    data.extend(nla_put_u32(NFTA_BITWISE_LEN, 4));
    let mut m = Vec::new();
    m.extend(nla_put(NFTA_DATA_VALUE, &mask.to_ne_bytes()));
    data.extend(nla_nested(NFTA_BITWISE_MASK, &m));
    let mut x = Vec::new();
    x.extend(nla_put(NFTA_DATA_VALUE, &0u32.to_ne_bytes()));
    data.extend(nla_nested(NFTA_BITWISE_XOR, &x));
    expr("bitwise", &data)
}

pub fn expr_cmp_neq_u32(reg: u32, val: u32) -> Vec<u8> {
    let mut data = Vec::new();
    data.extend(nla_put_u32(NFTA_CMP_SREG, reg));
    data.extend(nla_put_u32(NFTA_CMP_OP, 1)); // NFT_CMP_NEQ = 1
    let mut d = Vec::new();
    d.extend(nla_put(NFTA_DATA_VALUE, &val.to_ne_bytes()));
    data.extend(nla_nested(NFTA_CMP_DATA, &d));
    expr("cmp", &data)
}

fn expr(name: &str, data: &[u8]) -> Vec<u8> {
    let mut e = Vec::new();
    e.extend(nla_put_str(NFTA_EXPR_NAME, name));
    e.extend(nla_nested(NFTA_EXPR_DATA, data));
    // wrap as list elem
    nla_nested(NFTA_LIST_ELEM, &e)
}

pub fn msg_new_rule(seq: u32, family: u8, table: &str, chain: &str, exprs: &[u8]) -> Vec<u8> {
    let mut payload = Vec::new();
    payload.extend(nla_put_str(NFTA_RULE_TABLE, table));
    payload.extend(nla_put_str(NFTA_RULE_CHAIN, chain));
    payload.extend(nla_nested(NFTA_RULE_EXPRESSIONS, exprs));
    nlmsg(
        seq,
        nft_msg_type(NFT_MSG_NEWRULE),
        NLM_F_CREATE | NLM_F_APPEND | NLM_F_ACK,
        family,
        &payload,
    )
}

pub fn family_byte(f: crate::aegis::policy::Family) -> u8 {
    use crate::aegis::policy::Family;
    match f {
        Family::Inet => NFPROTO_INET,
        Family::Ip => NFPROTO_IPV4,
        Family::Ip6 => NFPROTO_IPV6,
    }
}
