"""Local desktop pairing form. ADB runs off the UI thread; codes stay in memory."""

from __future__ import annotations

import queue
import threading
from pathlib import Path

from codex_crew.mobile import MobileError


def launch(bridge, args) -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        raise MobileError(
            "Install your OS tkinter package, or run without --gui for terminal setup."
        ) from None
    try:
        window = tk.Tk()
    except tk.TclError:
        raise MobileError(
            "No desktop display is available. Run without --gui for terminal setup."
        ) from None
    window.title("Codex Crew — Android setup")
    window.geometry("600x660")
    window.minsize(340, 560)
    window.columnconfigure(0, weight=1)
    window.rowconfigure(0, weight=1)
    canvas = tk.Canvas(window, highlightthickness=0)
    scrollbar = ttk.Scrollbar(window, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")
    form = ttk.Frame(canvas, padding=16)
    content = canvas.create_window((0, 0), window=form, anchor="nw")
    canvas.bind(
        "<Configure>", lambda event: canvas.itemconfigure(content, width=event.width)
    )
    form.bind(
        "<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    form.columnconfigure(0, weight=1)
    status = tk.StringVar(
        value="Connect USB and approve debugging, or enable Wireless debugging."
    )
    fields = {}
    widgets = []
    events = queue.Queue()
    busy = False

    def label(text):
        item = ttk.Label(form, text=text, wraplength=540, justify="left")
        item.grid(sticky="ew", pady=4)
        window.bind(
            "<Configure>",
            lambda e: item.configure(wraplength=max(260, form.winfo_width() - 32)),
            add="+",
        )

    def field(name, initial="", secret=False, choices=False):
        label(name)
        variable = tk.StringVar(value=initial)
        widget = (
            ttk.Combobox(form, textvariable=variable)
            if choices
            else ttk.Entry(form, textvariable=variable, show="•" if secret else "")
        )
        widget.grid(sticky="ew", pady=2)
        fields[name] = variable
        widgets.append(widget)
        return widget

    def task(work, done):
        nonlocal busy
        if busy:
            return
        busy = True
        for widget in widgets:
            widget.configure(state="disabled")
        status.set("Working…")

        def run():
            try:
                events.put((done, work(), None))
            except (MobileError, OSError, ValueError) as exc:
                events.put(
                    (
                        done,
                        None,
                        str(exc)
                        if isinstance(exc, MobileError)
                        else "Operation failed. Check the APK file and refresh the ports.",
                    )
                )

        threading.Thread(target=run, daemon=True).start()

    def poll():
        nonlocal busy
        try:
            done, value, error = events.get_nowait()
            busy = False
            for widget in widgets:
                widget.configure(state="normal")
            if error:
                status.set(error)
            else:
                done(value)
        except queue.Empty:
            pass
        window.after(100, poll)

    def button(text, command):
        item = ttk.Button(form, text=text, command=command)
        item.grid(sticky="ew", pady=5)
        widgets.append(item)

    label("Android setup")
    button(
        "Samsung Auto Blocker help",
        lambda: messagebox.showinfo(
            "Samsung Auto Blocker",
            "If Samsung blocks debugging or APK installation, open phone Settings → "
            "Security and privacy → Auto Blocker (or search Settings for Auto Blocker). "
            "Turn it off and confirm on the phone, then enable debugging in Developer "
            "options and retry.\n\nThis temporarily removes Auto Blocker protections. "
            "Turn it back on after debugging; this may interrupt ADB. "
            "Direct HTTPS dashboard access does not require disabling it.",
            parent=window,
        ),
    )
    label(
        "USB: accept the phone’s debugging prompt. Wireless: open Developer options → Wireless debugging. Pairing and connection ports are separate and can change."
    )
    device = field(
        "Connected phone / connection IP:port",
        args.device or args.connect or "",
        choices=True,
    )
    pairing = field("Pairing popup IP:port", choices=True)
    field("Pairing code", secret=True)

    def refreshed(result):
        devices, services = result
        ready = [serial for serial, state in devices.items() if state == "device"]
        connections = [s.address for s in services if "connect" in s.kind]
        device.configure(values=list(dict.fromkeys(ready + connections)))
        pairing.configure(values=[s.address for s in services if "pairing" in s.kind])
        # Keep user selection: never switch to a different discovered phone.
        if not fields["Connected phone / connection IP:port"].get() and len(ready) == 1:
            fields["Connected phone / connection IP:port"].set(ready[0])
        status.set(
            "Ports refreshed. Select your phone’s current endpoint. If discovery is empty, type the address from Android; mDNS may not cross a VPN."
        )

    def refresh():
        task(lambda: (bridge.devices(), bridge.discover()), refreshed)

    button("Refresh devices and current ports", refresh)

    def pair():
        address, code = (
            fields["Pairing popup IP:port"].get(),
            fields["Pairing code"].get(),
        )
        fields["Pairing code"].set("")

        def paired(_):
            status.set(
                "Paired. Refresh and select the connection port from the main Wireless debugging page."
            )
            refresh()

        task(lambda: bridge.pair(address, code), paired)

    button("Pair with popup code", pair)
    field("Desktop dashboard port", str(args.host_port))
    field("Phone local port", str(args.phone_port))
    field("APK (optional if already installed)", str(args.apk or ""))

    def browse():
        value = filedialog.askopenfilename(filetypes=[("Android app", "*.apk")])
        if value:
            fields["APK (optional if already installed)"].set(value)

    button("Choose APK", browse)

    def connect():
        selected = fields["Connected phone / connection IP:port"].get().strip()
        host_port, phone_port = (
            fields["Desktop dashboard port"].get(),
            fields["Phone local port"].get(),
        )
        apk = fields["APK (optional if already installed)"].get().strip()

        def work():
            serial = selected
            if bridge.devices().get(serial) != "device":
                serial = bridge.connect(selected)
            bridge.open_app(serial, host_port, phone_port, Path(apk) if apk else None)

        task(
            work,
            lambda _: status.set(
                "Connected. Confirm the address on the phone and sign in to your dashboard."
            ),
        )

    button("Install / connect / open dashboard", connect)
    notice = ttk.Label(form, textvariable=status, wraplength=540, justify="left")
    notice.grid(sticky="ew", pady=8)
    window.bind(
        "<Configure>",
        lambda e: notice.configure(wraplength=max(260, form.winfo_width() - 32)),
        add="+",
    )
    window.after(100, poll)
    refresh()
    window.mainloop()
