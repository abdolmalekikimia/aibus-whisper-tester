"""Tkinter desktop client for manually testing AI Bus Whisper and quotas."""

from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from client import ApiBusClient, ApiResponse, NetworkError


DEFAULT_URL = "https://example.invalid"
HISTORY_PATH = Path(__file__).with_name("history.jsonl")


class WhisperTester(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AI Bus - Whisper API Tester")
        self.geometry("920x760")
        self.minsize(780, 640)

        self.base_url_var = tk.StringVar(value=DEFAULT_URL)
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.api_key_var = tk.StringVar()
        self.audio_path_var = tk.StringVar()
        self.model_var = tk.StringVar(value="whisper-1")
        self.language_var = tk.StringVar(value="fa")
        self.max_attempts_var = tk.StringVar(value="30")
        self.ignore_ssl_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="وارد شوید تا درخواست آزمایشی بفرستید.")

        self.client: ApiBusClient | None = None
        self.client_config: tuple[str, bool] | None = None
        self.busy = False
        self.ui_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._build_ui()
        self.after(100, self._drain_queue)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)

        ttk.Label(root, text="AI Bus Whisper API Tester", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10)
        )
        ttk.Label(
            root,
            text="کلیدها فقط در همین اجرا نگه داشته می‌شوند و داخل تاریخچه ذخیره نمی‌شوند.",
            foreground="#555555",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 12))

        self._entry_row(root, 2, "آدرس پایه", self.base_url_var)
        self._entry_row(root, 3, "نام کاربری", self.username_var)
        self._entry_row(root, 4, "رمز عبور", self.password_var, show="*")
        self._entry_row(root, 5, "AI Bus API Key", self.api_key_var, show="*")

        ttk.Label(root, text="SSL", foreground="#555555").grid(row=6, column=0, sticky="e", padx=(0, 10))
        ttk.Checkbutton(
            root,
            text="نادیده‌گرفتن خطای SSL برای سرور آزمایشی خودامضا",
            variable=self.ignore_ssl_var,
        ).grid(row=6, column=1, sticky="w", pady=4)

        self.login_button = ttk.Button(root, text="۱) ورود و دریافت توکن نشست", command=self.login)
        self.login_button.grid(row=7, column=1, sticky="w", pady=(8, 12))
        ttk.Separator(root).grid(row=8, column=0, columnspan=3, sticky="ew", pady=(0, 10))

        audio_frame = ttk.Frame(root)
        audio_frame.grid(row=9, column=0, columnspan=3, sticky="ew", pady=4)
        audio_frame.columnconfigure(1, weight=1)
        ttk.Label(audio_frame, text="فایل صوتی").grid(row=0, column=0, sticky="e", padx=(0, 10))
        ttk.Entry(audio_frame, textvariable=self.audio_path_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(audio_frame, text="انتخاب فایل", command=self.choose_audio).grid(row=0, column=2, padx=(8, 0))

        options = ttk.Frame(root)
        options.grid(row=10, column=0, columnspan=3, sticky="ew", pady=5)
        ttk.Label(options, text="مدل").pack(side="left")
        ttk.Entry(options, textvariable=self.model_var, width=18).pack(side="left", padx=(6, 16))
        ttk.Label(options, text="زبان").pack(side="left")
        ttk.Entry(options, textvariable=self.language_var, width=8).pack(side="left", padx=(6, 16))
        ttk.Label(options, text="حداکثر درخواست در حلقه").pack(side="left")
        ttk.Entry(options, textvariable=self.max_attempts_var, width=8).pack(side="left", padx=(6, 0))

        actions = ttk.Frame(root)
        actions.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(8, 8))
        self.send_button = ttk.Button(actions, text="۲) ارسال یک درخواست", command=self.send_once)
        self.send_button.pack(side="left")
        self.loop_button = ttk.Button(
            actions, text="ارسال تکراری تا اولین خطا / رسیدن به سقف", command=self.run_until_blocked
        )
        self.loop_button.pack(side="left", padx=8)
        ttk.Button(actions, text="پاک‌کردن پاسخ", command=self.clear_output).pack(side="right")

        ttk.Label(root, textvariable=self.status_var, foreground="#333333").grid(
            row=12, column=0, columnspan=3, sticky="w", pady=(0, 5)
        )
        output_frame = ttk.Frame(root)
        output_frame.grid(row=13, column=0, columnspan=3, sticky="nsew")
        root.rowconfigure(13, weight=1)
        output_frame.rowconfigure(0, weight=1)
        output_frame.columnconfigure(0, weight=1)
        self.output = tk.Text(output_frame, wrap="word", height=18, font=("Consolas", 10))
        scrollbar = ttk.Scrollbar(output_frame, orient="vertical", command=self.output.yview)
        self.output.configure(yscrollcommand=scrollbar.set)
        self.output.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        ttk.Label(
            root,
            text="قبل از اجرای حلقه، در پنل AI Bus سهمیه‌ای کم و مختص برنامهٔ آزمایشی بسازید.",
            foreground="#8a4b00",
        ).grid(row=14, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def _entry_row(
        self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, show: str | None = None
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="e", padx=(0, 10), pady=3)
        entry = ttk.Entry(parent, textvariable=variable, show=show or "")
        entry.grid(
            row=row, column=1, sticky="ew", pady=3
        )
        ttk.Button(
            parent,
            text="چسباندن",
            command=lambda: self._paste_into(variable, label),
        ).grid(row=row, column=2, sticky="e", padx=(8, 0), pady=3)

        # Keep paste reliable on Windows (including masked password fields), even
        # when the active Tk theme does not provide the usual Entry bindings.
        def paste(_event: tk.Event | None = None) -> str:
            try:
                value = entry.clipboard_get()
            except tk.TclError:
                return "break"
            if entry.selection_present():
                entry.delete("sel.first", "sel.last")
            entry.insert("insert", value)
            return "break"

        def select_all(_event: tk.Event | None = None) -> str:
            entry.selection_range(0, "end")
            entry.icursor("end")
            return "break"

        entry.bind("<Control-v>", paste)
        entry.bind("<Control-V>", paste)
        entry.bind("<Shift-Insert>", paste)
        entry.bind("<Control-a>", select_all)
        entry.bind("<Control-A>", select_all)

        context_menu = tk.Menu(entry, tearoff=False)
        context_menu.add_command(label="Paste", command=paste)
        context_menu.add_command(label="Select all", command=select_all)

        def show_context_menu(event: tk.Event) -> str:
            entry.focus_set()
            context_menu.tk_popup(event.x_root, event.y_root)
            return "break"

        entry.bind("<Button-3>", show_context_menu)

    def _paste_into(self, variable: tk.StringVar, label: str) -> None:
        """Paste directly into a field without depending on keyboard focus bindings."""
        try:
            value = self.clipboard_get()
        except tk.TclError:
            messagebox.showwarning("کلیپ‌بورد", "متن قابل چسباندنی در کلیپ‌بورد پیدا نشد.")
            return
        variable.set(value.rstrip("\r\n"))
        self.status_var.set(f"متن کلیپ‌بورد در فیلد «{label}» قرار گرفت.")

    def _get_client(self) -> ApiBusClient:
        base_url = self.base_url_var.get().strip()
        if not base_url:
            raise ValueError("آدرس پایه را وارد کنید.")
        verify_tls = not self.ignore_ssl_var.get()
        current = (base_url.rstrip("/"), verify_tls)
        if self.client is None or self.client_config != current:
            self.client = ApiBusClient(base_url, verify_tls=verify_tls)
            self.client_config = current
        return self.client

    def login(self) -> None:
        username, password = self.username_var.get().strip(), self.password_var.get()
        if not username or not password:
            messagebox.showwarning("اطلاعات ورود", "نام کاربری و رمز عبور را وارد کنید.")
            return
        self._start_worker(self._login_worker, username, password)

    def _login_worker(self, username: str, password: str) -> None:
        try:
            client = self._get_client()
            response = client.login(username, password)
            self.ui_queue.put(("login", (response, bool(client.session_token))))
        except NetworkError as exc:
            self.ui_queue.put(("error", f"خطای شبکه یا SSL هنگام ورود: {exc}"))
        except Exception as exc:
            self.ui_queue.put(("error", str(exc)))

    def choose_audio(self) -> None:
        path = filedialog.askopenfilename(
            title="انتخاب فایل صوتی",
            filetypes=[("Audio files", "*.wav *.mp3 *.m4a *.ogg *.webm *.mp4 *.mpeg *.mpga"), ("All files", "*.*")],
        )
        if path:
            self.audio_path_var.set(path)

    def _validate_transcription(self) -> tuple[ApiBusClient, str, str, str, str]:
        client = self._get_client()
        if not client.session_token:
            raise ValueError("اول دکمهٔ ورود را بزنید و توکن نشست بگیرید.")
        audio_path = self.audio_path_var.get().strip()
        if not audio_path:
            raise ValueError("یک فایل صوتی انتخاب کنید.")
        if not self.api_key_var.get().strip():
            raise ValueError("AI Bus API Key را وارد کنید.")
        return client, audio_path, self.api_key_var.get(), self.model_var.get().strip() or "whisper-1", self.language_var.get().strip() or "fa"

    def send_once(self) -> None:
        try:
            args = self._validate_transcription()
        except Exception as exc:
            messagebox.showwarning("درخواست ناقص", str(exc))
            return
        self._start_worker(self._send_once_worker, *args)

    def _send_once_worker(self, client: ApiBusClient, audio_path: str, api_key: str, model: str, language: str) -> None:
        try:
            response = client.transcribe(audio_path, api_key, model, language)
            self.ui_queue.put(("single_response", (1, response, Path(audio_path).name)))
        except NetworkError as exc:
            self.ui_queue.put(("error", f"خطای شبکه هنگام ارسال فایل: {exc}"))
        except Exception as exc:
            self.ui_queue.put(("error", str(exc)))

    def run_until_blocked(self) -> None:
        try:
            args = self._validate_transcription()
            max_attempts = int(self.max_attempts_var.get())
            if not 1 <= max_attempts <= 200:
                raise ValueError("حداکثر درخواست باید بین ۱ تا ۲۰۰ باشد.")
        except Exception as exc:
            messagebox.showwarning("تنظیمات حلقه", str(exc))
            return
        self._start_worker(self._loop_worker, *args, max_attempts)

    def _loop_worker(
        self, client: ApiBusClient, audio_path: str, api_key: str, model: str, language: str, max_attempts: int
    ) -> None:
        for index in range(1, max_attempts + 1):
            try:
                response = client.transcribe(audio_path, api_key, model, language)
                self.ui_queue.put(("response", (index, response, Path(audio_path).name)))
                if not response.ok or not self._payload_completed(response):
                    self.ui_queue.put(("loop_end", f"حلقه در درخواست {index} متوقف شد؛ پاسخ موفق نبود."))
                    return
                time.sleep(0.25)
            except NetworkError as exc:
                self.ui_queue.put(("loop_end", f"حلقه در درخواست {index} متوقف شد: {exc}"))
                return
            except Exception as exc:
                self.ui_queue.put(("loop_end", f"حلقه متوقف شد: {exc}"))
                return
        self.ui_queue.put(("loop_end", f"حداکثر {max_attempts} درخواست انجام شد؛ خطایی دریافت نشد."))

    @staticmethod
    def _payload_completed(response: ApiResponse) -> bool:
        try:
            data = response.json()
        except ValueError:
            return response.ok
        if not isinstance(data, dict):
            return response.ok
        return response.ok and data.get("processing_status") not in {"failed", "error"} and not data.get("error_code")

    def _start_worker(self, target: Any, *args: Any) -> None:
        if self.busy:
            return
        self.busy = True
        self._set_buttons("disabled")
        self.status_var.set("در حال ارسال درخواست...")
        threading.Thread(target=target, args=args, daemon=True).start()

    def _set_buttons(self, state: str) -> None:
        for button in (self.login_button, self.send_button, self.loop_button):
            button.configure(state=state)

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "login":
                    response, token_found = payload
                    self._append_response(0, response, "login")
                    if response.ok and token_found:
                        self.status_var.set("ورود موفق شد؛ توکن نشست فقط در حافظه نگه‌داری شد.")
                    elif response.ok:
                        self.status_var.set("ورود موفق بود، اما کوکی aibus_admin پیدا نشد.")
                    else:
                        self.status_var.set(f"ورود ناموفق بود: HTTP {response.status_code}")
                    self._finish_worker()
                elif kind == "single_response":
                    index, response, filename = payload
                    self._append_response(index, response, filename)
                    self.status_var.set(f"درخواست {index}: HTTP {response.status_code}")
                    self._finish_worker()
                elif kind == "response":
                    index, response, filename = payload
                    self._append_response(index, response, filename)
                    self.status_var.set(f"درخواست {index}: HTTP {response.status_code}")
                elif kind == "loop_end":
                    self.status_var.set(payload)
                    self._append_text(f"\n{payload}\n")
                    self._finish_worker()
                elif kind == "error":
                    self._append_text(f"\nخطا: {payload}\n")
                    self.status_var.set("درخواست با خطا متوقف شد.")
                    self._finish_worker()
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)

    def _append_response(self, index: int, response: ApiResponse, label: str) -> None:
        try:
            body: Any = response.json()
            body_text = json.dumps(body, ensure_ascii=False, indent=2)
        except ValueError:
            body = None
            body_text = response.text
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        self._append_text(f"\n[{timestamp}] {label} | درخواست {index or '-'} | HTTP {response.status_code}\n{body_text}\n")
        if label != "login":
            usage = body.get("usage") if isinstance(body, dict) else None
            record = {
                "timestamp": timestamp,
                "request_number": index,
                "audio_file": label,
                "http_status": response.status_code,
                "processing_status": body.get("processing_status") if isinstance(body, dict) else None,
                "usage": usage,
                "tokens_consumed": body.get("tokens_consumed") if isinstance(body, dict) else None,
                "error_code": body.get("error_code") if isinstance(body, dict) else None,
            }
            try:
                with HISTORY_PATH.open("a", encoding="utf-8") as history:
                    history.write(json.dumps(record, ensure_ascii=False) + "\n")
            except OSError as exc:
                self._append_text(f"هشدار: ذخیرهٔ تاریخچه ممکن نشد: {exc}\n")

    def _append_text(self, text: str) -> None:
        self.output.insert("end", text)
        self.output.see("end")

    def clear_output(self) -> None:
        self.output.delete("1.0", "end")

    def _finish_worker(self) -> None:
        self.busy = False
        self._set_buttons("normal")


def main() -> None:
    WhisperTester().mainloop()


if __name__ == "__main__":
    main()
