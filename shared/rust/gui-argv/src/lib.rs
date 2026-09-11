//! App-owned, authority-free adaptation of a common Host GUI selector.

use std::ffi::{OsStr, OsString};

/// Remove one leading Host selector, retaining argv[0] and every user argument.
///
/// `gui_launch` selects parsing behavior only. It is not proof of identity,
/// permission, or access to any resource or transport.
pub fn normalize<I>(argv: I, gui_launch: bool, selector: &OsStr) -> Vec<OsString>
where
    I: IntoIterator<Item = OsString>,
{
    argv.into_iter()
        .enumerate()
        .filter_map(|(index, argument)| {
            if gui_launch && index == 1 && !selector.is_empty() && argument == selector {
                None
            } else {
                Some(argument)
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/lib.rs"));
}
