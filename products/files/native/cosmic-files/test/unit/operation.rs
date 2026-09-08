use std::fs::{self, File};
use std::io;
use std::path::PathBuf;

use cosmic::iced::futures::channel::mpsc;
use cosmic::iced::futures::{StreamExt, future};
use log::debug;
use test_log::test;
use tokio::sync;

use super::{Controller, Operation, OperationError, OperationSelection, ReplaceResult};
use crate::app::test_utils::{
    NAME_LEN, NUM_DIRS, NUM_FILES, NUM_HIDDEN, NUM_NESTED, empty_fs, filter_dirs, filter_files,
    simple_fs,
};
use crate::app::{DialogPage, Message};
use crate::fl;

/// Simple wrapper around `[Operation::Copy]`
pub async fn operation_copy(
    paths: Vec<PathBuf>,
    to: PathBuf,
) -> Result<OperationSelection, OperationError> {
    let id = fastrand::u64(0..u64::MAX);
    let (tx, mut rx) = mpsc::channel(1);
    let paths_clone = paths.clone();
    let to_clone = to.clone();

    // Wrap this into its own future so that it may be polled concurerntly with the message handler.
    let handle_copy = async move {
        Operation::Copy {
            paths: paths_clone,
            to: to_clone,
        }
        .perform(&sync::Mutex::new(tx).into(), Controller::default())
        .await
    };

    // Concurrently handling messages will prevent the mpsc channel from blocking when full.
    let handle_messages = async move {
        while let Some(msg) = rx.next().await {
            match msg {
                Message::DialogPush(DialogPage::Replace { tx, .. }, _id_to_focus) => {
                    debug!("[{id}] Replace request");
                    tx.send(ReplaceResult::Cancel)
                        .await
                        .expect("Sending a response to a replace request should succeed");
                }
                _ => unreachable!(
                    "Only [ `Message::PendingProgress`, `Message::DialogPush(DialogPage::Replace)` ] are sent from operation"
                ),
            }
        }
    };

    future::join(handle_messages, handle_copy).await.1
}

#[test(compio::test)]
async fn copy_file_to_same_location() -> io::Result<()> {
    let fs = simple_fs(NUM_FILES, 0, 1, 0, NAME_LEN)?;
    let path = fs.path();

    // Get the first file from the first directory
    let first_dir = filter_dirs(path)?
        .next()
        .expect("Should have at least one directory");
    let first_file = filter_files(&first_dir)?
        .next()
        .expect("Should have at least one file");

    // Duplicate that file
    let base_name = first_file
        .file_name()
        .and_then(|name| name.to_str())
        .expect("File name exists and is valid");
    debug!(
        "Duplicating {} in {}",
        first_file.display(),
        first_dir.display()
    );
    operation_copy(vec![first_file.clone()], first_dir.clone())
        .await
        .expect("Copy operation should have succeeded");

    assert!(first_file.exists(), "Original file should still exist");
    let expected = first_dir.join(format!("{base_name} ({} 1)", fl!("copy_noun")));
    assert!(expected.exists(), "File should have been duplicated");

    Ok(())
}

#[test(compio::test)]
async fn copy_file_with_extension_to_same_loc() -> io::Result<()> {
    let fs = empty_fs()?;
    let path = fs.path();

    let base_name = "foo.txt";
    let base_path = path.join(base_name);
    File::create(&base_path)?;
    debug!("Duplicating {}", base_path.display());
    operation_copy(vec![base_path.clone()], path.to_owned())
        .await
        .expect("Copy operation should have succeeded");

    assert!(base_path.exists(), "Original file should still exist");
    let expected = path.join(format!("foo ({} 1).txt", fl!("copy_noun")));
    assert!(expected.exists(), "File should have been duplicated");

    Ok(())
}

#[test(compio::test)]
async fn copy_dir_to_same_location() -> io::Result<()> {
    let fs = simple_fs(NUM_FILES, 0, NUM_DIRS, NUM_NESTED, NAME_LEN)?;
    let path = fs.path();

    // First directory path
    let first_dir = filter_dirs(path)?
        .next()
        .expect("Should have at least one directory");
    let base_name = first_dir
        .file_name()
        .and_then(|name| name.to_str())
        .expect("First directory exists and has a valid name");
    debug!("Duplicating directory {}", first_dir.display());
    operation_copy(vec![first_dir.clone()], path.to_owned())
        .await
        .expect("Copy operation should have succeeded");

    assert!(first_dir.exists(), "Original directory should still exist");
    let expected = path.join(format!("{base_name} ({} 1)", fl!("copy_noun")));
    assert!(expected.exists(), "Directory should have been duplicated");

    Ok(())
}

#[test(compio::test)]
async fn copying_file_multiple_times_to_same_location() -> io::Result<()> {
    let fs = empty_fs()?;
    let path = fs.path();

    let base_name = "cosmic";
    let base_path = path.join(base_name);
    File::create(&base_path)?;

    for i in 1..5 {
        debug!("Duplicating {}", base_path.display());
        operation_copy(vec![base_path.clone()], path.to_owned())
            .await
            .expect("Copy operation should have succeeded");
        assert!(base_path.exists(), "Original file should still exist");
        assert!(
            path.join(format!("{base_name} ({} {i})", fl!("copy_noun")))
                .exists(),
            "File should have been duplicated (copy #{i})"
        );
    }

    Ok(())
}

#[test(compio::test)]
async fn copy_to_diff_dir_doesnt_dupe_files() -> io::Result<()> {
    let fs = simple_fs(NUM_FILES, NUM_HIDDEN, NUM_DIRS, NUM_NESTED, NAME_LEN)?;
    let path = fs.path();

    let (first_dir, second_dir) = {
        let mut dirs = filter_dirs(path)?;
        (
            dirs.next().expect("Should have at least two dirs"),
            dirs.next().expect("Should have at least two dirs"),
        )
    };
    let first_file = filter_files(&first_dir)?
        .next()
        .expect("Should have at least one file");
    // Both directories have a file with the same name.
    let base_name = first_file
        .file_name()
        .and_then(|name| name.to_str())
        .expect("File name exists and is valid");

    debug!(
        "Copying {} to {}",
        first_file.display(),
        second_dir.display()
    );
    operation_copy(vec![first_file.clone()], second_dir.clone())
        .await
        .expect(concat!(
            "Copy operation should have been cancelled ",
            "because we're copying to different directories ",
            "without replacement"
        ));
    assert!(
        first_dir.join(base_name).exists(),
        "First file should still exist"
    );
    assert!(
        second_dir.join(base_name).exists(),
        "Second file should still exist"
    );

    Ok(())
}

#[test(compio::test)]
async fn copy_file_with_diff_name_to_diff_dir() -> io::Result<()> {
    let fs = empty_fs()?;
    let path = fs.path();

    let dir_path = path.join("cosmic");
    fs::create_dir(&dir_path)?;
    let file_path = path.join("ferris");
    File::create(&file_path)?;
    let expected = dir_path.join("ferris");

    debug!("Copying {} to {}", file_path.display(), expected.display());
    operation_copy(vec![file_path.clone()], dir_path.clone())
        .await
        .expect("Copy operation should have succeeded");

    assert!(file_path.exists(), "Original file should still exist");
    assert!(expected.exists(), "File should have been copied");

    Ok(())
}
