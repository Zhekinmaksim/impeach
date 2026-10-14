# Impeach presentation film

A 60-second English motion film in the project's green, graphite and red visual
identity. Output: 1920 × 1080, 30 fps, H.264 MP4 with stereo AAC music. No narration. The closing card links to https://impeach.click.

The soundtrack is **Onchain Verdict** by zhekinmaksim, supplied in
`/Users/zmaxx/Music/Onchain Verdict.mp3`. The film uses seconds 12–72, normalizes
the music to a target of −16 LUFS with a −1.5 dBTP ceiling, and fades both ends.
The original music file is not modified or uploaded.

The evidence scene uses the finalized snapshots in `web/case.json` and
`runs/v2-live-case.json`. The scripted memoriser has 24 recall matches and 13
admitted rewrite pairs. The real Llama trial has 23 of 24 pairs admitted and a
`CLEAN` ruling. The film explicitly labels the latter as a partial trial.

## Render

The renderer uses `@napi-rs/canvas`, FFmpeg, the repository's bundled fonts and
logos, and the system Georgia font for Greek symbols. It makes no network or
model requests. Set `MOTION_NODE_MODULES` to the directory containing
`@napi-rs/canvas` if not using the local Codex dependency bundle.

```sh
node video/render.mjs --preview
node video/render.mjs
```

Outputs are in `output/video/`: the final MP4, nine preview frames, a storyboard,
the timing/source manifest and layout checks. The soundtrack path, scene timing
and copy are editable in `render.mjs`.
