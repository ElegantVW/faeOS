//! Password verification for seal.
//!
//! Order: hearth daemon (multi-user) → PAM service `seal` → sudo local fallback.
//!
//! PAM talks to libpam directly (no bindgen) so we stay lean to build.

use std::ffi::CString;
use std::io::Write;
use std::os::raw::{c_char, c_int, c_void};
use std::process::{Command, Stdio};
use std::ptr;

// ── libpam FFI (application side only) ────────────────────────────────

const PAM_SUCCESS: c_int = 0;
const PAM_PROMPT_ECHO_OFF: c_int = 1;
const PAM_PROMPT_ECHO_ON: c_int = 2;
const PAM_ERROR_MSG: c_int = 3;
const PAM_TEXT_INFO: c_int = 4;

#[repr(C)]
struct PamMessage {
    msg_style: c_int,
    msg: *const c_char,
}

#[repr(C)]
struct PamResponse {
    resp: *mut c_char,
    resp_retcode: c_int,
}

#[repr(C)]
struct PamConv {
    conv: Option<
        unsafe extern "C" fn(
            num_msg: c_int,
            msg: *mut *const PamMessage,
            resp: *mut *mut PamResponse,
            appdata_ptr: *mut c_void,
        ) -> c_int,
    >,
    appdata_ptr: *mut c_void,
}

#[repr(C)]
struct PamHandle {
    _private: [u8; 0],
}

#[link(name = "pam")]
unsafe extern "C" {
    fn pam_start(
        service_name: *const c_char,
        user: *const c_char,
        pam_conversation: *const PamConv,
        pamh: *mut *mut PamHandle,
    ) -> c_int;

    fn pam_authenticate(pamh: *mut PamHandle, flags: c_int) -> c_int;
    fn pam_acct_mgmt(pamh: *mut PamHandle, flags: c_int) -> c_int;
    fn pam_end(pamh: *mut PamHandle, pam_status: c_int) -> c_int;
}

struct ConvData {
    password: CString,
}

unsafe extern "C" fn pam_conv(
    num_msg: c_int,
    msg: *mut *const PamMessage,
    resp: *mut *mut PamResponse,
    appdata_ptr: *mut c_void,
) -> c_int {
    if num_msg <= 0 || msg.is_null() || resp.is_null() || appdata_ptr.is_null() {
        return 19; // PAM_CONV_ERR
    }

    let data = &*(appdata_ptr as *const ConvData);
    let n = num_msg as usize;

    // calloc-style: pam_end will free responses with free()
    let responses = libc::calloc(n, std::mem::size_of::<PamResponse>()) as *mut PamResponse;
    if responses.is_null() {
        return 19;
    }

    for i in 0..n {
        let m = *msg.add(i);
        if m.is_null() {
            continue;
        }
        let style = (*m).msg_style;
        let r = responses.add(i);
        match style {
            PAM_PROMPT_ECHO_OFF | PAM_PROMPT_ECHO_ON => {
                // pam expects malloc'd C string
                let dup = libc::strdup(data.password.as_ptr());
                if dup.is_null() {
                    // free what we allocated so far
                    for j in 0..i {
                        let prev = responses.add(j);
                        if !(*prev).resp.is_null() {
                            libc::free((*prev).resp as *mut c_void);
                        }
                    }
                    libc::free(responses as *mut c_void);
                    return 19;
                }
                (*r).resp = dup;
                (*r).resp_retcode = 0;
            }
            PAM_ERROR_MSG | PAM_TEXT_INFO => {
                (*r).resp = ptr::null_mut();
                (*r).resp_retcode = 0;
            }
            _ => {
                (*r).resp = ptr::null_mut();
                (*r).resp_retcode = 0;
            }
        }
    }

    *resp = responses;
    PAM_SUCCESS
}

/// Verify `user`/`password`. Never panics; never logs the secret.
pub fn verify_user_password(user: &str, password: &str) -> bool {
    if user.is_empty() || password.is_empty() {
        return false;
    }

    if let Some(result) = crate::users::verify_password(user, password) {
        return result;
    }

    if verify_pam(user, password) {
        return true;
    }

    verify_local(user, password)
}

/// PAM against `/etc/pam.d/seal` (then common fallbacks).
pub fn verify_pam(user: &str, password: &str) -> bool {
    if user.is_empty() || password.is_empty() {
        return false;
    }
    for service in ["seal", "login", "system-auth"] {
        if verify_pam_service(service, user, password) {
            return true;
        }
    }
    false
}

fn verify_pam_service(service: &str, user: &str, password: &str) -> bool {
    let Ok(svc) = CString::new(service) else {
        return false;
    };
    let Ok(usr) = CString::new(user) else {
        return false;
    };
    let Ok(pass) = CString::new(password) else {
        return false;
    };

    let mut conv_data = ConvData { password: pass };
    let conv = PamConv {
        conv: Some(pam_conv),
        appdata_ptr: &mut conv_data as *mut ConvData as *mut c_void,
    };

    let mut pamh: *mut PamHandle = ptr::null_mut();
    unsafe {
        let start = pam_start(svc.as_ptr(), usr.as_ptr(), &conv, &mut pamh);
        if start != PAM_SUCCESS || pamh.is_null() {
            if !pamh.is_null() {
                let _ = pam_end(pamh, start);
            }
            return false;
        }

        let auth = pam_authenticate(pamh, 0);
        let acct = if auth == PAM_SUCCESS {
            pam_acct_mgmt(pamh, 0)
        } else {
            auth
        };
        let _ = pam_end(pamh, acct);
        acct == PAM_SUCCESS
    }
}

/// Last-resort: `sudo -S -k -v` only works for the *current* user on wheel.
pub fn verify_local(user: &str, password: &str) -> bool {
    let current = std::env::var("USER").unwrap_or_default();
    if user != current {
        return false;
    }

    let mut child = match Command::new("sudo")
        .args(["-S", "-k", "-v"])
        .env("LANG", "C")
        .env("LC_ALL", "C")
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(c) => c,
        Err(_) => return false,
    };

    if let Some(mut stdin) = child.stdin.take() {
        let _ = stdin.write_all(password.as_bytes());
        let _ = stdin.write_all(b"\n");
        let _ = stdin.flush();
    }

    child.wait().map(|s| s.success()).unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_password_never_ok() {
        assert!(!verify_user_password("root", ""));
        assert!(!verify_pam("nobody", ""));
    }
}
