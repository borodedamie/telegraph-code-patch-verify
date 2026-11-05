//! Comparator module for the CODE_PATCH_VERIFY family.
//!
//! Implements the Telegraph reference comparison rule line for line (see
//! pkg/scoring/comparator/reference.go in telegraph-wasm-baseline):
//! code 0 Exact, 1 AbsTol, 2 RelTol, 3 PassFail; unknown codes fall back to
//! Exact; multiplications saturate; RelTol's product is computed in 128 bits.
//! No imports, no allocator, no state between calls.
#![no_std]

const ONE: i64 = 10_000;

#[panic_handler]
fn panic(_: &core::panic::PanicInfo) -> ! {
    core::arch::wasm32::unreachable()
}

// ponytail: one fixed 64-byte scratch buffer; the node only ever asks for the 16-byte spec.
static mut SCRATCH: [u8; 64] = [0; 64];

#[no_mangle]
pub extern "C" fn imw_alloc(size: i32) -> i32 {
    if size < 0 || size as usize > 64 {
        return 0;
    }
    core::ptr::addr_of_mut!(SCRATCH) as i32
}

#[no_mangle]
pub extern "C" fn imw_free(_ptr: i32, _size: i32) {}

#[no_mangle]
pub unsafe extern "C" fn imw_score_deterministic(truth: i64, miner: i64, spec_ptr: i32) -> i64 {
    let p = spec_ptr as usize as *const [u8; 8];
    let code = i64::from_le_bytes(core::ptr::read_unaligned(p));
    let tol = i64::from_le_bytes(core::ptr::read_unaligned(p.add(1)));
    score(code, tol, truth, miner)
}

pub fn score(code: i64, tol: i64, truth: i64, miner: i64) -> i64 {
    let diff = miner.wrapping_sub(truth).wrapping_abs();
    match code as i32 {
        1 => decay(diff, tol),
        2 => {
            let mut denom = truth.wrapping_abs();
            if denom < 1 {
                denom = 1;
            }
            let q = (diff as i128) * (ONE as i128) / (denom as i128);
            let err = if q >= i64::MIN as i128 && q <= i64::MAX as i128 { q as i64 } else { i64::MAX };
            decay(err, tol)
        }
        _ => {
            if miner == truth {
                ONE
            } else {
                0
            }
        }
    }
}

fn decay(err: i64, tol: i64) -> i64 {
    if tol <= 0 {
        return if err == 0 { ONE } else { 0 };
    }
    let window = tol.saturating_mul(2);
    if err >= window {
        return 0;
    }
    ONE.saturating_mul(window.wrapping_sub(err)) / window
}
