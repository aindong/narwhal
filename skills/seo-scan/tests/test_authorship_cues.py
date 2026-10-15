"""Attribution witnesses are bounded candidates, not identity verification."""

import html
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_content
import compare
import diff_scan
import plan
import scan
from lib import authorship, htmlx, http
from lib.report import Report

URL = 'https://example.test/guide'
PRESENT = 'content.authorship.signal.present'
MISSING = 'content.no.visible.author.byline'


def observe(source):
    return authorship.observe(SimpleNamespace(document_html=source))


def audit(source, article=True):
    doc = htmlx._parse_stdlib(source, URL)
    report = Report(URL, final_url=URL, fetched_status=200)
    audit_content._authorship(doc, doc.body_text, report, article=article)
    return doc, report


class TestAuthorshipObservations(unittest.TestCase):
    def test_prose_words_and_whitespace_metadata_do_not_pass(self):
        for source in ('<p>Filter records by category before reading.</p>',
                       '<p>The author field stores a label, not the writer.</p>',
                       '<p>By following these steps</p>', '<p>Written by the process</p>',
                       '<p>By 2026 the records changed</p>',
                       '<meta name="author" content=" \t\n ">',
                       '<p class="byline">  </p>', '<p>By</p>', '<p>Author:</p>',
                       '<p class="byline">Author:</p>', '<span class="byline">By:</span>'):
            with self.subTest(source=source):
                _, report = audit(source)
                finding, = report.findings
                self.assertEqual((MISSING, 'low'), (finding.rule_id, finding.severity))
                self.assertIn('does not prove anonymity', finding.detail)
                self.assertIn('do not invent people', finding.recommendation)

    def test_metadata_requires_nonempty_values_and_preserves_declared_kind(self):
        result = observe('<meta NAME="AUTHOR" content=" "><meta name="author" content="Jane Doe">'
                         '<meta property="ARTICLE:AUTHOR" content="/people/example">')
        self.assertEqual([('author_meta', 'Jane Doe'), ('article_author_meta', '/people/example')],
                         [(c['kind'], c['value']) for c in result['candidates']])
        self.assertEqual('candidate_observed', result['state'])
        self.assertIn('writer identity', result['limits_note'])

    def test_author_links_are_exact_tokens_not_followed_or_authenticated(self):
        for tag in ('a', 'link', 'area'):
            for destination in ('/writers/example', 'mailto:example@example.test', '#writer',
                                'javascript:untrusted()', 'https://example.invalid/name'):
                with self.subTest(tag=tag, destination=destination):
                    with mock.patch('socket.socket', side_effect=AssertionError('No network')):
                        result = observe('<' + tag + ' rel="nofollow AUTHOR" href="'
                                         + destination + '">Editor</' + tag + '>')
                    self.assertEqual([{'kind': 'author_link', 'value': destination, 'truncated': False}],
                                     result['candidates'])
        for rel, href in (('coauthor', '/writer'), ('author-profile', '/writer'), ('author', '  ')):
            self.assertEqual([], observe('<a rel="' + rel + '" href="' + href + '">Editor</a>')['candidates'])

    def test_short_leading_labels_and_explicit_markers(self):
        for value in ('By Jane Doe', 'Written by Jane Doe', 'Reviewed by Example Team',
                      'Author: Jane Doe', 'By 王小明', 'By محمد'):
            with self.subTest(value=value):
                self.assertEqual(value, observe('<p>' + value + '</p>')['candidates'][0]['value'])
        for marker in ('byline', 'article-author', 'author-name', 'post-author'):
            result = observe('<span class="other ' + marker + '">jane doe</span>')
            self.assertEqual('jane doe', result['candidates'][0]['value'])
        # Localized labels/lowercase unmarked pen names remain unverified, not absent.
        self.assertEqual([], observe('<p>By jane doe</p><p>Par Jean Dupont</p>')['candidates'])

    def test_long_or_late_byline_blocks_are_not_claimed(self):
        for source in ('<p>' + 'x ' * 751 + '</p><p>By Jane Doe</p>',
                       '<p class="byline">' + 'name ' * 40 + '</p>',
                       '<p>By ' + 'Name ' * 9 + '</p>'):
            self.assertEqual([], observe(source)['candidates'])
        self.assertTrue(observe('<p>By <strong>Jane</strong> Doe</p>')['candidates'])

    def test_inert_hidden_and_chrome_sources_are_excluded(self):
        cue = '<meta name="author" content="Fake"><a rel="author" href="/fake">By Fake</a>'
        for tag in ('script', 'style', 'template', 'textarea', 'title', 'nav', 'footer', 'aside', 'noscript'):
            with self.subTest(tag=tag):
                self.assertEqual([], observe('<' + tag + '>' + cue + '</' + tag + '>')['candidates'])
        for attrs in ('hidden', 'hidden="false"', 'aria-hidden="TRUE"'):
            self.assertEqual([], observe('<div ' + attrs + '>' + cue + '</div>')['candidates'])

    def test_self_closing_nonvoid_tags_cannot_expose_hidden_candidates(self):
        cue = '<meta name="author" content="Fake">'
        for opener, closer in (('<div hidden/>', '</div>'), ('<template/>', '</template>'),
                               ('<script/>', '</script>'), ('<textarea/>', '</textarea>')):
            with self.subTest(opener=opener):
                self.assertEqual([], observe(opener + cue + closer)['candidates'])
                result = observe(opener + cue + closer + '<p>By Jane Doe</p>')
                self.assertEqual('By Jane Doe', result['candidates'][0]['value'])

    def test_template_and_noscript_cannot_close_an_outer_frame(self):
        for tag in ('template', 'noscript'):
            source = '<header><' + tag + '></header><meta name="author" content="Fake"></' + tag + '>'
            self.assertEqual([], observe(source)['candidates'])
        source = '<template><template></template><meta name="author" content="Fake"></template>'
        self.assertEqual([], observe(source)['candidates'])

    def test_selected_noscript_fallback_is_explicit(self):
        doc = SimpleNamespace(document_html='<noscript><p>By Jane Doe</p></noscript>',
                              extraction='noscript fallback')
        self.assertEqual('By Jane Doe', authorship.observe(doc)['candidates'][0]['value'])

    def test_bogus_declarations_and_comments_do_not_supply_metadata(self):
        for source in ('<!--[fake]><meta name="author" content="Fake">-->',
                       '<![broken declaration]><p>Filter by category.</p>',
                       '<!-- <p>By Fake</p> -->'):
            self.assertEqual([], observe(source)['candidates'])

    def test_candidate_caps_deduplication_and_fresh_state(self):
        one = '<meta name="author" content="Jane Doe">'
        self.assertEqual(1, len(observe(one * 10)['candidates']))
        source = ''.join('<meta name="author" content="Team ' + str(i) + '">' for i in range(7))
        result = observe(source)
        self.assertEqual(authorship.MAX_CANDIDATES, len(result['candidates']))
        self.assertTrue(result['coverage']['candidates_omitted'])
        self.assertEqual([], observe('<p>Records</p>')['candidates'])
        self.assertFalse(observe(one)['coverage']['candidates_omitted'])
        json.dumps(result, allow_nan=False)

    def test_value_source_and_depth_limits_are_reported(self):
        value = 'J' * (authorship.MAX_VALUE_CHARS + 1)
        result = observe('<meta name="author" content="' + value + '">')
        self.assertEqual(value[:-1], result['candidates'][0]['value'])
        self.assertTrue(result['candidates'][0]['truncated'])
        source = ' ' * authorship.MAX_SOURCE_CHARS + '<meta name="author" content="Late">'
        result = observe(source)
        self.assertTrue(result['coverage']['source_truncated'])
        self.assertEqual([], result['candidates'])
        result = observe('<div>' * (authorship.MAX_DEPTH + 1) + '<p>By Fake</p>')
        self.assertTrue(result['coverage']['depth_limited'])
        self.assertEqual([], result['candidates'])

    def test_truncated_unclosed_block_is_not_emitted(self):
        source = '<p>By Jane Doe' + ' ' * authorship.MAX_SOURCE_CHARS
        result = observe(source)
        self.assertTrue(result['coverage']['source_truncated'])
        self.assertEqual([], result['candidates'])
        self.assertTrue(observe('<p>By Jane Doe')['candidates'])

    def test_normalized_doc_fallback_is_bounded_and_labels_its_basis(self):
        tag = htmlx.Tag('meta', {'name': 'author', 'content': 'Example Team'})
        doc = SimpleNamespace(meta=[tag], links=[], link_rels=[])
        result = authorship.observe(doc)
        self.assertEqual('normalized_doc_fields', result['basis'])
        self.assertEqual('Example Team', result['candidates'][0]['value'])
        link = htmlx.Tag('a', {'rel': ['nofollow', 'author'], 'href': '/writer'})
        doc = SimpleNamespace(meta=[], links=[link], link_rels=[])
        self.assertEqual('/writer', authorship.observe(doc)['candidates'][0]['value'])
        consumed = []
        def fields():
            for index in range(100_000):
                consumed.append(index)
                yield htmlx.Tag('meta', {})
        doc = SimpleNamespace(meta=fields(), links=[], link_rels=[])
        result = authorship.observe(doc, 'By Jane Doe')
        self.assertEqual(authorship.MAX_NORMALIZED_FIELDS + 1, len(consumed))
        self.assertTrue(result['coverage']['normalized_fields_limited'])
        self.assertEqual('provided_text', result['candidates'][0]['kind'])


class TestAttributionIntegration(unittest.TestCase):
    def test_nonarticle_without_cues_has_no_missing_finding_or_section(self):
        _, report = audit('<p>Catalog</p>', article=False)
        self.assertEqual([], report.findings)
        self.assertNotIn('## Attribution cue evidence', report.to_markdown())
        self.assertNotIn('<h2>Attribution cue evidence', report.to_html())

    def test_scan_and_comparison_agree_independently_of_main_text(self):
        source = '<header><p class="byline">By Jane Doe</p></header><article><p>Catalog text.</p></article>'
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, source, 1)
        receipts = []
        for parser in (htmlx._parse_stdlib, htmlx.parse):
            with self.subTest(parser=parser.__name__):
                with mock.patch.object(http, 'fetch', return_value=response), \
                        mock.patch.object(scan.htmlx, 'parse', side_effect=parser), \
                        mock.patch.object(htmlx, '_main_content', return_value='Catalog text.'), \
                        mock.patch('socket.socket', side_effect=AssertionError('No network')):
                    report = scan.scan(URL, only=['content'], ctx={}, check_images=False)
                fact = compare.facts(report, report._doc)
                self.assertTrue(fact['author_signal'])
                self.assertEqual(report.meta['authorship_cues']['candidates'], fact['authorship_cues']['candidates'])
                self.assertIn(PRESENT, {f.rule_id for f in report.findings})
                self.assertEqual(['content'], report.meta['scan_scope']['completed'])
                receipts.append(fact['authorship_cues'])
        self.assertEqual(receipts[0], receipts[1])

    def test_comparison_advice_is_conditional_and_retains_boolean_contract(self):
        for source, expected in (('<p>Filter by category</p>', False),
                                 ('<meta name="author" content="   ">', False),
                                 ('<a rel="author" href="/writer">Editor</a>', True)):
            doc, report = audit(source)
            self.assertIs(expected, compare.facts(report, doc)['author_signal'])
        entry, = [item for item in compare._BOOL_GAPS if item[0] == 'author_signal']
        self.assertEqual('Attribution cues', entry[1])
        self.assertIn('do not verify writers', entry[2])
        self.assertIn('Do not invent people', entry[2])

    def test_current_and_legacy_plans_require_context_and_real_people(self):
        for title, rule in (('No visible author/byline', None), ('Review article attribution cues', MISSING)):
            finding = {'category': 'content', 'severity': 'low', 'title': title}
            if rule:
                finding['rule_id'] = rule
            packet = {'schema_version': '2.0', 'url': URL, 'findings': [finding]}
            with mock.patch('socket.socket', side_effect=AssertionError('No network')):
                built = plan.build_plan(packet, str(Path(__file__).parent / 'fixtures/planner/nextjs'))
            action, = built['actions']
            self.assertEqual('review_required', action['safety'])
            self.assertIn('do not invent people', action['proposed_change'])
            self.assertIn('does not prove anonymity', action['proposed_change'])

    def test_priority_correction_preserves_identity_not_page_improvement(self):
        old = Report(URL, final_url=URL, fetched_status=200)
        old.add('content', 'medium', 'No visible author/byline')
        _, current = audit('<p>Catalog text.</p>')
        delta = diff_scan.diff_reports(json.loads(old.to_json()), json.loads(current.to_json()))
        self.assertEqual([], delta['added'])
        self.assertEqual([], delta['resolved'])
        self.assertEqual(1, len(delta['improved']))

    def test_witness_values_are_literal_in_native_and_markdown_html(self):
        value = '``` </code><script>alert(1)</script> [name](https://example.invalid/)'
        source = '<meta name="author" content="' + html.escape(value, quote=True) + '">'
        _, report = audit(source)
        native, markdown = report.to_html(), report.to_markdown()
        self.assertIn('Author metadata: ' + value, markdown)
        self.assertIn('not identity verification', markdown)
        self.assertNotIn('<script>alert(1)</script>', native)
        self.assertNotIn('href="https://example.invalid/"', native)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', native)
        import render_report
        rendered = render_report.render(markdown)
        self.assertNotIn('<script>alert(1)</script>', rendered)
        self.assertNotIn('href="https://example.invalid/"', rendered)

    def test_malformed_report_receipts_never_create_evidence_or_crash(self):
        base = {'version': 1, 'interpretation': 'attribution_candidates_only', 'article_hint': True}
        for candidate in (None, {}, {'kind': [], 'value': 'x'}, {'kind': 'unknown', 'value': 'x'},
                          {'kind': 'author_meta', 'value': {}}, {'kind': 'author_meta', 'value': ' '}):
            receipt = dict(base, candidates=[candidate])
            lines = authorship.evidence_lines({'authorship_cues': receipt})
            self.assertEqual(['No candidate observed in the checked sources; attribution remains unverified.'], lines)
        for version in (True, '1', 2, None):
            self.assertEqual([], authorship.evidence_lines({'authorship_cues': dict(base, version=version)}))

    def test_evidence_limits_are_visible_and_controls_cannot_break_code_fences(self):
        receipt = observe('<meta name="author" content="Jane&#10;```&#10;Doe">')
        receipt['coverage']['normalized_fields_limited'] = True
        lines = authorship.evidence_lines({'authorship_cues': receipt})
        self.assertEqual('Author metadata: Jane ``` Doe', lines[0])
        self.assertIn('unchecked evidence remains unknown', lines[1])


if __name__ == '__main__':
    unittest.main()
