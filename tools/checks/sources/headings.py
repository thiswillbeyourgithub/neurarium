"""Family 5: the shape of the derived book-heading trails the gate collected.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""


def check_heading_shapes(report, headings):
    """A source's `heading` (the breadcrumb of book headings the passage sits under)
    is DERIVED, keyed by quote id, from the author-side page trees by
    tools/fetch/fetch_quote_headers.py. Nothing in the emitted data proves it is
    still current, so check what is checkable without the books: the shape. A
    blank level would render as an empty crumb, which reads like a heading the
    book actually prints rather than one the resolver failed to find."""
    before_shape = report.errors
    for ctx, corpus, page, trail in headings:
        if not isinstance(trail, list) or not trail:
            report.error(f"{ctx}: heading must be a non-empty list of headings, "
                         f"outermost first (got {trail!r}); omit it rather than "
                         f"storing an empty breadcrumb")
            continue
        for part in trail:
            if not isinstance(part, str) or not part.strip():
                report.error(f"{ctx}: heading trail has a blank level ({trail!r}); "
                             f"drop the level rather than storing a blank crumb")
    if report.errors == before_shape and headings:
        report.ok(f"all {len(headings)} derived heading trails are non-empty lists "
                  f"of non-blank headings")
