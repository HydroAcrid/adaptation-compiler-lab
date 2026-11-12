# Temper build storage

- Reuse an existing suitable checkout for normal builds and validation. Check active work and dirty state before creating another checkout; preserve unfinished work.
- Before native compilation or Cargo tests, run `.venv/Scripts/python.exe packaging/build_native.py --check-storage` on Windows, or `.venv/bin/python packaging/build_native.py --check-storage` on Mac. Resolve its disk reserve or generated-output warning before continuing.
- Native generated output is limited to 4 GiB at admission, with at least 8 GiB free before a build. Do not enable Rust debug symbols/incremental retention or per-start Windows engine extraction without revisiting the storage regression checks.
- Keep selected installer/binary hashes and test receipts. After installation or an abandoned candidate, use Cargo's bounded clean commands for obsolete targets; preserve source, dirty files, credentials, grants, runtime history and private evidence. Never clean a whole recovery directory as build cache.
- No GitHub CI for this work. Use local native platform checks and the shared pre-flight gate before release actions.

# Product interface direction

- Do not use cards or boxed statistic tiles. Organize content with typography, whitespace, aligned rows, and section dividers. Dialogs and actual input controls remain recognizable controls, not nested content cards.
- Give automatic temporary workflow guidance a prominent place in Overview and Tools: explain selection for the current task, approved-source updates, switching, and cleanup using actual supported behavior. Do not bury this primary feature in settings or claim universal best-tool selection.
- Loading must preserve layout and existing useful content, communicate the specific operation, and honor reduced motion. Check slow, empty, failure, and recovery states in the actual rendered app.
- Finished UI and promotional video copy is customer-facing; keep internal production notes and agent commentary out of it. Video demonstrations must follow the same cardless visual direction and truthful feature scope.
- Lead repeat-use pages with current activity, actual state, and useful actions. Keep one-time explanations in optional help; do not substitute explanatory prose or invented activity for populated product states. Review populated, empty, loading, and failure states separately using clearly fictional fixtures.
