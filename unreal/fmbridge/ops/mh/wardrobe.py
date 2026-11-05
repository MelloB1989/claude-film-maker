"""The character's wardrobe in Creator: grooms (hair, eyebrows, beard, mustache, eyelashes, peach fuzz) and outfits are
items in the character's palette (its internal collection), one selected per slot on the collection's default
instance; each selected item has instance parameters (a groom's melanin, redness, dye colour, ombre, highlights; a
garment's colours) that the build bakes in."""
from __future__ import annotations

import unreal

from .. import op
from ...errors import OpError, not_found
from ..assets import list_assets, load
from . import _core as K


def _coll(c):
    coll = c.get_editor_property("internal_collection")
    if coll is None:
        raise OpError(f"{c.get_path_name()} has no internal collection", code="engine",
                      hint="open it once with mh.add (TryAddObjectToEdit sets the collection up)")
    return coll


def _inst(coll):
    return coll.get_editor_property("default_instance")


@op("mh.wardrobe", mutates=False, idempotent=True)
def wardrobe(kind: str = "") -> list:
    """Wardrobe items (grooms and clothing) the engine ships: kind Hair, Beards, Eyebrows, Eyelashes, Mustaches,
    Peachfuzz, Clothing, or empty for all.

    Returns: item asset paths for mh.add_item / mh.groom.
    Example: film-ue op mh.wardrobe kind=Hair
    """
    items = [p for c, p in list_assets(K.OPTIONAL, "MetaHumanWardrobeItem")]
    return [p for p in items if not kind or f"/{kind}/".lower() in p.lower()]


def _item_path(item: str) -> str:
    """A wardrobe item by path or by asset name (WI_Hair_S_BuzzCut)."""
    if item.startswith("/"):
        return K.package(item)
    allp = wardrobe()
    hit = [p for p in allp if p.rsplit("/", 1)[-1].lower() == item.lower()]
    if not hit:  # a palette key's name (mh.palette, mh.export): the principal asset, e.g. Hair_S_BuzzCut_Binding
        def core(n):
            n = n.lower()
            for a in ("wi_",):
                n = n[len(a):] if n.startswith(a) else n
            for z in ("_binding", "_groom"):
                n = n[:-len(z)] if n.endswith(z) else n
            return n.replace("_", "")
        hit = [p for p in allp if core(p.rsplit("/", 1)[-1]) == core(item)]
    if hit:
        return hit[0]
    raise not_found("wardrobe item", item, [p.rsplit("/", 1)[-1] for p in allp], hint="list them with mh.wardrobe")


def _slot_for(item: str, slot: str) -> str:
    if slot:
        return slot
    for s in K.GROOM_SLOTS:
        if f"/{s}" in item:  # /Grooms/.../Hair/, /Beards/, /Mustaches/ ...
            return s
    return "Outfits"


def _key_name(key) -> str:
    try:
        return str(key.to_asset_name_string())
    except Exception:
        return str(unreal.MetaHumanPaletteKeyBlueprintLibrary.to_asset_name_string(key))


def _is_null(key) -> bool:
    try:
        return bool(key.is_null())
    except Exception:
        return not _key_name(key)


def _selected(inst) -> dict:
    """{slot: FMetaHumanPipelineSlotSelection} on an instance."""
    out = {}
    for d in inst.get_slot_selection_data() or []:
        sel = d.get_editor_property("selection")
        out[str(sel.get_editor_property("slot_name"))] = sel
    return out


_ASSEMBLED = {}  # instance path -> the selection it was last assembled for


def _assemble(inst) -> bool:
    """Assemble the instance, once per selection: live (UE 5.8.4, day 1) no item has instance parameters until it
    is assembled (get_instance_parameter_item_paths() == []), so a groom's Melanin cannot be read or set before.
    False when it was already assembled for this selection (an item that has no parameters stays without)."""
    sig = tuple(sorted((s, _key_name(x.get_editor_property("selected_item"))) for s, x in _selected(inst).items()))
    if _ASSEMBLED.get(inst.get_path_name()) == sig and inst.is_assembled():
        return False
    inst.assemble()
    _ASSEMBLED[inst.get_path_name()] = sig
    return True


def _read_params(inst, path) -> list:
    try:
        got = inst.get_instance_parameters(path)  # ScriptMethod "GetInstanceParameters"
    except AttributeError:
        got = unreal.MetaHumanCharacterInstanceBlueprintLibrary.get_instance_parameters_for_item(inst, path)
    return list(got or [])


def _params(inst, sel) -> list:
    """The selected item's instance parameters, assembling the instance first when they are not there yet."""
    try:
        path = sel.get_selected_item_path()
    except AttributeError:  # the ScriptMethod's static form
        path = unreal.MetaHumanPipelineSlotSelectionBlueprintLibrary.get_selected_item_path(sel)
    got = _read_params(inst, path)
    if not got and not _is_null(sel.get_editor_property("selected_item")):
        if _assemble(inst):
            got = _read_params(inst, path)
    return got


def _param_value(p):
    t = K.enum_name(p.get_editor_property("type")).upper()
    try:
        v = {"BOOL": p.get_bool, "FLOAT": p.get_float, "COLOR": p.get_color, "NAME": p.get_name,
             "STRING": p.get_string}.get(t, lambda: None)()
    except Exception:
        return None
    return K.plain(v)


def _set_param(p, value) -> bool:
    t = K.enum_name(p.get_editor_property("type")).upper()
    if t == "BOOL":
        return bool(p.set_bool(bool(value)))
    if t == "FLOAT":
        return bool(p.set_float(float(value)))
    if t == "COLOR":
        if not isinstance(value, (list, tuple)) or len(value) not in (3, 4):
            raise OpError(f"{p.get_editor_property('name')}: a colour is [r, g, b] linear", code="bad_args")
        return bool(p.set_color(unreal.LinearColor(r=float(value[0]), g=float(value[1]), b=float(value[2]),
                                                  a=float(value[3]) if len(value) > 3 else 1.0)))
    if t == "NAME":
        return bool(p.set_name(str(value)))
    if t == "STRING":
        return bool(p.set_string(str(value)))
    raise OpError(f"{p.get_editor_property('name')}: parameters of type {t} are not settable by mh ops",
                  code="unsupported")


def _pkey(name: str) -> str:
    """Parameter names compare without case, underscores and a leading bool 'b' (bUseOmbre == use_ombre)."""
    n = str(name)
    if len(n) > 1 and n[0] == "b" and n[1].isupper():
        n = n[1:]
    return n.replace("_", "").lower()


def selections(c, params: bool = True) -> dict:
    """{slot: {"item": asset name, "display", "params": {name: value}}} of what the character wears."""
    coll = _coll(c)
    inst = _inst(coll)
    out = {}
    for slot, sel in _selected(inst).items():
        key = sel.get_editor_property("selected_item")
        if _is_null(key):
            out[slot] = None
            continue
        e = {"item": _key_name(key)}
        try:
            e["display"] = str(coll.get_item_display_name(key))
        except Exception:
            pass
        if params:
            e["params"] = {str(p.get_editor_property("name")): _param_value(p) for p in _params(inst, sel)}
        out[slot] = e
    return out


@op("mh.palette", mutates=False, idempotent=True)
def palette(character: str) -> dict:
    """What the character wears now: its collection's slots, every item in its palette and the selection per slot
    with the selected items' parameters.

    Returns: {"slots": [...], "items": [...], "selected": {slot: {"item", "params"} or null}}.
    Example: film-ue op mh.palette character=/Game/Characters/Ava/MH_Ava
    """
    c = K.char(character)
    coll = _coll(c)
    out = {"slots": [str(s) for s in coll.get_slot_names()]}
    try:
        out["items"] = [_key_name(k) for k in coll.get_all_item_keys()]
    except Exception as e:
        out["items_error"] = str(e)
    out["selected"] = selections(c)
    return out


def _ensure_item(coll, slot: str, item: str):
    """The palette key of `item` in `slot`, adding it to the palette only if it is not there yet (a second
    try_add_item_from_wardrobe_item makes a second entry, 'Hair_S_BuzzCut_Binding (2)')."""
    wi = load(item)
    try:
        for k in coll.get_item_keys_for_wardrobe_item(wi) or []:
            if str(coll.get_item_slot_name(k)) == slot:
                return k, False
    except Exception:
        pass
    key = coll.try_add_item_from_wardrobe_item(slot, wi)
    if key is None:
        raise OpError(f"{item} cannot go in slot {slot}", code="engine", candidates=[str(s) for s in coll.get_slot_names()],
                      hint="a groom goes in its own slot (Hair, Eyebrows, Beard, Mustache, Eyelashes, Peachfuzz), "
                           "clothing in Outfits")
    return key, True


@op("mh.add_item", mutates=True, idempotent=True, tags=["metahuman"])
def add_item(character: str, item: str, slot: str = "", *, params: dict | None = None, save: bool = True) -> dict:
    """Wear a wardrobe item: put it (a groom or garment from mh.wardrobe) in its slot of the character's collection
    and select it there, replacing what the slot held; optionally set its parameters.

    Args: character: the character. item: a wardrobe item path or asset name (WI_Hair_S_BuzzCut). slot: Hair,
    Eyebrows, Beard, Mustache, Eyelashes, Peachfuzz, Outfits (guessed from the item's path when empty). params: the
    item's instance parameters (mh.item_params lists them), e.g. {"Melanin": 0.9, "Redness": 0.1}.
    Returns: {"slot", "item", "display", "changed", "params"}. Rebuild (mh.build) to see it on the Blueprint.
    Example: film-ue op mh.add_item character=/Game/Characters/Ava/MH_Ava item=WI_Hair_L_Straight 'params={"Melanin": 1.0}'
    """
    c = K.char(character)
    coll = _coll(c)
    item = _item_path(item)
    slot = _slot_for(item, slot)
    key, added = _ensure_item(coll, slot, item)
    inst = _inst(coll)
    cur = _selected(inst).get(slot)
    same = cur is not None and _key_name(cur.get_editor_property("selected_item")) == _key_name(key)
    changed = added or not same
    if not same:
        inst.set_single_slot_selection(slot, key)
    out = {"slot": slot, "item": _key_name(key), "changed": changed}
    try:
        out["display"] = str(coll.get_item_display_name(key))
    except Exception:
        pass
    if params:
        r = _apply_params(inst, slot, params)
        out["params"], out["changed"] = r["params"], out["changed"] or r["changed"]
    if out["changed"] and save:
        K.save(character)
    return out


@op("mh.clear_slot", mutates=True, idempotent=True)
def clear_slot(character: str, slot: str, *, save: bool = True) -> dict:
    """Wear nothing in a slot (e.g. no Beard).

    Returns: {"slot", "changed"}.
    Example: film-ue op mh.clear_slot character=/Game/Characters/Ava/MH_Ava slot=Beard
    """
    c = K.char(character)
    inst = _inst(_coll(c))
    cur = _selected(inst).get(slot)
    changed = cur is not None and not _is_null(cur.get_editor_property("selected_item"))
    if changed:
        inst.set_single_slot_selection(slot, unreal.MetaHumanPaletteItemKey())
        if save:
            K.save(character)
    return {"slot": slot, "changed": changed}


def _apply_params(inst, slot: str, params: dict) -> dict:
    sel = _selected(inst).get(slot)
    if sel is None or _is_null(sel.get_editor_property("selected_item")):
        raise OpError(f"nothing is worn in slot {slot}", code="conflict", hint="wear an item first with mh.add_item")
    have = {_pkey(p.get_editor_property("name")): p for p in _params(inst, sel)}
    changed = False
    for name, value in params.items():
        p = have.get(_pkey(name))
        if p is None:
            names = [str(x.get_editor_property("name")) for x in have.values()]
            raise OpError(f"the item in {slot} has no parameter {name!r}", code="bad_args",
                          candidates=K.closest(name, names), hint="mh.item_params lists them: " + ", ".join(names))
        if _param_value(p) != K.plain(_norm_value(value)):
            if not _set_param(p, value):
                raise OpError(f"the engine refused {slot}.{name}={value!r}", code="engine")
            changed = True
    sel = _selected(inst).get(slot)
    return {"changed": changed, "params": {str(p.get_editor_property("name")): _param_value(p)
                                           for p in _params(inst, sel)}}


def _norm_value(v):
    if isinstance(v, (list, tuple)) and len(v) == 3:
        return [float(x) for x in v] + [1.0]
    if isinstance(v, int) and not isinstance(v, bool):
        return float(v)
    return v


@op("mh.item_params", mutates=False, idempotent=True)
def item_params(*, character: str, slot: str) -> dict:
    """The instance parameters of the item worn in a slot, with their values: for a groom Melanin, Redness,
    Roughness, Whiteness, Lightness, DyeColor, bUseOmbre/OmbreU/OmbreV/..., bUseRegions/..., bUseHighlights/...
    (MetaHumanDefaultGroomPipeline); for a garment its material colours.

    Returns: {"slot", "item", "params": {name: value}}.
    Example: film-ue op mh.item_params character=/Game/Characters/Ava/MH_Ava slot=Hair
    """
    c = K.char(character)
    s = selections(c).get(slot)
    if s is None:
        raise OpError(f"nothing is worn in slot {slot}", code="not_found",
                      candidates=[k for k, v in selections(c, False).items() if v], hint="mh.palette shows the slots")
    return {"slot": slot, "item": s["item"], "params": s.get("params", {})}


@op("mh.item_set", mutates=True, idempotent=True, tags=["metahuman"])
def item_set(*, character: str, slot: str, params: dict, save: bool = True) -> dict:
    """Set instance parameters of the item worn in a slot: hair colour by melanin/redness (0..1), dye colour, ombre,
    highlights; a garment's colours. Only differing values are written.

    Returns: {"slot", "changed", "params"}.
    Example: film-ue op mh.item_set character=/Game/Characters/Ava/MH_Ava slot=Hair 'params={"Melanin": 1.0, "Redness": 0.05}'
    """
    c = K.char(character)
    r = _apply_params(_inst(_coll(c)), slot, params)
    if r["changed"] and save:
        K.save(character)
    return {"slot": slot, **r}


@op("mh.groom", mutates=True, idempotent=True, tags=["metahuman"])
def groom(*, character: str, slot: str, item: str = "", melanin: float = None, redness: float = None,
          params: dict | None = None, save: bool = True) -> dict:
    """A groom in one call: wear `item` in `slot` (or keep what is worn, or wear nothing with item="none") and set its
    colour (melanin: 0 blond .. 1 black; redness 0..1) and any other groom parameter.

    Args: slot: Hair|Eyebrows|Beard|Mustache|Eyelashes|Peachfuzz. item: a groom wardrobe item (mh.wardrobe kind=Hair),
    "" to keep, "none" to clear. Returns: {"slot", "item", "changed", "params"}.
    Example: film-ue op mh.groom character=/Game/Characters/Ava/MH_Ava slot=Hair item=WI_Hair_L_Straight melanin=1.0 redness=0.05
    """
    if slot not in K.GROOM_SLOTS:
        raise OpError(f"{slot!r} is not a groom slot", code="bad_args", candidates=K.closest(slot, K.GROOM_SLOTS),
                      hint=", ".join(K.GROOM_SLOTS))
    if item.lower() == "none":
        return {**clear_slot(character, slot, save=save), "item": None}
    p = dict(params or {})
    if melanin is not None:
        p["Melanin"] = melanin
    if redness is not None:
        p["Redness"] = redness
    if item:
        return add_item(character, item, slot, params=p or None, save=save)
    r = item_set(character=character, slot=slot, params=p, save=save) if p else {"changed": False}
    return {"slot": slot, "item": item_params(character=character, slot=slot)["item"], **r}
