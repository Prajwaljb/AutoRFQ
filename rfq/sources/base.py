"""What every product source looks like.

A source turns one product ID into {RFQ column: Cell}. Adding a source (e.g. a competitor finder) is one
new file with a class like this; the pipeline decides the order and how results are merged.
"""


class Source:
    name = "source"   # live / spec / catalog
    found_via = ""    # label used in counts and on the item

    def lookup(self, product_id):
        """{column: Cell} for the product, {} if this source has nothing, or raise SourceUnavailable."""
        raise NotImplementedError

    def extra(self, product_id):
        """Commercial fields that are not RFQ columns (price, availability, URLs)."""
        return {}


class SourceUnavailable(Exception):
    """The source can't answer right now (blocked, timed out, offline). The caller falls back."""
