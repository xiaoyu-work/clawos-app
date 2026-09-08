use super::exec_to_command;

#[test]
fn keys_within_words() {
    let exec = "/usr/bin/foo --option=%f";
    let paths = ["file1"];
    let commands = exec_to_command(exec, "keys_within_words", None, &paths)
        .expect("Should parse valid exec");

    assert_eq!(1, commands.len());
    let command = commands.first().unwrap();

    assert_eq!("/usr/bin/foo", command.get_program().to_str().unwrap());
    assert_eq!(
        "--option=file1",
        command.get_args().next().unwrap().to_str().unwrap()
    );
}

#[test]
fn no_path_f_field_code() {
    let exec = "/usr/bin/foo %f";
    let paths: [&str; 0] = [];
    let commands = exec_to_command(exec, "no_path_f_field_code", None, &paths)
        .expect("Should parse valid exec");

    assert_eq!(1, commands.len());
    let command = commands.first().unwrap();

    assert_eq!("/usr/bin/foo", command.get_program().to_str().unwrap());
    assert_eq!(0, command.get_args().len());
}

#[test]
fn one_path_f_field_code() {
    let exec = "/usr/bin/foo %f";
    let paths = ["file1"];
    let commands = exec_to_command(exec, "one_path_f_field_code", None, &paths)
        .expect("Should parse valid exec");

    assert_eq!(1, commands.len());
    let command = commands.first().unwrap();

    assert_eq!("/usr/bin/foo", command.get_program().to_str().unwrap());
    assert_eq!(
        "file1",
        command.get_args().next().unwrap().to_str().unwrap()
    );
}

#[test]
#[allow(non_snake_case)]
fn one_path_F_field_code() {
    let exec = "/usr/bin/cosmic-term -w %F";
    let paths = ["/home/user"];
    let commands = exec_to_command(exec, "one_path_F_field_code", None, &paths)
        .expect("Should parse valid exec");

    assert_eq!(1, commands.len());
    let command = commands.first().unwrap();
    let mut args = command.get_args();

    assert_eq!(
        "/usr/bin/cosmic-term",
        command.get_program().to_str().unwrap()
    );
    assert_eq!("-w", args.next().unwrap().to_str().unwrap());
    assert_eq!(paths[0], args.next().unwrap().to_str().unwrap());
}

#[test]
fn one_path_u_field_code() {
    let exec = "/usr/bin/cosmic-term -w %u";
    let paths = ["/home/user"];
    let commands = exec_to_command(exec, "one_path_u_field_code", None, &paths)
        .expect("Should parse valid exec");

    assert_eq!(1, commands.len());
    let command = commands.first().unwrap();
    let mut args = command.get_args();

    assert_eq!(
        "/usr/bin/cosmic-term",
        command.get_program().to_str().unwrap()
    );
    assert_eq!("-w", args.next().unwrap().to_str().unwrap());
    assert_eq!(paths[0], args.next().unwrap().to_str().unwrap());
}

#[test]
#[allow(non_snake_case)]
fn one_path_U_field_code() {
    let exec = "/usr/bin/rmrfbye %U";
    let paths = ["/"];
    let commands = exec_to_command(exec, "one_path_U_field_code", None, &paths)
        .expect("Should parse valid exec");

    assert_eq!(1, commands.len());
    let command = commands.first().unwrap();

    assert_eq!("/usr/bin/rmrfbye", command.get_program().to_str().unwrap());
    assert_eq!("/", command.get_args().next().unwrap().to_str().unwrap());
}

#[test]
fn mult_path_f_field_code() {
    let exec = "/usr/games/ppsspp %f";
    let paths = [
        "/usr/share/games/psp/miku.iso",
        "/usr/share/games/psp/eternia.iso",
    ];
    let commands = exec_to_command(exec, "mult_path_f_field_code", None, &paths)
        .expect("Should parse valid exec");

    assert_eq!(paths.len(), commands.len());
    for (command, path) in commands.into_iter().zip(paths.iter()) {
        assert_eq!("/usr/games/ppsspp", command.get_program().to_str().unwrap());

        assert_eq!(1, command.get_args().len());
        let command_path = command.get_args().next().unwrap();
        assert_eq!(*path, command_path.to_str().unwrap());
    }
}

#[test]
#[allow(non_snake_case)]
fn mult_path_F_field_code() {
    let exec = "/usr/games/gzdoom %F";
    let paths = [
        "/usr/share/games/doom2/hr.wad",
        "/usr/share/games/doom2/hrmus.wad",
    ];
    let commands = exec_to_command(exec, "mult_path_F_field_code", None, &paths)
        .expect("Should parse valid exec");

    assert_eq!(1, commands.len());
    let command = commands.first().unwrap();

    assert_eq!("/usr/games/gzdoom", command.get_program().to_str().unwrap());
    assert!(
        paths
            .iter()
            .zip(command.get_args())
            .all(|(&expected, actual)| expected == actual.to_string_lossy())
    );
}

#[test]
fn mult_path_u_field_code() {
    let exec = "/usr/bin/cosmic_browser %u";
    let paths = [
        "file:///home/josh/Books/osstep.pdf",
        "https://redox-os.org/",
        "https://system76.com/",
    ];
    let commands = exec_to_command(exec, "mult_path_u_field_code", None, &paths)
        .expect("Should parse valid exec");

    assert_eq!(paths.len(), commands.len());
    for (command, path) in commands.into_iter().zip(paths.iter()) {
        assert_eq!(
            "/usr/bin/cosmic_browser",
            command.get_program().to_str().unwrap()
        );

        assert_eq!(1, command.get_args().len());
        let command_path = command.get_args().next().unwrap();
        assert_eq!(*path, command_path.to_str().unwrap());
    }
}

#[test]
#[allow(non_snake_case)]
fn mult_path_U_field_code() {
    let exec = "/usr/bin/mpv %U";
    let paths = [
        "frieren01.mkv",
        "rtmp://example.org/this/video/doesnt/exist.avi",
    ];
    let commands = exec_to_command(exec, "mult_path_U_field_code", None, &paths)
        .expect("Should parse valid exec");

    assert_eq!(1, commands.len());
    let command = commands.first().unwrap();
    assert_eq!(paths.len(), command.get_args().count());

    assert_eq!("/usr/bin/mpv", command.get_program().to_str().unwrap());
    assert!(
        paths
            .iter()
            .zip(command.get_args())
            .all(|(&expected, actual)| expected == actual.to_string_lossy())
    );
}

#[test]
fn flatpak_style_exec() {
    // Tests args before field codes
    let exec = "/usr/bin/flatpak run --branch=stable --command=ferris --file-forwarding org.joshfake.ferris @@u %U";
    let args = [
        "run",
        "--branch=stable",
        "--command=ferris",
        "--file-forwarding",
        "org.joshfake.ferris",
        "@@u",
    ];
    let paths = ["file1.rs", "file2.rs"];
    let commands = exec_to_command(exec, "flatpak_style_exec", None, &paths)
        .expect("Should parse valid exec");

    assert_eq!(1, commands.len());
    let command = commands.first().unwrap();
    assert_eq!(args.len() + paths.len(), command.get_args().count());

    assert_eq!("/usr/bin/flatpak", command.get_program().to_str().unwrap());
    assert!(
        args.iter()
            .chain(paths.iter())
            .zip(command.get_args())
            .all(|(&expected, actual)| expected == actual.to_string_lossy())
    );
}

#[test]
fn multiple_field_codes() {
    // Tests that only one field code is used rather than passing paths to each field code
    let exec = "/usr/games/roguelike %U %f";
    let paths = [
        "file:///usr/share/games/roguelike/mods/mod1",
        "file:///usr/share/games/roguelike/mods/mod2",
    ];
    let commands = exec_to_command(exec, "multiple_field_codes", None, &paths)
        .expect("Should parse valid exec");

    assert_eq!(1, commands.len());
    let command = commands.first().unwrap();

    assert_eq!(
        "/usr/games/roguelike",
        command.get_program().to_str().unwrap()
    );
    assert!(
        paths
            .iter()
            .zip(command.get_args())
            .all(|(&expected, actual)| expected == actual.to_string_lossy())
    );
}

#[test]
fn sandwiched_field_code() {
    // Tests that arguments before and after the field code works
    // (Borrowed from KDE because someone had this exact line in an issue)
    let exec = "/usr/bin/flatpak run --branch=stable --arch=x86_64 --command=okular --file-forwarding org.kde.okular @@u %U @@";
    let args_leading = [
        "run",
        "--branch=stable",
        "--arch=x86_64",
        "--command=okular",
        "--file-forwarding",
        "org.kde.okular",
        "@@u",
    ];
    let paths = ["rust_game_dev.pdf", "superhero_ferris.epub"];
    let args_trailing = ["@@"];
    let commands = exec_to_command(exec, "sandwiched_field_code", None, &paths)
        .expect("Should parse valid exec");

    assert_eq!(1, commands.len());
    let command = commands.first().unwrap();
    assert_eq!(
        args_leading.len() + paths.len() + args_trailing.len(),
        command.get_args().len()
    );

    assert_eq!("/usr/bin/flatpak", command.get_program().to_str().unwrap());
    assert!(
        args_leading
            .iter()
            .chain(paths.iter())
            .chain(args_trailing.iter())
            .zip(command.get_args())
            .all(|(&expected, actual)| expected == actual.to_string_lossy())
    );
}
