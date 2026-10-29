class DependencyUnavailable(Exception):
    """A service the current turn cannot be answered without - the database,
    or Gemini embeddings for a search - failed.

    Raised instead of returning an empty or placeholder result, because to
    the agents an empty result is an answer: [] from a product search reads
    as "we don't sell that", a missing order id as "nothing to save". The
    API turns this into a 503 so the user is asked to retry rather than
    told something untrue.
    """
