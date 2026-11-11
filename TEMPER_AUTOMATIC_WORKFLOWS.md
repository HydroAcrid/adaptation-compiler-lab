# Automatic task workflows

The Hub uses the connected agent's current task and repository instructions to
choose applicable approved skills. It reuses SkillKit for discovery and
installation. The agent can choose an empty skill profile. This selection does
not require a second model or contribute to personal learning.

Each prepared repository has at most one live task lease. The owning connection
can renew the lease or switch work with its current receipt. A task change
commits cleanup before another profile can be published. A stale receipt cannot
publish or remove a successor's files. Concurrent work in separate physical
checkouts can hold separate leases when each checkout is approved.

Completion, failure, and cancellation release the task profile and its temporary
runtime workspace. Cleanup deletes files whose contents still match the Hub's
ownership record and reports edited paths it preserved. A native connection
can request cleanup at a turn's terminal event. If the connection closes, the
bridge releases its leases. A later Hub poll or task preparation can recover
after a process death or expired lease. This fallback depends on the Hub
running again. The separate, read-only Temper context endpoint stays available
independently of the Hub.

## Remotion title cards

One executable workflow renders an animated title and optional subtitle to
a 320 × 400 H.264 MP4 at 15 frames per second. The request contains text,
three colors, and a duration of one to three seconds. The adapter supplies the
composition and command. Its browser and encoding processes run under a bounded
Windows Job. The MP4 is retained in the Hub's private artifacts directory.
Temporary files are released on return or on exact-lease recovery.

The Windows x64 adapter requires separate admission for the installed Node 24
executable, exact Remotion 4.0.542 package tree, and Chrome Headless Shell. Skill
publisher permission alone grants no renderer access. Rendering reads the
admitted installation and uses a private directory for the bundle, browser
profile, and intermediates. It does not install packages or start a provider
model. Runtime admission and execution do not expand the repositories already
authorized for Hub work.

The first implementation covers this bounded Remotion composition and the
existing SkillKit profile flow. General framework discovery, installation,
or arbitrary project code execution are outside this contract. Workflow fit is
an agent decision under the current request and native instructions. Its
selection does not establish a comparative efficacy or owner-effort result.
