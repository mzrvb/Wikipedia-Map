"""MediaWiki API access — the single entry point to Wikipedia.

Rules: namespace 0 only, filtered with `p.ns == 0` (never a colon-in-title check);
descriptive User-Agent from .env as `appname/version (contact)`; retry with a small
delay on failure. Synchronous (`wikipedia-api`) until caching proves insufficient.
"""
