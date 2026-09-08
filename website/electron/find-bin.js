// Universal .app bundles (packaging/build-desktop.sh UNIVERSAL=1) ship one
// complete backend tree per CPU architecture under backend-dist/. Maps a Node
// `process.arch` value to the directory suffix; arches without an entry
// (e.g. "ia32") simply skip the arch-suffixed candidates.
const ARCH_DIR_SUFFIX = { arm64: "arm64", x64: "x64" };

/**
 * Locate the codexcrew backend binary by checking well-known paths in order.
 *
 * Returns the first executable candidate, or bare `"codexcrew"` as a PATH
 * fallback. Dependencies are injected so the function is pure and testable
 * without mocking globals.
 *
 * @param {typeof import("fs")} fs - Node fs module (needs `accessSync`, `constants.X_OK`)
 * @param {typeof import("os")} os - Node os module (needs `homedir()`)
 * @param {typeof import("path")} path - Node path module
 * @param {string|undefined} resourcesPath - `process.resourcesPath` (Electron only)
 * @param {string} dirname - `__dirname` of the calling module
 * @param {string} [arch] - CPU arch selecting the backend tree in universal
 *   bundles (defaults to `process.arch`)
 * @param {boolean} [isWindows] - whether the host is Windows (defaults to
 *   `process.platform === "win32"`). On Windows the backend ships as a real
 *   `codexcrew.exe` console script under `Scripts\` (venv) — Node's `spawn()`
 *   does no PATHEXT resolution for a bare name, so an absolute `.exe` path is
 *   required.
 * @returns {string} Absolute path to the binary, or `"codexcrew"` /
 *   `"codexcrew.exe"` (Windows) as a PATH fallback
 */
function findKirocrewBin(
  fs,
  os,
  path,
  resourcesPath,
  dirname,
  arch = process.arch,
  isWindows = process.platform === "win32"
) {
  const home = os.homedir();
  const candidates = [];
  // 0. Universal-bundle layout: arch-suffixed backend trees, selected by the
  //    running shell's arch. Ranked above the unsuffixed layout so a universal
  //    bundle never falls back to a wrong-arch tree; plain per-arch bundles
  //    don't ship these dirs so the probes miss (ENOENT) and fall through.
  const suffix = ARCH_DIR_SUFFIX[arch];
  if (suffix) {
    const archBackend = `codexcrew-backend-${suffix}`;
    candidates.push(
      path.join(resourcesPath || "", "backend-dist", archBackend, "bin", "codexcrew"),
      path.resolve(dirname, "backend-dist", archBackend, "bin", "codexcrew")
    );
  }
  candidates.push(
    // 1. Windows bundled layout (packaging/build-desktop.sh
    //    build_backend_windows): the PBS interpreter ships python.exe at
    //    the tree root with a bin\codexcrew.cmd launcher shim. Probed on
    //    every platform (costs one ENOENT elsewhere) so this function
    //    stays platform-agnostic and testable; only a Windows bundle
    //    actually contains the .cmd. Keep in sync with
    //    build-desktop.sh's bin/codexcrew.cmd.
    //
    //    This MUST outrank backend-dist/.../Scripts/codexcrew.exe below.
    //    `pip install` also drops a console-script .exe in the bundle's
    //    Scripts\ dir, but distlib embeds the ABSOLUTE interpreter path of
    //    the machine that built it, so inside a shipped bundle that .exe
    //    points at a build-agent path (D:\a\CodexCrew\...) that does not
    //    exist on the user's machine. The .cmd shim resolves the
    //    interpreter via %~dp0 and is the only relocatable launcher of the
    //    two. Ranking them the other way round both broke the build-time
    //    resolver gate and, had the gate not caught it, would have shipped
    //    an app whose backend could never start.
    path.join(resourcesPath || "", "backend-dist", "codexcrew-backend", "bin", "codexcrew.cmd"),
    path.resolve(dirname, "backend-dist", "codexcrew-backend", "bin", "codexcrew.cmd"),
    // 2. Bundled POSIX layout (packaging/build-desktop.sh): a
    //    python-build-standalone interpreter copied into backend-dist with a
    //    `bin/codexcrew` launcher wrapper (exec python3.12 -s -m codex_crew).
    //    This is what a freshly-built .app actually ships. Keep this in sync
    //    with build-desktop.sh's BACKEND_OUT/bin/codexcrew path.
    path.join(resourcesPath || "", "backend-dist", "codexcrew-backend", "bin", "codexcrew"),
    path.resolve(dirname, "backend-dist", "codexcrew-backend", "bin", "codexcrew"),
    path.resolve(dirname, "..", "bin", "codexcrew")
  );
  if (isWindows) {
    // 3. The bundle's pip console-script .exe. Ranked BELOW the .cmd shim
    //    (distlib bakes the building machine's absolute interpreter path into
    //    it, so in a shipped bundle it points at a path that does not exist)
    //    but still ABOVE the user-level install paths below: a bundled app
    //    must prefer its own backend over whatever happens to be installed on
    //    the machine. It is correct for a bundle built where it runs (a local
    //    `make desktop`), which is why it is probed at all.
    candidates.push(
      path.join(resourcesPath || "", "backend-dist", "codexcrew-backend", "Scripts", "codexcrew.exe"),
      path.resolve(dirname, "backend-dist", "codexcrew-backend", "Scripts", "codexcrew.exe")
    );

    // 4. Windows source checkout: a pip/venv install exposes `codexcrew.exe`
    //    under `Scripts\`. Keep checkout virtual environments below every
    //    bundled launcher so packaged builds cannot accidentally run repo code
    //    when the app was built from a checkout. When backend-dist is absent,
    //    a developer launch still falls through to the checkout environment.
    candidates.push(
      path.resolve(dirname, "..", "..", ".venv", "Scripts", "codexcrew.exe"),
      path.resolve(dirname, "..", ".venv", "Scripts", "codexcrew.exe")
    );
  }
  // 5. Well-known install paths (toolbox, installer symlink, and venv). Last,
  //    so a packaged app never prefers a stray user-level install over the
  //    backend it shipped with.
  candidates.push(
    path.join(home, ".toolbox", "bin", "codexcrew"),
    path.join(home, ".local", "bin", "codexcrew"),
    path.join(home, ".codexcrew-app", ".venv", "bin", "codexcrew")
  );
  if (isWindows) {
    // Windows equivalents of the user-level paths above (one-liner installer
    // venv, toolbox, and local pip Scripts dirs).
    candidates.push(
      path.join(home, ".codexcrew-app", ".venv", "Scripts", "codexcrew.exe"),
      path.join(home, ".toolbox", "bin", "codexcrew.exe"),
      path.join(home, ".local", "bin", "codexcrew.exe")
    );
  }
  for (const bin of candidates) {
    try {
      fs.accessSync(bin, fs.constants.X_OK);
      return bin;
    } catch (e) {
      if (e.code !== "ENOENT") console.warn(`codexcrew candidate ${bin}: ${e.code}`);
    }
  }
  return isWindows ? "codexcrew.exe" : "codexcrew"; // fall back to PATH
}

module.exports = { findKirocrewBin };
