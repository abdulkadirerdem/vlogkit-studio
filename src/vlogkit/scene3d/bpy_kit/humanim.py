"""Acting for the realistic people: library animations on NLA strips (blended into each other), a
gesture layer on top for what the library lacks, and moves through the set.

- Library actions (Quaternius UAL and Mesh2Motion, both CC0): idle, talk, walk, run, jog, sneak,
  jump, sit, dance, fall, hit, pickup, push, roll, punch, swim, drive, crouch, interact, fix, and
  nod, yes, no, clap, confused, angry, fold_arms, listen, greet, wave, cheer, phone, sleep, lie,
  sit_ground, cry, pray, tired, shiver, knock, open_door, dizzy, kneel, sit_write, texting...
- Every person idles in their own way: an idle picked from a pool per person, started at their
  own point in it, so a group never moves in step; under everything a "life" layer breathes,
  shifts the weight and looks around.
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
    # Mesh2Motion's sitting clips: their seat height is measured (the runtime lifts the person
    # onto a bed or a sofa instead of sinking the legs into it)
    "sit": (["sitting-enter", "sitting-idle"], False),
    "sit_talk": (["sitting-talking"], True),
    "stand_up": (["sitting-exit"], False),
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
    # Mesh2Motion (CC0): the clips the gestures used to fake, and many the kit lacked
    "nod": (["head-nod"], False),
    "yes": (["yes"], False),
    "no": (["reject"], False),
    "clap": (["clapping"], True),
    "confused": (["confused"], False),
    "angry": (["angry"], False),
    "fold_arms": (["idle-foldarms"], True),
    "listen": (["idle-listening"], True),
    "greet": (["greeting"], False),
    "wave": (["greeting"], False),
    # real recordings for what used to be computed arm poses (a pose snapped in and held still
    # read as a robot): startled step back, shiver, slumped, puzzled, a fist pump without a jump
    "cheer": (["victory-fist-pump"], False),
    "shock": (["dodge-back"], False),
    "scared": (["shiver"], True),
    "sad": (["tired-hunched"], True),
    "shrug": (["confused"], False),
    "arms_up": (["victory"], False),
    "victory": (["victory-fist-pump"], False),
    "phone": (["idle-talkingphone"], True),
    "texting": (["texting-walk"], True),
    "sleep": (["sleeping"], True),
    "lie": (["sleeping"], True),
    "sit_ground": (["sit-ground-idle"], True),
    "cry": (["sit-ground-crying"], True),
    "sit_write": (["sitting-writing"], True),
    "pray": (["pray"], True),
    "tired": (["tired-hunched"], True),
    "shiver": (["shiver"], True),
    "knock": (["knock"], False),
    "open_door": (["open-door"], False),
    "dizzy": (["dizzy"], True),
    "kneel": (["kneel"], True),
    "meditate": (["meditate"], True),
    "sing": (["singing"], True),
    "walk_happy": (["walk-happy"], True),
    "walk_tired": (["walk-injured"], True),
}
# idles a person may stand in: picked per person, so two people never stand alike
# (Quaternius' Idle_Loop, a wide game-ready stance, only when nothing else is there)
IDLES = ["idle-subtle", "idle-a", "idle-listening"]
TALKS = ["idle-talking", "Idle_Talking_Loop"]
SEATED = ("sit", "sit_talk", "sit_write", "stand_up", "lie", "sleep")
SPEED = {
    "walk": 1.35,
    "walk_formal": 1.25,
    "walk_happy": 1.4,
    "walk_tired": 0.9,
    "texting": 1.1,
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
    "give": {"upperarm_r": (0.1, 1.0, -0.25), "lowerarm_r": (0.0, 1.0, 0.05)},
    "dodge": {"upperarm_s": (0.35, 0.7, 0.35), "lowerarm_s": (-0.3, 0.3, 0.9)},
    "fly": {"upperarm_s": (0.12, 0.55, 0.85), "lowerarm_s": (0.05, 0.4, 0.95)},
}


PREFIXES = ("ual_", "m2m_")  # the Quaternius bodies' clips; MakeHuman people use "mp_"


def _clip(name: str, prefixes: tuple = PREFIXES) -> bpy.types.Action:
    for pre in prefixes:
        a = bpy.data.actions.get(pre + name)
        if a is not None:
            return a
    raise ValueError(f"kütüphanede animasyon yok: {name}")


def has_clip(name: str, prefixes: tuple = PREFIXES) -> bool:
    return any(bpy.data.actions.get(pre + name) for pre in prefixes)


def bone(arm, name: str):
    """A pose bone by name, whatever its case ("Head" on one rig, "head" on the other)."""
    pb = arm.pose.bones.get(name)
    if pb is None:
        low = name.lower()
        pb = next((b for b in arm.pose.bones if b.name.lower() == low), None)
    return pb


def _seed(name: str) -> int:
    return sum(ord(c) * (i + 7) for i, c in enumerate(name))


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
        self.blend = max(3, round(0.3 * fps))  # clip to clip: a person never snaps
        self._last_end = 1
        self.mp = bool(self.arm.get("vk_mpfb"))
        self.pre = ("mp_",) if self.mp else PREFIXES
        seed = _seed(person.name)
        pool = [n for n in IDLES if has_clip(n, self.pre)] or ["Idle_Loop"]
        self.idle = pool[seed % len(pool)]
        talks = [n for n in TALKS if has_clip(n, self.pre)] or ["Idle_Talking_Loop"]
        self.talk = talks[seed % len(talks)]
        self.phase = (seed % 97) / 97.0  # where in the idle this person starts

    # ---- base clips
    def _free(self, f: float) -> float:
        """The first frame from `f` the base track has room for (strips may not overlap)."""
        ends = [s.frame_end for s in self.base.strips]
        return max([f, *ends]) if ends and max(ends) > f else f

    def _pad(self, f: float) -> None:
        """Idle from the end of the track up to frame f. Strips are laid down in time order, so
        there is always room after the last one (Blender will not slide a strip into a gap)."""
        ends = [s.frame_end for s in self.base.strips]
        end = math.ceil(max(ends) - 1e-6) if ends else 1
        want = math.floor(f) - end
        if want < 1:
            return
        idle = _clip(self.idle, self.pre)
        length = _frames(idle)
        a0 = idle.frame_range[0]
        # this person's own point in the loop (a crowd standing in step looks like a machine)
        off = round(self.phase * length) if end <= 1 else 0
        if off and want > 2:
            first = int(min(want, length - off))  # whole frames: strips.new takes an int start
            st = self.base.strips.new(f"idle.{end}", end, idle)
            st.action_frame_start, st.action_frame_end = a0 + off, a0 + off + first
            st.extrapolation = "HOLD_FORWARD"
            end, want = end + first, want - first
            if want < 1:
                return
        st = self.base.strips.new(f"idle.{end}", end, idle)
        if want >= length:
            st.repeat = want / length
        else:
            st.action_frame_end = a0 + want
        st.extrapolation = "HOLD_FORWARD"
        st.blend_in = min(self.blend, want // 2) if end > 1 else 0

    def clip(self, action: str, f0: int, f1: int, speed: float = 1.0) -> None:
        if action == "idle":
            clips, loops = [self.idle], True
        elif action == "talk":
            clips, loops = [self.talk], True
        else:
            clips, loops = LIB.get(action, ([self.idle], True))
        clips = [c for c in clips if has_clip(c, self.pre)] or [self.idle]
        self._pad(f0)
        f = float(self._free(f0))
        for i, name in enumerate(clips):
            a = _clip(name, self.pre)
            length = _frames(a) / max(0.3, speed)
            last = i == len(clips) - 1
            span = (f1 - f) if (last and loops) or (last and name.endswith("_Loop")) else length
            if action == "jump" and name == "Jump_Loop":  # the time in the air
                span = max(
                    4.0,
                    (f1 - f0)
                    - _frames(_clip("Jump_Start", self.pre))
                    - _frames(_clip("Jump_Land", self.pre)),
                )
            if action == "sit" and name in ("Sitting_Idle_Loop", "sitting-idle"):
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
        """Idle after the last clip to the end of the shot (gaps before clips are padded as the
        clips are laid down)."""
        if not self.base.strips:
            self._pad(1)
            if not self.base.strips:  # nothing at all: idle the whole beat
                idle = _clip(self.idle, self.pre)
                st = self.base.strips.new("idle.1", 1, idle)
                st.repeat = max(1.0, self.n / _frames(idle))
                st.extrapolation = "HOLD_FORWARD"
                return
        self._pad(self.n + 1)

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
            flat = math.dist(a[:2], b[:2]) > 1e-3
            h = math.atan2(b[0] - a[0], -(b[1] - a[1])) if flat else self.arm.rotation_euler.z
            for f, pt in ((fa, a), (fb, b)):
                self.arm.location.x, self.arm.location.y = pt[0], pt[1]
                if len(pt) > 2:  # flying: the path has heights
                    self.arm.location.z = pt[2]
                self.arm.rotation_euler.z = h
                self.arm.keyframe_insert("location", frame=f)
                self.arm.keyframe_insert("rotation_euler", index=2, frame=f)

    def jump(self, f0: int, f1: int, height: float = 0.5) -> int:
        """A real jump: the take-off clip, a ballistic arc (air time from the height and g), the
        landing clip touching down on its first frame. Returns the frame it is over."""
        start, loop, land = (
            _clip("Jump_Start", self.pre),
            _clip("Jump_Loop", self.pre),
            _clip("Jump_Land", self.pre),
        )
        g = 9.81
        air = max(6, round(self.fps * 2 * math.sqrt(2 * height / g)))
        s_len, l_len = _frames(start), _frames(land)
        room = max(1, f1 - f0)
        k = min(
            1.0, max(0.6, (room - air) / (s_len + l_len))
        )  # a short beat plays the clips faster
        self._pad(f0)
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

    # ---- life: breathing, weight shifting, looking around (under everything, added on top)
    def life(self) -> None:
        """A layer that never stops: the chest rises and falls (~4 s), the weight shifts from
        foot to foot (~8 s), the head turns to look somewhere now and then. Combined (quaternion
        product) with whatever the clips do, so it rides on idles, talks and sits alike."""
        import random

        from mathutils import Quaternion

        pose = self.arm.pose.bones
        bones = self.arm.data.bones
        head = bone(self.arm, "Head")
        if head is None or not all(
            b in pose for b in ("spine_02", "spine_03", "pelvis", "neck_01")
        ):
            return
        hn = head.name
        left, fwd, up = self._basis()
        rng = random.Random(_seed(self.p.name) * 13 + 5)
        fps = self.fps

        def local(bone: str, axis, deg: float) -> Quaternion:
            rest = bones[bone].matrix_local.to_quaternion()
            return Quaternion(rest.inverted() @ axis, math.radians(deg))

        breath_t = rng.uniform(3.6, 4.6) * fps
        sway_t = rng.uniform(7.0, 9.5) * fps
        ph1, ph2 = rng.uniform(0, math.tau), rng.uniform(0, math.tau)
        # where the eyes go: a hold every 1.5-4 s, a quick turn between
        looks, f = [], 1.0
        while f < self.n + fps:
            looks.append((f, rng.uniform(-11, 11), rng.uniform(-4, 3)))
            f += rng.uniform(1.5, 4.0) * fps

        def look_at(fr: float) -> tuple[float, float]:
            prev = looks[0]
            for k in looks:
                if k[0] > fr:
                    turn = 0.55 * fps
                    u = min(1.0, max(0.0, (fr - (k[0] - turn)) / turn))
                    u = u * u * (3 - 2 * u)
                    return prev[1] + (k[1] - prev[1]) * u, prev[2] + (k[2] - prev[2]) * u
                prev = k
            return prev[1], prev[2]

        act = bpy.data.actions.new(f"{self.p.name}.life")
        ad = self.arm.animation_data
        keep = ad.action
        ad.action = act
        step = max(2, round(fps / 6))
        rows: dict[tuple[str, int], list[float]] = {}
        for fr in range(1, self.n + 2, step):
            b = math.sin(math.tau * fr / breath_t + ph1)
            s = math.sin(math.tau * fr / sway_t + ph2)
            yaw, pitch = look_at(fr)
            q = {
                "spine_02": local("spine_02", left, 0.9 * b),
                "spine_03": local("spine_03", left, 1.3 * b),
                "pelvis": local("pelvis", up, 1.6 * s) @ local("pelvis", fwd, 0.8 * s),
                "spine_01": local("spine_01", fwd, -0.8 * s),
                "neck_01": local("neck_01", up, 0.4 * yaw) @ local("neck_01", left, 0.4 * pitch),
                hn: local(hn, up, 0.6 * yaw) @ local(hn, left, 0.6 * pitch),
            }
            for bn, qq in q.items():
                for i in range(4):
                    rows.setdefault((bn, i), []).extend((fr, qq[i]))
        for (bn, i), co in rows.items():
            fc = act.fcurve_ensure_for_datablock(
                self.arm, f'pose.bones["{bn}"].rotation_quaternion', index=i
            )
            fc.keyframe_points.add(len(co) // 2)
            fc.keyframe_points.foreach_set("co", co)
            fc.update()
        ad.action = keep
        tr = ad.nla_tracks.new()
        tr.name = "life"
        st = tr.strips.new("life", 1, act)
        if hasattr(st, "action_slot") and act.slots:
            st.action_slot = act.slots[0]
        st.blend_type = "COMBINE"
        st.extrapolation = "HOLD"

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
            ramp = max(2, min(round(0.45 * self.fps), (f1 - f0) // 3))
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
                        q = pb.rotation_quaternion.copy()
                        if q.w < 0:  # one side, like the clips (opposite signs blend the long way)
                            q.negate()
                        keys.append((bn, f, tuple(q)))
        # 2) write: Blender only keys a layer it can see (a 0-influence REPLACE layer refuses)
        ad.action_influence = 1.0
        for bn, f, q in keys:
            pb = pose[bn]
            pb.rotation_quaternion = q
            pb.keyframe_insert("rotation_quaternion", frame=f)
        slot = act.slots[0] if hasattr(ad, "action_slot") and act.slots else None
        # 3) play: each gesture is a window of that action on a top NLA track, faded in and out by
        # the strip itself (an action cannot animate its own influence), nothing outside it
        ad.action = None
        ad.action_influence = 1.0
        tracks: list = []
        for f0, f1, ramp in sorted(ramps):
            end = min(self.n + 1, f1 + ramp)
            tr = next((t for t in tracks if all(s.frame_end <= f0 for s in t.strips)), None)
            if tr is None:
                tr = ad.nla_tracks.new()
                tr.name = f"gestures{len(tracks)}"
                tracks.append(tr)
            far = round(max([s.frame_end for s in tr.strips] + [self.n + 10]) + 10)
            st = tr.strips.new(f"g.{f0}", far, act)
            if slot is not None and hasattr(st, "action_slot"):
                st.action_slot = slot
            st.use_sync_length = False
            st.action_frame_start = f0
            st.action_frame_end = max(f0 + 2, end)
            st.frame_start_ui = f0
            st.blend_type = "REPLACE"
            st.extrapolation = "NOTHING"
            st.blend_in = min(ramp, (end - f0) // 2)
            st.blend_out = min(ramp, (end - f0) // 2)
        sc.frame_set(1)

    # ---- face: MakeHuman people have ARKit face units and visemes as shape keys
    def _keyed(self):
        return [o for o in self.p.parts if o.type == "MESH" and o.data.shape_keys]

    def keys(self, values: dict, f: int, ease: int = 0) -> None:
        """Set face shape keys (every part that has them: face, brows, lashes, teeth...) at f,
        holding the previous values until f - ease."""
        for o in self._keyed():
            kb = o.data.shape_keys.key_blocks
            for name, v in values.items():
                k = kb.get(name)
                if k is None:
                    continue
                if ease and f - ease > 1:
                    k.keyframe_insert("value", frame=f - ease)
                k.value = float(v)
                k.keyframe_insert("value", frame=f)

    def expression(self, expr: str, f: int) -> None:
        want = EXPRESSIONS.get(expr, {})
        values = {k: want.get(k, 0.0) for k in EXPR_KEYS}
        self.keys(values, f, ease=round(0.15 * self.fps) if f > 1 else 0)

    def blinks(self) -> None:
        """A blink every 2-6 s (0.15 s), at this person's own times."""
        import random

        rng = random.Random(_seed(self.p.name) * 7 + 1)
        f = rng.uniform(0.5, 2.0) * self.fps
        while f < self.n:
            a = round(f)
            shut = a + max(1, round(0.06 * self.fps))
            opened = shut + max(1, round(0.09 * self.fps))
            for fr, v in ((a, 0.0), (shut, 1.0), (opened, 0.0)):
                self.keys({"eyeBlinkLeft": v, "eyeBlinkRight": v}, fr)
            f += rng.uniform(2.0, 6.0) * self.fps

    def talk(self, windows: list) -> None:
        """The mouth moving while this person speaks: open-close syllables (~6 a second), each
        a different mouth shape made of ARKit face units (open, round, wide, closed)."""
        import random

        rng = random.Random(_seed(self.p.name) * 3 + 2)
        shapes = [  # a syllable: jaw opening + lips
            {"jawOpen": 0.32, "mouthLowerDownLeft": 0.3, "mouthLowerDownRight": 0.3},  # a
            {"jawOpen": 0.18, "mouthStretchLeft": 0.35, "mouthStretchRight": 0.35},  # e, i
            {"jawOpen": 0.22, "mouthFunnel": 0.55},  # o
            {"jawOpen": 0.1, "mouthPucker": 0.6},  # u, ü
            {
                "jawOpen": 0.05,
                "mouthClose": 0.3,
                "mouthPressLeft": 0.3,
                "mouthPressRight": 0.3,
            },  # m, b, p
            {"jawOpen": 0.14, "mouthUpperUpLeft": 0.3, "mouthUpperUpRight": 0.3},  # s, t, d
        ]
        names = sorted({k for sh in shapes for k in sh})
        rest = dict.fromkeys(names, 0.0)
        for t0, t1 in windows:
            f, end = 1 + t0 * self.fps, 1 + t1 * self.fps
            self.keys(rest, max(1, round(f)))
            while f < end - 0.1 * self.fps:
                sh = rng.choice(shapes)
                k = rng.uniform(0.7, 1.15)
                self.keys({**rest, **{n: v * k for n, v in sh.items()}}, round(f + 0.06 * self.fps))
                f += rng.uniform(0.12, 0.19) * self.fps
            self.keys(rest, round(end))

    # ---- face (the Quaternius heads have no face rig: brows and eyes carry the expression)
    def face(self, expr: str, f: int) -> None:
        if self.mp:
            self.expression(expr, f)
            return
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


# ARKit face units per expression of the kit (MakeHuman people)
EXPRESSIONS = {
    "happy": {"mouthSmileLeft": 0.55, "mouthSmileRight": 0.55, "cheekSquintLeft": 0.25, "cheekSquintRight": 0.25},
    "grin": {"mouthSmileLeft": 0.85, "mouthSmileRight": 0.85, "cheekSquintLeft": 0.45, "cheekSquintRight": 0.45,
             "eyeSquintLeft": 0.25, "eyeSquintRight": 0.25},
    "shock": {"jawOpen": 0.35, "eyeWideLeft": 0.8, "eyeWideRight": 0.8, "browInnerUp": 0.8,
              "browOuterUpLeft": 0.6, "browOuterUpRight": 0.6, "mouthFunnel": 0.2},
    "surprised": {"jawOpen": 0.2, "eyeWideLeft": 0.55, "eyeWideRight": 0.55, "browInnerUp": 0.6,
                  "browOuterUpLeft": 0.45, "browOuterUpRight": 0.45},
    "sad": {"mouthFrownLeft": 0.6, "mouthFrownRight": 0.6, "browInnerUp": 0.65, "eyeSquintLeft": 0.15,
            "eyeSquintRight": 0.15, "mouthPressLeft": 0.2, "mouthPressRight": 0.2},
    "angry": {"browDownLeft": 0.8, "browDownRight": 0.8, "noseSneerLeft": 0.35, "noseSneerRight": 0.35,
              "mouthPressLeft": 0.4, "mouthPressRight": 0.4, "eyeSquintLeft": 0.3, "eyeSquintRight": 0.3},
    "scared": {"eyeWideLeft": 0.65, "eyeWideRight": 0.65, "browInnerUp": 0.85, "mouthStretchLeft": 0.45,
               "mouthStretchRight": 0.45, "jawOpen": 0.12},
    "confused": {"browInnerUp": 0.35, "browDownRight": 0.45, "mouthLeft": 0.3, "eyeSquintRight": 0.2},
    "smug": {"mouthSmileLeft": 0.55, "browOuterUpLeft": 0.3, "eyeSquintLeft": 0.2},
    "talk": {},
    "neutral": {},
}  # fmt: skip
EXPR_KEYS = sorted({k for v in EXPRESSIONS.values() for k in v})


def perform(person, actor: dict, fps: float, n: int) -> Performer:
    """Turn the plan's actor entry into a performance."""
    pf = Performer(person, fps, n)
    acts = sorted(actor.get("acts", []), key=lambda a: a["t0"])
    for a in acts:
        f0 = 1 + round(a["t0"] * fps)
        f1 = min(n + 1, max(f0 + 2, 1 + round(a["t1"] * fps)))
        do = a["do"]
        if do in (
            "walk",
            "run",
            "jog",
            "sneak",
            "walk_formal",
            "walk_happy",
            "walk_tired",
            "texting",
        ) and a.get("path"):
            pf.move(a["path"], f0, f1, do)
        elif do == "fly":
            path = a.get("path") or [
                [*actor.get("at", [0, 0])[:2], 0],
                [*actor.get("at", [0, 0])[:2], 3],
            ]
            pf.move(path, f0, f1, "float")
            pf.gesture("fly", f0, f1)
        elif do == "jump":
            pf.jump(f0, f1, float(a.get("height", 0.5)))
        elif do in LIB:
            pf.clip(do, f0, f1)
        elif do in GESTURES:
            pf.clip("talk" if actor.get("talk") else "idle", f0, f1)
            pf.gesture(do, f0, f1)
            if do == "dodge":  # a step back, away from what comes
                h = pf.arm.rotation_euler.z
                back = (-math.sin(h) * 0.35, math.cos(h) * 0.35)
                x, y = pf.arm.location.x, pf.arm.location.y
                for f, k in ((f0, 0.0), (min(f1, f0 + round(0.35 * fps)), 1.0)):
                    pf.arm.location.x, pf.arm.location.y = x + back[0] * k, y + back[1] * k
                    pf.arm.keyframe_insert("location", index=0, frame=f)
                    pf.arm.keyframe_insert("location", index=1, frame=f)
        else:
            pf.clip("idle", f0, f1)
    if actor.get("talk") and not acts:
        pf.clip("talk", 1, n + 1)
    pf.fill_idle()
    pf.life()
    pf.bake_gestures()
    if pf.mp:
        pf.blinks()
        talk = actor.get("talk")
        if isinstance(talk, list) and talk:
            pf.talk([tuple(w) for w in talk])
    pf.face(actor.get("face", "neutral"), 1)
    for fc in actor.get("faces", []):
        pf.face(fc["face"], 1 + round(fc["t"] * fps))
    return pf
