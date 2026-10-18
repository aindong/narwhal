"""Compact native evidence must not hide uncertainty or change recorded facts."""
from collections import Counter
import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import audit
import audit_content
from lib import htmlx
from lib.report import Report, _measurement_evidence

URL='https://example.test/guide'


def measured(*,text='Useful instructions.',language='en',meta='',article=True):
    tag='article' if article else 'main'
    source=('<html lang="'+language+'"><head><title>Controlled guide</title>'+meta+'</head>'
            '<body><'+tag+'><h1>Controlled guide</h1><p>'+text+'</p></'+tag+'></body></html>')
    doc=htmlx._parse_stdlib(source,URL)
    report=Report(URL,final_url=URL,fetched_status=200)
    audit_content.audit(doc,None,report)
    return report


def audit_data(report):
    return {'site':URL,'page':report,'site_result':{'base':URL,'avg_score':report.score(),'pages_scanned':1,
            'pages':[{'url':URL,'score':report.score()}],'recurring':Counter(),
            'links':{'broken':[],'checked':0,'skipped_over_cap':0},'duplicates':[]},
            'sitemap':{'start':URL,'seeds':[]}}


class Tags(HTMLParser):
    def __init__(self,markup):
        super().__init__(convert_charrefs=True)
        self.tags=[];self.feed(markup)
    def handle_starttag(self,tag,attrs):
        self.tags.append((tag,dict(attrs)))


class TestMeasurementDisclosure(unittest.TestCase):
    def test_native_disclosure_is_closed_with_a_print_copy_and_no_script(self):
        output=measured().to_html();tags=Tags(output).tags
        details=[attrs for tag,attrs in tags if tag=='details']
        self.assertEqual([{'class':'measurement-details'}],details)
        self.assertEqual(1,sum(tag=='div' and attrs.get('class')=='measurement-print' for tag,attrs in tags))
        self.assertFalse(any(tag=='script' for tag,attrs in tags))
        self.assertIn('@media print{.measurement-details{display:none}.measurement-print{display:block}',output)

    def test_overview_keeps_counts_and_nonverification_visible(self):
        report=measured(meta='<meta name="author" content="Jane Doe"><meta name="date" content="not-a-date">')
        overview=report.to_html().split('<section class="card measurement-overview">')[1].split('<details')[0]
        for value in ('Text length: 4 ASCII-pattern matches','Flesch estimate -8.7, FK estimate 15.5',
                      'Attribution: 1 captured candidate witness(es); identity is unverified',
                      'Date cues: 1 captured candidate(s); publication dates and freshness are unverified'):
            self.assertIn(value,overview)
        self.assertIn('not verified page quality',overview)

    def test_unsupported_reading_and_length_are_not_presented_as_passes(self):
        output=measured(text='API 这是使用说明。',language='en').to_html()
        overview=output.split('<section class="card measurement-overview">')[1].split('<details')[0]
        self.assertIn('threshold review not applied (language/text scope)',overview)
        self.assertIn('Readability formula: unassessed',overview)
        self.assertNotIn('Flesch estimate',overview)

    def test_zero_candidates_are_not_absence_or_freshness_verdicts(self):
        output=measured().to_html().split('<section class="card measurement-overview">')[1].split('<details')[0]
        self.assertIn('Attribution: 0 captured candidate',output)
        self.assertIn('Date cues: 0 captured candidate',output)
        self.assertIn('identity is unverified',output)
        self.assertIn('freshness are unverified',output)
        self.assertNotIn('No dates',output)

    def test_captured_limits_remain_visible_before_opening(self):
        report=measured(meta='<meta name="date" content="'+'x'*5000+'">')
        report.meta['authorship_cues']['coverage']['source_truncated']=True
        output=report.to_html().split('<section class="card measurement-overview">')[1].split('<details')[0]
        self.assertEqual(2,output.count('Capture limits reached; unchecked evidence remains unknown.'))

    def test_legacy_empty_or_unsupported_metadata_does_not_invent_observations(self):
        for meta in (None,{}, {'content_length':{'version':999},'readability':{'version':999},
                              'authorship_cues':{'version':999},'date_cues':{'version':999}}):
            self.assertEqual('',_measurement_evidence(meta))
        self.assertNotIn('<section class="card measurement-overview">',Report(URL).to_html())

    def test_each_supported_panel_can_appear_without_inventing_other_receipts(self):
        report=measured()
        for key,title in [('content_length','Text-length observation'),('readability','Readability formula observation'),
                          ('authorship_cues','Attribution cue evidence'),('date_cues','Date-cue evidence')]:
            output=_measurement_evidence({key:report.meta[key]})
            self.assertEqual(2,output.count('<h2>'+title))
            self.assertEqual(1,output.count('<details class="measurement-details">'))

    def test_literal_source_values_stay_escaped_in_both_detail_copies(self):
        report=measured(meta='<meta name="author" content="&lt;script&gt;ATTACK&lt;/script&gt;">'
                             '<meta name="date" content="&lt;img src=https://evil.test/pixel&gt;">')
        output=report.to_html();tags=Tags(output).tags
        self.assertEqual(2,output.count('&lt;script&gt;ATTACK&lt;/script&gt;'))
        self.assertEqual(2,output.count('&lt;img src=https://evil.test/pixel&gt;'))
        self.assertFalse(any(tag=='script' or tag=='img' and attrs.get('src','').startswith('https://evil.test')
                             or tag=='a' and 'evil.test' in attrs.get('href','') for tag,attrs in tags))

    def test_primary_findings_and_non_scoring_resource_notes_stay_outside_disclosure(self):
        report=measured()
        report.add('technical','critical','FIX_FIRST','Verify this captured defect.','Repair the confirmed defect.')
        report.meta['http_robots']={'version':1,'basis':'response_header_fields','notes':['RESOURCE_UNCERTAINTY']}
        prefix=report.to_html().split('<details class="measurement-details">')[0]
        self.assertIn('FIX_FIRST',prefix)
        self.assertIn('RESOURCE_UNCERTAINTY',prefix)
        self.assertIn('Priority fixes',prefix)

    def test_native_audit_uses_the_same_disclosure_without_mutating_page_facts(self):
        report=measured();before=report.to_json()
        output=audit.render_html(audit_data(report))
        self.assertEqual(1,output.count('<details class="measurement-details">'))
        self.assertIn('Homepage audit',output);self.assertIn('Site-wide',output)
        self.assertEqual(before,report.to_json())

    def test_rendering_preserves_json_markdown_scores_scope_and_findings_offline(self):
        report=measured();before=report.to_json();markdown=report.to_markdown()
        scores=(report.score(),report.counts());original=copy.deepcopy(report.meta)
        with mock.patch.object(socket,'socket',side_effect=AssertionError('No network')):
            report.to_html();audit.render_html(audit_data(report))
        self.assertEqual(before,report.to_json());self.assertEqual(markdown,report.to_markdown())
        self.assertEqual(scores,(report.score(),report.counts()));self.assertEqual(original,report.meta)
        self.assertNotIn('measurement-details',json.dumps(report.meta))


if __name__=='__main__':
    unittest.main()
