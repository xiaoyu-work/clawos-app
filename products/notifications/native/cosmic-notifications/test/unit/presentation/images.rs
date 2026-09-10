use super::*;

use crate::presentation::tests::fixture::Fixture;

fn png(width: u32, height: u32) -> Vec<u8> {
    let mut bytes = Vec::new();
    let pixels = vec![0_u8; (width * height * 4) as usize];
    image::codecs::png::PngEncoder::new(&mut bytes)
        .write_image(&pixels, width, height, image::ExtendedColorType::Rgba8)
        .unwrap();
    bytes
}

fn svg_image(href: &str) -> String {
    format!(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"2\" height=\"2\"><image href=\"{href}\" width=\"2\" height=\"2\"/></svg>"
    )
}

#[test]
fn source_pixels_are_bounded_before_decode_and_normalized_before_transport() {
    let bytes = png(1024, 1024);
    assert!(bytes.len() < MAX_IMAGE_BYTES);
    let Icon::Rgba {
        width,
        height,
        pixels,
    } = raster_icon(&bytes).unwrap()
    else {
        panic!("expected pixels")
    };
    assert_eq!((width, height, pixels.len()), (512, 512, MAX_IMAGE_BYTES));
    for bytes in [png(4097, 1), png(2049, 2048)] {
        assert!(bytes.len() < MAX_IMAGE_BYTES);
        let error = raster_icon(&bytes).unwrap_err();
        let diagnostic = format!("{error:#}");
        assert!(
            diagnostic.contains("limit") || diagnostic.contains("dimension"),
            "{diagnostic}"
        );
    }
    assert!(source_dimensions(u32::MAX, u32::MAX).is_err());
    assert!(source_dimensions(4096, 1024).is_ok());
    assert!(source_dimensions(4096, 1025).is_err());
    assert!(source_dimensions(4097, 1).is_err());
    assert!(
        image_icon(&NotificationImage::Data {
            width: 1,
            height: 1,
            data: vec![0; 8],
        })
        .is_err(),
        "trailing pixel bytes are not accepted"
    );
}

#[test]
fn default_svg_decoder_reads_a_private_file_but_projection_never_resolves_references() {
    let fixture = Fixture::new();
    let path = fixture.root.join("private-canary.png");
    let canary = png(2, 2);
    std::fs::write(&path, &canary).unwrap();
    let svg = svg_image(path.to_str().unwrap());
    let default_tree = usvg::Tree::from_str(&svg, &usvg::Options::default()).unwrap();
    fn contains_canary(group: &usvg::Group, bytes: &[u8]) -> bool {
        group.children().iter().any(|node| match node {
            usvg::Node::Group(group) => contains_canary(group, bytes),
            usvg::Node::Image(image) => {
                matches!(image.kind(), usvg::ImageKind::PNG(data) if data.as_slice() == bytes)
            }
            _ => false,
        })
    }
    assert!(
        contains_canary(default_tree.root(), &canary),
        "the actual default resolver read the private image bytes"
    );
    for href in [
        path.to_str().unwrap().to_owned(),
        url::Url::from_file_path(&path).unwrap().to_string(),
        "https://example.invalid/icon.png".into(),
        "../private-canary.png".into(),
    ] {
        let error = svg_icon(svg_image(&href).as_bytes(), false).unwrap_err();
        assert!(error.to_string().contains("reference"), "{error:#}");
    }
    let fifo = fixture.root.join("must-not-open");
    rustix::fs::mkfifoat(
        rustix::fs::CWD,
        &fifo,
        rustix::fs::Mode::RUSR | rustix::fs::Mode::WUSR,
    )
    .unwrap();
    let writer_path = fifo.clone();
    let writer = std::thread::spawn(move || {
        use std::io::Write;
        let deadline = std::time::Instant::now() + std::time::Duration::from_millis(250);
        loop {
            match rustix::fs::open(
                &writer_path,
                rustix::fs::OFlags::WRONLY | rustix::fs::OFlags::NONBLOCK,
                rustix::fs::Mode::empty(),
            ) {
                Ok(fd) => {
                    File::from(fd).write_all(&canary).unwrap();
                    return true;
                }
                Err(rustix::io::Errno::NXIO) if std::time::Instant::now() < deadline => {
                    std::thread::sleep(std::time::Duration::from_millis(5));
                }
                Err(rustix::io::Errno::NXIO) => return false,
                Err(error) => panic!("fixture FIFO writer failed: {error}"),
            }
        }
    });
    assert!(svg_icon(svg_image(fifo.to_str().unwrap()).as_bytes(), false).is_err());
    assert!(
        !writer.join().unwrap(),
        "the projection must not open an embedded FIFO"
    );
}

#[test]
fn svgz_dtd_oversized_geometry_and_excessive_nodes_are_errors_not_empty_icons() {
    assert!(svg_icon(&[0x1f, 0x8b, 0, 0], false).is_err());
    assert!(svg_icon(b"<!DOCTYPE svg [<!ENTITY x \"content\">]><svg/>", false).is_err());
    assert!(
        svg_icon(
            b"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"4097\" height=\"1\"/>",
            false
        )
        .is_err()
    );
    let svg = format!(
        "<svg xmlns=\"http://www.w3.org/2000/svg\">{}</svg>",
        "<g/>".repeat(MAX_SVG_NODES as usize)
    );
    assert!(svg_icon(svg.as_bytes(), false).is_err());
    assert!(svg_icon(b"<svg", false).is_err());
    assert!(svg_icon(b"", false).is_err());
}

#[test]
fn embedded_images_are_bounded_and_nested_vectors_cannot_reopen_resource_loading() {
    let png = embedded_raster(&png(2, 2)).unwrap();
    let decoded = decode_raster(&png).unwrap();
    assert_eq!((decoded.width(), decoded.height()), (2, 2));
    let href = format!(
        "data:image/png,{}",
        png.iter()
            .map(|byte| format!("%{byte:02X}"))
            .collect::<String>()
    );
    let icon = svg_icon(svg_image(&href).as_bytes(), false).unwrap();
    icon.validate().unwrap();
    let image = format!("<image href=\"{href}\" width=\"2\" height=\"2\"/>");
    let excessive = format!(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"2\" height=\"2\">{}</svg>",
        image.repeat(MAX_SVG_IMAGES + 1)
    );
    assert!(svg_icon(excessive.as_bytes(), false).is_err());
    for href in [
        "data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'/%3E",
        "data:image/png;base64,aW52YWxpZA==",
    ] {
        assert!(svg_icon(svg_image(href).as_bytes(), false).is_err());
    }
}

#[test]
fn theme_resources_are_resolved_inside_the_app_not_forwarded_to_the_host() {
    let fixture = Fixture::new();
    let root = fixture
        .root
        .join("icons")
        .join(cosmic::icon_theme::default());
    let icons = root.join("scalable/apps");
    std::fs::create_dir_all(&icons).unwrap();
    std::fs::write(root.join("index.theme"), "[Icon Theme]\nName=Fixture\nDirectories=scalable/apps\n[scalable/apps]\nSize=16\nType=Scalable\nMinSize=1\nMaxSize=512\nContext=Applications\n").unwrap();
    let name = format!(
        "claw-fixture-{}-symbolic",
        fixture.root.file_name().unwrap().to_string_lossy()
    );
    let path = icons.join(format!("{name}.svg"));
    std::fs::write(&path, b"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"2\" height=\"2\"><rect width=\"2\" height=\"2\"/></svg>").unwrap();
    assert!(matches!(
        named_icon(&name).unwrap(),
        Some(Icon::Mask { .. })
    ));
    assert!(
        named_icon("claw-fixture-definitely-missing")
            .unwrap()
            .is_none()
    );
    assert!(named_icon("https://example.invalid/image.png").is_err());
}

#[test]
fn vector_projection_preserves_color_or_symbolic_alpha_without_encoded_data() {
    let svg = b"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"2\" height=\"1\"><rect width=\"2\" height=\"1\" fill=\"#ff0000\" fill-opacity=\"0.5\"/></svg>";
    let Icon::Rgba {
        width,
        height,
        pixels,
    } = svg_icon(svg, false).unwrap()
    else {
        panic!("expected pixels")
    };
    assert_eq!((width, height), (128, 128));
    assert!(pixels.chunks_exact(4).all(|pixel| pixel[0] == 255
        && pixel[1] == 0
        && pixel[2] == 0
        && (127..=128).contains(&pixel[3])));
    let Icon::Mask { alpha, .. } = svg_icon(svg, true).unwrap() else {
        panic!("expected mask")
    };
    assert_eq!(
        alpha,
        pixels
            .chunks_exact(4)
            .map(|pixel| pixel[3])
            .collect::<Vec<_>>()
    );
    let non_square = b"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"2\" height=\"1\"><rect width=\"1\" height=\"1\" fill=\"red\"/><rect x=\"1\" width=\"1\" height=\"1\" fill=\"blue\"/></svg>";
    let Icon::Rgba { pixels, .. } = svg_icon(non_square, false).unwrap() else {
        panic!("expected pixels")
    };
    assert!(
        pixels
            .chunks_exact(4)
            .all(|pixel| pixel == [255, 0, 0, 255]),
        "preserve the renderer's square-viewport SVG cropping, not raster stretching"
    );
}
