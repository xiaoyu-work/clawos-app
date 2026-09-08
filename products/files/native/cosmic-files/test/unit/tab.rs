use std::path::PathBuf;
use std::{fs, io};

use cosmic::iced::mouse::ScrollDelta;
use cosmic::iced::runtime::keyboard::Modifiers;
use cosmic::widget;
use log::{debug, trace};
use tempfile::TempDir;
use test_log::test;

use super::{Location, Message, Tab, respond_to_scroll_direction, scan_path};
use crate::app::test_utils::{
    NAME_LEN, NUM_DIRS, NUM_FILES, NUM_HIDDEN, NUM_NESTED, assert_eq_tab_path, empty_fs,
    eq_path_item, filter_dirs, read_dir_sorted, simple_fs, tab_click_new,
};
use crate::config::{IconSizes, TabConfig, ThumbCfg};

// Boilerplate for tab tests. Checks if simulated clicks selected items.
fn tab_selects_item(
    clicks: &[usize],
    modifiers: Modifiers,
    expected_selected: &[bool],
) -> io::Result<()> {
    let (_fs, mut tab) = tab_click_new(NUM_FILES, NUM_NESTED, NUM_DIRS, NUM_NESTED, NAME_LEN)?;

    // Simulate clicks by triggering Message::Click
    for &click in clicks {
        debug!("Emitting Message::Click(Some({click})) with modifiers: {modifiers:?}");
        tab.update(Message::Click(Some(click)), modifiers);
    }

    let items = tab
        .items_opt
        .as_deref()
        .expect("tab should be populated with items");

    for (i, (&expected, actual)) in expected_selected.iter().zip(items).enumerate() {
        assert_eq!(
            expected,
            actual.selected,
            "expected index {i} to be {}",
            if expected {
                "selected but it was deselected"
            } else {
                "deselected but it was selected"
            }
        );
    }

    Ok(())
}

fn tab_history() -> io::Result<(TempDir, Tab, Vec<PathBuf>)> {
    let fs = simple_fs(NUM_FILES, NUM_NESTED, NUM_DIRS, NUM_NESTED, NAME_LEN)?;
    let path = fs.path();
    let mut tab = Tab::new(
        Location::Path(path.into()),
        TabConfig::default(),
        ThumbCfg::default(),
        None,
        widget::Id::unique(),
        None,
    );

    // All directories (simple_fs only produces one nested layer)
    let dirs: Vec<PathBuf> = {
        let top_level = filter_dirs(path)?;
        let mut result = Vec::new();
        for dir in top_level {
            let nested_dirs = filter_dirs(&dir)?;
            result.push(dir);
            result.extend(nested_dirs);
        }
        result
    };
    assert!(
        dirs.len() == NUM_DIRS + NUM_DIRS * NUM_NESTED,
        "Sanity check: Have {} dirs instead of {}",
        dirs.len(),
        NUM_DIRS + NUM_DIRS * NUM_NESTED
    );

    debug!("Building history by emitting Message::Location");
    for dir in &dirs {
        debug!(
            "Emitting Message::Location(Location::Path(\"{}\"))",
            dir.display()
        );
        tab.update(
            Message::Location(Location::Path(dir.clone())),
            Modifiers::empty(),
        );
    }
    trace!("Tab history: {:?}", tab.history);

    Ok((fs, tab, dirs))
}

#[test]
fn scan_path_succeeds_on_valid_path() -> io::Result<()> {
    let fs = simple_fs(NUM_FILES, NUM_HIDDEN, NUM_DIRS, NUM_NESTED, NAME_LEN)?;
    let path = fs.path();

    // Read directory entries and sort as cosmic-files does
    let entries = read_dir_sorted(path)?;

    debug!("Calling scan_path(\"{}\")", path.display());
    let actual = scan_path(&path.to_owned(), IconSizes::default());

    // scan_path shouldn't skip any entries
    assert_eq!(entries.len(), actual.len());

    // Correct files should be scanned
    assert!(
        entries
            .into_iter()
            .zip(actual.into_iter())
            .all(|(path, item)| eq_path_item(&path, &item))
    );

    Ok(())
}

#[test]
fn scan_path_returns_empty_vec_for_invalid_path() -> io::Result<()> {
    let fs = simple_fs(NUM_FILES, NUM_NESTED, NUM_DIRS, NUM_NESTED, NAME_LEN)?;
    let path = fs.path();

    // A nonexisting path within the temp dir
    let invalid_path = path.join("ferris");
    assert!(!invalid_path.exists());

    debug!("Calling scan_path(\"{}\")", invalid_path.display());
    let actual = scan_path(&invalid_path, IconSizes::default());

    assert!(actual.is_empty());

    Ok(())
}

#[test]
fn scan_path_empty_dir_returns_empty_vec() -> io::Result<()> {
    let fs = empty_fs()?;
    let path = fs.path();

    debug!("Calling scan_path(\"{}\")", path.display());
    let actual = scan_path(&path.to_owned(), IconSizes::default());

    assert_eq!(0, path.read_dir()?.count());
    assert!(actual.is_empty());

    Ok(())
}

#[test]
fn tab_location_changes_location() -> io::Result<()> {
    let fs = simple_fs(NUM_FILES, NUM_NESTED, NUM_DIRS, NUM_NESTED, NAME_LEN)?;
    let path = fs.path();

    // Next directory in temp directory
    // This does not have to be sorted
    let next_dir = filter_dirs(path)?
        .next()
        .expect("temp directory should have at least one directory");

    let mut tab = Tab::new(
        Location::Path(path.to_owned()),
        TabConfig::default(),
        ThumbCfg::default(),
        None,
        widget::Id::unique(),
        None,
    );
    debug!(
        "Emitting Message::Location(Location::Path(\"{}\"))",
        next_dir.display()
    );
    tab.update(
        Message::Location(Location::Path(next_dir.clone())),
        Modifiers::empty(),
    );

    // Validate that the tab's path updated
    // NOTE: `items_opt` is set to None with Message::Location so this ONLY checks for equal paths
    // If item contents are NOT None then this needs to be reevaluated for correctness
    assert_eq_tab_path(&tab, &next_dir);
    assert!(
        tab.items_opt.is_none(),
        "Tab's `items` is not None which means this test needs to be updated"
    );

    Ok(())
}

#[test]
fn tab_click_single_selects_item() -> io::Result<()> {
    // Select the second directory with no keys held down
    tab_selects_item(&[1], Modifiers::empty(), &[false, true])
}

#[test]
fn tab_click_double_opens_folder() -> io::Result<()> {
    let (fs, mut tab) = tab_click_new(NUM_FILES, NUM_NESTED, NUM_DIRS, NUM_NESTED, NAME_LEN)?;
    let path = fs.path();

    // Simulate double clicking second directory
    debug!("Emitting double click Message::DoubleClick(Some(1))");
    tab.update(Message::DoubleClick(Some(1)), Modifiers::empty());

    // Path to second directory
    let second_dir = read_dir_sorted(path)?
        .into_iter()
        .filter(|p| p.is_dir())
        .nth(1)
        .expect("should be at least two directories");

    // Location should have changed to second_dir
    assert_eq_tab_path(&tab, &second_dir);

    Ok(())
}

#[test]
fn tab_click_ctrl_selects_multiple() -> io::Result<()> {
    // Select the first and second directory by holding down ctrl
    tab_selects_item(&[0, 1], Modifiers::CTRL, &[true, true])
}

#[test]
fn tab_gonext_moves_forward_in_history() -> io::Result<()> {
    let (fs, mut tab, dirs) = tab_history()?;
    let path = fs.path();

    // Rewind to the start
    for _ in 0..dirs.len() {
        debug!("Emitting Message::GoPrevious to rewind to the start",);
        tab.update(Message::GoPrevious, Modifiers::empty());
    }
    assert_eq_tab_path(&tab, path);

    // Back to the future. Directories should be in the order they were opened.
    for dir in dirs {
        debug!("Emitting Message::GoNext",);
        tab.update(Message::GoNext, Modifiers::empty());
        assert_eq_tab_path(&tab, &dir);
    }

    Ok(())
}

#[test]
fn tab_goprev_moves_backward_in_history() -> io::Result<()> {
    let (fs, mut tab, dirs) = tab_history()?;
    let path = fs.path();

    for dir in dirs.into_iter().rev() {
        assert_eq_tab_path(&tab, &dir);
        debug!("Emitting Message::GoPrevious",);
        tab.update(Message::GoPrevious, Modifiers::empty());
    }
    assert_eq_tab_path(&tab, path);

    Ok(())
}

#[test]
fn tab_scroll_up_with_ctrl_modifier_zooms() -> io::Result<()> {
    let message_maybe =
        respond_to_scroll_direction(ScrollDelta::Pixels { x: 0.0, y: 1.0 }, &Modifiers::CTRL);
    assert!(message_maybe.is_some());
    assert!(matches!(message_maybe.unwrap(), Message::ZoomIn));
    Ok(())
}

#[test]
fn tab_scroll_up_without_ctrl_modifier_does_not_zoom() -> io::Result<()> {
    let message_maybe = respond_to_scroll_direction(
        ScrollDelta::Pixels { x: 0.0, y: 1.0 },
        &Modifiers::empty(),
    );
    assert!(message_maybe.is_none());
    Ok(())
}

#[test]
fn tab_scroll_down_with_ctrl_modifier_zooms() -> io::Result<()> {
    let message_maybe =
        respond_to_scroll_direction(ScrollDelta::Pixels { x: 0.0, y: -1.0 }, &Modifiers::CTRL);
    assert!(message_maybe.is_some());
    assert!(matches!(message_maybe.unwrap(), Message::ZoomOut));
    Ok(())
}

#[test]
fn tab_scroll_down_without_ctrl_modifier_does_not_zoom() -> io::Result<()> {
    let message_maybe = respond_to_scroll_direction(
        ScrollDelta::Pixels { x: 0.0, y: -1.0 },
        &Modifiers::empty(),
    );
    assert!(message_maybe.is_none());
    Ok(())
}
#[test]
fn tab_empty_history_does_nothing_on_prev_next() -> io::Result<()> {
    let fs = simple_fs(0, NUM_NESTED, NUM_DIRS, 0, NAME_LEN)?;
    let path = fs.path();
    let mut tab = Tab::new(
        Location::Path(path.into()),
        TabConfig::default(),
        ThumbCfg::default(),
        None,
        widget::Id::unique(),
        None,
    );

    // Tab's location shouldn't change if GoPrev or GoNext is triggered
    debug!("Emitting Message::GoPrevious",);
    tab.update(Message::GoPrevious, Modifiers::empty());
    assert_eq_tab_path(&tab, path);

    debug!("Emitting Message::GoNext",);
    tab.update(Message::GoNext, Modifiers::empty());
    assert_eq_tab_path(&tab, path);

    Ok(())
}

#[test]
fn tab_locationup_moves_up_hierarchy() -> io::Result<()> {
    let fs = simple_fs(0, NUM_NESTED, NUM_DIRS, 0, NAME_LEN)?;
    let path = fs.path();
    let mut next_dir = filter_dirs(path)?
        .next()
        .expect("should be at least one directory");

    let mut tab = Tab::new(
        Location::Path(next_dir.clone()),
        TabConfig::default(),
        ThumbCfg::default(),
        None,
        widget::Id::unique(),
        None,
    );
    // This will eventually yield false once root is hit
    while next_dir.pop() {
        debug!("Emitting Message::LocationUp",);
        tab.update(Message::LocationUp, Modifiers::empty());
        assert_eq_tab_path(&tab, &next_dir);
    }

    Ok(())
}

#[test]
fn sort_long_number_file_names() -> io::Result<()> {
    let fs = empty_fs()?;
    let path = fs.path();

    // Create files with names 255 characters long that only contain a single number
    // Example: 0000...0 for 255 characters
    // https://en.wikipedia.org/wiki/Filename#Comparison_of_filename_limitations
    let mut base_nums: Vec<_> = ('0'..='9').collect();
    fastrand::shuffle(&mut base_nums);
    debug!("Shuffled numbers for paths: {base_nums:?}");
    let paths: Vec<_> = base_nums
        .iter()
        .copied()
        .map(|base| path.join(std::iter::repeat_n(base, 255).collect::<String>()))
        .collect();

    for (file, base) in paths.iter().zip(base_nums.into_iter()) {
        trace!("Creating long file name for {base}");
        fs::File::create(file)?;
    }

    debug!("Creating tab for directory of long file names");
    Tab::new(
        Location::Path(path.into()),
        TabConfig::default(),
        ThumbCfg::default(),
        None,
        widget::Id::unique(),
        None,
    );

    Ok(())
}

#[test]
fn mode_calculations() {
    use super::{
        MODE_SHIFT_GROUP, MODE_SHIFT_OTHER, MODE_SHIFT_USER, get_mode_part, set_mode_part,
    };
    for user in 0..=7 {
        for group in 0..=7 {
            for other in 0..=7 {
                let mode = (user << MODE_SHIFT_USER)
                    | (group << MODE_SHIFT_GROUP)
                    | (other << MODE_SHIFT_OTHER);
                assert_eq!(format!("{mode:03o}"), format!("{user:o}{group:o}{other:o}"),);
                assert_eq!(get_mode_part(mode, MODE_SHIFT_USER), user);
                assert_eq!(get_mode_part(mode, MODE_SHIFT_GROUP), group);
                assert_eq!(get_mode_part(mode, MODE_SHIFT_OTHER), other);

                let mode_no_user = (group << MODE_SHIFT_GROUP) | (other << MODE_SHIFT_OTHER);
                assert_eq!(
                    format!("{mode_no_user:03o}"),
                    format!("0{group:o}{other:o}")
                );
                assert_eq!(set_mode_part(mode_no_user, MODE_SHIFT_USER, user), mode);

                let mode_no_group = (user << MODE_SHIFT_USER) | (other << MODE_SHIFT_OTHER);
                assert_eq!(
                    format!("{mode_no_group:03o}"),
                    format!("{user:o}0{other:o}")
                );
                assert_eq!(set_mode_part(mode_no_group, MODE_SHIFT_GROUP, group), mode);

                let mode_no_other = (user << MODE_SHIFT_USER) | (group << MODE_SHIFT_GROUP);
                assert_eq!(
                    format!("{mode_no_other:03o}"),
                    format!("{user:o}{group:o}0")
                );
                assert_eq!(set_mode_part(mode_no_other, MODE_SHIFT_OTHER, other), mode);
            }
        }
    }
}
