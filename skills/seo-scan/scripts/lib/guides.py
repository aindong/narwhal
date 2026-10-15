"""Static reference navigation; never fetch sources or infer finding validity."""

_BASE = 'https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/'
_GUIDES = {
    'technical': 'technical-seo.md',
    'content': 'content-eeat.md',
    'schema': 'schema.md',
    'geo': 'geo-llmo.md',
}

# Rule identities, not human wording, select precise sections. Unmapped checks
# get their general category guide rather than a guessed section.
_SECTION_RULES = (
    ('technical', 'title--meta-description',
     'missing.title title.is.very.short title.may.be.truncated.in.serps '
     'homepage.title.is.just.the.brand missing.meta.description '
     'meta.description.is.short meta.description.may.be.truncated'),
    ('technical', 'headings',
     'no.h1.heading multiple.h1.headings heading.levels.skip.a.level'),
    ('technical', 'canonicalization', 'no.canonical.url canonical.points.elsewhere'),
    ('technical', 'robots-directives-two-layers',
     'page.is.set.to.noindex page.level.nofollow no.robots.txt.found '
     'robots.txt.has.no.sitemap.directive no.xml.sitemap.found'),
    ('technical', 'mobile--rendering',
     'no.responsive.viewport.tag no.lang.attribute.on.html '
     'content.served.only.as.a.noscript.fallback'),
    ('technical', 'hreflang-international', 'duplicate.hreflang.entries no.x.default.hreflang'),
    ('technical', 'images', 'images.missing.alt.text no.lazy.loaded.images'),
    ('technical', 'links', 'links.with.no.anchor.text generic.anchor.text'),
    ('technical', 'http-hygiene',
     'redirect.chain page.not.served.over.https unexpected.content.type no.compression.header'),
    ('content', 'content-depth-not-word-count-for-its-own-sake',
     'thin.content content.is.on.the.short.side link.hub.page.with.little.prose'),
    ('content', 'readability', 'content.is.fairly.hard.to.read content.is.very.hard.to.read'),
    ('content', 'topical-focus', 'body.may.not.reinforce.the.title.topic'),
    ('content', 'filler--ai-writing-detection',
     'filler.padding.language some.filler.phrasing reads.as.ai.generated.generic '
     'some.generic.ai.sounding.phrasing repetitive.vocabulary'),
    ('content', 'experience--expertise', 'no.visible.author.byline'),
    ('content', 'freshness', 'no.visible.date.signal'),
    ('content', 'social--preview-metadata', 'incomplete.open.graph.tags no.twitter.x.card.type'),
    ('schema', 'format', 'no.structured.data microdata.extraction rdfa.extraction'),
    ('geo', '1-question-based-headings', 'few.question.based.headings'),
    ('geo', '2-citable-self-contained-passages', 'few.self.contained.citable.passages'),
    ('geo', '3-evidence-density', 'no.statistics.or.citations'),
    ('geo', '4-direct-answer-intro-inverted-pyramid', 'no.direct.answer.up.top'),
    ('geo', '5-entity-clarity', 'title.and.h1.don.t.share.terms'),
    ('geo', 'ai-crawler-policies--distinguish-purpose-before-recommending-access',
     'ai.crawlers.are.blocked.in.robots.txt'),
    ('geo', 'llmstxt--low-cost-low-certainty', 'no.llms.txt'),
)
_SECTIONS = {
    (category, category + '.' + rule): anchor
    for category, anchor, rules in _SECTION_RULES for rule in rules.split()
}
_PREFIX_SECTIONS = (
    ('schema', 'schema.ecommerce.', 'product-and-merchant-listing-checks'),
    ('schema', 'schema.deprecated.rich.result.type.', 'retired-google-search-rich-result-features'),
)


def reference_url(category, rule_id):
    """Return trusted guide context for a category, optionally a known section."""
    if not isinstance(category, str) or category not in _GUIDES:
        return None
    anchor = None
    if isinstance(rule_id, str):
        anchor = _SECTIONS.get((category, rule_id))
        if anchor is None:
            for group, prefix, section in _PREFIX_SECTIONS:
                if category == group and rule_id.startswith(prefix):
                    anchor = section
                    break
    return _BASE + _GUIDES[category] + ('#' + anchor if anchor else '')
