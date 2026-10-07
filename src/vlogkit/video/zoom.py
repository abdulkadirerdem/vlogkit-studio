"""Animated zoom / reframing: `scale` with eval=frame followed by a fixed-size `crop`.

Rule: a zoom term must start and end *inside one shot* (use scene-cut times). A zoom that is still
running when the next shot starts shows up as a visible jump mid-shot.

ffmpeg's crop keeps the frame size it saw when the graph was configured (`iw`, and its x/y clamp)
even when scale hands it bigger frames later. So the scale is configured at the zoom's *peak* size
(`Zoom.peak`) and the crop position is computed from the current scaled size itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vlogkit.timecode import fmt
from vlogkit.video.expr import between, nan_safe, total, window


@dataclass
class Zoom:
    """z(t) = 1 + sum of windowed terms."""

    terms: list[str] = field(default_factory=list)
    amounts: list[float] = field(default_factory=list)  # each term's largest value

    def peak(self) -> float:
        """Upper bound of z(t): 1 + every term at its largest (constant terms parsed)."""
        consts = []
        for term in self.terms[: len(self.terms) - len(self.amounts)]:
            try:
                consts.append(max(0.0, float(term)))
            except ValueError:
                consts.append(1.0)  # unknown expression: assume up to 2x
        return 1.0 + sum(consts) + sum(max(0.0, a) for a in self.amounts)

    def push(self, t0: float, t1: float, amount: float) -> Zoom:
        """Slow push-in from 1.0 to 1+amount across the window."""
        self.terms.append(window(t0, t1, f"{fmt(amount)}*(t-{fmt(t0)})/{fmt(t1 - t0)}"))
        self.amounts.append(amount)
        return self

    def punch(
        self, t0: float, t1: float, amount: float, decay: float = 10.0, drift: float = 0.0
    ) -> Zoom:
        """Instant punch-in that eases back out (+ optional slow drift until t1)."""
        e = f"{fmt(amount)}*exp(-(t-{fmt(t0)})*{fmt(decay)})"
        if drift:
            e += f"+{fmt(drift)}*(t-{fmt(t0)})/{fmt(t1 - t0)}"
        self.terms.append(window(t0, t1, e))
        self.amounts.append(amount + max(0.0, drift))
        return self

    def snap(self, t0: float, t1: float, amount: float, speed: float = 45.0) -> Zoom:
        """Meme snap-zoom: jumps to 1+amount within ~2 frames and holds until t1."""
        self.terms.append(window(t0, t1, f"{fmt(amount)}*(1-exp(-(t-{fmt(t0)})*{fmt(speed)}))"))
        self.amounts.append(amount)
        return self

    def step(self, t0: float, t1: float, frm: float, to: float, speed: float = 18.0) -> Zoom:
        """From zoom offset `frm` to `to` with an exponential ease (speed 18: ~0.2 s), held until
        t1. Chain steps (a, b), (b, c), ... for "punch in, punch in more, back" camera moves:
        each starts where the previous one ended, so there is no dip at the boundary."""
        e = f"{fmt(frm)}+({fmt(to - frm)})*(1-exp(-(t-{fmt(t0)})*{fmt(speed)}))"
        self.terms.append(window(t0, t1, e))
        self.amounts.append(max(frm, to))
        return self

    def expr(self) -> str:
        return total("1", self.terms)


@dataclass
class Focus:
    """Where the crop is centred (0..1 of the scaled frame) plus pixel offsets (shake)."""

    fx: list[str] = field(default_factory=lambda: ["0.5"])
    fy: list[str] = field(default_factory=lambda: ["0.5"])
    dx: list[str] = field(default_factory=lambda: ["0"])
    dy: list[str] = field(default_factory=lambda: ["0"])

    def offset(self, t0: float, t1: float, dfx: float = 0.0, dfy: float = 0.0) -> Focus:
        """Move the crop centre by (dfx, dfy) during the window (e.g. to keep a face in frame)."""
        if dfx:
            self.fx.append(f"{fmt(dfx)}*{between(t0, t1)}")
        if dfy:
            self.fy.append(f"({fmt(dfy)})*{between(t0, t1)}")
        return self

    def shake(
        self, t0: float, t1: float, ax: float = 14, ay: float = 11, wx: float = 97, wy: float = 83
    ) -> Focus:
        self.dx.append(f"{fmt(ax)}*sin(t*{fmt(wx)})*{between(t0, t1)}")
        self.dy.append(f"{fmt(ay)}*cos(t*{fmt(wy)})*{between(t0, t1)}")
        return self

    @staticmethod
    def _join(parts: list[str]) -> str:
        return parts[0] if len(parts) == 1 else "+".join(parts)


def zoom_crop(zoom: Zoom | str, focus: Focus | None = None, w: int = 1080, h: int = 1920) -> str:
    """scale by z(t) then crop w x h around the focus point. NaN-safe for graph (re)config.

    The scale is configured at the peak zoom (a plain string zoom: at 2x) so the crop's clamp
    never binds; x/y are clipped against the *current* scaled size (`sw` x `sh`, same formula as
    the scale), keeping the crop inside the actual frame. `sh` follows the input's aspect like
    `h=-2`; the y range keeps 2 px back for its rounding.
    """
    peak = zoom.peak() if isinstance(zoom, Zoom) else 2.0
    z = zoom.expr() if isinstance(zoom, Zoom) else zoom
    f = focus or Focus()
    fx, fy = Focus._join(f.fx), Focus._join(f.fy)
    dx, dy = Focus._join(f.dx), Focus._join(f.dy)
    scale_w = f"2*trunc({w // 2}*{nan_safe(z, fmt(peak))})"
    sw = f"(2*trunc({w // 2}*({z})))"  # the scaled width at this frame (crop sees the same t)
    sh = f"({sw}*ih/iw)"  # crop's iw/ih: the peak-size frame, same aspect as every frame
    x = f"clip(({fx})*{sw}-{w // 2}+({dx}),0,{sw}-{w})"
    y = f"clip(({fy})*{sh}-{h // 2}+({dy}),0,max(0,{sh}-{h}-2))"
    return (
        f"scale=w='{scale_w}':h='2*trunc(ow*ih/iw/2)':eval=frame:flags=lanczos,"
        f"crop={w}:{h}:x='{nan_safe(x, f'(iw-{w})/2')}':y='{nan_safe(y, f'(ih-{h})/2')}'"
    )
