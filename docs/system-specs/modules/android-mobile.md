# Android mobile client and local connection assistant

The Android application under `mobile/android` is a WebView client of the
existing browser dashboard. The gateway remains the source of UI assets,
authorization, tools and session behavior. No gateway API or policy changes
are needed. Native setup and error controls must fit narrow and foldable
screens, respond to system/IME insets and preserve WebView during resizing.

`codexcrew-mobile` (`mobile.py`, `mobile_gui.py`) is an operator-run host CLI
and optional desktop form. It uses Android SDK ADB with argument arrays,
bounded subprocess timeouts and exact serial selection. Pairing input goes
on stdin, is never logged, and is not retained in config. Discovery accepts
only TLS pairing/connect mDNS records with valid literal IP endpoints. ADB
exit status alone is insufficient: pairing requires its success response;
connection requires devices/get-state verification; tunnel and launch both
require confirmation. Multiple phones require explicit selection.

The assistant refreshes mDNS after pairing and on demand. Pairing, connection,
gateway and phone-local ports are distinct. No port scanning, unauthenticated
legacy tcpip enablement, silent device switching or unattended daemon exists.
Manual current endpoint entry supports networks without mDNS propagation.

The ADB help menu includes Samsung Auto Blocker assistance: explain the
Security and privacy → Auto Blocker path, offer the public Android security
settings intent with a general-settings fallback, and leave the toggle and
confirmation to the owner. Host GUI/terminal guidance is also available before
ADB works. Explain the temporary reduction in protections and restoring the
setting after debugging; no automatic setting changes or status detection are
claimed. HTTPS access does not need this setting disabled.

ADB reverse forwards the phone's loopback port to the existing host gateway
port over USB or wireless ADB. The gateway still requires normal login. Direct
network use requires an existing HTTPS gateway endpoint. Android network
security permits cleartext only for localhost/127.0.0.1.
HTTP loopback origins canonicalize to localhost to match the gateway redirect;
the port remains part of the origin and other hosts are never aliases. No TLS
exception, file/content access or native JavaScript bridge is provided. Main-frame
navigation stays on the selected origin; gesture-initiated external HTTPS
links require confirmation and use the system browser. Launcher connection
extras also require confirmation. The selected origin has no credentials,
query, fragment or subpath; it is stored only in Android private preferences.
Backup is disabled; forgetting clears WebView login data and the origin.

Build uses pinned Android Gradle plugin 9.4.0, SDK 36, minimum API 26, Java 17.
Debug APKs are sideload artifacts. Release signing and app-store publication
are separate from source publication. No device endpoint, pairing key,
credential, SDK path, signing key or runtime state may enter source control.
