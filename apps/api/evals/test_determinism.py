"""§7 determinism guard: recompiling unchanged approved KUs => no new version."""
from apps.api.compiler.skill_compiler import compile_skill


def test_recompile_is_stable(seeded, db, org_id):
    s1 = compile_skill(db, org_id, "refund")
    v1 = s1.version
    sig1 = s1.content_signature
    s2 = compile_skill(db, org_id, "refund")
    assert s2.version == v1, "unchanged KUs must not bump the version"
    assert s2.content_signature == sig1
