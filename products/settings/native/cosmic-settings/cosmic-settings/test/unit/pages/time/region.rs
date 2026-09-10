use super::*;

#[test]
fn test_parse_locale_output_handles_empty_input() {
    let output = "";
    let result = parse_locale_output(output);
    assert_eq!(result.len(), 0);
}

#[test]
fn test_parse_locale_output_preserves_locale_strings() {
    let output = "en_US.utf8\nde_DE.utf8\nfr_FR.utf8\n";
    let result = parse_locale_output(output);
    assert_eq!(result.len(), 3);
    assert!(result.contains(&"en_US.utf8".to_string()));
}

fn synthetic_locale(code: &str) -> SystemLocale {
    SystemLocale {
        lang_code: code.into(),
        display_name: code.into(),
        region_name: code.into(),
    }
}

fn regional_page() -> Page {
    Page {
        language: Some(synthetic_locale("en_US.UTF-8")),
        region: Some(synthetic_locale("en_US.UTF-8")),
        ..Page::default()
    }
}

fn changed(
    generation: u64,
    system: Result<(), Failure>,
    owner: Option<Result<(), Failure>>,
) -> Message {
    Message::Changed(Box::new(ChangeResult {
        generation,
        language: synthetic_locale("de_DE.UTF-8"),
        region: synthetic_locale("de_DE.UTF-8"),
        system,
        owner,
        time_preferences: None,
    }))
}

#[test]
fn regional_failures_preserve_observed_state_without_hiding_partial_owner_success() {
    for failure in [
        Failure::Denied("missing system grant".into()),
        Failure::Review("rv-pending".into()),
        Failure::Unavailable("offline".into()),
        Failure::Unconfirmed("lost acknowledgement".into()),
    ] {
        let mut page = regional_page();
        let generation = page.pending.begin().unwrap();
        let _task = page.update(changed(generation, Err(failure), Some(Ok(()))));
        assert_eq!(page.language.as_ref().unwrap().lang_code, "en_US.UTF-8");
        assert_eq!(page.region.as_ref().unwrap().lang_code, "en_US.UTF-8");
        assert!(page.notice.is_some());
        assert!(!page.pending.busy());
    }
}

#[test]
fn regional_system_success_is_not_rolled_back_when_owner_language_fails() {
    let mut page = regional_page();
    let generation = page.pending.begin().unwrap();
    let _task = page.update(changed(
        generation,
        Ok(()),
        Some(Err(Failure::Denied("owner grant missing".into()))),
    ));
    assert_eq!(page.language.as_ref().unwrap().lang_code, "de_DE.UTF-8");
    assert_eq!(page.region.as_ref().unwrap().lang_code, "de_DE.UTF-8");
    assert!(page.notice.is_some());
}

#[test]
fn stale_regional_results_are_ignored_and_leaving_does_not_cancel_an_accepted_mutation() {
    let mut page = regional_page();
    let old_revision = page.pending.revision();
    let generation = page.pending.begin().unwrap();
    let _task = page.update(changed(generation + 1, Ok(()), None));
    assert_eq!(page.language.as_ref().unwrap().lang_code, "en_US.UTF-8");
    assert!(page.pending.busy());
    let _task = page::Page::on_leave(&mut page);
    assert!(page.pending.busy());
    let _task = page.update(changed(generation, Ok(()), None));
    let notice = page.notice.clone();
    let _task = page.update(Message::Refresh(
        old_revision,
        Arc::new(Err(eyre::eyre!("stale read"))),
    ));
    assert_eq!(page.notice, notice);
    assert_eq!(page.region.as_ref().unwrap().lang_code, "de_DE.UTF-8");
}

#[test]
fn regional_mutation_source_has_no_direct_privileged_dbus_setter_or_detached_write() {
    let source = include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/src/pages/time/region.rs"
    ));
    assert!(!source.contains(".set_locale("));
    assert!(!source.contains(".set_language("));
    assert!(!source.contains("tokio::spawn("));
    assert!(!source.contains("pkexec"));
    assert!(!source.contains("approval-helper"));
}

#[test]
fn test_parse_locale_output_filters_pseudo_locales() {
    let output = "C\nC.utf8\nC.UTF-8\nPOSIX\nen_US.utf8\nde_DE.UTF-8\n";
    let result = parse_locale_output(output);

    // Should filter out all C and POSIX variants
    assert!(!result.contains(&"C".to_string()));
    assert!(!result.contains(&"C.utf8".to_string()));
    assert!(!result.contains(&"C.UTF-8".to_string()));
    assert!(!result.contains(&"POSIX".to_string()));

    // Should keep actual locales
    assert!(result.contains(&"en_US.utf8".to_string()));
    assert!(result.contains(&"de_DE.UTF-8".to_string()));
    assert_eq!(result.len(), 2);
}

#[test]
fn test_parse_locale_output_accepts_only_utf8_locales() {
    let output = "en_US\nen_US.utf8\nen_US.UTF-8\nar_IN\nar_IN.utf8\nde_DE.iso88591\nfr_FR.UTF-8\n";
    let result = parse_locale_output(output);

    // Should accept UTF-8 variants
    assert!(result.contains(&"en_US.utf8".to_string()));
    assert!(result.contains(&"en_US.UTF-8".to_string()));
    assert!(result.contains(&"ar_IN.utf8".to_string()));
    assert!(result.contains(&"fr_FR.UTF-8".to_string()));

    // Should filter out non-UTF-8 encoded locales
    assert!(!result.contains(&"en_US".to_string()));
    assert!(!result.contains(&"ar_IN".to_string()));
    assert!(!result.contains(&"de_DE.iso88591".to_string()));

    assert_eq!(result.len(), 4);
}

#[test]
fn test_parse_locale_output_filters_any_c_posix_variant() {
    let output = "C\nC.iso88591\nC.anything\nPOSIX\nPOSIX.utf8\nen_US.utf8\n";
    let result = parse_locale_output(output);

    // Should filter out any C or POSIX variant regardless of encoding
    assert!(!result.contains(&"C".to_string()));
    assert!(!result.contains(&"C.iso88591".to_string()));
    assert!(!result.contains(&"C.anything".to_string()));
    assert!(!result.contains(&"POSIX".to_string()));
    assert!(!result.contains(&"POSIX.utf8".to_string()));

    // Should keep actual locales
    assert!(result.contains(&"en_US.utf8".to_string()));
    assert_eq!(result.len(), 1);
}

#[test]
fn test_parse_locale_output_handles_whitespace() {
    let output = "  en_US.utf8  \n\t de_DE.UTF-8\t\n   fr_FR.utf8   \n";
    let result = parse_locale_output(output);

    // Should handle leading/trailing whitespace
    assert!(result.contains(&"en_US.utf8".to_string()));
    assert!(result.contains(&"de_DE.UTF-8".to_string()));
    assert!(result.contains(&"fr_FR.utf8".to_string()));
    assert_eq!(result.len(), 3);
}

#[test]
fn test_parse_locale_output_handles_empty_lines() {
    let output = "en_US.utf8\n\n\nde_DE.UTF-8\n\n";
    let result = parse_locale_output(output);

    // Should skip empty lines
    assert!(result.contains(&"en_US.utf8".to_string()));
    assert!(result.contains(&"de_DE.UTF-8".to_string()));
    assert_eq!(result.len(), 2);
}

#[test]
fn test_parse_locale_output_catalan_not_filtered_as_pseudo() {
    let output = "C\nca_ES.UTF-8\nca_ES.utf8\ncs_CZ.UTF-8\nen_US.utf8\n";
    let result = parse_locale_output(output);

    // Should filter out C but not Catalan (ca_*) or Czech (cs_*)
    assert!(!result.contains(&"C".to_string()));
    assert!(result.contains(&"ca_ES.UTF-8".to_string()));
    assert!(result.contains(&"ca_ES.utf8".to_string()));
    assert!(result.contains(&"cs_CZ.UTF-8".to_string()));
    assert_eq!(result.len(), 4);
}

#[test]
fn test_parse_locale_output_handles_locale_modifiers() {
    let output = "en_US.UTF-8@euro\nca_ES.UTF-8@valencia\nde_DE.utf8\n";
    let result = parse_locale_output(output);

    // Locales with modifiers should be accepted
    assert!(result.contains(&"en_US.UTF-8@euro".to_string()));
    assert!(result.contains(&"ca_ES.UTF-8@valencia".to_string()));
    assert!(result.contains(&"de_DE.utf8".to_string()));
    assert_eq!(result.len(), 3);
}

#[test]
fn test_parse_locale_output_case_variations() {
    let output = "en_US.UTF-8\nen_US.utf-8\nen_US.utf8\nen_US.UTF8\nde_DE.Utf8\n";
    let result = parse_locale_output(output);

    // All case variations should be accepted (case-insensitive regex)
    assert!(result.contains(&"en_US.UTF-8".to_string()));
    assert!(result.contains(&"en_US.utf-8".to_string()));
    assert!(result.contains(&"en_US.utf8".to_string()));
    assert!(result.contains(&"en_US.UTF8".to_string()));
    assert!(result.contains(&"de_DE.Utf8".to_string()));
    assert_eq!(result.len(), 5);
}
