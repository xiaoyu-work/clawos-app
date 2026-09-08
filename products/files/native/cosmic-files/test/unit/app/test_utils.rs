use std::cmp::Ordering;
use std::fs::File;
use std::io::{self, Write};
use std::iter;
use std::path::Path;

use log::{debug, trace};
use tempfile::{TempDir, tempdir};

use crate::config::{IconSizes, TabConfig, ThumbCfg};
use crate::tab::Item;

use super::*;

// Default number of files, directories, and nested directories for test file system
pub const NUM_FILES: usize = 2;
pub const NUM_HIDDEN: usize = 1;
pub const NUM_DIRS: usize = 2;
pub const NUM_NESTED: usize = 1;
pub const NAME_LEN: usize = 5;

/// Add `n` temporary files in `dir`
///
/// Each file is assigned a numeric name from [0, n) with a prefix.
pub fn file_flat_hier<D: AsRef<Path>>(dir: D, n: usize, prefix: &str) -> io::Result<Vec<File>> {
    let dir = dir.as_ref();
    (0..n)
        .map(|i| -> io::Result<File> {
            let name = format!("{prefix}{i}");
            let path = dir.join(&name);

            let mut file = File::create(path)?;
            file.write_all(name.as_bytes())?;

            Ok(file)
        })
        .collect()
}

// Random alphanumeric String of length `len`
fn rand_string(len: usize) -> String {
    let mut rng = fastrand::Rng::new();
    iter::repeat_with(|| rng.alphanumeric()).take(len).collect()
}

/// Create a small, temporary file hierarchy.
///
/// # Arguments
///
/// * `files` - Number of files to create in temp directories
/// * `hidden` - Number of hidden files to create
/// * `dirs` - Number of directories to create
/// * `nested` - Number of nested directories to create in new dirs
/// * `name_len` - Length of randomized directory names
pub fn simple_fs(
    files: usize,
    hidden: usize,
    dirs: usize,
    nested: usize,
    name_len: usize,
) -> io::Result<TempDir> {
    // Files created inside of a TempDir are deleted with the directory
    // TempDir won't leak resources as long as the destructor runs
    let root = tempdir()?;
    debug!("Root temp directory: {}", root.as_ref().display());
    trace!(
        "Creating {files} files and {hidden} hidden files in {dirs} temp dirs with {nested} nested temp dirs"
    );

    // All paths for directories and nested directories
    let paths = iter::repeat_with(|| {
        let root = root.as_ref();
        let current = rand_string(name_len);

        iter::once(root.join(&current)).chain(
            iter::repeat_with(move || {
                let mut path = root.join(&current);
                path.push(rand_string(name_len));
                path
            })
            .take(nested),
        )
    })
    .take(dirs)
    .flatten();

    // Create directories from `paths` and add a few files
    for path in paths {
        fs::create_dir_all(&path)?;

        // Normal files
        file_flat_hier(&path, files, "")?;
        // Hidden files
        file_flat_hier(&path, hidden, ".")?;

        for entry in path.read_dir()? {
            let entry = entry?;
            if entry.file_type()?.is_file() {
                trace!("Created file: {}", entry.path().display());
            }
        }
    }

    Ok(root)
}

/// Empty file hierarchy
pub fn empty_fs() -> io::Result<TempDir> {
    tempdir()
}

/// Sort files.
///
/// Directories are placed before files.
/// Files are lexically sorted.
/// This is more or less copied right from the [Tab] code
pub fn sort_files(a: &Path, b: &Path) -> Ordering {
    match (a.is_dir(), b.is_dir()) {
        (true, false) => Ordering::Less,
        (false, true) => Ordering::Greater,
        _ => LANGUAGE_SORTER.compare(
            a.file_name()
                .expect("temp entries should have names")
                .to_str()
                .expect("temp entries should be valid UTF-8"),
            b.file_name()
                .expect("temp entries should have names")
                .to_str()
                .expect("temp entries should be valid UTF-8"),
        ),
    }
}

/// Read directory entries from `path` and sort.
pub fn read_dir_sorted(path: &Path) -> io::Result<Vec<PathBuf>> {
    let mut entries: Vec<_> = path
        .read_dir()?
        .map(|maybe_entry| maybe_entry.map(|entry| entry.path()))
        .collect::<io::Result<_>>()?;
    entries.sort_by(|a, b| sort_files(a, b));

    Ok(entries)
}

/// Filter `path` for directories
pub fn filter_dirs(path: &Path) -> io::Result<impl Iterator<Item = PathBuf> + use<>> {
    Ok(path.read_dir()?.filter_map(|entry| {
        entry.ok().and_then(|entry| {
            let path = entry.path();
            path.is_dir().then_some(path)
        })
    }))
}

// Filter `path` for files
pub fn filter_files(path: &Path) -> io::Result<impl Iterator<Item = PathBuf> + use<>> {
    Ok(path.read_dir()?.filter_map(|entry| {
        entry.ok().and_then(|entry| {
            let path = entry.path();
            path.is_file().then_some(path)
        })
    }))
}

/// Boiler plate for Tab tests
pub fn tab_click_new(
    files: usize,
    hidden: usize,
    dirs: usize,
    nested: usize,
    name_len: usize,
) -> io::Result<(TempDir, Tab)> {
    let fs = simple_fs(files, hidden, dirs, nested, name_len)?;
    let path = fs.path();

    // New tab with items
    let location = Location::Path(path.to_owned());
    let (parent_item_opt, items) = location.scan(IconSizes::default());
    let mut tab = Tab::new(
        location,
        TabConfig::default(),
        ThumbCfg::default(),
        None,
        widget::Id::unique(),
        None,
    );
    tab.parent_item_opt = parent_item_opt;
    tab.set_items(items);

    // Ensure correct number of directories as a sanity check
    let items = tab.items_opt().expect("tab should be populated with Items");
    assert_eq!(NUM_DIRS, items.len());

    Ok((fs, tab))
}

/// Equality for [Path] and [Item].
pub fn eq_path_item(path: &Path, item: &Item) -> bool {
    let name = path
        .file_name()
        .expect("temp entries should have names")
        .to_str()
        .expect("temp entries should be valid UTF-8");
    let is_dir = path.is_dir();

    // NOTE: I don't want to change `tab::hidden_attribute` to `pub(crate)` for
    // tests without asking
    #[cfg(not(target_os = "windows"))]
    let is_hidden = name.starts_with('.');

    #[cfg(target_os = "windows")]
    let is_hidden = {
        use std::os::windows::fs::MetadataExt;
        const FILE_ATTRIBUTE_HIDDEN: u32 = 2;
        let metadata = path.metadata().expect("fetching file metadata");
        metadata.file_attributes() & FILE_ATTRIBUTE_HIDDEN == FILE_ATTRIBUTE_HIDDEN
    };

    name == item.name
        && is_dir == item.metadata.is_dir()
        && path == item.path_opt().expect("item should have path")
        && is_hidden == item.hidden
}

/// Asserts `tab`'s location changed to `path`
pub fn assert_eq_tab_path(tab: &Tab, path: &Path) {
    // Paths should be the same
    let Some(tab_path) = tab.location.path_opt() else {
        panic!("Expected tab's location to be a path");
    };

    assert_eq!(
        path,
        tab_path,
        "Tab's path is {} instead of being updated to {}",
        tab_path.display(),
        path.display()
    );
}

/// Assert that tab's items are equal to a path's entries.
pub fn assert_eq_tab_path_contents(tab: &Tab, path: &Path) {
    let Some(tab_path) = tab.location.path_opt() else {
        panic!("Expected tab's location to be a path");
    };

    // Tab items are sorted so paths from read_dir must be too
    let entries = read_dir_sorted(path).expect("should be able to read paths from temp dir");

    // Check lengths.
    // `items_opt` is optional and the directory at `path` may have zero entries
    // Therefore, this doesn't panic if `items_opt` is None
    let items_len = tab.items_opt().map(Vec::len).unwrap_or_default();
    assert_eq!(entries.len(), items_len);

    assert!(
        entries
            .into_iter()
            .zip(tab.items_opt().map_or([].as_slice(), Vec::as_slice))
            .all(|(a, b)| eq_path_item(&a, b)),
        "Path ({}) and Tab path ({}) don't have equal contents",
        path.display(),
        tab_path.display()
    );
}
