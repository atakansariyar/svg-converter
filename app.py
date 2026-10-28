"""SVG Dönüştürücü - dosya seçimli arayüz (Windows / macOS)."""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import convert

FILETYPES = [("PDF ve görseller", "*.pdf *.png *.jpg *.jpeg"), ("Tümü", "*.*")]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SVG Dönüştürücü")
        self.geometry("560x430")
        self.minsize(520, 400)
        self.files: list[Path] = []
        self.out_dir: Path | None = None
        self.busy = False

        pad = {"padx": 12, "pady": 6}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=6, pady=6)

        # Dosya listesi
        ttk.Label(frm, text="Dosyalar (PDF / PNG / JPG)").pack(anchor="w", **pad)
        row = ttk.Frame(frm)
        row.pack(fill="both", expand=True, padx=12)
        self.listbox = tk.Listbox(row, height=6, selectmode="extended")
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(row, command=self.listbox.yview)
        sb.pack(side="left", fill="y")
        self.listbox.config(yscrollcommand=sb.set)
        btns = ttk.Frame(row)
        btns.pack(side="left", padx=(8, 0), anchor="n")
        ttk.Button(btns, text="Dosya Seç...", command=self.add_files).pack(fill="x")
        ttk.Button(btns, text="Kaldır", command=self.remove_selected).pack(fill="x", pady=4)
        ttk.Button(btns, text="Temizle", command=self.clear).pack(fill="x")

        # Çıktı klasörü
        orow = ttk.Frame(frm)
        orow.pack(fill="x", **pad)
        ttk.Label(orow, text="Kayıt yeri:").pack(side="left")
        self.out_var = tk.StringVar(value="Girdi dosyasının yanına")
        ttk.Label(orow, textvariable=self.out_var, foreground="#555").pack(
            side="left", padx=6, fill="x", expand=True)
        ttk.Button(orow, text="Klasör Seç...", command=self.choose_out).pack(side="right")

        # Ayarlar
        sett = ttk.LabelFrame(frm, text="Ayarlar")
        sett.pack(fill="x", **pad)
        self.smooth = tk.IntVar(value=convert.SMOOTH)
        self.thresh = tk.IntVar(value=convert.LINE_THRESHOLD)
        self._slider(sett, "Yumuşatma (0-10)", self.smooth, 0, 10)
        self._slider(sett, "Çizgi eşiği (koyuluk)", self.thresh, 20, 220)

        self.force_scan = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            sett, text="PDF'i taranmış görüntü gibi işle (zorla)",
            variable=self.force_scan).pack(anchor="w", padx=8, pady=(0, 6))

        # Çalıştır
        self.btn = ttk.Button(frm, text="SVG'ye Dönüştür", command=self.start)
        self.btn.pack(fill="x", **pad)
        self.status = tk.StringVar(value="Hazır.")
        ttk.Label(frm, textvariable=self.status, foreground="#555").pack(anchor="w", padx=12)
        self.prog = ttk.Progressbar(frm, mode="determinate")
        self.prog.pack(fill="x", padx=12, pady=(2, 8))

    def _slider(self, parent, text, var, lo, hi):
        r = ttk.Frame(parent)
        r.pack(fill="x", padx=8, pady=4)
        ttk.Label(r, text=text, width=22).pack(side="left")
        val = ttk.Label(r, width=4, text=str(var.get()))
        ttk.Scale(
            r, from_=lo, to=hi, variable=var,
            command=lambda v: (var.set(round(float(v))), val.config(text=str(var.get()))),
        ).pack(side="left", fill="x", expand=True)
        val.pack(side="left", padx=6)

    # --- dosya işlemleri ---
    def add_files(self):
        for p in filedialog.askopenfilenames(title="Dosya seç", filetypes=FILETYPES):
            path = Path(p)
            if path not in self.files:
                self.files.append(path)
                self.listbox.insert("end", str(path))

    def remove_selected(self):
        for i in reversed(self.listbox.curselection()):
            self.listbox.delete(i)
            del self.files[i]

    def clear(self):
        self.listbox.delete(0, "end")
        self.files.clear()

    def choose_out(self):
        d = filedialog.askdirectory(title="Kayıt klasörü")
        if d:
            self.out_dir = Path(d)
            self.out_var.set(d)

    # --- dönüştürme ---
    def start(self):
        if self.busy:
            return
        if not self.files:
            messagebox.showinfo("Dosya yok", "Önce dönüştürülecek dosya seçin.")
            return
        convert.SMOOTH = int(self.smooth.get())
        convert.LINE_THRESHOLD = int(self.thresh.get())
        self.busy = True
        self.btn.config(state="disabled")
        self.prog.config(value=0, maximum=len(self.files))
        threading.Thread(target=self.work, args=(list(self.files), self.force_scan.get()),
                         daemon=True).start()

    def work(self, files, force_scan):
        errors = []
        for n, f in enumerate(files, 1):
            self.after(0, self.status.set, f"({n}/{len(files)}) {f.name} işleniyor...")
            try:
                out_dir = self.out_dir or f.parent
                if f.suffix.lower() == ".pdf":
                    convert.pdf_to_svg(f, out_dir, force_scan)
                else:
                    convert.img_to_svg(f, out_dir)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{f.name}: {e}")
            self.after(0, self.prog.config, {"value": n})
        self.after(0, self.done, errors)

    def done(self, errors):
        self.busy = False
        self.btn.config(state="normal")
        if errors:
            self.status.set("Bazı dosyalarda hata oluştu.")
            messagebox.showerror("Hata", "\n".join(errors))
        else:
            self.status.set("Tamamlandı.")
            messagebox.showinfo("Bitti", "Dönüştürme tamamlandı.")


if __name__ == "__main__":
    App().mainloop()
