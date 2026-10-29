# CI's EditMode editor runs on OpenGL: a shader test reads the source, not the compiled passes

**The fact.** The game repo's CI runs the EditMode suite in an editor on GLCore (OpenGL). There Unity drops every pass
of a shader marked `exclude_renderers glcore` (or not compiled for it), and `shader.renderQueue` can report Geometry
for a subshader whose own tag says otherwise. A test that asks the compiled shader which passes or LightModes it has
passes on a Windows editor (D3D11) and fails on CI, or the reverse.

**Incident (w2488, 2026-10-28, #2777).** The planets fix added `Assets/Tests/Lights/DepthPrimingTest.cs`: every
opaque forward shader must have a DepthNormals pass, because URP depth priming (Auto) with SSAO on DepthNormals draws
the opaque pass with ZTest Equal, and a shader without that pass vanishes (Planet, GasGiant, Star on Medium and
Ultra). It passed locally and went red on CI while players had broken planets live.

**How to apply.** For a `.shader`, read its LightMode and Queue tags from the source text (`File.ReadAllText` on the
asset path, a regex on `"Queue" = "..."`; DepthPrimingTest.cs:91-103). For a Shader Graph, take the queue from the
subshader's own tag (`subshader.FindTagValue(new ShaderTagId("Queue"))`; DepthPrimingTest.cs:107-115). To reproduce
CI's result before pushing, run the editor with `-force-glcore`. If it still cannot pass on OpenGL quickly and the fix
is urgent, skip the test on GLCore with a one-line reason (the orchestrator for Ben, w2488) rather than hold the fix.
