"""JPEG marker-fill regressions using independently decoded fixtures.

ITU T.81 B.1.1.2 permits FF fill before markers:
https://www.w3.org/Graphics/JPEG/itu-t81.pdf
"""
import base64
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lib.images import probe_dimensions
from lib import htmlx, images
from lib.report import Report


def samples():
    fixture = Path(__file__).parent / 'fixtures/image-header-dimensions.json'
    for case in json.loads(fixture.read_text())['images']:
        if case['name'].startswith('jpeg'):
            yield case['name'], base64.b64decode(case['data_base64']), tuple(case['size'])


class TestJpegMarkerFill(unittest.TestCase):
    def test_social_image_finding_uses_the_measured_dimensions(self):
        url = 'https://example.test/'
        doc = htmlx.parse('<meta property="og:image" content="/card.jpg">', base_url=url)
        for name, data, size in samples():
            padded = data[:2] + b'\xff' + data[2:]
            with self.subTest(format=name):
                facts = images.audit_images(doc, url,
                    head_info=lambda *args, **kwargs: (200, {'content-type': 'image/jpeg'}, None),
                    fetch_range=lambda *args, **kwargs: (padded, None))
                report = Report(url)
                images.findings(facts, report)
                self.assertEqual(size, facts['og_image']['dimensions'])
                self.assertIn('og:image is too small', [f.title for f in report.findings])
                self.assertNotIn('og:image reachable', [f.title for f in report.findings])

    def test_fill_before_app_table_and_frame_markers_keeps_dimensions(self):
        for name, data, size in samples():
            frame = b'\xff\xc2' if name == 'jpeg_progressive' else b'\xff\xc0'
            for offset in (2, data.index(b'\xff\xdb'), data.rindex(frame)):
                for count in (1, 2, 8):
                    with self.subTest(format=name, offset=offset, fill=count):
                        padded = data[:offset] + b'\xff' * count + data[offset:]
                        self.assertEqual(size, probe_dimensions(padded))

    def test_long_fill_run_and_incomplete_marker_prefix_stay_bounded(self):
        for name, data, size in samples():
            with self.subTest(format=name):
                self.assertEqual(size, probe_dimensions(data[:2] + b'\xff' * 4096 + data[2:]))
                self.assertIsNone(probe_dimensions(data[:2] + b'\xff' * 4096))


if __name__ == '__main__':
    unittest.main()
