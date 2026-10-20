"""Timeless v3.1 stage: the nested zoom (flow type `nest`), the user's method for every zoom-in / zoom-out cut.

ONE world layout per window, clips static, only the rig moves (EDIT.md "v3.1: nested null-camera zooms"):
  push  the FRONT card is A (its home card); B's card (a copy, uniform scale k) sits D metres behind A's region, its
        focus on the line through the region's inner point. A's opacity inside the region (eye / lens / background)
        ramps 1 -> 0 from `reveal[0]` f before the camera reaches A's plane, B already playing; the camera dollies
        through the region into B's hold framing.
  pull  the mirror: the FRONT card is B (a copy, scale 1/k relative to A's home card, in front of it), A is the BACK.
        The camera starts on A behind B's plane, pulls back through B's region, and B's region fades back to opaque.
Front-card space: the front card is the plane z = 0, the back card the plane z = -D (axis-aligned, rolled by phi so the
camera's roll is continuous), the camera at z(t) = k F / s_K(t) - D, where s_K is the back card's apparent scale. ln s_K
is the window's one smooth curve: an exponential attack (x g per frame, from the hold's rate) into the crossing at f - 0.5,
then the measured decay (x1.22 / f) into the landing; `land` (s_K at the crossing) is solved so the speed is the same on
both sides. D and k come from the region's size at the reveal (the back card framed `fill` x the region) and `land`.
After w1 the camera teleports from the copy to B's home card with an identical relative pose (invisible).
DOF: focused on the back card during the approach (push: A defocuses as it nears); pull: rack to B after the crossing.
"""
import math

from mathutils import Matrix, Quaternion, Vector

import camlib as cl
import cards
import flow
import regions

F = cl.FILL_DIST
DEF = dict(land=1.1, reveal=(10, 8), fill=1.15, fstop=2.0)
PAN_MIN = 6.0  # px / f: the least pan a nest is entered with after a hold
CENTRE_BY = 0.6  # an eye / lens opening reaches frame centre after this share of the approach
LAND_LO = 1.0  # the back card's least scale at the crossing (it must cover the frame when the front plane passes)
GROW_MIN = 1.2  # the back card grows at least this much between the reveal and the crossing (eye / lens)
GROW_OPEN = 3.0  # an eye / lens opening: B grows at least this much from the reveal to the crossing
GROW_BG = 1.8  # ... and a background reveal (B shows most of the frame behind the subject; its faded tiles at the rim)
ROOM_GROW = 1.3  # the landing room the speed cap plans with (B's settle x this over LAND_LO)
SETTLE_GROW = 1.35
PULL_SHRINK = 0.25  # a pull's A shrinks at least x e^0.25 from w0 to the crossing
PULL_LAND_LO = 0.55  # ... down to this at most  # how much deeper than the EDL settle a push may land (to keep the landing's natural decay)


def sign_of(T):
    return -1 if T["p"].get("mode") == "pull" else 1


def _adjacent_prev(T, ctx):
    return any(c["w1"] == T["w0"] and c["id"] != T["id"] for c in ctx.E["cuts"])


def bounds(T, ctx):
    p = T["p"]
    sg = sign_of(T)
    out = {}
    A = ctx.entry_state(T)
    adj = _adjacent_prev(T, ctx)
    R = float(p.get("roll", 0.0) or 0.0)
    prevc = next((c for c in ctx.E["cuts"] if T.get("a") and c.get("b") == T["a"]["id"] and c["id"] in ctx.bounds
                  and "B" in ctx.bounds[c["id"]]), None)
    pB = ctx.bounds[prevc["id"]]["B"] if prevc is not None else None
    if not adj and flow.prev_hold(T, ctx) >= flow.REVERSAL_MIN:
        A = A.with_(ds=max(A.ds, flow.ENTRY) if sg > 0 else min(A.ds, -flow.ENTRY))
        if pB is not None and abs(pB.dr) > 0.05:
            # the roll keeps the previous landing's direction through the hold (a slow roll turning round in a hold
            # stops the picture together with the zoom turn); the window's own roll turns it, fast
            A = A.with_(dr=math.copysign(max(abs(A.dr), flow.ROLL_CARRY), pB.dr))
        elif R:
            A = A.with_(dr=math.copysign(max(abs(A.dr), flow.ROLL_CARRY), R))
    elif not adj:
        # a short hold cannot turn the zoom round: the entry keeps the previous landing's rate when it already goes the
        # window's way (a push after a push landing keeps pushing)
        if pB is not None and pB.ds * sg > 0:
            A = A.with_(ds=sg * max(abs(pB.ds), flow.ENTRY))
    A = ctx.settle_entry(T, A, fixed_rate=True)
    B = ctx.exit_state(T)
    settle = float(p.get("settle", B.s))
    B = B.with_(s=max(settle, cl.min_scale(B.cx, B.cy, B.r, 0.01)))
    nxt = next((c for c in ctx.E["cuts"] if T.get("b") and c.get("a") == T["b"]["id"]), None)
    nsg = None
    if nxt is not None and nxt.get("type") in ("nest", "zt", "slam"):
        nsg = -1 if (nxt.get("p") or {}).get("mode") == "pull" else 1
    if flow.next_hold(T, ctx) >= flow.REVERSAL_MIN or nsg == sg:
        # leave still going the window's way (a short hold before a same-sign zoom keeps it: no turn at all)
        B = B.with_(ds=max(B.ds, flow.EXIT) if sg > 0 else min(B.ds, -flow.EXIT))
        if R:
            B = B.with_(dr=math.copysign(max(abs(B.dr), flow.ROLL_CARRY), R))
    if sg > 0:
        fb = flow.focus_of(T, "b", ctx)
        cx, cy = cl.clamp_center(B.s, B.cx + 0.7 * (fb[0] - B.cx), B.cy + 0.7 * (fb[1] - B.cy), B.r, 0.01)
        B = B.with_(cx=cx, cy=cy)
    # the pan keeps its direction through the window edges: A already drifts towards the crossing point and B's exit
    # drift continues the landing's direction (a Hermite from slope 1.2 x mean to 0 never turns round)
    L = Layout(T, ctx, A, B)
    TA, TB = L.tx - L.w0, L.w1 - L.tx
    cpre = L.P if L.push else L.fK
    cpost = L.fK if L.push else L.P
    if not adj and flow.prev_hold(T, ctx) >= flow.REVERSAL_MIN:
        TCn = max(2.0, CENTRE_BY * TA) if L.kind != "bg" else TA
        # settle_entry moves A by half the hold x the rate, the rate depends on A: a damped fixed point (gain > 1)
        dcx, dcy = A.dcx, A.dcy
        for _ in range(24):
            A = ctx.settle_entry(T, A.with_(dcx=dcx, dcy=dcy), fixed_rate=True)
            dcx = 0.7 * dcx + 0.3 * 1.2 * (cpre[0] - A.cx) / TCn
            dcy = 0.7 * dcy + 0.3 * 1.2 * (cpre[1] - A.cy) / TCn
        A = ctx.settle_entry(T, A.with_(dcx=dcx, dcy=dcy), fixed_rate=True)
        sp = math.hypot(A.dcx, A.dcy)
        if sp < PAN_MIN:
            # never a dead pan into the window (the crossing point may sit where the frame already is): the hold
            # intent's drift direction tops it up
            ix, iy = A.dcx or ctx.intent(T["a"]["id"], T["w0"]).dcx, A.dcy or ctx.intent(T["a"]["id"], T["w0"]).dcy
            n = math.hypot(ix, iy) or 1.0
            A = ctx.settle_entry(T, A.with_(dcx=ix / n * PAN_MIN, dcy=iy / n * PAN_MIN), fixed_rate=True)
    elif adj and prevc is not None and prevc.get("type") == "nest":
        # touching the previous window: A's place is fixed (it is that window's landing), but its drift already heads
        # for the crossing point, so the landing before flows into this approach without a turn
        TCn = max(2.0, CENTRE_BY * TA) if L.kind != "bg" else TA
        A = A.with_(dcx=0.8 * (cpre[0] - A.cx) / TCn, dcy=0.8 * (cpre[1] - A.cy) / TCn)
    ctx.log(f"  nest {T['id']} bounds: prev hold {flow.prev_hold(T, ctx)} adj {adj} cpre {[round(v) for v in cpre]} "
            f"A c ({A.cx:.0f},{A.cy:.0f}) dc ({A.dcx:+.1f},{A.dcy:+.1f})")
    if flow.next_hold(T, ctx) >= flow.REVERSAL_MIN:
        B = B.with_(dcx=1.2 * (B.cx - cpost[0]) / TB, dcy=1.2 * (B.cy - cpost[1]) / TB)
    if L.push and L.B_s > B.s * 1.001:
        B = B.with_(s=L.B_s)  # the landing goes deeper than the EDL settle: the hold after starts there
    # the attack needs a minimum entry speed (x G_MAX per frame at most): the hold accelerates into it
    if not adj:
        for _ in range(3):
            L = Layout(T, ctx, A, B)
            if L.curve.g is None or L.curve.g <= flow.G_MAX * 1.02:
                break
            need = flow.attack_r0(abs(L.curve.Lx - L.curve.L0), L.curve.TA, flow.G_MAX)
            ds = need * (L.z0 + L.D) / L.z0 if sg > 0 else -need
            A = ctx.settle_entry(T, A.with_(ds=ds), fixed_rate=True)
    out["A"], out["B"] = A, B
    return out


# ---- the one curve: ln s_K(t) ---------------------------------------------------------------------------------------------
class LnCurve:
    """ln s_K from (L0, r0) at w0 through Lx at the crossing tx to (L1, r1) at w1: an exponential attack (x g / frame)
    then a mirrored expo decay whose start rate equals the attack's end rate (C1 at the crossing)."""

    def __init__(self, L0, r0, Lx, L1, r1, w0, tx, w1, decay=flow.DECAY, kB=None):
        self.L0, self.r0, self.Lx, self.L1, self.r1 = L0, r0, Lx, L1, r1
        self.w0, self.tx, self.w1 = w0, tx, w1
        self.TA, self.TB = tx - w0, w1 - tx
        self.sg = 1.0 if Lx >= L0 else -1.0
        d = abs(Lx - L0)
        a0 = r0 * self.sg
        self.g = None
        self.mode = "expo"
        if a0 > 0.003 and d > 1e-4:
            g = flow.attack_g(d, self.TA, a0)
            if g >= 1.03:
                self.g = g
                self.Va = a0 * g ** self.TA
            else:
                self.mode = "hermite"
        else:
            self.mode = "ramp"
        if self.mode == "ramp":
            self.kA = math.log(flow.ATTACK) * self.TA
            self.Va = abs(flow.ramp_in(L0, r0, Lx, self.TA, self.kA, self.TA)[1])
        elif self.mode == "hermite":
            self.Va = max(a0, 1.5 * d / self.TA)
        else:
            self.kA = max(0.3, math.log(self.g) * self.TA)
        if self.mode == "hermite":
            self.kA = 1.0
        # decay: start rate = Va (solved k), unless kB is given (the natural decay, for balancing)
        if kB is None:
            kB = flow.k_for_start_rate(Lx, L1, r1, self.TB, self.sg * self.Va)
        self.kB = max(0.3, kB)
        self.Vb = abs(flow.ramp_out(Lx, L1, r1, self.TB, self.kB, self.TB)[1])

    def __call__(self, t):
        """-> (ln s_K, d ln s_K / dt)."""
        if t <= self.tx:
            tau = max(-2.0, t - self.w0)
            if self.mode == "expo":
                g = self.g
                return self.L0 + self.r0 * (g ** tau - 1) / math.log(g), self.r0 * g ** tau
            if self.mode == "ramp":
                return flow.ramp_in(self.L0, self.r0, self.Lx, self.TA, self.kA, tau)
            u = tau / self.TA
            m1 = self.sg * self.Va
            return (cl.hermite(self.L0, self.r0 * self.TA, self.Lx, m1 * self.TA, u),
                    cl.hermite_d(self.L0, self.r0 * self.TA, self.Lx, m1 * self.TA, u) / self.TA)
        tp = max(0.0, self.w1 - t)
        return flow.ramp_out(self.Lx, self.L1, self.r1, self.TB, self.kB, tp)

    def decay(self):
        return math.exp(self.kB / self.TB)


def _hermite_px(p0, m0, p1, m1, T, tau):
    u = max(0.0, min(1.0, tau / T)) if T > 0 else 1.0
    return cl.hermite(p0, m0 * T, p1, m1 * T, u), cl.hermite_d(p0, m0 * T, p1, m1 * T, u) / max(T, 1e-6)


# ---- layout -----------------------------------------------------------------------------------------------------------------
class Layout:
    """Solve D, k, land and the curves for window T with bounds A (at w0, on A's card) and B (at w1, on B's card)."""

    def __init__(self, T, ctx, A, B, fixed_B=False):
        self.T, self.ctx, self.A, self.B = T, ctx, A, B
        self.fixed_B = fixed_B  # build time: B is what the hold after starts from, never moved again
        p = T["p"]
        self.p = p
        self.sg = sign_of(T)
        self.push = self.sg > 0
        self.w0, self.w1, self.f = T["w0"], T["w1"], T["f"]
        self.tx = self.f - 0.5
        self.kind = p.get("region", "bg")
        self.fsid = p.get("shot") or (T["a"]["id"] if self.push else T["b"]["id"])
        self.ksid = T["b"]["id"] if self.push else T["a"]["id"]
        lead, dur = p.get("reveal", DEF["reveal"])
        lead, dur = float(lead), float(dur)
        self.kind = p.get("region", "bg")
        if not self.push:
            lead = max(3.0, min(lead, self.w1 - 1.5 - self.tx))
        elif self.kind != "bg":
            lead = max(3.0, min(lead, self.tx - self.w0 - 1.0))  # B shows in the opening once the camera heads for it
        dur = max(2.0, min(dur, lead - 1.0))
        self.lead, self.dur = lead, dur
        self.t_r = self.tx - lead if self.push else self.tx + lead
        # regions on the front shot
        if self.push:
            fr = range(int(math.floor(self.t_r)) - 2, int(self.f) + 1)
        else:
            fr = range(int(self.f) - 1, int(math.ceil(self.t_r)) + 3)
        key = (self.fsid, self.kind)
        cache = ctx.__dict__.setdefault("_regcache", {})
        if key not in cache or not set(fr) <= {k for k in cache[key][1] if isinstance(k, int)}:
            size = p.get("size")
            cache[key] = regions.prepare(ctx, self.fsid, self.kind, fr, size=size, at=p.get("at"))
        self.region_img, self.meta = cache[key]
        info_x = regions.info_at(self.meta, self.f - 1 if self.push else self.f)
        info_r = regions.info_at(self.meta, int(round(self.t_r)))
        self.info_r = info_r
        self.P = [float(v) for v in (p.get("at") or info_x["inner"])]
        bx0, by0, bx1, by1 = info_r["bbox"]
        self.regfrac = max(0.02, (bx1 - bx0) / 1920.0, (by1 - by0) / 1080.0)
        self.eq_diam = 2.0 * math.sqrt(max(1e-6, info_r["area"]) * 1920 * 1080 / math.pi)
        self.fK = flow.focus_of(T, "b" if self.push else "a", ctx)
        if self.push and self.w1 - self.tx < 4:
            # a landing of < 4 f (the next window takes over): B is crossed into where it lands, no lateral rush
            TBs = self.w1 - self.tx
            self.fK = [B.cx - B.dcx * TBs, B.cy - B.dcy * TBs]
        self.fill = float(p.get("fill", DEF["fill"]))
        self.touching = any(c["w0"] == self.w1 and c["id"] != T["id"] for c in ctx.E["cuts"])
        land = float(p.get("land", DEF["land"]))
        if self.push:
            land = max(0.95, min(land, B.s / 1.08))
        self.land_min = land
        self.solve()

    # front-card units: z0 = camera distance to the front plane at w0 (push) / at w1 (pull)
    def solve(self):
        A, B = self.A, self.B
        if self.push:
            self.z0 = F / A.s
            z_r = self.z0 * 0.6
        else:
            self.z1 = F / B.s
            z_r = self.z1 * 0.7
        D = 0.5 * z_r
        land = self.land_min if self.push else min(self.land_min, A.s * math.exp(-PULL_SHRINK))
        self.B_s = B.s  # a push may need a deeper landing than the EDL settle (see _push_land)
        for _ in range(16):
            land = self._push_land(D) if self.push else self._balance(D, land)
            curve = self._curve(D, land)
            z_r = self._z_at(self.t_r, D, land, curve)
            z_r = max(0.02, z_r)
            sF_r = F / z_r
            q = max(0.02, min(self.fill * self.regfrac * sF_r, land / (GROW_BG if self.kind == "bg" else GROW_MIN)))
            D_new = z_r * q / (land - q)
            if self.push:
                # the speed cap, but an opening keeps B growing at least GROW_OPEN x from the reveal to the crossing
                # (B framed in the eye, as in the refs), even if the landing then decays harder than x1.22 / f
                D_cap = self._speed_D(D_new, z_r)
                if self.kind != "bg":
                    D_cap = min(D_cap, z_r / (float(self.p.get("grow", GROW_OPEN)) - 1.0))
                D_new = max(D_new, D_cap)
            if abs(D_new - D) < 1e-5:
                D = D_new
                break
            D = 0.5 * D + 0.5 * D_new
        self.D = D
        self.land = land
        self.k = land * D / F
        self.curve = self._curve(D, land)
        self.q = self.k * F / (max(0.02, self._z_at(self.t_r, D, land, self.curve)) + D)
        if self.push:
            self.z0 = F / A.s

    def _ends(self, D, land):
        k = land * D / F
        A, B = self.A, self.B
        if self.push:
            z0 = F / A.s
            L0, r0 = math.log(k * F / (z0 + D)), A.ds * z0 / (z0 + D)
            L1, r1 = math.log(getattr(self, "B_s", B.s)), B.ds
        else:
            z1 = F / B.s
            L0, r0 = math.log(A.s), A.ds
            L1, r1 = math.log(k * F / (z1 + D)), B.ds * z1 / (z1 + D)
        return L0, r0, L1, r1

    def _curve(self, D, land, kB=None):
        L0, r0, L1, r1 = self._ends(D, land)
        return LnCurve(L0, r0, math.log(land), L1, r1, self.w0, self.tx, self.w1, kB=kB)

    def _speed_D(self, D_lo, z_r):
        """Push: the least D whose attack end speed (ln s_K / f at the crossing, = dolly speed / D) the landing can
        absorb with the natural decay inside `room` (B's settle x ROOM_GROW over LAND_LO). A small opening (an eye)
        would otherwise put B just behind it: B's growth explodes at the crossing and stops dead."""
        TB = self.w1 - self.tx
        # a landing the next window takes over has no room to grow: it may land smaller and decay harder instead
        kn = math.log(flow.DECAY_RANGE[1] if self.touching else flow.DECAY) * TB
        e = cl.expo_in_d(1.0, kn)
        r1 = self.B.ds
        room = math.log(self.B.s / 0.85) if self.touching else math.log(self.B.s * ROOM_GROW / LAND_LO)
        vcap = r1 - (r1 * TB - room) * e / TB

        def va(D):
            return self._curve(D, 0.85 if self.touching else LAND_LO, kB=kn).Va
        if va(D_lo) <= vcap:
            return D_lo
        lo, hi = D_lo, max(D_lo * 2, z_r * 40.0)
        if va(hi) > vcap:
            return hi
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if va(mid) > vcap:
                lo = mid
            else:
                hi = mid
        return hi

    def _push_land(self, D):
        """Push: the attack's end speed Va does not depend on land (the pre side covers ln((z0 + D) / D)), so land is
        solved in closed form so that the natural decay (x DECAY / f) from Va lands exactly on B's settle with B's exit
        rate: L1 = Lx + r1 TB - (r1 - Va) TB / E'(1). If that land would leave the frame uncovered at the crossing
        (< LAND_LO) the landing goes deeper instead (B's settle raised, at most x SETTLE_GROW)."""
        TB = self.w1 - self.tx
        kn = math.log(flow.DECAY) * TB
        self.B_s = self.B.s
        c = self._curve(D, self.land_min, kB=kn)
        e = cl.expo_in_d(1.0, kn)
        L1, r1, Va = math.log(self.B_s), c.r1, c.Va
        room = r1 * TB - (r1 - Va) * TB / e  # ln s_K the landing covers after the crossing
        Lx = L1 - room
        lo, hi = math.log(min(LAND_LO, self.land_min)), math.log(self.B_s / 1.03)
        if Lx < lo:
            if self.touching or self.fixed_B:
                # the next window starts at w1 from this landing: keep B, let the crossing scale give (>= 0.85)
                Lx = max(Lx, math.log(0.85))
            else:
                Lx = lo
                self.B_s = min(self.B.s * SETTLE_GROW, math.exp(Lx + room))
        return math.exp(min(hi, Lx))

    def _balance(self, D, land0):
        """land so the attack's end speed equals the natural decay's start speed (push: the post side depends on
        land; pull: the pre side does). Bisection within the allowed range."""
        kn = math.log(flow.DECAY) * (self.w1 - self.tx)
        L0, r0, L1, r1 = self._ends(D, land0)
        if self.push:
            lo, hi = math.log(self.land_min), max(math.log(self.land_min), L1 - 0.06)
        else:
            # a pull: A (the back card) shrinks from its entry scale into the crossing; it may show its faded mirror
            # tiles there (the frame is A seen through B's region), like the old zt pull
            hi = min(math.log(self.land_min), L0 - PULL_SHRINK)
            lo = min(hi, math.log(PULL_LAND_LO))
        if hi - lo < 1e-4:
            return math.exp(lo)

        def diff(Lx):
            c = self._curve(D, math.exp(Lx), kB=kn)
            return c.Va - c.Vb
        dlo, dhi = diff(lo), diff(hi)
        if dlo * dhi > 0:
            return math.exp(lo if abs(dlo) < abs(dhi) else hi)
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if diff(mid) * dlo > 0:
                lo = mid
            else:
                hi = mid
        return math.exp(0.5 * (lo + hi))

    def _z_at(self, t, D, land, curve):
        if self.push and t < self.w0:
            return F / self.A.at(t - self.w0).s
        if (not self.push) and t > self.w1:
            return F / self.B.at(t - self.w1).s
        k = land * D / F
        L, _ = curve(t)
        return k * F / math.exp(L) - D


class Nest:
    """A built nested zoom: geometry + the camera path (front-card space -> world)."""

    def __init__(self, L, ctx):
        self.L = L
        self.ctx = ctx
        self.T = L.T
        self.id = L.T["id"]
        self.push = L.push
        self.mode = "push" if L.push else "pull"
        self.kind, self.fsid, self.ksid = L.kind, L.fsid, L.ksid
        self.D, self.k, self.land, self.q = L.D, L.k, L.land, L.q
        self.t_x, self.t_r = L.tx, L.t_r
        self.w0, self.w1 = L.w0, L.w1
        self.curve = L.curve
        A, B = L.A, L.B
        TA, TB = L.tx - L.w0, L.w1 - L.tx
        p = L.p
        R = float(p.get("roll", 0.0) or 0.0)
        kAr, kBr = L.curve.kA * 1.2, min(60.0, L.curve.kB * 1.2)
        XA, XB = flow.roll_split(A.dr, B.dr, R, TA, TB, kAr, kBr)
        self.rA_end = A.r + A.dr * TA + XA
        self.rB_start = B.r - B.dr * TB - XB
        self.kAr, self.kBr = kAr, kBr
        self.R = R
        # the back card is rolled by phi (about its normal) so the camera's world roll is continuous at the crossing:
        # pre side rolls on the pre card (push: front, phi 0), post side on the post card
        self.phi = (self.rA_end - self.rB_start) if L.push else (self.rB_start - self.rA_end)
        # crossing points: P on the front card, fK on the back card, on the same line
        Pl = Vector((*cl.px_to_local(*L.P), 0.0))
        fl = Vector((*cl.px_to_local(*L.fK), 0.0))
        Rphi = Matrix.Rotation(math.radians(self.phi), 4, "Z")
        self.Kloc = Matrix.Translation((0, 0, -self.D)) @ Matrix.Translation(Pl - (Rphi @ fl) * self.k) @ Rphi @ \
            Matrix.Diagonal((self.k, self.k, self.k, 1.0))  # back card in front-card space
        if L.push:
            self.front = ctx.card(T_id(L.T, "a"))
            self.MF = self.front.matrix_world.copy()
            self.MK = self.MF @ self.Kloc
        else:
            self.MK = ctx.card(T_id(L.T, "a")).matrix_world.copy()
            self.MF = self.MK @ self.Kloc.inverted()
        self.P, self.fK = L.P, L.fK

    # ---- path ------------------------------------------------------------------------------------------------------
    def z(self, t):
        """Camera distance to the front plane (front-card metres; < 0 behind it)."""
        return self.L._z_at(t, self.D, self.land, self.curve)

    def _local(self, t):
        """Camera in front-card space at t -> (x, y, z, world roll deg)."""
        L, A, B = self.L, self.L.A, self.L.B
        TA, TB = L.tx - L.w0, L.w1 - L.tx
        z = self.z(t)
        if t <= L.tx:
            tau = t - L.w0
            cpre = L.P if L.push else L.fK
            # an opening is centred well before the crossing (the eye reads in the middle of the frame while B shows
            # in it); a background crossing point is reached at the crossing
            TC = max(2.0, CENTRE_BY * TA) if L.kind != "bg" else TA
            cx, _ = _hermite_px(A.cx, A.dcx, cpre[0], 0.0, TC, tau)
            cy, _ = _hermite_px(A.cy, A.dcy, cpre[1], 0.0, TC, tau)
            r, _ = flow.ramp_in(A.r, A.dr, self.rA_end, TA, self.kAr, max(0.0, tau))
            if tau < 0:
                r = A.r + A.dr * tau
            if L.push:
                x, y = cl.px_to_local(cx, cy)
                return x, y, z, r
            v = self.Kloc @ Vector((*cl.px_to_local(cx, cy), 0.0))
            return v.x, v.y, z, r + self.phi
        tp = L.w1 - t
        cpost = L.fK if L.push else L.P
        cx, _ = _hermite_px(B.cx, -B.dcx, cpost[0], 0.0, TB, tp)
        cy, _ = _hermite_px(B.cy, -B.dcy, cpost[1], 0.0, TB, tp)
        r, _ = flow.ramp_out(self.rB_start, B.r, B.dr, TB, self.kBr, max(0.0, tp))
        # the landing keeps the frame on B's real picture (no mirrored tile at an edge), faded in after the crossing
        sB = math.exp(self.curve(t)[0]) if L.push else (F / z if z > 1e-3 else 50.0)
        w = cl.smootherstep((t - L.tx) / 4.0)
        if w > 0 and sB >= 1.0:
            qx, qy = cl.clamp_center(sB, cx, cy, r, 0.01)
            cx, cy = cx + (qx - cx) * w, cy + (qy - cy) * w
        if L.push:
            v = self.Kloc @ Vector((*cl.px_to_local(cx, cy), 0.0))
            return v.x, v.y, z, r + self.phi
        x, y = cl.px_to_local(cx, cy)
        return x, y, z, r

    def pose(self, t):
        """Camera world (loc, quat) at t (before hits / offsets)."""
        x, y, z, r = self._local(t)
        return self.MF @ Vector((x, y, z)), self.MF.to_quaternion() @ Quaternion((0, 0, 1), math.radians(r))

    def point(self, card, px, py, dz=0.0):
        """World point of card pixel (px, py) at dz metres in front of it (card = 'front' / 'back' / an object)."""
        M = self.MF if card == "front" else self.MK if card == "back" else card.matrix_world
        return M @ Vector((*cl.px_to_local(px, py), dz))

    def state_on(self, which, t):
        """The camera as a State on the front / back card at t (for coverage checks and the gate)."""
        x, y, z, r = self._local(t)
        if which == "front":
            return cl.State(F / max(1e-4, z), *cl.local_to_px(x, y), r)
        v = self.Kloc.inverted() @ Vector((x, y, z))
        return cl.State(F / max(1e-4, v.z), *cl.local_to_px(v.x, v.y), r - self.phi)


def T_id(T, which):
    return T[which]["id"]


# ---- build ------------------------------------------------------------------------------------------------------------------
def build_nest(T, ctx):
    p = T["p"]
    b = ctx.bounds.get(T["id"]) or bounds(T, ctx)
    A, B = b["A"], b["B"]
    L = Layout(T, ctx, A, B, fixed_B=True)
    n = Nest(L, ctx)
    w0, w1, tx = T["w0"], T["w1"], L.tx
    asid, bsid = T["a"]["id"], T["b"]["id"]
    act = ctx.act_of(L.fsid)
    tint = ctx.palette(act)["leak"]
    # cards: push -> A's home card gets the region material, B's copy behind; pull -> B's copy (with the region) in front
    depthB = float(T["b"].get("move", {}).get("depth", 0.0) or 0.0)
    if L.push:
        front = ctx.card(asid)
        mat = cards.card_material(f"m_nestF_{T['id']}", ctx.plate_image(asid), extension="MIRROR", tile_tint=tint,
                                  region_img=L.region_img)
        front.data.materials.clear()
        front.data.materials.append(mat)
        back = ctx.make_card(bsid, f"nestK_{T['id']}", matrix=n.MK, depth=depthB, tile=3,
                             frames=(int(math.floor(L.t_r)) - 2, w1 + 1), tile_fade=0.05)  # B framed small: no mirror reads
    else:
        front = ctx.make_card(bsid, f"nestF_{T['id']}", matrix=n.MF, depth=depthB, tile=3,
                              frames=(int(math.floor(tx)) - 1, w1 + 1), region=L.region_img)
        back = ctx.card(asid)
        mat = front.active_material
        # A (the back) shrinks below the frame: its mirror tiles fade into the haze fast while the window runs
        tfn = back.active_material.node_tree.nodes.get("TileFade") if back.active_material else None
        if tfn is not None:
            v = tfn.outputs[0]
            for f, val in ((w0 - 1, 0.22), (w0 + 1, 0.05), (w1, 0.05), (w1 + 1, 0.22)):
                v.default_value = val
                v.keyframe_insert("default_value", frame=f)
    n.front, n.back = front, back
    front["amv3_region_area"] = float(L.info_r["area"])
    zs = [n.z(w0 + 0.25 * i) for i in range(int((min(w1, tx + 3) - w0) * 4))]  # the end may turn into the next hold
    if any(b2 > a2 + 1e-6 for a2, b2 in zip(zs, zs[1:])) if L.push else any(b2 < a2 - 1e-6 for a2, b2 in zip(zs, zs[1:])):
        ctx.log(f"  WARN nest {T['id']}: the dolly doubles back inside the window")
    # the reveal: opacity of the front card inside the region, feather scaled with the region's size on screen
    nt = mat.node_tree
    op = nt.nodes["RegOp"].outputs[0]
    rw = nt.nodes["RegW"].outputs[0]
    f_lo = int(math.floor(L.t_r)) - 2 if L.push else int(math.floor(tx)) - 1
    f_hi = int(math.ceil(tx)) + 2 if L.push else min(w1, int(math.ceil(L.t_r)) + 2)
    for f in range(f_lo, f_hi + 1):
        if L.push:
            o = 1.0 - cl.smoothstep((f - L.t_r) / L.dur)
        else:
            o = cl.smoothstep((f - (L.t_r - L.dur)) / L.dur)
        z = n.z(f)
        sF = F / z if z > 1e-3 else 50.0
        fs = max(3.0, min(12.0, 0.06 * L.eq_diam * sF))
        op.default_value = o
        op.keyframe_insert("default_value", frame=f)
        rw.default_value = regions.feather_w(fs / sF, L.meta)
        rw.keyframe_insert("default_value", frame=f)
    if L.push:
        op.default_value = 1.0
        op.keyframe_insert("default_value", frame=w1 + 1)  # A's home card is whole again once the camera has left
    # camera: one path on [w0, w1), then the copy -> B's home card teleport (identical relative pose)
    th = w1 - 0.5
    ctx.teleport(th)
    ctx.seamless.add(th)  # copy -> home card, identical relative pose: the gate measures straight through it
    ctx.key_path(n.pose, w0, w1, 0.25)
    cardB = ctx.card(bsid)
    eps = ctx.EPS
    post = lambda t: ctx.pose(cardB, B.at(t - w1))  # noqa: E731
    l0, r0 = post(th + eps)
    l1, r1 = post(th + eps + 0.05)
    ctx.key_cam(th + eps, l0, r0, ahead=(l1, r1, None, 0.05))
    # DOF
    fs = float(p.get("fstop", DEF["fstop"]))
    t = math.floor((L.t_r - 5) * 4) / 4.0 if L.push else math.floor((tx - 3) * 4) / 4.0
    t_end = w1 - 0.5 - 0.25
    while t <= t_end + 1e-6:
        z = n.z(t)
        dK = max(0.05, z + n.D)
        if L.push:
            u = cl.smoothstep((t - (L.t_r - 5)) / 4.0) * (1 - cl.smoothstep((t - (tx + 1)) / 4.0))
            focus = dK
        else:
            u = cl.smoothstep((t - (tx - 2)) / 2.0) * (1 - cl.smoothstep((t - (tx + 4)) / 3.0))
            rk = cl.smoothstep((t - (tx + 0.5)) / 3.5)
            focus = dK + (max(0.05, z) - dK) * rk
        N = 1.0 / (1.0 / cl.FSTOP_SHARP + (1.0 / fs - 1.0 / cl.FSTOP_SHARP) * u)
        ctx.key_dof(t, focus, N)
        t = round(t + 0.25, 4)
    c = L.curve
    ctx.log(f"  nest {T['id']} {n.mode} {L.kind}({L.fsid}) at {[round(v) for v in L.P]}: D {n.D:.3f} m  k {n.k:.3f}  "
            f"back {n.q:.2f}x at reveal f{L.t_r:.0f} -> land {n.land:.2f}x at f{tx}  attack x{(c.g or 0):.2f}/f ({c.mode})  "
            f"speed {c.Va:.3f}|{abs(c(tx + 0.01)[1]):.3f} d ln s_K/f  decay x{c.decay():.2f}/f  phi {n.phi:+.1f}  "
            f"roll {n.rA_end:+.1f}|{n.rB_start:+.1f}")
    return n


def build(T, ctx):
    ctx.nest(T)
