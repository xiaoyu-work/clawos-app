use super::*;

#[test]
fn retired_and_disconnected_handles_are_reclaimed_only_for_their_sender() {
    let (tx, _rx) = channel(10);
    let mut server = Notifications::new(tx);
    let bound = server.allocate(":1.1", 0).unwrap().0;
    let persistent = server.allocate(":1.1", 0).unwrap().0;
    let foreign = server.allocate(":1.2", 0).unwrap().0;
    server.connection_bound.extend([bound, foreign]);
    assert!(server.retire_sender(":1.3").is_empty());
    assert_eq!(server.retire_sender(":1.1"), vec![bound]);
    assert!(
        server.owners.contains_key(&persistent),
        "ordinary freedesktop lifetime is unchanged"
    );
    assert!(server.owners.contains_key(&foreign));
    for _ in 0..5000 {
        let id = server.allocate(":1.4", 0).unwrap().0;
        assert!(
            server.retire(id),
            "evicted presentations must not exhaust the handle bound"
        );
    }
    assert_eq!(server.owners.len(), 2);
}

#[test]
fn numerical_ids_are_sender_bound_not_hints_or_labels() {
    let (tx, _) = channel(10);
    let mut daemon = Notifications::new(tx);
    let (first, replaced) = daemon.allocate(":1.1", 0).unwrap();
    assert!(!replaced);
    assert_eq!(daemon.allocate(":1.1", first).unwrap(), (first, true));
    assert!(daemon.allocate(":1.2", first).is_err());
    let (second, replaced) = daemon.allocate(":1.2", 999).unwrap();
    assert!(!replaced);
    assert_ne!(second, first);
    assert_ne!(second, 999, "unknown replacement ids cannot become aliases");
    daemon.next = NonZeroU32::new(u32::MAX).unwrap();
    daemon.allocate(":1.2", 0).unwrap();
    assert_ne!(daemon.allocate(":1.2", 0).unwrap().0, first);
}
