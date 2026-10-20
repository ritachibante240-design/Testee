import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.main import save_video_upload


class VideoUploadTests(unittest.TestCase):
    def test_saves_supported_non_mp4_video_format(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            upload = SimpleNamespace(
                filename="recording.mkv",
                file=io.BytesIO(b"matroska video content"),
            )

            with patch("app.main.VIDEO_DIR", Path(directory)):
                path = save_video_upload(upload)

            try:
                self.assertEqual(path.suffix, ".mkv")
                self.assertEqual(path.read_bytes(), b"matroska video content")
            finally:
                path.unlink(missing_ok=True)

    def test_detects_webm_content_even_when_named_mp4(self) -> None:
        webm_header = (
            b"\x1a\x45\xdf\xa3\x9f"
            b"\x42\x86\x81\x01"
            b"\x42\xf7\x81\x01"
            b"\x42\xf2\x81\x04"
            b"\x42\xf3\x81\x08"
            b"\x42\x82\x84webm"
        )
        with tempfile.TemporaryDirectory() as directory:
            upload = SimpleNamespace(
                filename="video.mp4",
                file=io.BytesIO(webm_header + b"video data"),
            )

            with patch("app.main.VIDEO_DIR", Path(directory)):
                path = save_video_upload(upload)

            try:
                self.assertEqual(path.suffix, ".webm")
                self.assertEqual(path.read_bytes(), webm_header + b"video data")
            finally:
                path.unlink(missing_ok=True)

    def test_rejects_non_video_file_extension(self) -> None:
        upload = SimpleNamespace(filename="document.pdf", file=io.BytesIO(b"data"))

        with self.assertRaises(HTTPException) as error:
            save_video_upload(upload)

        self.assertEqual(error.exception.status_code, 415)

    def test_rejects_mp4_extension_with_invalid_file_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            upload = SimpleNamespace(
                filename="video.mp4",
                file=io.BytesIO(b"not an mp4 video"),
            )

            with patch("app.main.VIDEO_DIR", Path(directory)):
                with self.assertRaises(HTTPException) as error:
                    save_video_upload(upload)

            self.assertEqual(error.exception.status_code, 400)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
