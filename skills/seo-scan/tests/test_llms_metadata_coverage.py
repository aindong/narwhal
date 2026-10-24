"""An llms.txt starter must not treat unavailable page metadata as observed."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_llms as llms
import mcp_server
from lib import http

URL = 'https://example.test/'
HTML = '<html><head><title>Example</title><meta name="description" content="Site description"></head></html>'


def response(url=URL, status=200, headers=None, text=HTML, error=None):
    return http.Response(url, url, status, {'content-type': 'text/html'} if headers is None else headers,
                         text, 1, error=error)


def unavailable():
    return [response(status=503, error='PRIVATE_RESPONSE_DETAIL'), response(status=304),
            response(status=206), response(headers={'content-range': ''}),
            response(headers={'x-narwhal-truncated': 'true'}),
            response(headers={'content-type': 'application/json'}, text='{"title":"misleading"}'),
            response(text=' \n\t')]


class TestLlmsMetadataCoverage(unittest.TestCase):
    def test_unusable_homepage_stops_before_discovery_or_parsing(self):
        for home in unavailable():
            with self.subTest(status=home.status, headers=home.headers):
                with mock.patch.object(http, 'fetch', return_value=home) as fetch, \
                        mock.patch.object(llms.crawl_site, 'discover') as discover, \
                        mock.patch.object(llms.htmlx, 'parse') as parse, \
                        mock.patch.object(http, 'fetch_text') as text:
                    with self.assertRaises(llms.GenerationError) as error:
                        llms.build(URL)
                    self.assertNotIn('PRIVATE_RESPONSE_DETAIL', str(error.exception))
                    self.assertLess(len(str(error.exception)), 250)
                    self.assertEqual(1, fetch.call_count)
                    discover.assert_not_called(); parse.assert_not_called(); text.assert_not_called()

    def test_unusable_child_responses_are_not_parsed_or_used(self):
        for child in unavailable():
            with mock.patch.object(http, 'fetch', return_value=child), \
                    mock.patch.object(llms.htmlx, 'parse') as parse:
                self.assertIsNone(llms._page_meta(URL + 'child', False, 20))
                parse.assert_not_called()

    def test_only_selected_metadata_fetches_count_in_coverage(self):
        good, partial, failed, blocked = [URL + path for path in ('good', 'partial', 'failed', 'blocked')]
        responses = {URL: response(), good: response(good, text='<title>Good</title>'),
                     partial: response(partial, status=206), failed: response(failed, status=500)}
        with mock.patch.object(http, 'fetch', side_effect=lambda url, **kwargs: responses[url]), \
                mock.patch.object(http, 'fetch_text', return_value='User-agent: *\nDisallow: /blocked'), \
                mock.patch.object(llms.crawl_site, 'discover', return_value=[good, partial, failed, blocked]):
            data = llms.build(URL)
        self.assertEqual(1, data['pages'])
        self.assertEqual({'basis': 'selected_page_metadata_fetches_v1', 'attempted_pages': 3,
                          'included_pages': 1, 'omitted_pages': 2}, data['coverage'])
        self.assertEqual([good], [page['url'] for _, pages in data['sections'] for page in pages])
        output = llms.render_llms_txt(data['site_name'], data['description'], data['sections'], coverage=data['coverage'])
        self.assertIn('1 of 3 selected page fetches included; 2 omitted', output)
        self.assertIn('Review missing entries before publishing', output)
        self.assertNotIn(blocked, output)

    def test_healthy_xhtml_and_missing_content_type_remain_supported(self):
        for headers in ({}, {'content-type': 'application/xhtml+xml; charset=utf-8'},
                        {'content-type': 'text/html; charset=UTF-8'}):
            with mock.patch.object(http, 'fetch', return_value=response(headers=headers)), \
                    mock.patch.object(http, 'fetch_text', return_value=''), \
                    mock.patch.object(llms.crawl_site, 'discover', return_value=[URL]):
                data = llms.build(URL)
            output = llms.render_llms_txt(data['site_name'], data['description'], data['sections'], coverage=data['coverage'])
            self.assertEqual(llms.render_llms_txt(data['site_name'], data['description'], data['sections']), output)
            self.assertEqual(0, data['coverage']['omitted_pages'])
            self.assertIn('# Example', output)

    def test_cli_home_failure_preserves_existing_output_and_creates_no_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'llms.txt'
            for existing in (False, True):
                if existing:
                    output.write_bytes(b'curated original')
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(http, 'fetch', return_value=response(status=503)), \
                        mock.patch.object(http, 'fetch_text', return_value=''), \
                        mock.patch.object(llms.crawl_site, 'discover', return_value=[]), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = llms.main([URL, '-o', str(output)])
                self.assertEqual(2, code)
                self.assertEqual('', out.getvalue())
                self.assertIn('homepage', err.getvalue().lower())
                self.assertNotIn('Traceback', err.getvalue())
                self.assertEqual(b'curated original' if existing else None,
                                 output.read_bytes() if output.exists() else None)

    def test_mcp_keeps_omission_disclosure_and_rejects_unusable_home(self):
        data = {'site_name': 'Example', 'description': '', 'sections': [], 'pages': 0,
                'coverage': {'basis': 'selected_page_metadata_fetches_v1', 'attempted_pages': 1,
                             'included_pages': 0, 'omitted_pages': 1}}
        with mock.patch.object(llms, 'build', return_value=data):
            self.assertIn('0 of 1 selected page fetches included; 1 omitted', mcp_server._llms(URL))
        with mock.patch.object(http, 'fetch', return_value=response(status=503)):
            with self.assertRaises(llms.GenerationError):
                mcp_server._llms(URL)


if __name__ == '__main__':
    unittest.main()
