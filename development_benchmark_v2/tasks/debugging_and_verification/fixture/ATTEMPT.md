# Previous timeout investigation

The first report blamed whitespace around `X-Request-Timeout`. Header names and values are now
stripped and normalized before parsing, so the incident was marked fixed.

The current reproduction still observes a request-specific value on a later request that did not
supply the header.
