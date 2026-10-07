# vlogkit-vt

A small Swift command-line tool around Apple's VideoToolbox frame processors (VTFrameProcessor, macOS 26+ on Apple silicon):

- ML super resolution (4x),
- frame rate conversion,
- temporal noise filter,
- motion blur.

You don't build it by hand. `vlogkit.video.vt.ensure_built()` compiles `main.swift` into `build/bin/vlogkit-vt` on first use, and again whenever the source changes:

```
swiftc -O -swift-version 5 tools/vt/main.swift -o build/bin/vlogkit-vt
```

```
vlogkit-vt info
vlogkit-vt upscale     IN OUT [--scale 4] [--denoise] [--strength 0.5]
vlogkit-vt denoise     IN OUT [--strength 0.5]
vlogkit-vt interpolate IN OUT [--factor 2] [--slowmo]
vlogkit-vt motionblur  IN OUT [--blur 50]
```

The tool only handles video and writes a ProRes 422 HQ .mov. Use it from Python (`vlogkit.video.vt`), which takes care of three things:

- **Input:** it renders the input upright and starting at t=0.
- **Tone:** it corrects the small tone shift the super resolution model introduces.
- **Output:** it scales the result to the target size and puts the sound back.
