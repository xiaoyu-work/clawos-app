use super::*;

fn arguments(values: &[&str]) -> Vec<OsString> {
    values.iter().map(OsString::from).collect()
}

#[test]
fn host_selector_is_removed_once_without_reordering_user_arguments() {
    let input = arguments(&[
        "program",
        "--gui",
        "file with spaces",
        "https://example.test/a?b=c",
        "--flag",
        "value",
        "--",
        "--gui",
    ]);
    let expected = arguments(&[
        "program",
        "file with spaces",
        "https://example.test/a?b=c",
        "--flag",
        "value",
        "--",
        "--gui",
    ]);
    assert_eq!(normalize(input, true, OsStr::new("--gui")), expected);
}

#[test]
fn direct_cli_and_nonmatching_arguments_are_unchanged() {
    for values in [
        vec![],
        vec!["program"],
        vec!["program", "--gui", "--help"],
        vec!["program", "--version"],
        vec!["program", "--", "--gui"],
        vec!["program", "file", "--gui"],
        vec!["program", "--gui=value"],
        vec!["--gui", "file"],
    ] {
        let input = arguments(&values);
        assert_eq!(normalize(input.clone(), false, OsStr::new("--gui")), input);
        if input.get(1).map(OsString::as_os_str) != Some(OsStr::new("--gui")) {
            assert_eq!(normalize(input.clone(), true, OsStr::new("--gui")), input);
        }
    }
}

#[test]
fn repeated_selector_help_and_end_of_options_remain_parser_owned() {
    for user_args in [
        vec!["--gui"],
        vec!["--help"],
        vec!["--version"],
        vec!["--", "--gui", "--help"],
        vec!["--option", "--gui"],
    ] {
        let mut input = arguments(&["program", "--gui"]);
        input.extend(arguments(&user_args));
        let mut expected = arguments(&["program"]);
        expected.extend(arguments(&user_args));
        assert_eq!(normalize(input, true, OsStr::new("--gui")), expected);
    }
}

#[test]
fn selector_matching_is_exact_and_never_consumes_argv_zero() {
    let input = arguments(&["program", "", "--gui"]);
    assert_eq!(normalize(input.clone(), true, OsStr::new("")), input);
    let input = arguments(&["--gui", "about"]);
    assert_eq!(normalize(input.clone(), true, OsStr::new("--gui")), input);
    assert_eq!(
        normalize(
            arguments(&["program", "gui", "about"]),
            true,
            OsStr::new("gui")
        ),
        arguments(&["program", "about"])
    );
}

#[cfg(unix)]
#[test]
fn os_strings_are_preserved_without_unicode_conversion() {
    use std::os::unix::ffi::OsStringExt;

    let program = OsString::from_vec(b"program-\xff".to_vec());
    let path = OsString::from_vec(b"path-\xfe".to_vec());
    assert_eq!(
        normalize(
            vec![program.clone(), OsString::from("--gui"), path.clone()],
            true,
            OsStr::new("--gui"),
        ),
        vec![program, path]
    );
}
