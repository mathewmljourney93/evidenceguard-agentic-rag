"""Model-provider boundary and fakes for EvidenceGuard (M5a, ADR-0019).

M5a adds only the ``ModelProvider`` protocol, the validating ``call_validated`` boundary and the
test-owned ``ScriptedFakeProvider``. Nothing here is registered, configured or networked. This
package may import ``evidenceguard_domain`` only (and, later, ``evidenceguard_observability``).
"""
