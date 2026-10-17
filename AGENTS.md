# Temper build storage

- Reuse an existing suitable checkout for normal builds and validation. Check active work and dirty state before creating another checkout; preserve unfinished work.
- Before native compilation or Cargo tests, run `.venv/Scripts/python.exe packaging/build_native.py --check-storage` on Windows, or `.venv/bin/python packaging/build_native.py --check-storage` on Mac. Resolve its disk reserve or generated-output warning before continuing.
- Native generated output is limited to 4 GiB at admission, with at least 8 GiB free before a build. Do not enable Rust debug symbols/incremental retention or per-start Windows engine extraction without revisiting the storage regression checks.
- Keep selected installer/binary hashes and test receipts. After installation or an abandoned candidate, use Cargo's bounded clean commands for obsolete targets; preserve source, dirty files, credentials, grants, runtime history and private evidence. Never clean a whole recovery directory as build cache.
- No GitHub CI for this work. Use local native platform checks and the shared pre-flight gate before release actions.
