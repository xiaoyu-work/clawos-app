use super::*;

#[test]
fn recoll_hits_preserve_paths_mime_time_and_snippets() {
    let hits = parse_search_hits(&json!({"results":[{
        "path":"/work/a.txt", "mime":"text/plain", "mtime":"123", "snippet":"match",
    }]})).unwrap();
    assert_eq!(hits[0].path, Path::new("/work/a.txt"));
    assert_eq!(hits[0].mtime, "123");
    assert_eq!(hits[0].snippet, "match");
    assert!(parse_search_hits(&json!({"results":[{"path":42}]})).is_err());
    assert!(parse_search_hits(&json!({"hits":[]})).is_err());
}

#[test]
fn ai_instructions_mark_document_content_untrusted() {
    assert!(SYSTEM.contains("untrusted data"));
}
