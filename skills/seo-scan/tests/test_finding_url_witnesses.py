"""Bounded recurring-rule labels preserve counts and reject unsupported mapping evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import crawl_site
from lib import finding_urls
from lib.report import Report
from test_crawl_rule_handoff import crawl_reports

BASE = 'https://example.test/'


class TestFindingURLWitnesses(unittest.TestCase):
    def test_samples_are_bounded_sorted_distinct_and_order_independent(self):
        urls = [BASE + str(i) for i in range(8)] + [BASE + '0']
        samples, reverse = {}, {}
        for url in urls:
            finding_urls.record(samples, 'rule', url)
        for url in reversed(urls):
            finding_urls.record(reverse, 'rule', url)
        self.assertEqual(samples, reverse)
        self.assertEqual(urls[:5], samples['rule']['urls'])
        self.assertTrue(samples['rule']['truncated'])
        row = {'count': len(urls), 'url_sample': samples['rule']}
        self.assertEqual(samples['rule'], finding_urls.read(row, BASE))

    def test_unsupported_or_credential_like_labels_are_omitted_without_network(self):
        samples = {}
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            for url in (None, 'file:///etc/passwd', BASE + 'a\nb', 'https://user:secret@example.test/',
                        BASE + '?contact=user%40example.test'):
                finding_urls.record(samples, 'rule', url)
        self.assertEqual([], samples['rule']['urls'])
        self.assertEqual(5, samples['rule']['omitted'])
        self.assertNotIn('secret', json.dumps(samples))

    def test_invalid_labels_fail_closed_for_nonempty_objects_spaces_controls_and_hosts(self):
        for value in (42, ['url'], {'url': BASE}, BASE + 'a b', BASE + 'a\x00b',
                      'https:///missing', 'ftp://example.test/'):
            with self.subTest(value=value):
                samples = {}
                finding_urls.record(samples, 'rule', value)
                self.assertEqual(1, samples['rule']['omitted'])
                self.assertEqual([], samples['rule']['urls'])

    def test_reader_supports_occurrences_and_single_observation_defaults(self):
        sample = {'basis': finding_urls.BASIS, 'urls': [BASE], 'truncated': False, 'omitted': 0}
        self.assertEqual(sample, finding_urls.read({'url_sample': sample}, BASE))
        two = dict(sample, urls=[BASE, BASE + 'docs/'])
        self.assertEqual(two, finding_urls.read({'url_sample': two, 'occurrences': 2}, BASE))
        self.assertIsNone(finding_urls.read({'url_sample': two, 'occurrences': 1}, BASE))
        self.assertIsNone(finding_urls.read({'url_sample': two}, BASE))
        for urls, count, omitted in (([BASE, BASE], 2, 0), ([None], 1, 0),
                                      ([BASE + str(i) for i in range(6)], 6, 0),
                                      ([BASE], 1, 0.0)):
            invalid = dict(sample, urls=urls, omitted=omitted)
            self.assertIsNone(finding_urls.read({'url_sample': invalid, 'count': count}, BASE))

    def test_origin_matching_keeps_scheme_ports_and_authority_distinct(self):
        self.assertTrue(finding_urls.same_origin_label('HTTPS://EXAMPLE.TEST:443/a', BASE))
        self.assertTrue(finding_urls.same_origin_label('http://example.test:80/a', 'http://example.test/'))
        self.assertTrue(finding_urls.same_origin_label('http://example.test:0/a', 'http://example.test:0/'))
        for url in ('http://example.test/a', 'https://other.test/', 'https://example.test:0/',
                    'https://example.test:bad/', 'https://[broken/', '/relative', 'https://@example.test/'):
            with self.subTest(url=url):
                self.assertFalse(finding_urls.same_origin_label(url, BASE))
        self.assertFalse(finding_urls.same_origin_label(BASE, ''))

    def test_reader_rejects_malformed_foreign_duplicate_and_inconsistent_receipts(self):
        valid = {'count': 1, 'url_sample': {'basis': finding_urls.BASIS, 'urls': [BASE],
                                         'truncated': False, 'omitted': 0}}
        self.assertEqual('recorded_crawl_rule_url_labels_v1', valid['url_sample']['basis'])
        for field, value in (('basis', 'future'), ('urls', None), ('urls', []), ('urls', [None]),
                             ('urls', [BASE, BASE]), ('urls', [BASE + str(i) for i in range(6)]),
                             ('urls', ['https://foreign.test/']), ('truncated', 1),
                             ('truncated', True), ('omitted', -1), ('omitted', True), ('omitted', 2)):
            row = copy.deepcopy(valid)
            row['url_sample'][field] = value
            with self.subTest(field=field, value=value):
                self.assertIsNone(finding_urls.read(row, BASE))
        for count in (0, True, '1'):
            row = dict(valid, count=count)
            self.assertIsNone(finding_urls.read(row, BASE))
        self.assertIsNone(finding_urls.read({}, BASE))
        row = copy.deepcopy(valid)
        row['url_sample']['extra'] = True
        self.assertIsNone(finding_urls.read(row, BASE))
        original = copy.deepcopy(valid)
        read = finding_urls.read(valid, BASE)
        read['urls'].append(BASE + 'other')
        self.assertEqual(original, valid)

    def test_all_omitted_observations_remain_unlocated_not_invalid_file_claims(self):
        row = {'count': 2, 'url_sample': {'basis': finding_urls.BASIS, 'urls': [],
                                        'truncated': False, 'omitted': 2}}
        self.assertEqual([], finding_urls.read(row, BASE)['urls'])

    def test_truncation_requires_an_additional_valid_observation_beyond_omissions(self):
        row = {'count': 7, 'url_sample': {'basis': finding_urls.BASIS,
               'urls': [BASE + str(i) for i in range(5)], 'truncated': True, 'omitted': 2}}
        self.assertIsNone(finding_urls.read(row, BASE))
        row['count'] = 8
        self.assertEqual(row['url_sample'], finding_urls.read(row, BASE))

    def test_label_size_boundary_is_bounded_without_rewriting_urls(self):
        url = BASE + '?' + 'x' * (finding_urls.MAX_URL_CHARS - len(BASE) - 1)
        self.assertTrue(finding_urls.same_origin_label(url, BASE))
        samples = {}
        finding_urls.record(samples, 'rule', url)
        finding_urls.record(samples, 'rule', url + 'x')
        self.assertEqual([url], samples['rule']['urls'])
        self.assertEqual(1, samples['rule']['omitted'])

    def test_real_crawl_serialization_binds_response_urls_to_native_rule_identity(self):
        pages = []
        for suffix, rule in (('first', 'technical.first'), ('second', 'technical.second')):
            page = Report(BASE + suffix, final_url=BASE + suffix + '-final', fetched_status=200)
            page.add('technical', 'high', 'Same display title', rule_id=rule)
            pages.append(page)
        crawled = crawl_reports(pages)
        original = copy.deepcopy(crawled)
        payload = json.loads(crawl_site.render_json(crawled))
        rows = {row['rule_id']: row for row in payload['recurring']}
        self.assertNotIn('recurring_rule_urls', payload)
        for suffix, rule in (('first', 'technical.first'), ('second', 'technical.second')):
            self.assertEqual(1, rows[rule]['count'])
            self.assertEqual('high', rows[rule]['severity'])
            self.assertEqual('technical', rows[rule]['category'])
            self.assertEqual('Same display title', rows[rule]['title'])
            self.assertEqual([BASE + suffix + '-final'], rows[rule]['url_sample']['urls'])
        self.assertEqual(2, sum(crawled['recurring'].values()))
        self.assertEqual(original, crawled)
        crawled.pop('recurring_rule_urls')
        legacy = json.loads(crawl_site.render_json(crawled))
        self.assertTrue(all('url_sample' not in row for row in legacy['recurring']))
        self.assertEqual(set(rows), {row['rule_id'] for row in legacy['recurring']})


if __name__ == '__main__':
    unittest.main()
