# Judge amendment v1.2

The v1.1 judge schema was rejected by the provider before model inference because the
`judge_version` constant did not declare an explicit JSON string type. A diagnostic repeat exposed
the same HTTP 400 `invalid_json_schema` error. Neither attempt produced model output, a decision,
token usage, or a provider-billed call.

Version 1.2 adds explicit string types to every constant and enum field. It does not change the
blind packet, ordered output bindings, target episodes, automated scores, or condition mapping.
One actual tool-free `gpt-5.6-sol`/xhigh judge attempt is allowed with a new local output and
configuration root.
