# film-ue exec tools/mh_identity_probe.py -- READ-ONLY: what the editor's Python exposes for footage -> MetaHuman
# Identity -> MetaHuman Character on this box. Touches no capture data and prints no paths from it.
import unreal
R = {}
def t(k, f):
    try: R[k] = f()
    except Exception as e: R[k] = "ERR " + repr(e)[:300]
words = ("identity", "capture", "footage", "livelinkface", "ingest", "conform", "promot", "solve", "mesh2metahuman",
         "metahumanperformance", "depth", "calib", "takemetadata", "cameracalibration", "autorig", "teeth")
names = [n for n in dir(unreal) if any(w in n.lower() for w in words)]
R["unreal_names"] = sorted(names)[:400]
def members(cls_name, filt=None):
    c = getattr(unreal, cls_name, None)
    if c is None: return "missing"
    return [n for n in dir(c) if not n.startswith("_") and (filt is None or any(w in n.lower() for w in filt))]
for n in ("MetaHumanIdentity", "MetaHumanIdentityFace", "MetaHumanIdentityPose", "MetaHumanIdentityPromotedFrame",
          "FootageCaptureData", "MetaHumanCaptureSource", "LiveLinkFaceArchivesIngest", "MetaHumanIdentityBlueprintLibrary",
          "MetaHumanCharacterEditorSubsystem", "CaptureDataBlueprintLibrary", "MetaHumanFaceFittingSolver",
          "MetaHumanPerformance", "IngestCaptureData", "CaptureManagerBlueprintLibrary"):
    t("members:" + n, lambda n=n: members(n))
sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
t("char_subsystem_import", lambda: [n for n in dir(sub) if any(w in n.lower() for w in ("import", "identity", "conform", "fit", "template", "mesh", "dna", "from"))])
for n in names:
    c = getattr(unreal, n)
    if isinstance(c, type) and any(w in n.lower() for w in ("library", "subsystem")):
        t("lib:" + n, lambda c=c: [m for m in dir(c) if not m.startswith("_") and not m.startswith("get_editor_property")][:80])
t("plugins", lambda: [p for p in unreal.PluginBlueprintLibrary.get_enabled_plugin_names() if any(
    w in p.lower() for w in ("metahuman", "capture", "livelink", "footage"))])
result = R
