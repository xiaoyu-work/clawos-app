// SPDX-License-Identifier: GPL-3.0-only

use std::{
    fs::File,
    io::{Cursor, Read},
    path::Path,
    sync::{
        Arc, OnceLock,
        atomic::{AtomicBool, AtomicUsize, Ordering},
    },
};

use anyhow::{Context, Result, ensure};
use claw_notification_presentation::{Icon, MAX_IMAGE_BYTES, MAX_IMAGE_DIMENSION};
use cosmic::widget::icon;
use cosmic_notifications_util::Image as NotificationImage;
use image::{DynamicImage, ImageDecoder, ImageEncoder, ImageReader, RgbaImage};
use resvg::{tiny_skia, usvg};

const MAX_SOURCE_DIMENSION: u32 = 4096;
const MAX_SOURCE_PIXELS: u64 = 4 * 1024 * 1024;
const MAX_SVG_NODES: u32 = 4096;
const MAX_SVG_IMAGES: usize = 16;
const SVG_RASTER_DIMENSION: u32 = 128;

pub(super) fn image_icon(image: &NotificationImage) -> Result<Option<Icon>> {
    match image {
        NotificationImage::Name(name) => named_icon(name),
        NotificationImage::File(path) => file_icon(path).map(Some),
        NotificationImage::Data {
            width,
            height,
            data,
        } => {
            source_dimensions(*width, *height)?;
            ensure!(
                data.len() as u64 == u64::from(*width) * u64::from(*height) * 4,
                "invalid notification RGBA byte count"
            );
            let pixels = RgbaImage::from_raw(*width, *height, data.clone())
                .context("invalid notification RGBA pixels")?;
            rgba_icon(pixels).map(Some)
        }
    }
}

pub(super) fn named_icon(name: &str) -> Result<Option<Icon>> {
    if let Ok(url) = url::Url::parse(name) {
        if let Ok(path) = url.to_file_path() {
            return file_icon(&path).map(Some);
        }
    }
    if Path::new(name).is_absolute() {
        return file_icon(Path::new(name)).map(Some);
    }
    ensure!(
        !name.is_empty()
            && name.len() <= 1024
            && !matches!(name, "." | "..")
            && !name.chars().any(|c| c.is_control() || "/\\:".contains(c)),
        "invalid notification theme icon name"
    );
    let handle = icon::from_name(name.to_owned()).handle();
    match handle.data {
        icon::Data::Svg(handle_data) => {
            use cosmic::iced::advanced::svg::Data;
            match handle_data.data() {
                Data::Path(path) => svg_icon(&read_file(path)?, handle.symbolic).map(Some),
                Data::Bytes(bytes) if bytes.is_empty() => {
                    tracing::warn!(icon = name, "Notification theme icon is unavailable");
                    Ok(None)
                }
                Data::Bytes(bytes) => svg_icon(bytes, handle.symbolic).map(Some),
            }
        }
        icon::Data::Image(handle) => {
            use cosmic::iced::advanced::image::Handle;
            match handle {
                Handle::Path(_, path) => raster_icon(&read_file(&path)?).map(Some),
                Handle::Bytes(_, bytes) => raster_icon(&bytes).map(Some),
                Handle::Rgba {
                    width,
                    height,
                    pixels,
                    ..
                } => {
                    source_dimensions(width, height)?;
                    ensure!(
                        pixels.len() as u64 == u64::from(width) * u64::from(height) * 4,
                        "invalid theme RGBA byte count"
                    );
                    rgba_icon(
                        RgbaImage::from_raw(width, height, pixels.to_vec())
                            .context("invalid theme RGBA pixels")?,
                    )
                    .map(Some)
                }
            }
        }
    }
}

fn file_icon(path: &Path) -> Result<Icon> {
    let bytes = read_file(path)?;
    if path.extension().is_some_and(|extension| extension == "svg") {
        let symbolic = path
            .file_stem()
            .and_then(|name| name.to_str())
            .is_some_and(|name| name.ends_with("-symbolic"));
        svg_icon(&bytes, symbolic)
    } else {
        raster_icon(&bytes)
    }
}

fn read_file(path: &Path) -> Result<Vec<u8>> {
    let fd = rustix::fs::open(
        path,
        rustix::fs::OFlags::RDONLY | rustix::fs::OFlags::CLOEXEC | rustix::fs::OFlags::NONBLOCK,
        rustix::fs::Mode::empty(),
    )
    .context("open notification presentation image")?;
    let file = File::from(fd);
    ensure!(
        file.metadata()?.is_file(),
        "notification image is not a regular file"
    );
    let mut bytes = Vec::new();
    file.take((MAX_IMAGE_BYTES + 1) as u64)
        .read_to_end(&mut bytes)
        .context("read notification presentation image")?;
    encoded_length(&bytes)?;
    Ok(bytes)
}

fn encoded_length(bytes: &[u8]) -> Result<()> {
    ensure!(
        !bytes.is_empty() && bytes.len() <= MAX_IMAGE_BYTES,
        "empty or excessive image input"
    );
    Ok(())
}

fn source_dimensions(width: u32, height: u32) -> Result<()> {
    ensure!(
        width > 0
            && height > 0
            && width <= MAX_SOURCE_DIMENSION
            && height <= MAX_SOURCE_DIMENSION
            && u64::from(width) * u64::from(height) <= MAX_SOURCE_PIXELS,
        "notification image exceeds decoded dimension/pixel limits"
    );
    Ok(())
}

fn decode_raster(bytes: &[u8]) -> Result<RgbaImage> {
    encoded_length(bytes)?;
    let mut reader = ImageReader::new(Cursor::new(bytes)).with_guessed_format()?;
    let mut limits = image::Limits::default();
    limits.max_image_width = Some(MAX_SOURCE_DIMENSION);
    limits.max_image_height = Some(MAX_SOURCE_DIMENSION);
    limits.max_alloc = Some(MAX_SOURCE_PIXELS * 16);
    reader.limits(limits);
    let mut decoder = reader
        .into_decoder()
        .context("open bounded image decoder")?;
    let (width, height) = decoder.dimensions();
    source_dimensions(width, height)?;
    let orientation = decoder.orientation().context("read image orientation")?;
    let mut image = DynamicImage::from_decoder(decoder).context("decode notification image")?;
    image.apply_orientation(orientation);
    Ok(image.into_rgba8())
}

fn normalized(pixels: RgbaImage) -> RgbaImage {
    if pixels.width() <= MAX_IMAGE_DIMENSION && pixels.height() <= MAX_IMAGE_DIMENSION {
        pixels
    } else {
        image::imageops::thumbnail(&pixels, MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION)
    }
}

fn rgba_icon(pixels: RgbaImage) -> Result<Icon> {
    let pixels = normalized(pixels);
    let icon = Icon::Rgba {
        width: pixels.width(),
        height: pixels.height(),
        pixels: pixels.into_raw(),
    };
    icon.validate()?;
    Ok(icon)
}

fn raster_icon(bytes: &[u8]) -> Result<Icon> {
    rgba_icon(decode_raster(bytes)?)
}

fn svg_icon(bytes: &[u8], symbolic: bool) -> Result<Icon> {
    encoded_length(bytes)?;
    // UTF-8 XML only: do not inflate SVGZ or expand a DTD before applying limits.
    let text = std::str::from_utf8(bytes).context("SVG must be uncompressed UTF-8")?;
    ensure!(
        !text.contains("<!DOCTYPE"),
        "SVG document types are unsupported"
    );
    let document = usvg::roxmltree::Document::parse_with_options(
        text,
        usvg::roxmltree::ParsingOptions {
            allow_dtd: false,
            nodes_limit: MAX_SVG_NODES,
        },
    )
    .context("parse bounded SVG")?;
    let rejected = AtomicBool::new(false);
    let images = AtomicUsize::new(0);
    let resolver = usvg::ImageHrefResolver {
        resolve_string: Box::new(|_, _| {
            rejected.store(true, Ordering::Relaxed);
            None
        }),
        resolve_data: Box::new(|mime, bytes, _| {
            if images.fetch_add(1, Ordering::Relaxed) >= MAX_SVG_IMAGES
                || !matches!(
                    mime,
                    "image/png" | "image/jpeg" | "image/jpg" | "image/gif" | "image/webp"
                )
            {
                rejected.store(true, Ordering::Relaxed);
                return None;
            }
            match embedded_raster(&bytes) {
                Ok(bytes) => Some(usvg::ImageKind::PNG(Arc::new(bytes))),
                Err(error) => {
                    tracing::warn!(%error, "SVG embedded image was rejected");
                    rejected.store(true, Ordering::Relaxed);
                    None
                }
            }
        }),
    };
    let mut options = usvg::Options {
        image_href_resolver: resolver,
        ..usvg::Options::default()
    };
    if document.descendants().any(|node| node.has_tag_name("text")) {
        static FONTS: OnceLock<Arc<usvg::fontdb::Database>> = OnceLock::new();
        options.fontdb = FONTS
            .get_or_init(|| {
                let mut fonts = usvg::fontdb::Database::new();
                fonts.load_system_fonts();
                Arc::new(fonts)
            })
            .clone();
    }
    let tree = usvg::Tree::from_xmltree(&document, &options).context("prepare SVG")?;
    ensure!(
        !rejected.load(Ordering::Relaxed),
        "SVG contains an external, unsupported or excessive image reference"
    );
    let size = tree.size().to_int_size();
    source_dimensions(size.width(), size.height())?;
    let mut count = 0;
    let mut groups = vec![tree.root()];
    while let Some(group) = groups.pop() {
        for node in group.children() {
            count += 1;
            ensure!(count <= MAX_SVG_NODES, "SVG expanded node limit exceeded");
            if let usvg::Node::Group(group) = node {
                groups.push(group);
            }
        }
    }
    let width = SVG_RASTER_DIMENSION;
    let height = SVG_RASTER_DIMENSION;
    let target = size
        .scale_to_height(height)
        .context("SVG aspect ratio cannot be represented")?;
    let mut pixels =
        tiny_skia::Pixmap::new(width, height).context("allocate bounded SVG pixels")?;
    // Match the toolkit's square icon viewport, including non-square SVG cropping.
    resvg::render(
        &tree,
        tiny_skia::Transform::from_scale(
            target.width() as f32 / size.width() as f32,
            target.height() as f32 / size.height() as f32,
        ),
        &mut pixels.as_mut(),
    );
    let icon = if symbolic {
        Icon::Mask {
            width,
            height,
            alpha: pixels.pixels().iter().map(|pixel| pixel.alpha()).collect(),
        }
    } else {
        Icon::Rgba {
            width,
            height,
            pixels: pixels
                .pixels()
                .iter()
                .flat_map(|pixel| {
                    let color = pixel.demultiply();
                    [color.red(), color.green(), color.blue(), color.alpha()]
                })
                .collect(),
        }
    };
    icon.validate()?;
    Ok(icon)
}

fn embedded_raster(bytes: &[u8]) -> Result<Vec<u8>> {
    let pixels = normalized(decode_raster(bytes)?);
    let mut png = Vec::new();
    image::codecs::png::PngEncoder::new(&mut png).write_image(
        pixels.as_raw(),
        pixels.width(),
        pixels.height(),
        image::ExtendedColorType::Rgba8,
    )?;
    Ok(png)
}

#[cfg(test)]
mod tests {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/unit/presentation/images.rs"
    ));
}
