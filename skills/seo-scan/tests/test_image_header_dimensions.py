"""Header dimension vectors, not full-file image validation.

WebP layouts: https://developers.google.com/speed/webp/docs/riff_container
VP8 fields: https://datatracker.ietf.org/doc/html/rfc6386#section-9.1
VP8L fields: https://developers.google.com/speed/webp/docs/webp_lossless_bitstream_specification
GIF fields: https://www.w3.org/Graphics/GIF/spec-gif89a.txt
"""
from pathlib import Path
import base64
import json
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lib.images import probe_dimensions


def webp(kind, payload):
    chunk = kind + struct.pack('<I', len(payload)) + payload
    return b'RIFF' + struct.pack('<I', 4 + len(chunk) + len(payload) % 2) + b'WEBP' + chunk


def jpeg(marker, width, height, comment=False):
    app = b'\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
    sof = b'\xff' + bytes([marker]) + struct.pack('>HBHHB', 17, 8, height, width, 3)
    sof += b'\x01\x11\x00\x02\x11\x01\x03\x11\x01'
    return b'\xff\xd8' + app + (b'\xff\xfe\x00\x04ok' if comment else b'') + sof


class TestImageHeaderDimensions(unittest.TestCase):
    def test_complete_encoded_files_match_independently_decoded_sizes(self):
        fixture = Path(__file__).parent / 'fixtures/image-header-dimensions.json'
        for case in json.loads(fixture.read_text())['images']:
            with self.subTest(format=case['name']):
                self.assertEqual(tuple(case['size']), probe_dimensions(base64.b64decode(case['data_base64'])))

    def test_png_dimensions_at_the_24_byte_prefix_boundary(self):
        data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR' + struct.pack('>II', 1200, 630)
        self.assertEqual(24, len(data))
        self.assertEqual((1200, 630), probe_dimensions(data))
        for end in range(len(data)):
            with self.subTest(end=end):
                self.assertIsNone(probe_dimensions(data[:end]))

    def test_gif_versions_use_unsigned_little_endian_dimensions(self):
        for version in (b'GIF87a', b'GIF89a'):
            for width, height in ((1, 2), (320, 240), (32768, 65535)):
                data = version + struct.pack('<HH', width, height) + b'\x00' * 14
                with self.subTest(version=version, size=(width, height)):
                    self.assertEqual((width, height), probe_dimensions(data))

    def test_webp_extended_uses_one_based_24_bit_canvas_fields(self):
        for width, height in ((1, 1), (2, 3), (800, 420), (65537, 257), (257, 131073)):
            data = webp(b'VP8X', b'\x00' * 4 + (width - 1).to_bytes(3, 'little') + (height - 1).to_bytes(3, 'little'))
            with self.subTest(size=(width, height)):
                self.assertEqual((width, height), probe_dimensions(data))
                for end in range(len(data)):
                    self.assertIsNone(probe_dimensions(data[:end]))

    def test_webp_lossy_ignores_scale_bits_in_dimension_fields(self):
        for width, height in ((1, 2), (1200, 630), (16383, 16382)):
            for scale in range(4):
                frame = b'\x10\x00\x00\x9d\x01\x2a' + struct.pack('<HH', width | (scale << 14), height | (scale << 14))
                data = webp(b'VP8 ', frame)
                with self.subTest(size=(width, height), scale=scale):
                    self.assertEqual((width, height), probe_dimensions(data))
                    self.assertIsNone(probe_dimensions(data[:29]))

    def test_webp_lossless_masks_alpha_and_unpacks_one_based_fields(self):
        for width, height in ((1, 1), (2, 3), (1200, 630), (16384, 16383)):
            for alpha in (0, 1):
                fields = (width - 1) | ((height - 1) << 14) | (alpha << 28)
                data = webp(b'VP8L', b'\x2f' + struct.pack('<I', fields))
                with self.subTest(size=(width, height), alpha=alpha):
                    self.assertEqual(25, len(data))
                    self.assertEqual((width, height), probe_dimensions(data))
                    self.assertIsNone(probe_dimensions(data[:24]))

    def test_jpeg_baseline_and_progressive_skip_app_and_comment_segments(self):
        for marker in (0xC0, 0xC2):
            for comment in (False, True):
                for width, height in ((1200, 630), (40000, 1), (1, 40000)):
                    with self.subTest(marker=marker, comment=comment, size=(width, height)):
                        self.assertEqual((width, height), probe_dimensions(jpeg(marker, width, height, comment)))
        self.assertIsNone(probe_dimensions(b'\xff\xd8' + b'\x00' * 30))

    def test_unknown_chunk_and_mismatched_container_signatures_stay_unknown(self):
        data = webp(b'VP8X', b'\x00' * 4 + b'\x1f\x03\x00\xa3\x01\x00')
        for malformed in (data.replace(b'RIFF', b'RIFx'), data.replace(b'WEBP', b'WAVE'),
                          data.replace(b'VP8X', b'JUNK'), b'unknown format' + b'\x00' * 30):
            with self.subTest(prefix=malformed[:16]):
                self.assertIsNone(probe_dimensions(malformed))


if __name__ == '__main__':
    unittest.main()
