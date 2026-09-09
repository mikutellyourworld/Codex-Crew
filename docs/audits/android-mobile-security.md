# Android mobile security review

Scope: Android shell, connection-address parser, host ADB assistant and recovery
helper. This is a focused code/configuration review, not a penetration test or
an audit of every gateway feature or installed dashboard app.

## Findings addressed

- Sideload builds enabled Android and WebView debugging. Both build types now
  disable the debuggable flag, and WebView remote debugging is always disabled.
- File-picker completion needed stronger binding to its originating page.
  Pickers now require the selected dashboard origin, navigation cancels pending
  selection, stale request identifiers are ignored, and results require granted
  read access to content URIs. Uninitialized page URLs fail closed.

## Protections checked

- Only INTERNET permission; no broad storage, contacts, microphone or camera
  permission. Android document picker explicitly mediates uploads.
- HTTPS for network origins; HTTP allowed only on exact phone loopback hosts.
  TLS errors cancel, mixed content is disabled, Safe Browsing remains enabled.
- File/content WebView access and JavaScript/native bridges are disabled.
  Third-party cookies are disabled. Exported launcher connection proposals
  require explicit confirmation. Persisted origins exclude login tokens.
- Android backups/data extraction are disabled. Credentials and signing keys
  are not included in source control.
- ADB commands use argument arrays and bounded subprocess timeouts; pairing
  codes go through stdin. Recovery targets exactly one selected endpoint,
  checks device/mapping success and never changes phone security settings.

## Limits

Validation: Android build and lint passed; Java origin-security checks passed;
26 host connection/recovery tests passed. Inspection of the built APK manifest
confirmed only INTERNET permission, backup disabled, and no debuggable flag.
Working-tree credential/identity scanning passed (not a historical Git audit).

The currently installed APK is not hardened until the new build is installed.
Android/WebView updates and the chosen gateway remain part of the trust boundary.
The sideload artifact uses the local debug signing identity, even though runtime
debugging is disabled; public distribution still needs managed release signing.
ADB remains a powerful trusted-host interface. Direct HTTPS avoids keeping it
connected for routine app use. Auto Blocker changes remain manual and optional.
This review does not establish that all dependencies or gateway apps are free
of vulnerabilities. File-picker behavior still needs real-device validation.

Reference: [Android WebView file-access guidance](https://developer.android.com/privacy-and-security/risks/webview-unsafe-file-inclusion).
