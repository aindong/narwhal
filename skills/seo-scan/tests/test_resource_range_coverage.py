"""Complete-resource APIs must not certify ranged XML or empty range markers."""
import gzip
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from lib import http,llms_resource
from lib.report import recorded_llms_problem
from lib.sitemap_discovery import Discovery
from test_sitemap_fetch_completeness import XML,URL,REQUESTS,Stream,requests_response,fetch
from test_llms_resource import response as llms_response,report_for


class ResourceHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = gzip.compress(XML) if self.path == '/gzip' else XML
        self.send_response(206 if self.path == '/partial' else 200)
        self.send_header('Content-Length', str(len(body)))
        if self.path in ('/range', '/empty-range'):
            self.send_header('CoNtEnT-RaNgE', '' if self.path == '/empty-range' else 'bytes 0-80/900')
        if self.path == '/gzip':
            self.send_header('Content-Encoding', 'gzip')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class TestLiveResourceRangeCoverage(unittest.TestCase):
    """Exercise native header containers and sockets, without public networking."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), ResourceHandler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=5)

    def check_transport(self, requests_module):
        root = 'http://127.0.0.1:' + str(self.server.server_port)
        with mock.patch.dict(sys.modules, {'requests': requests_module}):
            for path in ('/partial', '/range', '/empty-range'):
                with self.subTest(path=path):
                    url = root + path
                    self.assertEqual((None, http.PARTIAL_RESOURCE_ERROR),
                                     http.fetch_bytes(url, allow_private=True, timeout=2))
                    reader = Discovery('crawl_candidates')
                    self.assertIsNone(reader.read(url, allow_private=True, timeout=2))
                    self.assertEqual(0, reader.receipt()['verified_files'])
                    self.assertEqual(1, reader.receipt()['unverified_files'])
                    self.assertEqual(0, reader.receipt()['absent_files'])
            for path in ('/plain', '/gzip'):
                with self.subTest(path=path):
                    self.assertEqual((XML, None), http.fetch_bytes(root + path, allow_private=True, timeout=2))

    def test_real_urllib_range_headers_and_complete_controls(self):
        self.check_transport(None)

    def test_real_requests_range_headers_and_complete_controls(self):
        try:
            import requests
        except ImportError:
            self.skipTest('Optional requests backend is not installed')
        self.check_transport(requests)


def ranged(provider,status=200,marker='bytes 900-980/4000',encoded=False):
    wire=gzip.compress(XML) if encoded else XML
    value=requests_response([wire],status,length=len(wire)) if provider=='requests' else Stream(wire,status,declared=len(wire))
    if marker is not None:value.headers['content-range']=marker
    if encoded:
        value.headers['content-encoding']='gzip'
        if provider=='requests':value.raw.read.return_value=wire
    return value


class TestResourceRangeCoverage(unittest.TestCase):
    def test_range_bytes_are_not_complete_resource_data_in_either_backend(self):
        for provider in ('requests','urllib'):
            for status,marker in ((206,None),(200,'bytes 0-80/900'),(200,''),(200,'secret:password@untrusted')):
                raw,error=fetch(provider,ranged(provider,status,marker))
                self.assertIsNone(raw,(provider,status,marker))
                self.assertIn('partial',error.lower())
                self.assertNotIn('password',error)

    def test_range_rejection_precedes_body_read_and_closes_each_transport(self):
        for provider in ('requests','urllib'):
            value=ranged(provider,206)
            if provider=='requests':value.iter_content.side_effect=AssertionError('Do not read range body')
            else:value.read=mock.Mock(side_effect=AssertionError('Do not read range body'))
            raw,error=fetch(provider,value)
            self.assertIsNone(raw);self.assertIn('partial',error.lower())
            if provider=='requests':value.close.assert_called_once();value.iter_content.assert_not_called()
            else:self.assertTrue(value.closed);value.read.assert_not_called()

    def test_range_rejection_precedes_encoded_read_and_xml_decode(self):
        for provider in ('requests','urllib'):
            value=ranged(provider,206,encoded=True)
            with mock.patch.object(http,'_decode_http_content',side_effect=AssertionError('No decode')):
                raw,error=fetch(provider,value)
            self.assertIsNone(raw);self.assertIn('partial',error.lower())
            if provider=='requests':value.raw.read.assert_not_called();value.close.assert_called_once()
            else:self.assertTrue(value.closed)

    def test_complete_plain_and_gzip_controls_keep_exact_decoded_bytes(self):
        for provider in ('requests','urllib'):
            for encoded in (False,True):
                self.assertEqual((XML,None),fetch(provider,ranged(provider,marker=None,encoded=encoded)))

    def test_http_error_control_retains_status_not_partial_success(self):
        for provider in ('requests','urllib'):
            self.assertEqual((None,'HTTP 404'),fetch(provider,ranged(provider,404)))

    def test_discovery_does_not_parse_range_bytes_as_a_verified_xml_root(self):
        for provider in ('requests','urllib'):
            name='_requests_safe' if provider=='requests' else '_urllib_safe_open'
            value=ranged(provider,206)
            with mock.patch.dict(sys.modules,{'requests':REQUESTS if provider=='requests' else None}), \
                    mock.patch.object(http,'assert_public_host'),mock.patch.object(http,name,return_value=(value,URL,[])), \
                    mock.patch('lib.sitemap.decode_checked',side_effect=AssertionError('No XML decode')):
                reader=Discovery('crawl_candidates')
                self.assertIsNone(reader.read(URL,allow_private=False,timeout=1))
            self.assertEqual(0,reader.receipt()['verified_files'])
            self.assertEqual(1,reader.receipt()['unverified_files'])

    def test_empty_range_marker_cannot_certify_llms_candidate_or_absence(self):
        for status in (200,404,410):
            value=llms_response(status=status);value.headers['content-range']=''
            receipt=llms_resource.assess(value)
            self.assertEqual('unverified',receipt['state'])
            self.assertEqual('partial_response',receipt['reason'])
            self.assertTrue(receipt['partial_response'])
            self.assertIsNotNone(llms_resource.recorded(receipt))

    def test_empty_range_marker_gives_verification_not_missing_file_advice(self):
        value=llms_response();value.headers['content-range']=''
        report=report_for(value)
        self.assertEqual('unverified',report.meta['llms_txt']['state'])
        self.assertIsNotNone(recorded_llms_problem(report.meta,for_score=True))
        self.assertNotIn('geo.llms.txt.published',{f.rule_id for f in report.findings})
        self.assertNotIn('geo.no.llms.txt',{f.rule_id for f in report.findings})
        self.assertNotIn('password',json.dumps(llms_resource.assess(value)))


if __name__=='__main__':unittest.main()
