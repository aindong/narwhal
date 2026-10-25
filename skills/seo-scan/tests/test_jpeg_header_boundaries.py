"""JPEG dimensions must precede scan/end markers and fit a plausible header.

ITU T.81 B.1.1.4 and B.2.2:
https://www.w3.org/Graphics/JPEG/itu-t81.pdf
"""
import base64
import json
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lib import htmlx, images
from lib.report import Report


def frame(length=17, components=3):
    return (b'\xff\xc0' + struct.pack('>HBHHB', length, 8, 630, 1200, components)
            + b'\x01\x11\x00\x02\x11\x01\x03\x11\x01')


def invalid_prefixes():
    for fill in (b'', b'\xff\xff'):
        yield b'\xff\xd8' + fill + b'\xff\xd9\x00\x00' + frame()
        yield b'\xff\xd8' + fill + b'\xff\xd9\x00\x02' + frame()
        yield b'\xff\xd8' + fill + b'\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x00\x00' + frame()
    for length in (0, 1):
        yield b'\xff\xd8\xff\xe1' + struct.pack('>H', length) + frame()
    for length in range(21):
        if length != 17:
            yield b'\xff\xd8' + frame(length) + b'\x00' * 8
    for length, components in ((17, 0), (17, 4), (8, 0)):
        yield b'\xff\xd8' + frame(length, components) + b'\x00' * 8


class TestJpegHeaderBoundaries(unittest.TestCase):
    def test_bytes_after_scan_end_or_invalid_lengths_cannot_supply_dimensions(self):
        for index, data in enumerate(invalid_prefixes()):
            with self.subTest(case=index):
                self.assertIsNone(images.probe_dimensions(data))

    def test_invalid_header_cannot_make_a_social_image_look_healthy(self):
        url = 'https://example.test/'
        doc = htmlx.parse('<meta property="og:image" content="/card.jpg">', base_url=url)
        for index, data in enumerate(invalid_prefixes()):
            with self.subTest(case=index):
                facts = images.audit_images(doc, url,
                    head_info=lambda *args, **kwargs: (200, {'content-type': 'image/jpeg'}, None),
                    fetch_range=lambda *args, **kwargs: (data, None))
                report = Report(url)
                images.findings(facts, report)
                self.assertIsNone(facts['og_image']['dimensions'])
                self.assertNotIn('og:image looks healthy', [f.title for f in report.findings])

    def test_minimum_grayscale_and_existing_color_headers_still_supply_dimensions(self):
        fixture = Path(__file__).parent / 'fixtures/image-header-dimensions.json'
        for case in json.loads(fixture.read_text())['images']:
            if not case['name'].startswith('jpeg'):
                continue
            data = base64.b64decode(case['data_base64'])
            with self.subTest(format=case['name']):
                self.assertEqual(tuple(case['size']), images.probe_dimensions(data))
                self.assertEqual(tuple(case['size']), images.probe_dimensions(data + b'\x00\x00' + frame()))
                self.assertEqual(tuple(case['size']), images.probe_dimensions(data[:2] + b'\xff\xef\x00\x02' + data[2:]))
                if case['name'] == 'jpeg_grayscale':
                    offset = data.index(b'\xff\xc0')
                    self.assertEqual(11, int.from_bytes(data[offset+2:offset+4], 'big'))


if __name__ == '__main__':
    unittest.main()
