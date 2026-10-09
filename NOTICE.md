# Third-party material

`calibration/gsm8k-24.items.json` contains 24 problems from the test split of
GSM8K (Cobbe et al., 2021), taken from
https://github.com/openai/grade-school-math and used under its MIT License,
Copyright (c) 2021 OpenAI. The problems are unmodified; answers are the final
numeric answers from the dataset.

The rewrites in `examples/rewrites/` and the controls in `examples/controls/`
are original to this repository and derived from those problems.

`scripts/genlayer_write.mjs` is carried over from the Suborn repository.

`web/assets/fonts/` holds latin subsets of Barlow Condensed (Jeremy Tribby),
STIX Two Text (STI Pub Companies) and IBM Plex Mono (IBM), each under the SIL
Open Font License 1.1, taken from the Fontsource packages.
