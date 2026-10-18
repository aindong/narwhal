"""Date candidates cannot certify publication, freshness or a required date."""
import copy
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_content
import brief
import compare
import plan
import scan
from lib import date_cues, htmlx, http
from lib.report import Report
from test_page_schema_review import FIXTURE

URL = 'https://example.test/guide'


def page(meta='', text='Useful reader instructions.', *, article=True, parser=htmlx._parse_stdlib):
    markup = ('<article>' if article else '<main>') + meta + '<h1>Guide</h1><p>' + text + '</p>' + ('</article>' if article else '</main>')
    doc = parser(markup, URL)
    report = Report(URL)
    audit_content._freshness(doc, doc.body_text, report)
    return doc, report


class TestDateCues(unittest.TestCase):
    def test_modified_metadata_has_the_same_page_and_comparison_candidate(self):
        doc, report = page('<meta property="article:modified_time" content="2026-10-01">')
        facts = compare.facts(report, doc)
        self.assertTrue(facts['date_signal'])
        self.assertEqual(report.meta['date_cues'], facts['date_cues'])
        self.assertEqual('modified_metadata', facts['date_cues']['candidates'][0]['kind'])
        self.assertEqual('Date-related candidate observed', report.findings[0].title)

    def test_blank_metadata_is_not_a_date_candidate_or_passing_finding(self):
        doc, report = page('<meta property="article:published_time" content="   ">')
        self.assertFalse(compare.facts(report, doc)['date_signal'])
        self.assertEqual([], report.meta['date_cues']['candidates'])
        self.assertEqual(('content.no.visible.date.signal', 'low'),
                         (report.findings[0].rule_id, report.findings[0].severity))

    def test_copyright_year_does_not_become_freshness_or_publication_evidence(self):
        doc, report = page(text='Copyright 2026 Example.')
        self.assertEqual(1, report.meta['date_cues']['year_pattern_matches'])
        self.assertEqual(0, report.meta['date_cues']['candidate_count'])
        self.assertFalse(compare.facts(report, doc)['date_signal'])
        self.assertNotIn('Date/freshness signal present', report.to_markdown())

    def test_nonarticle_without_candidates_gets_no_missing_date_instruction(self):
        _, report = page(article=False)
        self.assertEqual([], report.findings)
        self.assertEqual(0, report.meta['date_cues']['candidate_count'])

    def test_article_review_does_not_require_fabricated_or_cosmetic_updates(self):
        _, report = page()
        finding, = report.findings
        self.assertIn('only when useful and known', finding.recommendation)
        self.assertIn('do not invent dates', finding.recommendation)
        self.assertIn('without substantive change', finding.recommendation)

    def test_published_named_and_modified_metadata_are_all_inspectable(self):
        doc, report = page('<meta property="article:published_time" content="2025-01-01">'
                           '<meta property="article:modified_time" content="2026-10-01">'
                           '<meta name="date" content="2024-02-03">')
        candidates = report.meta['date_cues']['candidates']
        self.assertEqual(['published_metadata','modified_metadata','date_metadata'], [c['kind'] for c in candidates])
        self.assertEqual([1,2,3], [c['position'] for c in candidates])
        self.assertIn('article:modified_time metadata: 2026-10-01', report.to_markdown())

    def test_invalid_or_unrelated_metadata_values_are_not_validated_dates(self):
        _, report = page('<meta name="date" content="not-a-date">')
        self.assertEqual('not-a-date', report.meta['date_cues']['candidates'][0]['value'])
        self.assertIn('not validated dates', report.findings[0].detail)
        self.assertNotIn('Date/freshness signal present', report.findings[0].title)

    def test_english_month_and_iso_patterns_are_candidates_not_publication_ownership(self):
        for text in ('Published May 12, 2026.', 'Updated 2026-10-01.', 'Historical event: May 13, 1990.',
                     'Example invalid date 2026-99-99.'):
            with self.subTest(text=text):
                _, report = page(text=text)
                self.assertTrue(report.meta['date_cues']['candidates'])
                self.assertTrue(all(c['kind']=='text_pattern' for c in report.meta['date_cues']['candidates']))
                self.assertIn('not validated dates', report.findings[0].detail)

    def test_month_prefix_words_and_unmatched_languages_are_not_invented_dates(self):
        for text in ('Mayhem 12 is a heading.', 'Обновлено 1 октября 2026 года.', '၂၀၂၆'):
            with self.subTest(text=text):
                _, report = page(text=text)
                self.assertEqual(0, report.meta['date_cues']['candidate_count'])
                self.assertIn('does not establish that the page lacks dates', report.to_markdown())

    def test_text_prefix_limit_stays_explicit_without_an_absence_verdict(self):
        _, report = page(text='a ' * 1100 + 'Published May 12, 2026.')
        receipt = report.meta['date_cues']
        self.assertEqual(2000, receipt['text_prefix_characters'])
        self.assertTrue(receipt['coverage']['text_prefix_limited'])
        self.assertEqual(0, receipt['candidate_count'])
        self.assertIsNotNone(date_cues.recorded(receipt))

    def test_metadata_and_candidate_limits_retain_positive_observations(self):
        meta = '<meta name="other" content="x">' * 1000 + '<meta name="date" content="2026-10-01">'
        _, report = page(meta)
        self.assertTrue(report.meta['date_cues']['coverage']['metadata_limited'])
        self.assertEqual(0, report.meta['date_cues']['candidate_count'])
        _, report = page(''.join('<meta name="date" content="2026-10-0'+str(n)+'">' for n in range(1,8)))
        self.assertEqual(5, report.meta['date_cues']['candidate_count'])
        self.assertTrue(report.meta['date_cues']['coverage']['candidates_omitted'])

    def test_values_are_clipped_before_display_and_source_scope_is_bounded(self):
        _, report = page('<meta name="date" content="'+ 'x'*5000 +'">')
        receipt = report.meta['date_cues']
        self.assertEqual(160, len(receipt['candidates'][0]['value']))
        self.assertTrue(receipt['candidates'][0]['truncated'])
        self.assertTrue(receipt['coverage']['metadata_value_limited'])
        self.assertIsNotNone(date_cues.recorded(receipt))

    def test_normalized_nonstring_fields_do_not_create_candidate_truth(self):
        doc = htmlx.Doc(URL, meta=[htmlx.Tag('meta',{'name':'date','content':2026})])
        self.assertEqual([], date_cues.observe(doc)['candidates'])

    def test_inert_template_metadata_is_not_a_document_date_candidate(self):
        doc, report = page('<template><meta name="date" content="2026-10-01"></template>')
        self.assertEqual([], report.meta['date_cues']['candidates'])

    def test_optional_parser_paths_share_candidate_observations(self):
        values = []
        for parser in (htmlx._parse_stdlib, htmlx.parse):
            _, report = page('<meta property="article:modified_time" content="2026-10-01">', parser=parser)
            values.append(report.meta['date_cues']['candidates'])
        self.assertEqual(values[0], values[1])

    def test_modified_versus_published_comparison_has_no_prescriptive_date_gap(self):
        own, own_report = page('<meta property="article:modified_time" content="2026-10-01">')
        rival, rival_report = page('<meta property="article:published_time" content="2026-10-01">')
        result = compare.gap_analysis(compare.facts(own_report, own), [compare.facts(rival_report,rival)])
        self.assertNotIn('Publish/update date', [g['what'] for g in result['gaps']+result['leads']])

    def test_legacy_booleans_do_not_supply_receipt_scope(self):
        for value in (True,False):
            facts={'date_signal':value}
            self.assertEqual('Unrecorded',date_cues.cell(facts))
            self.assertIn('legacy booleans', ' '.join(date_cues.summary(facts,[])))

    def test_summary_reports_neutral_counts_without_source_markup_or_invented_scope(self):
        _, report = page('<meta name="date" content="&lt;img src=https://evil.test/pixel&gt;">')
        facts = {'date_cues': report.meta['date_cues']}
        text = ' '.join(date_cues.summary(facts, [facts]))
        self.assertIn('Your page: 1 captured', text)
        self.assertIn('1 of 1 compared page(s)', text)
        self.assertNotIn('evil.test', text)
        for rivals in (None, {}, [{}] * 101, [None]):
            self.assertIn('unrecorded or unsupported', ' '.join(date_cues.summary(None, rivals)))

    def test_malformed_unsupported_or_stale_receipts_do_not_crash_or_certify(self):
        _, report = page('<meta name="date" content="2026-10-01">')
        original=report.meta['date_cues']
        for key,value in [('version',True),('version',2),('basis','unknown'),('candidate_count',True),
                          ('candidate_count',0),('year_pattern_matches',1<<200),('source_basis',''),
                          ('source_basis_clipped',0),('candidates',[{'kind':[]}])]:
            candidate=copy.deepcopy(original);candidate[key]=value
            with self.subTest(key=key):
                self.assertIsNone(date_cues.recorded(candidate))
                self.assertEqual('Unrecorded',date_cues.cell({'date_cues':candidate}))
        for key,value in [('kind',[]),('value',''),('position',True),('position',1001),('truncated',1)]:
            candidate=copy.deepcopy(original);candidate['candidates'][0][key]=value
            with self.subTest(candidate_key=key):
                self.assertIsNone(date_cues.recorded(candidate))

    def test_current_and_legacy_plans_do_not_instruct_fake_dates(self):
        value={'url':URL,'findings':[{'category':'content','severity':'low','title':'No visible date signal',
                                     'rule_id':'content.no.visible.date.signal','recommendation':'Expose a date.'}]}
        result=plan.build_plan(value,str(FIXTURE));action,=result['actions']
        self.assertEqual('review_required',action['safety'])
        self.assertIn('only when useful and known',action['proposed_change'])
        self.assertIn('Do not invent dates',action['proposed_change'])

    def test_legacy_compare_and_brief_date_prescriptions_are_not_repeated(self):
        doc,report=page('<meta property="article:modified_time" content="2026-10-01">')
        own=compare.facts(report,doc);rival=copy.deepcopy(own);rival['url']='https://rival.test/guide'
        result={'you':own,'competitors':[rival],**compare.gap_analysis(own,[rival])}
        result['gaps'].append({'what':'Publish/update date','who':[rival['url']],'action':'ADD_FALSE_DATE'})
        result['leads'].append({'what':'Publish/update date','detail':'VERIFIED_FRESHER'})
        old=json.dumps(result,sort_keys=True)
        text=compare.render_markdown(result)
        self.assertNotIn('ADD_FALSE_DATE',text);self.assertNotIn('VERIFIED_FRESHER',text)
        self.assertEqual(old,json.dumps(result,sort_keys=True))
        value=brief.synthesize({'url':URL,'facts':own,'headings':doc.headings,'text':doc.body_text},
                               [{'url':rival['url'],'facts':rival,'headings':doc.headings,'text':doc.body_text}],None)
        value['gaps']=copy.deepcopy(result['gaps']);value['leads']=copy.deepcopy(result['leads'])
        before=brief.render_json(value);text=brief.render_markdown(value)
        self.assertNotIn('ADD_FALSE_DATE',text);self.assertNotIn('VERIFIED_FRESHER',text)
        self.assertEqual(before,brief.render_json(value))

    def test_topic_mode_does_not_invent_an_own_page_date_count(self):
        doc,report=page('<meta name="date" content="2026-10-01">')
        rival=compare.facts(report,doc)
        value=brief.synthesize(None,[{'url':URL,'facts':rival,'headings':doc.headings,'text':doc.body_text}],None,topic='Widget guide')
        text=brief.render_markdown(value)
        self.assertIn('Date-related candidates (not freshness)',text)
        self.assertNotIn('you',value)
        self.assertNotIn('Your page:',text)

    def test_actual_scan_records_shared_cues_without_extra_requests(self):
        source='<article><meta property="article:modified_time" content="2026-10-01"><h1>Guide</h1><p>Useful instructions.</p></article>'
        response=http.Response(URL,URL,200,{'content-type':'text/html'},source,1)
        with mock.patch.object(http,'fetch',return_value=response) as fetch:
            report=scan.scan(URL,only=['content'],ctx={},check_images=False)
        self.assertEqual(1,fetch.call_count)
        self.assertEqual(['content'],report.meta['scan_scope']['completed'])
        self.assertEqual(report.meta['date_cues'],compare.facts(report,report._doc)['date_cues'])

    def test_evidence_is_literal_bounded_and_does_not_execute_source_markup(self):
        doc=htmlx.Doc(URL,meta=[htmlx.Tag('meta',{'name':'date','content':'<script>ATTACK</script>\n```\n# TITLE'})])
        report=Report(URL);audit_content._freshness(doc,doc.body_text,report)
        before=report.to_json()
        self.assertIn('&lt;script&gt;ATTACK&lt;/script&gt;',report.to_html())
        self.assertIn('name=date metadata: <script>ATTACK</script> ``` # TITLE',report.to_markdown())
        self.assertEqual(before,report.to_json())

    def test_cue_projection_and_reports_are_offline_readonly(self):
        with mock.patch.object(socket,'socket',side_effect=AssertionError('No network')):
            doc,report=page('<meta property="article:modified_time" content="2026-10-01">')
            before=report.to_json();compare.facts(report,doc);report.to_markdown();report.to_html()
            plan.build_plan(json.loads(before),str(FIXTURE))
        self.assertEqual(before,report.to_json())


if __name__=='__main__':
    unittest.main()
