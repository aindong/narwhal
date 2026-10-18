#!/usr/bin/env python3
"""Literal frequency/overlap observations and conditional plans in Chromium."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import plan
from lib.report import html_document,md_to_html
from test_lexical_focus import measured,LATE,EARLY,FIXTURE,REVIEW,URL
from _measurement_browser import expand_measurements


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path)
    parser.add_argument('--html',type=Path,action='append',default=[])
    args=parser.parse_args(argv)
    if args.artifacts:args.artifacts.mkdir(parents=True,exist_ok=True)
    docs=[]
    for name,body,title in [('late',LATE,'Photosynthesis'),('early',EARLY,'Photosynthesis'),
                            ('synonym','automobile maintenance','Car repair'),('incidental','bank river banks','Bank account'),
                            ('clipped','x'*200+'a','x'*200+'b')]:
        doc,report=measured(body,title)
        before=report.to_json()
        docs += [(name,report.to_html()),(name+'-markdown',html_document('Lexical QA','',md_to_html(report.to_markdown())))]
        if name=='late':
            result=plan.build_plan(json.loads(before),str(FIXTURE))
            docs.append(('plan',html_document('Lexical review QA','',md_to_html(plan.render_markdown(result)))))
            legacy={'url':URL,'findings':[{'category':'content','severity':'low','rule_id':REVIEW,
                    'title':'Body may not reinforce the title topic','recommendation':'OLD_RANKING_PROMISE'}]}
            result=plan.build_plan(legacy,str(FIXTURE));saved=json.dumps(result,sort_keys=True)
            docs.append(('legacy-plan',html_document('Recorded lexical QA','',md_to_html(plan.render_markdown(result)))))
            assert saved==json.dumps(result,sort_keys=True)
        assert before==report.to_json()
    docs += [('installed-'+p.stem,p.read_text(encoding='utf-8')) for p in args.html]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        try:
            tab=browser.new_page();requests=[]
            def deny(route):requests.append(route.request.url);route.abort()
            tab.route('http://**/*',deny);tab.route('https://**/*',deny)
            for name,output in docs:
                tab.set_content(output);expand_measurements(tab)
                for media,width in [('screen',320),('screen',390),('screen',1100),('print',794)]:
                    tab.emulate_media(media=media);tab.set_viewport_size({'width':width,'height':1000})
                    text=tab.inner_text('body')
                    for claim in ('Dominant topics detected','Body may not reinforce the title topic','helps ranking and AI topical grounding','OLD_RANKING_PROMISE'):
                        assert claim not in text,(name,claim)
                    if 'plan' in name:
                        assert 'Review recorded lexical-focus observation' in text
                        assert 'Do not stuff keywords' in text
                        assert 'not a verified semantic gap' in text
                    else:
                        assert 'Frequent extracted-text terms observed' in text
                        assert 'not dominant topics, semantic relevance' in text
                    if name.startswith('late'):
                        assert 'Review literal title/H1 term overlap' in text
                        assert 'outside the top-8 cutoff' in text
                        assert 'photosynthesis' in text
                    if name.startswith('early'):
                        assert 'Review literal title/H1 term overlap' not in text
                    if name.startswith('clipped'):
                        assert 'x'*160 in text and 'x'*161 not in text
                        assert '[clipped]' in text
                    assert tab.evaluate('document.documentElement.scrollWidth<=innerWidth'),(name,media,width)
                    if args.artifacts and width==390:tab.screenshot(path=str(args.artifacts/(name+'-390.png')),full_page=True)
                if args.artifacts and name in ('late','plan'):
                    tab.pdf(path=str(args.artifacts/(name+'.pdf')),format='A4',print_background=True)
            assert not requests,requests
        finally:browser.close()
    print('OK: scoped literal frequency/cutoff observations and conditional current/legacy plans on mobile/desktop/print; no topic/ranking verdicts, JSON mutation or external rendering requests.')
    return 0


if __name__=='__main__':raise SystemExit(main())
