# Codex Crew for Android

An Android 8+ client for the existing Codex Crew browser dashboard. Chat,
sessions, apps, settings and authentication come from your running gateway,
so browser improvements arrive without rebuilding the APK. This is a remote
client: it does not run a Python gateway or Codex CLI on Android.

## Build

Use JDK 17+, Gradle 9.7.1 and Android SDK platform 36. With the Android SDK
command-line tools installed:

```sh
sdkmanager 'platforms;android-36' 'build-tools;36.0.0' 'platform-tools'
gradle -p mobile/android --no-daemon assembleDebug
```

The APK is `mobile/android/app/build/outputs/apk/debug/app-debug.apk`.
Local SDK paths, build products and signing keys are ignored. Debug builds
are for sideloading; a store release requires a privately held release key.

## Assisted USB or wireless setup

Install this checkout of Codex Crew, then run:

```sh
codexcrew-mobile --gui --apk mobile/android/app/build/outputs/apk/debug/app-debug.apk
```

The desktop form selects a phone, discovers advertised ports, pairs using
the popup code, installs the APK, verifies ADB connectivity, creates an ADB
reverse tunnel and opens the app. Without `--gui`, setup runs interactively
in a terminal. Linux GUI users need their distribution's `python3-tk` package.
ADB is located in the Android SDK, on PATH, or in a release kit's adjacent
`platform-tools` directory; `--adb` supplies an explicit path. The app itself
does not need ADB installed on the phone.

USB requires Android's debugging consent. Wireless debugging requires
Android 11+ and initial pairing approval on the phone. Pairing codes stay
in memory and pass to ADB over stdin, never command arguments or config.
ADB manages its own pairing keys outside the repository.

On Samsung devices, **ADB setup and pairing → Samsung Auto Blocker** explains
how to disable Auto Blocker when it blocks debugging or APK installation and
opens Android security settings (falling back to general Settings). Use
Settings → Security and privacy → Auto Blocker, or search for it in Settings.
The owner changes the switch and confirms on the phone. The desktop form and
terminal setup include the same guidance before pairing. Restore Auto Blocker
after debugging; restoring its protections may interrupt ADB. Direct HTTPS
access does not require this change. See [Samsung's Auto Blocker guide](https://www.samsung.com/us/support/answer/ANS10003636/).

Choose **Refresh devices and current ports** after changing networks or
toggling debugging. Pairing and connection ports differ. The assistant
refreshes discovery after pairing and verifies a real connected device
before making a tunnel. It never probes a port range or guesses a different
phone. mDNS may not cross Tailscale or isolated Wi-Fi: enter the phone's
reachable IP and the connection port shown on the main Wireless debugging
page. A remembered stale port is not treated as a lost pairing.

The desktop gateway and phone local ports default to 5486 and are separate
editable fields. Use the actual gateway port if yours differs. `adb reverse`
works over both USB and authenticated wireless ADB, keeps the gateway bound
to localhost, and is removed by Android when the transport disconnects.
Rerun the assistant after a disconnect to restore it. This initial version
does not install an unattended reconnection daemon.

## Direct Wi-Fi / Tailscale

Enter your dashboard's HTTPS origin in the app and sign in normally. ADB is
optional for this mode. Use the browser dashboard's existing Tailscale
publishing flow to obtain a reachable HTTPS address. The app does not open
host firewall ports or enable public publishing. Plain HTTP is accepted
only for localhost ADB tunnels. URL credentials, query strings, fragments
and non-root paths are rejected; only the dashboard origin is saved.

The app uses Android's trusted certificate store without TLS overrides.
External HTTPS links require confirmation and open in the browser. File
access, content access, mixed content, third-party cookies and JavaScript
native bridges are disabled. ADB launcher extras ask for confirmation before
changing the dashboard. The connection screen retains the saved address and
offers no forget/sign-out button; use dashboard session management for sign-out.
An empty address prefills the standard local ADB URL. Android backups are off.
Android Back returns to the Crew-themed native setup card after dashboard history is exhausted.

## Verification

The connection dropdown keeps separate ADB and HTTPS addresses. Select a slot,
edit its address, and tap **Save / overwrite selected address**. **Open dashboard**
also saves that slot. Existing saved addresses migrate without replacing a slot.
Only credential-free root addresses are accepted; sign-in links are not saved.

When both slots are saved, the foreground app checks the active ADB endpoint
immediately and every ten seconds after a check finishes. Two consecutive network
failures or server errors switch to the saved HTTPS address. Each check has
three-second connect and read timeouts, follows no redirects, and sends no WebView
cookies. Authentication responses count as reachable. Checks stop in the background;
stale results after navigation are ignored. HTTPS never downgrades to HTTP and
does not copy the ADB login session. Sign in on HTTPS separately. Unsaved messages
may be lost when switching dashboards. This cannot repair an offline host shared
by both connections.

Device acceptance for profiles: overwrite each slot, restart the app, confirm both
persist, open ADB, then remove its reverse tunnel and confirm a single HTTPS switch.
Repeat with an empty HTTPS slot (no switch), a brief interruption (no switch after
recovery), and background/resume. Verify HTTPS certificate errors remain blocked.

For automatic tunnel recovery after desktop restarts, run
`python -m codex_crew.mobile_recovery --connect IP:CONNECTION_PORT` under your
service manager. Keep that endpoint in local service configuration, outside Git.
The phone must already be paired. This restores only the selected phone's tunnel;
if Android changes its debugging port, update the endpoint. Use `--once` for a
single recovery attempt. Direct HTTPS does not depend on this tunnel.

```sh
python -m pytest -n 0 test/test_mobile.py
sh mobile/android/test-address.sh
gradle -p mobile/android --no-daemon assembleDebug lintDebug
```

Device acceptance: install, open via USB and wireless ADB, complete dashboard
login, send a chat message, fold/unfold, show the keyboard, rotate, disconnect,
and reconnect after refreshing ports. Verify developer-settings help, external
link confirmation and saved-address persistence. Do not publish screenshots
or logs containing device addresses, login links or private conversations.

References: [Android ADB](https://developer.android.com/tools/adb),
[ADB Wi-Fi architecture](https://android.googlesource.com/platform/packages/modules/adb/+/HEAD/docs/dev/adb_wifi.md),
[WebView file-access security](https://developer.android.com/privacy-and-security/risks/webview-unsafe-file-inclusion).
