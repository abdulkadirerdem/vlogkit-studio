"""Acting for the realistic people: library animations on NLA strips (blended into each other), a
gesture layer on top for what the library lacks, and moves through the set.

- Library actions (Quaternius UAL, mocap-quality loops): idle, talk, walk, run, jog, sneak, jump,
  sit, dance, fall, hit, pickup, push, roll, punch, swim, drive, crouch, interact, fix.
- Gestures (computed): wave, point, point_up, shock, arms_up, cheer, shrug, facepalm, think,
  flex, hands_hips, scared, hold, phone, sad. Each arm bone is aimed at a direction given in the
  character's own frame (outward, forward, up), on a REPLACE layer whose influence fades in and
  out, so the body underneath keeps breathing and shifting its weight.
"""

from __future__ import annotations

import itertools
import math

import bpy
from mathutils import Vector

R = math.radians
LIB = {  # action -> (library clips in order, loops?)
    "idle": (["Idle_Loop"], True),
    "talk": (["Idle_Talking_Loop"], True),
    "walk": (["Walk_Loop"], True),
    "walk_formal": (["Walk_Formal_Loop"], True),
    "jog": (["Jog_Fwd_Loop"], True),
    "run": (["Sprint_Loop"], True),
    "sneak": (["Crouch_Fwd_Loop"], True),
    "crouch": (["Crouch_Idle_Loop"], True),
    "jump": (["Jump_Start", "Jump_Loop", "Jump_Land"], False),
    "sit": (["Sitting_Enter", "Sitting_Idle_Loop"], False),
    "sit_talk": (["Sitting_Talking_Loop"], True),
    "stand_up": (["Sitting_Exit"], False),
    "dance": (["Dance_Loop"], True),
    "fall": (["Death01"], False),
    "hit": (["Hit_Chest"], False),
    "hit_head": (["Hit_Head"], False),
    "pickup": (["PickUp_Table"], False),
    "push": (["Push_Loop"], True),
    "roll": (["Roll"], False),
    "punch": (["Punch_Cross"], False),
    "swim": (["Swim_Fwd_Loop"], True),
    "float": (["Swim_Idle_Loop"], True),
    "drive": (["Driving_Loop"], True),
    "interact": (["Interact"], False),
    "fix": (["Fixing_Kneeling"], False),
    "present": (["Spell_Simple_Enter", "Spell_Simple_Idle_Loop"], False),
}
SPEED = {
    "walk": 1.35,
    "walk_formal": 1.25,
    "jog": 3.0,
    "run": 5.5,
    "sneak": 0.9,
    "swim": 1.0,
}  # m/s

# gestures: bone -> (outward, forward, up) direction; "_s" = the side's own arm (mirrored)
GESTURES = {
    "arms_up": {"upperarm_s": (0.3, 0.0, 1.0), "lowerarm_s": (0.15, 0.05, 1.0)},
    "cheer": {"upperarm_s": (0.7, 0.1, 0.75), "lowerarm_s": (0.15, 0.1, 1.0)},
    "shock": {"upperarm_s": (0.85, 0.25, 0.1), "lowerarm_s": (0.35, 0.45, 0.85)},
    "scared": {"upperarm_s": (0.25, 0.75, -0.25), "lowerarm_s": (-0.45, 0.45, 0.8)},
    "shrug": {"upperarm_s": (0.35, 0.2, -0.9), "lowerarm_s": (0.85, 0.5, 0.15)},
    "flex": {"upperarm_s": (1.0, 0.0, 0.08), "lowerarm_s": (0.1, 0.1, 1.0)},
    "hands_hips": {"upperarm_s": (0.65, -0.15, -0.65), "lowerarm_s": (-0.75, 0.15, 0.1)},
    "hold": {"upperarm_s": (0.15, 0.55, -0.8), "lowerarm_s": (-0.1, 1.0, 0.15)},
    "point": {"upperarm_r": (0.12, 1.0, 0.08), "lowerarm_r": (0.05, 1.0, 0.1)},
    "point_up": {"upperarm_r": (0.25, 0.3, 1.0), "lowerarm_r": (0.05, 0.1, 1.0)},
    "wave": {"upperarm_r": (0.75, 0.15, 0.6), "lowerarm_r": (0.15, 0.15, 1.0)},
    "facepalm": {"upperarm_r": (0.15, 0.75, -0.35), "lowerarm_r": (-0.35, 0.35, 0.9)},
    "think": {"upperarm_r": (0.15, 0.55, -0.8), "lowerarm_r": (-0.35, 0.45, 0.85)},
    "phone": {
        "upperarm_r": (0.2, 0.45, -0.85),
        "lowerarm_r": (-0.2, 0.85, 0.5),
        "upperarm_l": (0.2, 0.45, -0.85),
        "lowerarm_l": (0.2, 0.85, 0.5),
    },
    "sad": {"upperarm_s": (0.05, 0.05, -1.0), "lowerarm_s": (0.0, 0.1, -1.0)},
}


def _clip(name: str) -> bpy.types.Action:
    a = bpy.data.actions.get("ual_" + name)
    if a is None:
        raise ValueError(f"kütüphanede animasyon yok: {name}")
    return a


def _frames(a: bpy.types.Action) -> float:
    s, e = a.frame_range
    return max(1.0, e - s)


class Performer:
    """Lays out a person's performance for one shot: base clips, gestures, moves."""

    def __init__(self, person, fps: float, n: int):
        self.p, self.fps, self.n = person, fps, n
        self.arm = person.root
        ad = self.arm.animation_data_create()
        ad.action = None
        self.base = ad.nla_tracks.new()
        self.base.name = "base"
        self.layers: list[tuple[int, int, str]] = []
        self.blend = max(3, round(0.18 * fps))
        self._last_end = 1

    # ---- base clips
    def _free(self, f: float) -> float:
        """The first frame from `f` the base track has room for (strips may not overlap)."""
        ends = [s.frame_end for s in self.base.strips]
        return max([f, *ends]) if ends and max(ends) > f else f

    def clip(self, action: str, f0: int, f1: int, speed: float = 1.0) -> None:
        clips, loops = LIB.get(action, LIB["idle"])
        f = float(self._free(f0))
        for i, name in enumerate(clips):
            a = _clip(name)
            length = _frames(a) / max(0.3, speed)
            last = i == len(clips) - 1
            span = (f1 - f) if (last and loops) or (last and name.endswith("_Loop")) else length
            if action == "jump" and name == "Jump_Loop":  # the time in the air
                span = max(
                    4.0, (f1 - f0) - _frames(_clip("Jump_Start")) - _frames(_clip("Jump_Land"))
                )
            if action == "sit" and name == "Sitting_Idle_Loop":
                span = max(4.0, f1 - f)
            span = max(2.0, min(span, f1 - f)) if f < f1 else 0
            if span <= 0:
                break
            f = float(round(f + 0.499))  # whole frames, never before the previous strip's end
            st = self.base.strips.new(f"{name}.{round(f)}", round(f), a)
            st.scale = 1.0 / max(0.3, speed)
            loop_len = _frames(a) * st.scale
            if span >= loop_len and (name.endswith("_Loop") or loops):
                st.repeat = span / loop_len
            elif span < loop_len - 0.01:  # shorter than one pass: play the start of the clip
                st.action_frame_end = a.frame_range[0] + span / st.scale
            st.blend_in = min(self.blend, st.frame_end - st.frame_start - 1) if round(f) > 1 else 0
            st.blend_out = 0
            st.use_auto_blend = False
            st.extrapolation = "HOLD_FORWARD"
            f = st.frame_end
        self._last_end = max(self._last_end, round(f))

    def fill_idle(self) -> None:
        """Every frame not covered by a clip idles (strips may not overlap on one track)."""
        strips = sorted(self.base.strips, key=lambda s: s.frame_start)
        gaps, t = [], 1.0
        for s in strips:
            if s.frame_start - t > 1:
                gaps.append((t, s.frame_start))
            t = max(t, s.frame_end)
        if self.n + 1 - t > 1:
            gaps.append((t, self.n + 1))
        for a, b in gaps:
            a = math.ceil(a - 1e-6)
            if b - a < 1:
                continue
            idle = _clip("Idle_Loop")
            st = self.base.strips.new(f"idle.{a}", a, idle)
            st.repeat = max(1.0, (b - a) / _frames(idle))
            st.frame_end = b
            st.extrapolation = "HOLD_FORWARD"
            st.blend_in = min(self.blend, (b - a) // 2) if a > 1 else 0

    # ---- moves
    def move(self, path: list, f0: int, f1: int, kind: str) -> None:
        seg = [math.dist(a, b) for a, b in itertools.pairwise(path)]
        total = sum(seg) or 1.0
        need = total / max(1e-3, (f1 - f0) / self.fps)
        speed = max(0.6, min(1.7, need / SPEED.get(kind, 1.35)))
        self.clip(kind, f0, f1, speed)
        acc = 0.0
        for (a, b), d in zip(itertools.pairwise(path), seg, strict=True):
            fa = f0 + round((f1 - f0) * acc / total)
            acc += d
            fb = f0 + round((f1 - f0) * acc / total)
            h = math.atan2(b[0] - a[0], -(b[1] - a[1]))
            for f, pt in ((fa, a), (fb, b)):
                self.arm.location.x, self.arm.location.y = pt[0], pt[1]
                self.arm.rotation_euler.z = h
                self.arm.keyframe_insert("location", frame=f)
                self.arm.keyframe_insert("rotation_euler", index=2, frame=f)

    def jump(self, f0: int, f1: int, height: float = 0.5) -> int:
        """A real jump: the take-off clip, a ballistic arc (air time from the height and g), the
        landing clip touching down on its first frame. Returns the frame it is over."""
        start, loop, land = _clip("Jump_Start"), _clip("Jump_Loop"), _clip("Jump_Land")
        g = 9.81
        air = max(6, round(self.fps * 2 * math.sqrt(2 * height / g)))
        s_len, l_len = _frames(start), _frames(land)
        room = max(1, f1 - f0)
        k = min(
            1.0, max(0.6, (room - air) / (s_len + l_len))
        )  # a short beat plays the clips faster
        f0 = round(self._free(f0) + 0.499)
        t = float(f0)
        for a, length in ((start, s_len * k), (loop, float(air)), (land, l_len * k)):
            st = self.base.strips.new(f"{a.name}.{round(t)}", round(t), a)
            if a is loop:
                st.scale = 1.0
                st.repeat = max(0.1, length / _frames(a))
            else:
                st.scale = k
            st.blend_in = min(self.blend, 4) if a is start and round(t) > 1 else 0
            st.extrapolation = "HOLD_FORWARD"
            t = float(math.ceil(st.frame_end - 1e-6))
        take_off = round(f0 + s_len * k) - 1
        touch = take_off + air
        z0 = self.arm.location.z
        fc_frames = range(take_off, touch + 1)
        for f in fc_frames:
            u = (f - take_off) / max(1, touch - take_off)
            self.arm.location.z = z0 + 4 * height * u * (1 - u)
            self.arm.keyframe_insert("location", index=2, frame=f)
        self.arm.location.z = z0
        self.arm.keyframe_insert("location", index=2, frame=f0)
        self.arm.keyframe_insert("location", index=2, frame=round(t))
        # gravity has no ease: linear between the per-frame keys
        from .anim import _fcurves

        ad = self.arm.animation_data
        acts = [ad.action] if ad and ad.action else []
        for act in acts:
            for fc in _fcurves(act):
                if fc.data_path == "location" and fc.array_index == 2:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "LINEAR"
        self._last_end = max(self._last_end, round(t))
        return round(t)

    # ---- gestures
    def gesture(self, name: str, f0: int, f1: int) -> None:
        if name in GESTURES:
            self.layers.append((f0, f1, name))

    def _basis(self):
        bones = self.arm.data.bones
        fwd = bones["ball_l"].tail_local - bones["foot_l"].head_local
        fwd = Vector((fwd.x, fwd.y, fwd.z))
        up = (bones["neck_01"].head_local - bones["pelvis"].head_local).normalized()
        fwd = (fwd - up * fwd.dot(up)).normalized()
        left = (bones["upperarm_l"].head_local - bones["upperarm_r"].head_local).normalized()
        return left, fwd, up

    def bake_gestures(self) -> None:
        if not self.layers:
            return
        ad = self.arm.animation_data
        moves = (
            ad.action
        )  # the body's own moves (path, jump arc): keep them on a track of their own
        if moves is not None:
            tr = ad.nla_tracks.new()
            tr.name = "moves"
            st = tr.strips.new("moves", int(moves.frame_range[0]), moves)
            st.extrapolation = "HOLD"
            st.blend_type = "REPLACE"
        act = bpy.data.actions.new(f"{self.p.name}.gestures")
        ad.action = act
        ad.action_blend_type = "REPLACE"
        left, fwd, up = self._basis()
        sc = bpy.context.scene
        pose = self.arm.pose.bones
        # 1) measure: with the layer off, aim each bone and read back its local rotation
        ad.action_influence = 0.0
        keys: list[tuple[str, int, tuple]] = []
        ramps: list[tuple[int, int, int]] = []
        for f0, f1, name in self.layers:
            spec = GESTURES[name]
            ramp = max(2, min(round(0.2 * self.fps), (f1 - f0) // 3))
            ramps.append((f0, f1, ramp))
            frames = (
                [f0 + ramp, f1 - 1]
                if name != "wave"
                else list(range(f0 + ramp, f1, max(3, round(self.fps * 0.22))))
            )
            for i, f in enumerate(frames):
                sc.frame_set(f)
                for raw, d in spec.items():
                    for sd in ("l", "r") if raw.endswith("_s") else (raw[-1],):
                        bn = raw[:-1] + sd
                        pb = pose.get(bn)
                        if pb is None:
                            continue
                        out, fw, u = d
                        if name == "wave" and bn.startswith("lowerarm"):
                            out += 0.45 if i % 2 else -0.25
                        sign = 1 if sd == "l" else -1
                        want = (left * out * sign + fwd * fw + up * u).normalized()
                        pb.rotation_mode = "QUATERNION"
                        m = pb.matrix.copy()
                        q = m.to_3x3().col[1].normalized().rotation_difference(want)
                        new = (q.to_matrix() @ m.to_3x3()).to_4x4()
                        new.translation = m.translation
                        pb.matrix = new
                        bpy.context.view_layer.update()
                        keys.append((bn, f, tuple(pb.rotation_quaternion)))
        # 2) write: Blender only keys a layer it can see (a 0-influence REPLACE layer refuses)
        ad.action_influence = 1.0
        for bn, f, q in keys:
            pb = pose[bn]
            pb.rotation_quaternion = q
            pb.keyframe_insert("rotation_quaternion", frame=f)
        for f0, f1, ramp in ramps:
            for f, v in ((f0, 0.0), (f0 + ramp, 1.0), (f1 - 1, 1.0), (min(self.n, f1 + ramp), 0.0)):
                ad.action_influence = v
                self.arm.keyframe_insert("animation_data.action_influence", frame=f)
        if ramps and ramps[0][0] > 1:
            ad.action_influence = 0.0
            self.arm.keyframe_insert("animation_data.action_influence", frame=1)
        if hasattr(ad, "action_slot") and act.slots:
            ad.action_slot = act.slots[0]
        sc.frame_set(1)

    # ---- face (the realistic heads have no face rig: brows and eyes carry the expression)
    def face(self, expr: str, f: int) -> None:
        brow = next((o for o in self.p.parts if o.name.endswith("Eyebrows")), None)
        eyes = next((o for o in self.p.parts if o.name.endswith("Eyes")), None)
        lift = {
            "shock": 0.012,
            "surprised": 0.009,
            "scared": 0.008,
            "sad": 0.004,
            "angry": -0.006,
            "confused": 0.005,
        }.get(expr, 0.0)
        big = {"shock": 1.12, "surprised": 1.08, "scared": 1.1}.get(expr, 1.0)
        if brow is not None:
            if "_z0" not in brow:
                brow["_z0"] = brow.location.z
            brow.location.z = brow["_z0"] + lift
            brow.keyframe_insert("location", index=2, frame=f)
        del eyes, big  # the eye mesh's origin is not in the eyes: scaling it moves them


def perform(person, actor: dict, fps: float, n: int) -> Performer:
    """Turn the plan's actor entry into a performance."""
    pf = Performer(person, fps, n)
    acts = sorted(actor.get("acts", []), key=lambda a: a["t0"])
    for a in acts:
        f0 = 1 + round(a["t0"] * fps)
        f1 = min(n + 1, max(f0 + 2, 1 + round(a["t1"] * fps)))
        do = a["do"]
        if do in ("walk", "run", "jog", "sneak", "walk_formal") and a.get("path"):
            pf.move(a["path"], f0, f1, do)
        elif do == "jump":
            pf.jump(f0, f1, float(a.get("height", 0.5)))
        elif do in LIB:
            pf.clip(do, f0, f1)
        elif do in GESTURES:
            pf.clip("talk" if actor.get("talk") else "idle", f0, f1)
            pf.gesture(do, f0, f1)
        else:
            pf.clip("idle", f0, f1)
    if actor.get("talk") and not acts:
        pf.clip("talk", 1, n + 1)
    pf.fill_idle()
    pf.bake_gestures()
    pf.face(actor.get("face", "neutral"), 1)
    for fc in actor.get("faces", []):
        pf.face(fc["face"], 1 + round(fc["t"] * fps))
    return pf
