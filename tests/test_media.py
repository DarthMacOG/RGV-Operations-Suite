import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from core.media import (
    collect_media,
    find_ffmpeg,
    process_image,
    process_video,
    unique_output_path,
    watermark_coordinates,
    watermark_position_for,
)


class MediaTests(unittest.TestCase):
    def test_media_type_selects_fixed_position(self):
        self.assertEqual(watermark_position_for(Path("photo.jpg")), "Bottom Left")
        self.assertEqual(watermark_position_for(Path("clip.mp4")), "Top Right")

    def test_coordinates(self):
        self.assertEqual(watermark_coordinates((1000, 500), (100, 50), "Bottom Right", 20), (880, 430))
        self.assertEqual(watermark_coordinates((1000, 500), (100, 50), "Top Left", 20), (20, 20))

    def test_collect_media_recurses_and_filters(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "nested").mkdir()
            (root / "photo.jpg").touch()
            (root / "nested" / "clip.mp4").touch()
            (root / "notes.txt").touch()
            self.assertEqual({path.name for path in collect_media([root])}, {"photo.jpg", "clip.mp4"})

    def test_unique_output_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "camera.jpg"
            source.touch()
            first = unique_output_path(root, source)
            self.assertEqual(first.name, "camera_RGV.jpg")
            first.touch()
            self.assertEqual(unique_output_path(root, source).name, "camera_RGV_2.jpg")

    def test_process_image_places_transparent_logo(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.png"
            logo = root / "logo.png"
            destination = root / "result.png"
            Image.new("RGB", (400, 200), "white").save(source)
            Image.new("RGBA", (100, 50), (255, 0, 0, 255)).save(logo)
            process_image(source, logo, destination, "Bottom Right", 25, 100, 10)
            with Image.open(destination) as result:
                self.assertEqual(result.size, (400, 200))
                self.assertEqual(result.convert("RGB").getpixel((350, 170)), (255, 0, 0))
                self.assertEqual(result.convert("RGB").getpixel((10, 10)), (255, 255, 255))

    def test_process_image_enlarges_small_logo(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.png"
            logo = root / "tiny-logo.png"
            destination = root / "result.png"
            Image.new("RGB", (1000, 500), "white").save(source)
            Image.new("RGBA", (10, 5), (255, 0, 0, 255)).save(logo)
            process_image(source, logo, destination, "Top Left", 20, 100, 0)
            with Image.open(destination) as result:
                # A 20% watermark must span 200 pixels even if the source logo
                # is only 10 pixels wide.
                self.assertEqual(result.convert("RGB").getpixel((199, 50)), (255, 0, 0))
                self.assertEqual(result.convert("RGB").getpixel((201, 50)), (255, 255, 255))

    @unittest.skipUnless(find_ffmpeg(), "FFmpeg is not available")
    def test_video_is_full_length_and_compatible(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp4"
            logo = root / "logo.png"
            destination = root / "result.mp4"
            Image.new("RGBA", (100, 50), (255, 0, 0, 255)).save(logo)
            ffmpeg = str(find_ffmpeg())
            subprocess.run(
                [
                    ffmpeg, "-y", "-f", "lavfi", "-i",
                    "color=c=blue:s=640x360:d=2", "-pix_fmt", "yuv420p", str(source),
                ],
                check=True,
                capture_output=True,
            )
            process_video(source, logo, destination, "Top Left", 20, 100, 0)
            decoded = subprocess.run(
                [ffmpeg, "-hide_banner", "-i", str(destination), "-f", "null", "-"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(decoded.returncode, 0, decoded.stderr)
            self.assertIn("yuv420p", decoded.stderr)
            self.assertRegex(decoded.stderr, r"time=00:00:0[12]\.")

            frame = root / "frame.png"
            subprocess.run(
                [ffmpeg, "-y", "-i", str(destination), "-frames:v", "1", str(frame)],
                check=True,
                capture_output=True,
            )
            with Image.open(frame) as image:
                rgb = image.convert("RGB")
                red_pixels = [
                    (x, y)
                    for y in range(rgb.height)
                    for x in range(rgb.width)
                    if rgb.getpixel((x, y))[0] > 180
                    and rgb.getpixel((x, y))[1] < 80
                    and rgb.getpixel((x, y))[2] < 80
                ]
                self.assertTrue(red_pixels)
                rendered_width = max(x for x, _ in red_pixels) - min(x for x, _ in red_pixels) + 1
                # 20% of a 640-pixel frame is 128 pixels. Allow a few pixels
                # for H.264 edge compression.
                self.assertGreaterEqual(rendered_width, 124)
                self.assertLessEqual(rendered_width, 130)


if __name__ == "__main__":
    unittest.main()
