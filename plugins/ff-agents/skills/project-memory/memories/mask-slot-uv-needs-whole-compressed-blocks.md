# A mask-slot UV needs whole compressed blocks of that colour

**w375, 2026-10-13 (m5, cargo barge trim).** The barges' `Standard-LowPoly_SG` shader graph colours each face by
which channel of two mask textures (`CargoShipMaskA/B.png`) its UV lands on. New trim faces were all mapped to one
texel inside a 12x6-texel green island of mask B, beside red and blue islands. The editor sampled the PNG and looked
right; the built player drew the trim orange-white (measured (255,195,122) on a bar), because the masks import
block-compressed (4x4 texels a block) and the compressed block mixed the neighbouring slots.

**Rule:** a UV meant to pick one mask slot sits inside a region where the whole 4x4 block around it, and the
neighbouring blocks, are that colour alone (a 12x12-texel square is safe). Check it in a test that reads every
texel of the block and its neighbours, not one bilinear sample: the game repo's
`Assets/Tests/Presentation/CargoBargeHullTest.cs` (`TheTrimIsABrokenUpGlowingOutlineOnTheHull`) is the example, and
`Assets/Editor/CargoBargeModelBuilder.cs` `TrimUv` says where the safe square is.

**How to apply:** before mapping new faces to a mask slot, scan the mask for a block-aligned region of that colour
(the analysis loop is a few lines over the decoded PNG), and confirm the colour in a built-player crop, not the
editor preview: on thin bright lines bloom and the tonemapper also shift the hue (evidence-gate
`checklists/visual.md` 5c).
