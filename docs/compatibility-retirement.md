# Compatibility surface retirement register

This register separates supported compatibility surfaces from obsolete modules.
Obsolete modules belong in `clean_manifest.yaml` and must not resolve. The
surfaces listed in `compatibility_retirement.yaml` still resolve intentionally;
they are delivery or extension compatibility only and are not nodes in the
canonical fact pipeline.

No registered surface may be removed before DocMirror 2.0.0. Removal also
requires a public replacement with contract coverage, migration of every
in-repository production consumer, a published migration guide and changelog,
at least one shipped deprecation release, and major-version contract approval.

The current register covers the combined legacy plugin role, legacy plugin and
output-builder projection calls, singular and synchronous request aliases,
sealed-result read aliases, and the original OCR correction-pack identifier.
The machine-readable source of truth is
`docmirror/configs/architecture/compatibility_retirement.yaml`.

This register does not authorize compatibility code to mutate a sealed result,
apply facts outside Canonical Validation, select an edition during recognition,
or become a dependency of input acceptance, Dispatcher, Adapter, Canonical
Assembly, Normalize/Structure/Entity, or `seal()`.
