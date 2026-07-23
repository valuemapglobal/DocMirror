# Compatibility surface retirement register

This register separates supported compatibility surfaces from obsolete modules.
Obsolete modules belong in `clean_manifest.yaml` and must not resolve. The
surfaces listed in `compatibility_retirement.yaml` still resolve intentionally;
they are delivery or extension compatibility only and are not nodes in the
canonical fact pipeline.

DocMirror 1.1.0 is an owner-approved compatibility reset for the pre-seal
plugin contracts introduced in 1.0.12. The reset retires those contracts so
the canonical fact pipeline can remain closed before sealing. After 1.1.0,
removal of a registered public surface again requires a replacement with
contract coverage, migration of every in-repository production consumer, a
published migration guide and changelog, and explicit major-version approval.

The current register covers the combined legacy plugin role, legacy plugin and
output-builder projection calls, singular and synchronous request aliases,
sealed-result read aliases, and the original OCR correction-pack identifier.
The machine-readable source of truth is
`docmirror/configs/architecture/compatibility_retirement.yaml`.

This register does not authorize compatibility code to mutate a sealed result,
apply facts outside Canonical Validation, select an edition during recognition,
or become a dependency of input acceptance, Dispatcher, Adapter, Canonical
Assembly, Normalize/Structure/Entity, or `seal()`.
