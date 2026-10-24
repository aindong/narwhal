"""Formula estimates cannot certify comprehension, a grade or engine outcomes."""
import copy
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_content
import compare
import diff_scan
import plan
import scan
from lib import htmlx, http, readability_observation as reading, text as textlib
from lib.report import Report
from test_page_schema_review import FIXTURE

URL = 'https://example.test/guide'
IDS = {'content.content.is.very.hard.to.read', 'content.content.is.fairly.hard.to.read', 'content.readable.prose'}


def measured(text, **kwargs):
    report = Report(URL)
    audit_content._readability(text, report, **kwargs)
    return report


def scanned(text, *, language='en'):
    source = '<html lang="' + language + '"><article><h1>Guide</h1><p>' + text + '</p></article></html>'
    response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, source, 1)
    with mock.patch.object(scan.http, 'fetch', return_value=response) as fetch:
        report = scan.scan(URL, only=['content'], ctx={}, check_images=False)
    assert fetch.call_count == 1
    return json.loads(report.to_json())


class TestReadabilityObservation(unittest.TestCase):
    def test_four_word_sample_records_inputs_not_a_medium_comprehension_verdict(self):
        report = measured('Controlled guide Useful instructions.', article=True)
        value = report.meta['readability']
        self.assertEqual((4, 1, 10), tuple(value[k] for k in ('ascii_pattern_matches', 'sentence_fragments', 'estimated_syllables')))
        self.assertEqual((-8.7, 15.5), (value['flesch_reading_ease'], value['flesch_kincaid_grade']))
        finding, = report.findings
        self.assertEqual(('low', 'content.content.is.very.hard.to.read'), (finding.severity, finding.rule_id))
        self.assertNotIn('AI engines to quote', finding.recommendation)
        self.assertIn('preserve necessary technical terms', finding.recommendation)

    def test_legacy_formula_outputs_and_unclamped_ranges_are_preserved(self):
        for sample in ('', '1234', 'a', 'a. a.', 'Wait!', 'Controlled guide Useful instructions.',
                       'Use the tool. Check the page.', 'internationalization. ' * 100):
            words, fragments = textlib.words(sample), textlib.sentences(sample)
            syllables = sum(textlib.syllables(w) for w in words)
            fre = round(206.835 - 1.015 * (len(words)/len(fragments)) - 84.6 * (syllables/len(words)), 1) if words and fragments else None
            fk = round(0.39 * (len(words)/len(fragments)) + 11.8 * (syllables/len(words)) - 15.59, 1) if words and fragments else None
            self.assertEqual(fre, textlib.flesch_reading_ease(sample))
            self.assertEqual(fk, textlib.flesch_kincaid_grade(sample))
            self.assertEqual(fre, reading.observe(sample)['flesch_reading_ease'])
            self.assertIsNotNone(reading.recorded(reading.observe(sample)))

    def test_passing_formula_does_not_certify_readable_prose_or_school_grade(self):
        report = measured('Use the tool. Check the page.')
        finding, = report.findings
        self.assertEqual('content.readable.prose', finding.rule_id)
        self.assertEqual('good', finding.severity)
        self.assertNotEqual('Readable prose', finding.title)
        self.assertIn('not measured reader comprehension', finding.detail)
        self.assertLess(report.meta['readability']['flesch_kincaid_grade'], 0)

    def test_mixed_or_non_latin_text_is_not_judged_from_one_latin_token(self):
        for language in ('en', '', 'zh'):
            report = measured('API 这是使用说明。阅读此页面即可完成设置。', language=language)
            self.assertEqual([], report.findings)
            receipt = report.meta['readability']
            self.assertEqual(1, receipt['ascii_pattern_matches'])
            self.assertIsNone(receipt['flesch_reading_ease'])
            self.assertIn('non_ascii_letters_or_marks', receipt['uninterpreted_reasons'])
            self.assertIn('Formula interpretation withheld', report.to_markdown())

    def test_declared_non_english_and_invalid_english_prefixes_are_uninterpreted(self):
        for language in ('fr', 'FR-ca', 'enochian', 'en_US', 'ja'):
            report = measured('A concise definition.', language=language)
            self.assertEqual([], report.findings)
            self.assertIn('declared_non_english', report.meta['readability']['uninterpreted_reasons'])

    def test_accents_or_combining_marks_are_conservatively_uninterpreted_not_language_detection(self):
        for sample in ('A café guide.', 'A cafe\u0301 guide.'):
            report = measured(sample, language='en')
            self.assertEqual([], report.findings)
            self.assertEqual('uninterpreted', report.meta['readability']['formula_status'])
            self.assertIsNotNone(reading.recorded(report.meta['readability']))

    def test_punctuation_without_non_ascii_letters_does_not_disable_the_formula(self):
        for language in ('', 'en', ' EN-us '):
            receipt = reading.observe('Use the tool — check it.', language=language)
            self.assertEqual('computed', receipt['formula_status'])
            self.assertIsNotNone(reading.recorded(receipt))

    def test_hub_retains_counts_without_a_formula_comprehension_pass(self):
        report = measured('Useful site links. More pages.', hub=True)
        self.assertEqual([], report.findings)
        self.assertIn('link_hub', report.meta['readability']['uninterpreted_reasons'])
        self.assertGreater(report.meta['readability']['ascii_pattern_matches'], 0)
        self.assertIsNotNone(reading.recorded(report.meta['readability']))

    def test_empty_numeric_and_punctuation_inputs_do_not_invent_scores(self):
        for sample in ('', '12345', '...!?'):
            report = measured(sample)
            self.assertEqual([], report.findings)
            self.assertIn('no_formula_inputs', report.meta['readability']['uninterpreted_reasons'])
            self.assertIsNone(report.meta['readability']['flesch_reading_ease'])

    def test_counts_are_patterns_not_universal_words_sentences_or_syllables(self):
        receipt = reading.observe('I a code... API? 1234!')
        self.assertEqual((4, 3, 5), tuple(receipt[k] for k in ('ascii_pattern_matches', 'sentence_fragments', 'estimated_syllables')))
        self.assertIn('not multilingual words', reading.LIMITS)
        self.assertIn('not verified sentences', reading.LIMITS)
        self.assertIn('not validated syllables', reading.LIMITS)

    def test_receipt_does_not_retain_raw_text_and_clips_source_labels(self):
        receipt = reading.observe('UNIQUE_PRIVATE_TEXT.', basis='x'*1000, language='x'*1000)
        self.assertEqual((160,80), (len(receipt['source_basis']),len(receipt['declared_language'])))
        self.assertTrue(receipt['source_basis_clipped']);self.assertTrue(receipt['declared_language_clipped'])
        self.assertNotIn('UNIQUE_PRIVATE_TEXT', json.dumps(receipt))
        self.assertIsNotNone(reading.recorded(receipt))

    def test_unsupported_malformed_or_incoherent_receipts_do_not_become_evidence(self):
        original = reading.observe('Controlled guide Useful instructions.')
        for key, value in [('version',True),('version',2),('basis','other'),('word_pattern','other'),
                           ('source_basis',''),('source_basis_clipped',1),('ascii_pattern_matches',True),
                           ('declared_language','fr'),
                           ('text_characters',1),('estimated_syllables',0),('sentence_fragments',0),
                           ('flesch_reading_ease',0),('flesch_reading_ease',float('nan')),
                           ('flesch_reading_ease',1<<4000),
                           ('flesch_kincaid_grade',float('inf')),('uninterpreted_reasons',[[]]),
                           ('formula_status','uninterpreted'),('link_hub_hint',True)]:
            receipt = copy.deepcopy(original);receipt[key]=value
            with self.subTest(key=key,value=value):
                self.assertIsNone(reading.recorded(receipt))
                self.assertIsNone(reading.note({'readability':receipt}))
        self.assertIsNone(reading.note({}))

    def test_untrusted_saved_labels_limits_and_source_markup_are_not_executed_or_linked(self):
        receipt = reading.observe('A concise definition.')
        receipt['source_basis']='<script>ATTACK</script>';receipt['limits']='<img src="https://evil.test/pixel">'
        report=Report(URL);report.meta['readability']=receipt
        for output in (report.to_markdown(),report.to_html()):
            self.assertNotIn('ATTACK',output);self.assertNotIn('evil.test',output)
            self.assertIn('not measured reader comprehension',output)

    def test_current_and_legacy_plans_preserve_precision_without_formula_quotas(self):
        for rule in IDS-{'content.readable.prose'}:
            data={'url':URL,'findings':[{'category':'content','severity':'medium','title':'Content is very hard to read',
                                       'rule_id':rule,'recommendation':'OLD_AI_QUOTABILITY_CLAIM'}]}
            result=plan.build_plan(data,str(FIXTURE));action,=result['actions']
            self.assertEqual('review_required',action['safety'])
            self.assertIn('preserve necessary technical terms',action['proposed_change'])
            self.assertNotIn('OLD_AI_QUOTABILITY_CLAIM',action['proposed_change'])
            before=json.dumps(result,sort_keys=True)
            output=plan.render_markdown(result)
            self.assertNotIn('OLD_AI_QUOTABILITY_CLAIM',output)
            self.assertNotIn('Content is very hard to read',output)
            self.assertIn('Input report priority retained',output)
            self.assertEqual(before,json.dumps(result,sort_keys=True))
            self.assertEqual('Content is very hard to read',result['actions'][0]['title'])

    def test_actual_scan_records_explicit_formula_scope_without_extra_requests(self):
        for sample,language,expected in [('Useful instructions.','en',True),('API 这是说明。','en',False),('Useful instructions.','fr',False)]:
            data=scanned(sample,language=language)
            self.assertIs(expected,data['meta']['scan_settings']['readability_reviewed'])
            self.assertEqual(expected, data['meta']['readability']['formula_status']=='computed')

    def test_comparison_labels_only_explicit_recorded_scope_not_guesses_from_legacy_text(self):
        doc=htmlx._parse_stdlib('<article><h1>Guide</h1><p>Useful instructions.</p></article>',URL)
        report=measured(doc.body_text)
        for value, expected in [(True,True),(False,False),(1,None),('true',None),(None,None)]:
            report.meta['scan_settings']={'readability_reviewed':value}
            self.assertIs(expected,compare.facts(report,doc)['readability_reviewed'])

    def test_known_scope_change_is_not_reported_as_a_fix_in_page_or_crawl_diff(self):
        old=scanned('Useful instructions.');new=copy.deepcopy(old)
        new['meta']['scan_settings']['readability_reviewed']=False
        for a,b in [(old,new),({'overall_score':old['score'],'homepage':old,'crawl':{'pages':[{'url':URL,'scan_settings':old['meta']['scan_settings']}]}},
                              {'overall_score':old['score'],'homepage':old,'crawl':{'pages':[{'url':URL,'scan_settings':new['meta']['scan_settings']}]}})]:
            result=diff_scan.diff_reports(a,b)
            self.assertEqual('incomparable',result['comparison']['status'])
            self.assertFalse(result['resolved'])

    def test_matching_uninterpreted_scope_is_not_automatically_a_diff_failure(self):
        data=scanned('API 这是说明。')
        result=diff_scan.diff_reports(data,copy.deepcopy(data))
        self.assertEqual('comparable',result['comparison']['status'])

    def test_missing_legacy_scope_is_not_inferred_or_type_coerced(self):
        old=scanned('Useful instructions.');new=copy.deepcopy(old)
        del old['meta']['scan_settings']['readability_reviewed']
        for bad in (None, 'true', 1, []):
            old['meta']['scan_settings']['readability_reviewed']=bad
            result=diff_scan.diff_reports(old,new)
            self.assertNotIn('readability_reviewed',result['comparison']['old_settings'])

    def test_known_scope_change_causes_exit_two_in_ci_gate(self):
        old=scanned('Useful instructions.');new=copy.deepcopy(old)
        new['meta']['scan_settings']['readability_reviewed']=False
        with tempfile.TemporaryDirectory() as directory:
            paths=[Path(directory)/name for name in ('before.json','after.json')]
            for path,data in zip(paths,(old,new)):
                path.write_text(json.dumps(data),encoding='utf-8')
            with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                code=diff_scan.main([str(p) for p in paths]+['--fail-on-regression'])
        self.assertEqual(2,code)

    def test_contradictory_crawl_formula_settings_prevent_improvement_claims(self):
        data=scanned('Useful instructions.')
        settings=data['meta']['scan_settings']
        other={**settings,'readability_reviewed':False}
        value={'overall_score':data['score'],'homepage':data,'crawl':{'pages':[{'url':URL,'scan_settings':settings},{'url':URL,'scan_settings':other}]}}
        result=diff_scan.diff_reports(value,copy.deepcopy(value))
        self.assertEqual('incomparable',result['comparison']['status'])
        self.assertTrue(any('contradictory readability_reviewed' in r for r in result['comparison']['reasons']))

    def test_rendering_and_plan_are_readonly_and_offline(self):
        report=measured('Controlled guide Useful instructions.')
        before=report.to_json()
        with mock.patch.object(socket,'socket',side_effect=AssertionError('No network')):
            report.to_html();report.to_markdown();plan.build_plan(json.loads(before),str(FIXTURE))
        self.assertEqual(before,report.to_json())


if __name__=='__main__':
    unittest.main()
