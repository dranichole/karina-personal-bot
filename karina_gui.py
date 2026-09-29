"""Tkinter UI for Karina, your local desktop agent."""

from __future__ import annotations

import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from audio import default_input_device_index, list_input_devices
from config import Settings, get_settings, save_settings
from karina_core import KarinaSession, get_response, parse_close_command, parse_close_window_command
from llm import ensure_local_llm
from tray import TrayController, is_tray_available
from tts import is_tts_available, speak
from voice import VoiceRecognizer, WakeWordListener, is_voice_available

TITLE = "Karina Desktop AI"
HOLD_THRESHOLD_MS = 300
BG = "#1f1f2b"
PANEL = "#12121b"
ENTRY_BG = "#232338"


class KarinaUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(TITLE)
        self.geometry("780x620")
        self.minsize(560, 460)
        self.configure(bg=BG)

        self.settings = get_settings()
        self.session = KarinaSession()
        self._busy = False
        self._command_history: list[str] = []
        self._history_index = -1
        self._quitting = False
        self.voice_available, self.voice_status = is_voice_available()
        self.llm_available = False
        self.llm_status = "Starting local model..."
        self.voice = VoiceRecognizer() if self.voice_available else None
        self.wake: WakeWordListener | None = None
        self.tray: TrayController | None = None
        self._recording = False
        self._hold_mode = False
        self._toggle_mode = False
        self._press_time: float | None = None
        self._hold_timer: str | None = None
        self._transcribing = False
        self._mic_choices: list[tuple[int, str]] = list_input_devices()

        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=0)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_columnconfigure(2, weight=0)

        self._build_toolbar()
        self._build_chat()
        self._build_input_row()
        self._build_status()
        self._style_combobox()

        if self.voice:
            device = self._initial_mic_index()
            self.voice.set_device(device)
            self.settings.mic_device_index = device
            save_settings(self.settings)

        greeting = "Hello. I am Karina, your local desktop agent. Type 'help' for commands."
        if not self.voice_available:
            greeting += f" Voice: {self.voice_status}"
        self.print_message("Karina", greeting)
        self.entry.focus()

        self.protocol("WM_DELETE_WINDOW", self.on_close_window)
        if is_tray_available():
            self.tray = TrayController(on_show=self.show_from_tray, on_quit=self.quit_app)
            self.tray.start()

        self.after(100, self._start_llm_bootstrap)
        self.after(400, self._sync_wake_listener)

    def _build_toolbar(self) -> None:
        bar = tk.Frame(self, bg=BG)
        bar.grid(row=0, column=0, columnspan=3, sticky="ew", padx=12, pady=(10, 0))
        bar.grid_columnconfigure(1, weight=1)

        tk.Label(bar, text="Mic input", bg=BG, fg="#d0d0e8", font=("Segoe UI", 9)).grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )

        self.mic_var = tk.StringVar()
        self.mic_combo = ttk.Combobox(
            bar,
            textvariable=self.mic_var,
            state="readonly" if self._mic_choices else "disabled",
            values=self._combo_labels(),
        )
        self.mic_combo.grid(row=0, column=1, sticky="ew")
        self._select_saved_mic()
        self.mic_combo.bind("<<ComboboxSelected>>", self.on_mic_selected)

        self.settings_button = tk.Button(
            bar,
            text="Settings",
            command=self.open_settings,
            bg="#3a3a55",
            fg="#ffffff",
            activebackground="#555577",
            font=("Segoe UI", 9, "bold"),
        )
        self.settings_button.grid(row=0, column=2, padx=(8, 0))

    def _build_chat(self) -> None:
        self.chat_box = tk.Text(
            self,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg=PANEL,
            fg="#f7f7ff",
            insertbackground="#f7f7ff",
            padx=10,
            pady=10,
            font=("Segoe UI", 11),
        )
        self.chat_box.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=12, pady=(8, 6))
        scroll = tk.Scrollbar(self.chat_box, command=self.chat_box.yview)
        self.chat_box.configure(yscrollcommand=scroll.set)
        self.chat_box.tag_configure("time", foreground="#6d6d88", font=("Segoe UI", 8))
        self.chat_box.tag_configure("you", foreground="#8ec8ff", font=("Segoe UI", 11, "bold"))
        self.chat_box.tag_configure("karina", foreground="#b6e39a", font=("Segoe UI", 11, "bold"))
        self.chat_box.tag_configure("body", foreground="#f7f7ff", font=("Segoe UI", 11))

    def _build_input_row(self) -> None:
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(
            self,
            textvariable=self.entry_var,
            bg=ENTRY_BG,
            fg="#ffffff",
            insertbackground="#ffffff",
            font=("Segoe UI", 11),
        )
        self.entry.grid(row=2, column=0, sticky="ew", padx=(12, 6), pady=(0, 8))
        self.entry.bind("<Return>", self.on_send)
        self.entry.bind("<Up>", self.on_history_up)
        self.entry.bind("<Down>", self.on_history_down)

        self.mic_button = tk.Button(
            self,
            text="Mic",
            bg="#3a3a55",
            fg="#ffffff",
            activebackground="#555577",
            font=("Segoe UI", 10, "bold"),
            state=tk.NORMAL if self.voice_available else tk.DISABLED,
        )
        self.mic_button.grid(row=2, column=1, sticky="e", padx=(0, 6), pady=(0, 8))
        self.mic_button.bind("<ButtonPress-1>", self.on_mic_press)
        self.mic_button.bind("<ButtonRelease-1>", self.on_mic_release)

        self.send_button = tk.Button(
            self,
            text="Send",
            command=self.on_send,
            bg="#4a6cff",
            fg="#ffffff",
            activebackground="#6d83ff",
            font=("Segoe UI", 10, "bold"),
        )
        self.send_button.grid(row=2, column=2, sticky="e", padx=12, pady=(0, 8))

    def _build_status(self) -> None:
        self.status_var = tk.StringVar(value="Starting local model...")
        self.status = tk.Label(
            self,
            textvariable=self.status_var,
            anchor="w",
            bg=BG,
            fg="#a8a8c0",
            font=("Segoe UI", 9),
        )
        self.status.grid(row=3, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 8))

    def _style_combobox(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "TCombobox",
            fieldbackground=ENTRY_BG,
            background=ENTRY_BG,
            foreground="#ffffff",
            arrowcolor="#ffffff",
        )

    def _combo_labels(self) -> list[str]:
        return [f"{index}: {name}" for index, name in self._mic_choices]

    def _initial_mic_index(self) -> int | None:
        saved = self.settings.mic_device_index
        valid = {index for index, _name in self._mic_choices}
        if saved is not None and saved in valid:
            return saved
        return default_input_device_index()

    def _select_saved_mic(self) -> None:
        target = self._initial_mic_index()
        if target is None:
            return
        for label in self._combo_labels():
            if label.startswith(f"{target}:"):
                self.mic_var.set(label)
                return
        if self._combo_labels():
            self.mic_var.set(self._combo_labels()[0])

    def on_mic_selected(self, _event: tk.Event | None = None) -> None:
        label = self.mic_var.get()
        if not label or ":" not in label:
            return
        try:
            index = int(label.split(":", 1)[0])
        except ValueError:
            return
        self.settings.mic_device_index = index
        save_settings(self.settings)
        if self.voice:
            self.voice.set_device(index)
        self.set_status(f"Microphone set to {label}")
        self._sync_wake_listener()

    def print_message(self, speaker: str, message: str, speak_reply: bool = False) -> None:
        stamp = datetime.now().strftime("%H:%M")
        speaker_tag = "you" if speaker.lower() == "you" else "karina"
        self.chat_box.configure(state=tk.NORMAL)
        self.chat_box.insert(tk.END, f"{stamp}  ", "time")
        self.chat_box.insert(tk.END, f"{speaker}\n", speaker_tag)
        self.chat_box.insert(tk.END, f"{message}\n\n", "body")
        self.chat_box.configure(state=tk.DISABLED)
        self.chat_box.see(tk.END)
        if speak_reply and speaker.lower() == "karina":
            speak(message)

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _start_llm_bootstrap(self) -> None:
        def work() -> None:
            def progress(message: str) -> None:
                self.after(0, lambda msg=message: self.set_status(msg))

            available, status = ensure_local_llm(progress=progress)
            self.after(0, lambda: self._on_llm_ready(available, status))

        threading.Thread(target=work, daemon=True).start()

    def _on_llm_ready(self, available: bool, status: str) -> None:
        self.llm_available = available
        self.llm_status = status
        self.set_status(status)
        self.print_message("Karina", status if not available else f"Local chat is ready. {status}", speak_reply=True)

    def _confirm_if_needed(self, user_text: str) -> bool:
        if not self.settings.confirm_destructive:
            return True
        window_target = parse_close_window_command(user_text)
        if window_target:
            return messagebox.askyesno("Confirm", f"Close the window matching '{window_target}'?")
        if parse_close_command(user_text):
            return messagebox.askyesno("Confirm", "Close Karina?")
        return True

    def submit_command(self, text: str) -> None:
        user_text = text.strip()
        if not user_text or self._busy:
            return
        if not self._confirm_if_needed(user_text):
            self.print_message("Karina", "Okay, cancelled.")
            return

        self.print_message("You", user_text)
        self._command_history.append(user_text)
        self._history_index = len(self._command_history)
        self._set_busy(True)

        def work() -> None:
            try:
                response = get_response(user_text, self.session)
            except Exception as exc:
                error = str(exc)
                self.after(0, lambda: self._on_response_error(error))
                return
            self.after(0, lambda: self._on_response(response))

        threading.Thread(target=work, daemon=True).start()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.send_button.configure(state=state)
        if self.voice_available and not self._recording:
            self.mic_button.configure(state=state)

    def _on_response(self, response) -> None:
        self._set_busy(False)
        self.print_message("Karina", response.text, speak_reply=True)
        if response.should_close:
            self.after(200, self.quit_app)

    def _on_response_error(self, error: str) -> None:
        self._set_busy(False)
        self.print_message("Karina", f"Something went wrong: {error}")

    def on_send(self, event: tk.Event | None = None) -> str | None:
        user_text = self.entry_var.get()
        self.entry_var.set("")
        self.submit_command(user_text)
        return "break"

    def on_history_up(self, event: tk.Event) -> str:
        if not self._command_history:
            return "break"
        if self._history_index > 0:
            self._history_index -= 1
        self.entry_var.set(self._command_history[self._history_index])
        self.entry.icursor(tk.END)
        return "break"

    def on_history_down(self, event: tk.Event) -> str:
        if not self._command_history:
            return "break"
        if self._history_index < len(self._command_history) - 1:
            self._history_index += 1
            self.entry_var.set(self._command_history[self._history_index])
        else:
            self._history_index = len(self._command_history)
            self.entry_var.set("")
        self.entry.icursor(tk.END)
        return "break"

    def _set_mic_state(self, recording: bool) -> None:
        self._recording = recording
        if recording:
            self.mic_button.configure(bg="#e74c3c", activebackground="#ff6b5a", text="Rec")
            if self.wake:
                self.wake.pause()
        else:
            self.mic_button.configure(bg="#3a3a55", activebackground="#555577", text="Mic")
            if self.wake:
                self.wake.resume()

    def on_mic_press(self, event: tk.Event) -> None:
        if not self.voice_available or self._transcribing:
            return
        self._press_time = time.monotonic()
        self._hold_mode = False
        if self._hold_timer:
            self.after_cancel(self._hold_timer)
        self._hold_timer = self.after(HOLD_THRESHOLD_MS, self._start_hold_recording)

    def on_mic_release(self, event: tk.Event) -> None:
        if not self.voice_available or self._transcribing:
            return
        if self._hold_timer:
            self.after_cancel(self._hold_timer)
            self._hold_timer = None
        press_time = self._press_time
        self._press_time = None
        if press_time is None:
            return
        elapsed_ms = (time.monotonic() - press_time) * 1000
        if self._hold_mode:
            self._hold_mode = False
            self._finish_recording()
            return
        if elapsed_ms < HOLD_THRESHOLD_MS:
            if self._toggle_mode:
                self._toggle_mode = False
                self._finish_recording()
            else:
                self._toggle_mode = True
                self._start_recording()

    def _start_hold_recording(self) -> None:
        self._hold_timer = None
        self._hold_mode = True
        self._toggle_mode = False
        self._start_recording()

    def _start_recording(self) -> None:
        if not self.voice or self._recording:
            return
        try:
            self.voice.start_recording()
            self._set_mic_state(True)
        except Exception as exc:
            self.print_message("Karina", f"Could not start recording: {exc}")

    def _finish_recording(self) -> None:
        if not self.voice or not self._recording:
            return
        self._set_mic_state(False)
        self._transcribing = True

        def transcribe() -> None:
            try:
                text = self.voice.stop_recording()
            except Exception as exc:
                self.after(0, lambda: self._on_transcription_done("", str(exc)))
                return
            self.after(0, lambda: self._on_transcription_done(text, None))

        threading.Thread(target=transcribe, daemon=True).start()

    def _on_transcription_done(self, text: str, error: str | None) -> None:
        self._transcribing = False
        if error:
            self.print_message("Karina", f"Voice transcription failed: {error}")
            return
        if not text:
            self.print_message("Karina", "I didn't catch any speech.")
            return
        self.submit_command(text)

    def _sync_wake_listener(self) -> None:
        enabled = self.settings.wake_word_enabled and self.voice_available and self.voice is not None
        if not enabled:
            if self.wake:
                self.wake.stop()
                self.wake = None
            return
        if self.wake:
            self.wake.stop()
        self.wake = WakeWordListener(
            self.voice,
            on_command=lambda text: self.after(0, lambda: self.submit_command(text)),
            on_status=lambda text: self.after(0, lambda: self.set_status(text)),
        )
        self.wake.start()

    def open_settings(self) -> None:
        win = tk.Toplevel(self)
        win.title("Karina Settings")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self)

        threshold = tk.DoubleVar(value=self.settings.fuzzy_threshold)
        tts_enabled = tk.BooleanVar(value=self.settings.tts_enabled)
        wake_enabled = tk.BooleanVar(value=self.settings.wake_word_enabled)
        confirm_enabled = tk.BooleanVar(value=self.settings.confirm_destructive)
        tts_ok, tts_status = is_tts_available()

        frame = tk.Frame(win, bg=BG)
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        frame.grid_columnconfigure(1, weight=1)

        value_label = tk.Label(frame, text=f"{threshold.get():.0%}", bg=BG, fg="#c6c6e0")
        scale = tk.Scale(
            frame,
            from_=0.50,
            to=0.90,
            resolution=0.01,
            orient=tk.HORIZONTAL,
            variable=threshold,
            bg=BG,
            fg="#f7f7ff",
            highlightthickness=0,
            troughcolor=ENTRY_BG,
            command=lambda _v: value_label.configure(text=f"{threshold.get():.0%}"),
        )
        tk.Label(frame, text="Fuzzy match threshold", bg=BG, fg="#f7f7ff").grid(row=0, column=0, sticky="w", padx=12)
        scale.grid(row=0, column=1, sticky="ew", padx=12)
        value_label.grid(row=0, column=2, padx=8)

        tk.Checkbutton(
            frame, text="Speak replies (TTS)", variable=tts_enabled, bg=BG, fg="#f7f7ff",
            selectcolor=ENTRY_BG, activebackground=BG, activeforeground="#f7f7ff",
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=12)
        tk.Checkbutton(
            frame, text="Wake word (say 'hey Karina')", variable=wake_enabled, bg=BG, fg="#f7f7ff",
            selectcolor=ENTRY_BG, activebackground=BG, activeforeground="#f7f7ff",
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=12)
        tk.Checkbutton(
            frame, text="Confirm before closing windows or quitting", variable=confirm_enabled,
            bg=BG, fg="#f7f7ff", selectcolor=ENTRY_BG, activebackground=BG, activeforeground="#f7f7ff",
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=12)

        if not tts_ok:
            tk.Label(frame, text=tts_status, bg=BG, fg="#e8b4b4", wraplength=420, justify="left").grid(
                row=4, column=0, columnspan=3, sticky="w", padx=12
            )

        def save() -> None:
            self.settings = Settings(
                fuzzy_threshold=float(threshold.get()),
                tts_enabled=bool(tts_enabled.get()),
                wake_word_enabled=bool(wake_enabled.get()),
                confirm_destructive=bool(confirm_enabled.get()),
                mic_device_index=self.settings.mic_device_index,
            )
            save_settings(self.settings)
            self._sync_wake_listener()
            self.set_status(f"Settings saved. Fuzzy match {self.settings.fuzzy_threshold:.0%}.")
            win.destroy()

        tk.Button(
            frame, text="Save", command=save, bg="#4a6cff", fg="#ffffff",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=5, column=0, columnspan=3, pady=12)

    def show_from_tray(self) -> None:
        self.after(0, self._restore_window)

    def _restore_window(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def on_close_window(self) -> None:
        if self.tray and not self._quitting:
            self.withdraw()
            self.set_status("Karina is in the tray. Ctrl+Shift+K to show.")
            return
        self.quit_app()

    def quit_app(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        if self.wake:
            self.wake.stop()
        if self.tray:
            self.tray.stop()
        self.destroy()


def main() -> None:
    app = KarinaUI()
    app.mainloop()


if __name__ == "__main__":
    main()
