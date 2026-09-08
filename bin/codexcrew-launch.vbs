' Codex Crew silent launcher.
' Runs the tray launcher (PowerShell + WinForms NotifyIcon) with NO visible
' window. The tray script starts the gateway hidden, waits until the dashboard
' responds, opens it in Firefox, and shows a system-tray icon with an
' Open / Restart / Quit menu. Being windowless is deliberate: the gateway is a
' background service the user never types into.
Option Explicit

Dim shell, fso, repo, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Repo root = parent of the folder holding this script (...\Codex Crew\bin -> ...\Codex Crew).
repo = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
shell.CurrentDirectory = repo

' -WindowStyle Hidden + wscript's own windowless run = zero visible console.
cmd = "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & _
      repo & "\bin\codexcrew-tray.ps1"""
shell.Run cmd, 0, False
