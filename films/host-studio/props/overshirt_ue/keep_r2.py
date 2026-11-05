"""Before importing round 3's overshirt over SKM_Presenter_Overshirt: keep the round-2 one as SKM_Presenter_Overshirt_r2
(once; an existing copy is left alone). Run with film-ue exec."""
import unreal

EAL = unreal.EditorAssetLibrary
SRC = "/Game/Host/Presenter_Overshirt/SKM_Presenter_Overshirt"
KEEP = SRC + "_r2"
made = False
if not EAL.does_asset_exist(KEEP):
    made = EAL.duplicate_asset(SRC, KEEP) is not None
    EAL.save_asset(KEEP)
result = {"kept": KEEP, "made_now": made, "exists": EAL.does_asset_exist(KEEP)}
