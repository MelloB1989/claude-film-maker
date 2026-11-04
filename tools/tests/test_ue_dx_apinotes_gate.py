"""The "verify every engine API" rule (CONVENTIONS §6, B40), held from now on: an engine name the bridge uses that no
docs/unreal/*.md API_NOTES mentions fails this test, unless it is in ALLOWLIST (the names uncovered when the gate
was added, each sent to its owner to verify on the source box). Adding a row for one is the fix; then delete it here.

    cd tools && python -m filmtools.unreal.apinotes        # what is uncovered, by file
"""
from filmtools.unreal import apinotes

ALLOWLIST = {  # 2026-11-05, apinotes at ue-helpers 106fb52+: owner in the comment
    # agent-08 (look/env)
    "LightingChannels", "Vector4", "LightingBuildQuality", "get_default_object", "CollectionScalarParameter",
    "MaterialExpressionCollectionParameter", "MaterialExpressionComponentMask", "MaterialExpressionConstant3Vector",
    "MaterialExpressionDivide", "MaterialExpressionMaterialFunctionCall", "MaterialExpressionMin",
    "MaterialExpressionMultiply", "MaterialExpressionOneMinus", "MaterialExpressionSaturate",
    "MaterialExpressionScalarParameter", "MaterialExpressionSubtract", "MaterialExpressionTextureCoordinate",
    "MaterialExpressionTextureSampleParameter2D", "MaterialExpressionVectorParameter", "MaterialParameterCollection",
    "MaterialParameterCollectionFactoryNew", "TextureCompressionSettings",
    # agent-05 (render)
    "DirectoryPath", "IntPoint",
}


def test_no_new_engine_name_without_api_notes():
    missing = apinotes.report()["missing"]
    new = {n: w[:3] for n, w in missing.items() if n not in ALLOWLIST}
    assert not new, ("engine names used with no API_NOTES row (verify each on the UE source box, add a row to your "
                     "area doc's API_NOTES with its file:line): " + "; ".join(f"{n} at {', '.join(w)}" for n, w in
                                                                         sorted(new.items())))


def test_allowlist_only_holds_names_still_used():
    used = set(apinotes.used())
    assert ALLOWLIST <= used, f"no longer used, delete from ALLOWLIST: {sorted(ALLOWLIST - used)}"
