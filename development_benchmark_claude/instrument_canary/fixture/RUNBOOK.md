# Retry incident note

The earlier incident was attributed to inconsistent job-ID casing. Job identifiers are now
normalized before retry decisions.

The production reproduction still reports that exhausting one job's retry budget can affect a
different job.
