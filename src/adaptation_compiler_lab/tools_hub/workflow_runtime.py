"""Bounded data-only Remotion rendering with a separately admitted toolchain."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .manager import bounded_run
from .paths import check_root, safe

REMOTION_WORKFLOW = "remotion-title-card"
REMOTION_VERSION = "4.0.542"
MAX_TOOLCHAIN_BYTES = 750_000_000
MAX_RUN_BYTES = 160_000_000
MAX_RUN_ENTRIES = 8_000
MAX_ARTIFACT_BYTES = 4_000_000
COMPOSITOR = "@remotion/compositor-win32-x64-msvc"
PACKAGES = ("remotion", "@remotion/bundler", "@remotion/renderer", COMPOSITOR)
CHROME_DEBUG_LOG = "debug.log"


class MotionVideo(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(min_length=1, max_length=72)
    subtitle: str = Field(default="", max_length=96)
    background: str = Field(default="#17233a", pattern=r"^#[0-9a-fA-F]{6}$")
    foreground: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(default="#59d9ac", pattern=r"^#[0-9a-fA-F]{6}$")
    seconds: int = Field(default=2, ge=1, le=3)


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def tree_hash(
    root: Path,
    *,
    skip: frozenset[str] = frozenset(),
    ignore_chrome_log: bool = False,
) -> str:
    digest = hashlib.sha256()
    total = entries = 0
    for directory, subdirs, filenames in os.walk(check_root(root), followlinks=False):
        parent = Path(directory)
        if parent == root:
            subdirs[:] = [name for name in subdirs if name not in skip]
            if ignore_chrome_log and CHROME_DEBUG_LOG in subdirs:
                raise ValueError("Chrome debug log must be a regular file")
        subdirs.sort()
        entries += len(subdirs) + len(filenames)
        if entries > 25_000:
            raise ValueError("Remotion toolchain exceeds its file entry bound")
        for name in subdirs:
            child = parent / name
            if child.is_symlink() or child.is_junction():
                raise ValueError("Remotion toolchain paths must not be redirected")
        for name in sorted(filenames):
            path = parent / name
            is_browser_log = ignore_chrome_log and parent == root and name == CHROME_DEBUG_LOG
            try:
                info = path.lstat()
            except FileNotFoundError:
                if not is_browser_log:
                    raise
                # A separate browser launch may rotate its generated log.
                continue
            if (
                not stat.S_ISREG(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            ):
                raise ValueError("Remotion toolchain contains a redirected or special file")
            if is_browser_log:
                # Windows Chromium appends to this generated log by default.
                continue
            total += info.st_size
            if total > MAX_TOOLCHAIN_BYTES:
                raise ValueError("Remotion toolchain exceeds its storage bound")
            item = [path.relative_to(root).as_posix(), file_hash(path)]
            digest.update((json.dumps(item, ensure_ascii=True) + "\n").encode())
    if not entries:
        raise ValueError("Remotion toolchain directory is missing or empty")
    return digest.hexdigest()


def runtime_directory(root: Path, token: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", token):
        raise ValueError("Invalid Remotion task token")
    return safe(root, "runs/" + hashlib.sha256(token.encode()).hexdigest())


def check_run_budget(work: Path) -> None:
    pending = [check_root(work)]
    total = entries = 0
    while pending:
        folder = pending.pop()
        try:
            if folder.is_symlink() or folder.is_junction():
                raise ValueError("Remotion scratch contains a redirected directory")
            with os.scandir(folder) as scan:
                for entry in scan:
                    entries += 1
                    if entries > MAX_RUN_ENTRIES:
                        raise ValueError("Remotion scratch exceeded its file entry bound")
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    if (
                        stat.S_ISLNK(info.st_mode)
                        or getattr(info, "st_file_attributes", 0)
                        & stat.FILE_ATTRIBUTE_REPARSE_POINT
                    ):
                        raise ValueError("Remotion scratch contains a redirected resource")
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(Path(entry.path))
                    elif stat.S_ISREG(info.st_mode):
                        total += info.st_size
                        if total > MAX_RUN_BYTES:
                            raise ValueError("Remotion scratch exceeded its storage bound")
                    else:
                        raise ValueError("Remotion scratch contains a special file")
        except FileNotFoundError:
            # The owned renderer can remove a temporary directory during the scan.
            continue


class RemotionRuntime:
    """A local Windows x64 adapter. Its pin must come from owner-signed setup."""

    def __init__(self, admission: dict[str, Any]) -> None:
        self.admission = dict(admission)

    @staticmethod
    def pin(node: Path, node_modules: Path, browser: Path) -> dict[str, Any]:
        if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"}:
            raise ValueError("This Remotion toolchain requires native Windows x64")
        node, node_modules, browser = map(check_root, (node, node_modules, browser))
        if (
            node.name.lower() != "node.exe"
            or not node.is_file()
            or node.stat().st_size > 200_000_000
            or node_modules.name != "node_modules"
            or browser.name.lower() != "chrome-headless-shell.exe"
            or not browser.is_file()
        ):
            raise ValueError("Expected local Node, Remotion and Chrome Headless Shell")
        for name in PACKAGES:
            manifest = safe(node_modules, name + "/package.json")
            if manifest.stat().st_size > 256_000:
                raise ValueError("Remotion package manifest exceeds its supported bound")
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
            if metadata.get("name") != name or metadata.get("version") != REMOTION_VERSION:
                raise ValueError("Remotion runtime packages must all match the admitted version")
        return {
            "workflow": REMOTION_WORKFLOW,
            "version": REMOTION_VERSION,
            "platform": "windows-x64",
            "node": str(node),
            "node_digest": file_hash(node),
            "node_modules": str(node_modules),
            "module_tree_digest": tree_hash(node_modules, skip=frozenset({".cache", ".remotion"})),
            "browser": str(browser),
            "browser_tree_digest": tree_hash(browser.parent, ignore_chrome_log=True),
        }

    def verify(self) -> tuple[Path, Path, Path]:
        try:
            node = Path(self.admission["node"])
            modules = Path(self.admission["node_modules"])
            browser = Path(self.admission["browser"])
        except (KeyError, TypeError):
            raise ValueError("Remotion has no valid runtime admission") from None
        if self.admission != self.pin(node, modules, browser):
            raise ValueError("Remotion runtime differs from its owner admission")
        return node, modules, browser

    @staticmethod
    def reap(work_root: Path, task_token: str) -> bool:
        work = runtime_directory(work_root, task_token)
        if not work.exists():
            return False
        # The caller holds the same exclusive Hub writer as render. An
        # interrupted Windows process already lost its kill-on-close Job.
        # runtime_directory checked the exact token directory and all ancestors.
        # rmtree unlinks inner symlinks/junctions without entering their targets.
        # Deletion need not read file data or pass the render admission budget.
        shutil.rmtree(work)
        return True

    def render(
        self,
        work_root: Path,
        task_token: str,
        spec: MotionVideo,
        *,
        allowed: Callable[[], None],
    ) -> dict[str, Any]:
        allowed()
        work_root = check_root(work_root)
        node, modules, browser = self.verify()
        work = runtime_directory(work_root, task_token)
        self.reap(work_root, task_token)
        work.mkdir(parents=True, mode=0o700)
        try:
            (work / "entry.jsx").write_text(ENTRY, encoding="utf-8")
            (work / "render.cjs").write_text(RENDER, encoding="utf-8")
            (work / "input.json").write_text(spec.model_dump_json(), encoding="utf-8")
            (work / "package.json").write_text('{"private":true}', encoding="utf-8")

            def guard() -> None:
                allowed()
                check_run_budget(work)

            output = bounded_run(
                [str(node), str(work / "render.cjs"), str(modules), str(browser)],
                work,
                work / "private-home",
                timeout=75,
                guard=guard,
                extra={
                    "REMOTION_DISABLE_TELEMETRY": "1",
                    "CHROME_LOG_FILE": str(work / CHROME_DEBUG_LOG),
                },
            )
            if output["returncode"]:
                raise ValueError("The admitted Remotion render failed")
            rendered = safe(work, "result.mp4")
            size = rendered.stat().st_size
            with rendered.open("rb") as stream:
                header = stream.read(12)
            if not 1024 <= size <= MAX_ARTIFACT_BYTES or header[4:8] != b"ftyp":
                raise ValueError("Remotion returned an invalid or oversized MP4")
            check_run_budget(work)
            digest = file_hash(rendered)
            allowed()
            artifacts = safe(work_root, "artifacts")
            artifacts.mkdir(exist_ok=True, mode=0o700)
            artifact = safe(artifacts, "title-card-" + secrets.token_hex(12) + ".mp4")
            # Windows rename refuses to overwrite an existing destination.
            rendered.rename(artifact)
            return {
                "workflow": REMOTION_WORKFLOW,
                "version": REMOTION_VERSION,
                "artifact_path": str(artifact),
                "sha256": digest,
                "bytes": size,
                "width": 320,
                "height": 400,
                "fps": 15,
                "frames": spec.seconds * 15,
            }
        finally:
            self.reap(work_root, task_token)


ENTRY = """import React from 'react';
import {AbsoluteFill, Composition, Easing, interpolate, registerRoot,
  useCurrentFrame} from 'remotion';

const TitleCard = ({title, subtitle, background, foreground, accent}) => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [0, 10], [0, 1], {
    easing: Easing.out(Easing.cubic),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const titleSize = title.length > 48 ? 22 : title.length > 25 ? 29 : 37;
  return <AbsoluteFill style={{background, color: foreground, fontFamily: 'Arial, sans-serif',
      justifyContent: 'center', padding: 28, overflow: 'hidden'}}>
    <div style={{opacity: progress, transform: 'translateY(' + (20 * (1 - progress)) + 'px)',
        overflowWrap: 'anywhere'}}>
      <div style={{width: 56, height: 5, background: accent, marginBottom: 20}} />
      <div style={{fontSize: titleSize, fontWeight: 700, lineHeight: 1.1}}>{title}</div>
      {subtitle && <div style={{fontSize: 15, marginTop: 14, lineHeight: 1.2}}>{subtitle}</div>}
    </div>
  </AbsoluteFill>;
};

registerRoot(() => <Composition id="TemperTitleCard" component={TitleCard}
  width={320} height={400} fps={15} durationInFrames={30}
  calculateMetadata={({props}) => ({durationInFrames: props.seconds * 15})} />);
"""

RENDER = """const fs = require('node:fs');
const path = require('node:path');
const {createRequire, registerHooks} = require('node:module');
const {fileURLToPath} = require('node:url');

const [modules, browserExecutable] = process.argv.slice(2);
if (!process.versions.node.startsWith('24.')) {
  throw new Error('The admitted Remotion renderer requires Node 24');
}
registerHooks({
  resolve(specifier, context, nextResolve) {
    const resolved = nextResolve(specifier, context);
    if (resolved.url.startsWith('node:')) return resolved;
    const target = fs.realpathSync(fileURLToPath(resolved.url));
    const relative = path.relative(modules, target);
    if (relative.startsWith('..' + path.sep) || path.isAbsolute(relative)
        || relative.split(path.sep).some(part => part === '.cache' || part === '.remotion')) {
      throw new Error('Remotion module resolved outside its admitted toolchain');
    }
    return resolved;
  },
});
const fromToolchain = createRequire(path.join(modules, '.temper-runtime.cjs'));
const {bundle} = fromToolchain('@remotion/bundler');
const {openBrowser, selectComposition, renderMedia} = fromToolchain('@remotion/renderer');
const inputProps = JSON.parse(fs.readFileSync('input.json', 'utf8'));

async function render() {
  const serveUrl = await bundle({
    entryPoint: path.join(__dirname, 'entry.jsx'),
    rootDir: __dirname,
    outDir: path.join(__dirname, 'bundle'),
    enableCaching: false,
    webpackOverride: config => ({
      ...config,
      resolve: {...config.resolve, modules: [modules]},
    }),
  });
  const browser = await openBrowser('chrome', {browserExecutable, logLevel: 'error'});
  try {
    const composition = await selectComposition({
      serveUrl, id: 'TemperTitleCard', inputProps, puppeteerInstance: browser, logLevel: 'error',
    });
    await renderMedia({
      composition, serveUrl, inputProps, puppeteerInstance: browser,
      codec: 'h264', outputLocation: path.join(__dirname, 'result.mp4'),
      binariesDirectory: path.join(modules, '@remotion', 'compositor-win32-x64-msvc'),
      concurrency: 1, muted: true, logLevel: 'error',
    });
  } finally {
    await browser.close({silent: true});
  }
}

render().catch(error => {
  console.error(error instanceof Error ? error.message : 'Remotion render failed');
  process.exitCode = 1;
});
"""
