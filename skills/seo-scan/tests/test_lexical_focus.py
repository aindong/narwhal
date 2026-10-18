"""Lexical frequency/overlap receipts cannot establish semantic relevance."""
import copy
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import audit_content
import plan
import scan
from lib import htmlx,http,lexical_focus,text as textlib
from lib.report import Report
from test_page_schema_review import FIXTURE

URL='https://example.test/guide'
GOOD='content.dominant.topics.detected'
REVIEW='content.body.may.not.reinforce.the.title.topic'
LATE='leaves light water carbon sugar oxygen plants energy photosynthesis'
EARLY='photosynthesis leaves light water carbon sugar oxygen plants energy'


def measured(body=LATE,title='Photosynthesis',h1=None,parser=htmlx._parse_stdlib):
    markup='<title>'+title+'</title><main>'+ ('<h1>'+h1+'</h1>' if h1 else '') +'<p>'+body+'</p></main>'
    doc=parser(markup,URL);report=Report(URL,final_url=URL,fetched_status=200)
    audit_content._keywords(doc,doc.body_text,report)
    return doc,report


class TestLexicalFocus(unittest.TestCase):
    def test_ninth_tied_body_term_is_not_treated_as_a_semantic_absence(self):
        doc,report=measured()
        value=report.meta['lexical_focus']
        self.assertIn('photosynthesis',doc.body_text)
        self.assertEqual('zero_overlap',value['status'])
        self.assertEqual(0,value['shared_term_count'])
        self.assertEqual([('leaves',1),('light',1),('water',1),('carbon',1),('sugar',1),('oxygen',1),('plants',1),('energy',1)],
                         [(v['term'],v['count']) for v in value['body_terms']])
        finding=report.findings[-1]
        self.assertEqual((REVIEW,'low'),(finding.rule_id,finding.severity))
        self.assertIn('outside the top-8 cutoff',finding.evidence)
        self.assertIn('Do not repeat keywords',finding.recommendation)
        self.assertNotIn('helps ranking',finding.recommendation)

    def test_tie_order_and_existing_warning_selection_are_preserved_and_explained(self):
        _,late=measured(LATE);_,early=measured(EARLY)
        self.assertEqual([GOOD,REVIEW],[f.rule_id for f in late.findings])
        self.assertEqual([GOOD],[f.rule_id for f in early.findings])
        self.assertEqual('first_selected_text_occurrence',early.meta['lexical_focus']['tie_basis'])
        self.assertEqual(1,early.meta['lexical_focus']['shared_term_count'])
        self.assertIn('not dominant topics',early.findings[0].detail)

    def test_all_original_counts_phrases_focus_and_warning_conditions_are_preserved(self):
        for body,title,h1 in [(LATE,'Photosynthesis',None),(EARLY,'Photosynthesis',None),
                              ('automobile maintenance','Car repair',None),('bank river banks','Bank account',None),
                              ('alpha beta alpha beta','Other','Alpha'),('自然历史与海洋。','自然历史',None),
                              ('alpha beta','The and may',None),('I a go API code','API',None)]:
            doc,report=measured(body,title,h1)
            terms=textlib.top_keywords(doc.body_text,8)
            focus=set(textlib.words((doc.title or '').lower()))
            headings=[t for level,t in doc.headings if level==1]
            if headings:focus|=set(textlib.words(headings[0].lower()))
            focus={w for w in focus if len(w)>=3 and w not in textlib.STOPWORDS}
            value=report.meta['lexical_focus']
            self.assertEqual(terms,[(v['term'],v['count']) for v in value['body_terms']])
            self.assertEqual(textlib.top_bigrams(doc.body_text,3) if terms else [],[(v['term'],v['count']) for v in value['phrases']])
            self.assertEqual(len(focus),value['focus_term_count'])
            expected=bool(terms and focus and not (focus & {t for t,c in terms}))
            self.assertEqual(expected,any(f.rule_id==REVIEW for f in report.findings))
            self.assertIsNotNone(lexical_focus.recorded(value))

    def test_synonyms_and_incidental_word_matches_do_not_certify_semantics(self):
        for body,title in [('automobile maintenance','Car repair'),('bank river banks','Bank account')]:
            _,report=measured(body,title)
            for finding in report.findings:self.assertIn('not dominant topics, semantic relevance',finding.detail)
        self.assertIn('synonyms',measured('automobile maintenance','Car repair')[1].findings[-1].recommendation)

    def test_no_body_terms_records_scope_without_a_fake_topic_pass(self):
        _,report=measured('自然历史与海洋。','自然历史')
        self.assertEqual([],report.findings)
        self.assertEqual('no_body_terms',report.meta['lexical_focus']['status'])
        self.assertIsNotNone(lexical_focus.recorded(report.meta['lexical_focus']))

    def test_no_focus_terms_is_not_an_assessed_zero_overlap(self):
        _,report=measured('alpha beta','The and may')
        self.assertEqual([GOOD],[f.rule_id for f in report.findings])
        self.assertEqual('no_focus_terms',report.meta['lexical_focus']['status'])

    def test_only_first_h1_is_used_with_title_terms(self):
        doc=htmlx.Doc(URL,title='Alpha',headings=[(1,'Beta'),(1,'Gamma')],text='gamma delta')
        value=lexical_focus.observe(doc)
        self.assertEqual(['alpha','beta'],[t['term'] for t in value['focus_terms']])
        self.assertEqual('zero_overlap',value['status'])

    def test_ascii_pattern_hyphens_apostrophes_and_stopwords_are_literal(self):
        _,report=measured("cache-control don't cache-control API May the",'cache-control')
        value=report.meta['lexical_focus']
        self.assertEqual([('cache-control',2),("don't",1),('api',1)],[(v['term'],v['count']) for v in value['body_terms']])
        self.assertEqual(1,value['shared_term_count'])

    def test_focus_witness_cap_does_not_change_exact_overlap_for_omitted_terms(self):
        title='alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron zulu'
        _,report=measured('zulu zulu',title)
        value=report.meta['lexical_focus']
        self.assertEqual(13,value['focus_term_count'])  # two-letter mu/nu/xi omitted
        self.assertEqual(12,len(value['focus_terms']))
        self.assertTrue(value['focus_witnesses_omitted'])
        self.assertEqual(1,value['shared_term_count'])
        self.assertIsNotNone(lexical_focus.recorded(value))

    def test_clipped_equal_looking_witnesses_do_not_create_a_false_exact_match(self):
        prefix='x'*200
        _,report=measured(prefix+'a',prefix+'b')
        value=report.meta['lexical_focus']
        self.assertEqual(value['body_terms'][0]['term'],value['focus_terms'][0]['term'])
        self.assertTrue(value['body_terms'][0]['clipped']);self.assertTrue(value['focus_terms'][0]['clipped'])
        self.assertEqual(0,value['shared_term_count'])
        self.assertEqual('zero_overlap',value['status'])
        self.assertIsNotNone(lexical_focus.recorded(value))
        self.assertIn('[clipped]',report.findings[-1].evidence)

    def test_phrase_clipping_at_a_word_boundary_remains_supported(self):
        _,report=measured('x'*159+' beta','Other')
        value=report.meta['lexical_focus']
        self.assertTrue(value['phrases'][0]['clipped'])
        self.assertEqual(160,len(value['phrases'][0]['term']))
        self.assertTrue(value['phrases'][0]['term'].endswith(' '))
        self.assertIsNotNone(lexical_focus.recorded(value))

    def test_source_basis_is_bounded_and_full_text_is_not_retained(self):
        doc=SimpleNamespace(title='Term',headings=[],body_text='UNIQUE_PRIVATE_TEXT',extraction='x'*1000)
        value=lexical_focus.observe(doc)
        self.assertEqual(160,len(value['source_basis']))
        self.assertTrue(value['source_basis_clipped'])
        self.assertNotIn('body_text',value);self.assertNotIn('title',value)
        self.assertIsNotNone(lexical_focus.recorded(value))

    def test_stopword_fingerprint_tracks_the_actual_filter_not_an_inferred_version(self):
        doc=htmlx.Doc(URL,title='custom',text='custom alpha')
        before=lexical_focus.observe(doc)
        with mock.patch.object(textlib,'STOPWORDS',textlib.STOPWORDS|{'custom'}):
            after=lexical_focus.observe(doc)
            self.assertNotEqual(before['stopwords_sha256'],after['stopwords_sha256'])
            self.assertIsNone(lexical_focus.recorded(before))
            self.assertIsNotNone(lexical_focus.recorded(after))

    def test_malformed_legacy_or_incoherent_receipts_do_not_become_witnesses(self):
        _,report=measured();original=report.meta['lexical_focus']
        for key,value in [('version',True),('version',2),('basis','other'),('stopwords_sha256','bad'),
                          ('focus_term_count',True),('shared_term_count',99),('shared_term_count',1),
                          ('body_term_limit',True),('source_basis',''),('source_basis_clipped',1),
                          ('body_terms',[{}]),('focus_terms',None),('focus_witnesses_omitted',True),('status',[]),
                          ('phrases',[{'term':'alpha beta','clipped':False,'count':True}])]:
            candidate=copy.deepcopy(original);candidate[key]=value
            self.assertIsNone(lexical_focus.recorded(candidate),key)
            self.assertEqual('',lexical_focus.witnesses(candidate),key)
        self.assertEqual('',lexical_focus.witnesses({}))

    def test_saved_untrusted_terms_and_source_labels_are_not_rendered_as_markup(self):
        _,report=measured();value=report.meta['lexical_focus']
        value['source_basis']='<script>ATTACK</script>';value['limits']='https://evil.test/pixel'
        self.assertNotIn('ATTACK',lexical_focus.witnesses(value))
        value['focus_terms'][0]['term']='<img src=https://evil.test/pixel>'
        self.assertEqual('',lexical_focus.witnesses(value))

    def test_current_and_legacy_plans_are_conditional_and_keep_original_json(self):
        data={'url':URL,'findings':[{'category':'content','severity':'low','title':'Body may not reinforce the title topic',
                                   'rule_id':REVIEW,'recommendation':'OLD_RANKING_PROMISE'}]}
        result=plan.build_plan(data,str(FIXTURE));action,=result['actions']
        self.assertEqual('review_required',action['safety'])
        self.assertIn('Do not stuff keywords',action['proposed_change'])
        self.assertNotIn('OLD_RANKING_PROMISE',action['proposed_change'])
        before=json.dumps(result,sort_keys=True);output=plan.render_markdown(result)
        self.assertIn('Review recorded lexical-focus observation',output)
        self.assertNotIn('Body may not reinforce the title topic',output)
        self.assertNotIn('OLD_RANKING_PROMISE',output)
        self.assertEqual(before,json.dumps(result,sort_keys=True))

    def test_actual_scan_records_scope_without_extra_requests(self):
        source='<title>Photosynthesis</title><main><p>'+LATE+'</p></main>'
        response=http.Response(URL,URL,200,{'content-type':'text/html'},source,1)
        with mock.patch.object(scan.http,'fetch',return_value=response) as fetch:
            report=scan.scan(URL,only=['content'],ctx={},check_images=False)
        self.assertEqual(1,fetch.call_count)
        self.assertEqual('zero_overlap',report.meta['lexical_focus']['status'])

    def test_optional_parser_paths_preserve_the_frequency_observation(self):
        values=[]
        for parser in (htmlx._parse_stdlib,htmlx.parse):
            _,report=measured(parser=parser)
            values.append(report.meta['lexical_focus']['body_terms'])
        self.assertEqual(values[0],values[1])

    def test_reports_are_readonly_and_offline(self):
        _,report=measured();before=report.to_json()
        with mock.patch.object(socket,'socket',side_effect=AssertionError('No network')):
            report.to_markdown();report.to_html();plan.build_plan(json.loads(before),str(FIXTURE))
        self.assertEqual(before,report.to_json())


if __name__=='__main__':unittest.main()
