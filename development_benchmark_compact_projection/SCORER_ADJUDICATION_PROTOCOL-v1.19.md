# V1.19 scorer adjudication protocol

The original six target records, traces, patches, scores, packet, and completion receipt are
immutable. All six records failed only because the trusted scorer's minimal coordinator
environment omitted `/usr/sbin` from `PATH`; its preflight therefore could not resolve `chroot`
even though the sandbox invokes `/usr/sbin/chroot` explicitly.

No target may be rerun or replaced. Before condition unblinding, the adjudicator must:

1. verify the original report, completion receipt, execution contract, and scorer-failure receipt;
2. decrypt each exact target bundle and verify its run, trace, and patch digests;
3. reconstruct the frozen fixture and apply only that recorded patch;
4. require the recorded visible test and a fresh visible test to pass;
5. run the unchanged independent scorer with the project interpreter, project source, and exact
   trusted path `/usr/sbin:/usr/bin:/sbin:/bin`;
6. require every scorer sandbox receipt to succeed;
7. issue a new blinded report and append-only adjudication receipt linked to the originals; and
8. add zero target sessions, reveal no condition mapping, and access no external-validation data.

The secondary judge receives the unchanged anonymous packet. Automated adjudicated scores remain
primary; the judge cannot rescue an automated regression.
