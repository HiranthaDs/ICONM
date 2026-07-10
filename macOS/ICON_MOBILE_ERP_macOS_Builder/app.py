import os
import sys
import subprocess
import traceback
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from pathlib import Path
from urllib.parse import quote
from datetime import datetime

from config import (
    APP_NAME,
    APP_VERSION,
    PRODUCT_TYPES,
    CONDITIONS,
    GENERAL_WARRANTIES,
    PAYMENT_METHODS,
    EXTENDED_WARRANTIES,
    LOG_DIR,
    SYNC_PASSWORD,
    ADMIN_DEFAULT_PASSWORD,
    STAFF_DEFAULT_PASSWORD,
)
from database import init_db, get_setting, set_setting, query, query_one
from services import (
    authenticate,
    change_password,
    add_product,
    create_product_group,
    list_suppliers,
    update_product,
    set_product_offer,
    restock_product,
    delete_product,
    search_products,
    available_units,
    restock_history,
    create_retail_invoice,
    set_invoice_pdf,
    list_invoices,
    get_invoice,
    delete_invoice,
    add_shop,
    list_shops,
    create_wholesale_invoice,
    set_wholesale_pdf,
    add_wholesale_payment,
    shop_profile,
    financial_dashboard,
    staff_sold_items_month,
    export_backup,
    restore_backup,
    backup_due,
    client_statement_text,
    shop_statement_text,
    normalize_phone,
    product_display_name,
    money,
    n,
    i,
    warranty_days,
    date_add,
    generate_internal_ids,
    product_unit_history,
    product_supplier_summary,
    stock_detail_rows)
from pdf_utils import build_retail_invoice_pdf, build_wholesale_invoice_pdf, build_shop_statement_pdf
import lan_sync


class UI:
    # Apple/macOS inspired palette
    BG = "#f5f5f7"
    SURFACE = "#ffffff"
    CARD = "#fbfbfd"
    MUTED_BG = "#f2f2f7"
    TEXT = "#1d1d1f"
    MUTED = "#6e6e73"
    BORDER = "#d2d2d7"
    BLUE = "#007aff"
    BLUE_DARK = "#005ecb"
    GREEN = "#34c759"
    RED = "#ff3b30"
    AMBER = "#ff9500"
    SIDEBAR = "#ececf1"


def safe_run(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PermissionError as e:
            messagebox.showwarning("Admin Required", str(e))
        except Exception as e:
            LOG_DIR.mkdir(exist_ok=True)
            (LOG_DIR / "startup_error.log").write_text(traceback.format_exc(),
                                                       encoding="utf-8")
            messagebox.showerror(
                "System Error",
                f"{e}\n\nFull error saved in logs/startup_error.log")
    return wrapper


def open_file(path):
    if not path:
        messagebox.showwarning("Missing file", "No saved PDF/path found.")
        return
    p = Path(path)
    if not p.exists():
        messagebox.showwarning("File not found", str(p))
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(p)], check=False)
        else:
            webbrowser.open(p.as_uri())
    except Exception:
        webbrowser.open(p.as_uri())


def open_parent_select(path):
    if not path:
        return
    p = Path(path)
    try:
        if sys.platform.startswith("win"):
            subprocess.run(["explorer", f"/select,{p}"], check=False)
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", str(p)], check=False)
        else:
            webbrowser.open(p.parent.as_uri())
    except Exception:
        try:
            webbrowser.open(p.parent.as_uri())
        except Exception:
            pass


def safe_filename(value: str) -> str:
    raw = str(value or "").strip() or "file"
    return "".join(
        ch if ch.isalnum() or ch in (
            "-",
            "_",
            " ") else "_" for ch in raw).strip().replace(
        " ",
        "_")[
                :80]


def mac_card(parent, title=None, padding=14):
    frame = tk.Frame(
        parent,
        bg=UI.SURFACE,
        highlightbackground=UI.BORDER,
        highlightthickness=1,
        bd=0)
    inner = tk.Frame(frame, bg=UI.SURFACE)
    inner.pack(fill="both", expand=True, padx=padding, pady=padding)
    if title:
        tk.Label(
            inner,
            text=title,
            bg=UI.SURFACE,
            fg=UI.TEXT,
            font=(
                "Segoe UI",
                12,
                "bold")).pack(
            anchor="w",
            pady=(
                0,
                8))
    return frame, inner


def whatsapp_send(phone, text, pdf_path=""):
    number = normalize_phone(phone)
    if not number:
        messagebox.showwarning(
            "Missing WhatsApp",
            "WhatsApp number is missing.")
        return
    webbrowser.open(f"https://wa.me/{number}?text={quote(text)}")
    if pdf_path:
        open_parent_select(pdf_path)
        messagebox.showinfo(
            "Attach PDF",
            "WhatsApp opened with the message. The PDF file is selected/opened so you can attach and send it.")


class ScrollFrame(tk.Frame):
    def __init__(self, parent, bg=UI.BG):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self.vsb = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview)
        self.content = tk.Frame(self.canvas, bg=bg)
        self.window = self.canvas.create_window(
            (0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.content.bind(
            "<Configure>", lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")))
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(
                self.window,
                width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.canvas.bind_all("<Button-4>", self._on_mousewheel, add="+")
        self.canvas.bind_all("<Button-5>", self._on_mousewheel, add="+")
        self._inside = False
        self.canvas.bind("<Enter>", lambda e: setattr(self, "_inside", True))
        self.canvas.bind("<Leave>", lambda e: setattr(self, "_inside", False))
        # Bottom safety padding so buttons are not cropped on smaller screens.
        self._bottom_pad = tk.Frame(self.content, bg=bg, height=64)
        self._bottom_pad.pack(fill="x", side="bottom")

    def _on_mousewheel(self, event):
        # Canvas <Enter>/<Leave> is unreliable for embedded child widgets: the
        # canvas can receive Leave as soon as the pointer reaches an Entry,
        # Treeview or Button.  Pointer bounds keep scrolling active anywhere
        # inside this complete panel, including all nested controls.
        try:
            px, py = self.winfo_pointerxy()
            x0, y0 = self.winfo_rootx(), self.winfo_rooty()
            inside = x0 <= px < x0 + self.winfo_width() and y0 <= py < y0 + \
                self.winfo_height()
        except tk.TclError:
            inside = False
        if not inside:
            return
        if hasattr(event, "num") and event.num == 4:
            self.canvas.yview_scroll(-3, "units")
        elif hasattr(event, "num") and event.num == 5:
            self.canvas.yview_scroll(3, "units")
        else:
            delta = event.delta
            # macOS trackpads can send small deltas; normalize them.
            step = -1 if delta > 0 else 1
            if abs(delta) >= 120:
                step = int(-1 * (delta / 120))
            self.canvas.yview_scroll(step, "units")


class PaymentEditor(ttk.LabelFrame):
    def __init__(self, parent, title="Payment Breakdown", on_change=None):
        super().__init__(parent, text=title, padding=8)
        self.rows = []
        self.on_change = on_change
        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Label(
            header,
            text="Method",
            width=16).grid(
            row=0,
            column=0,
            sticky="w")
        ttk.Label(
            header,
            text="Amount",
            width=14).grid(
            row=0,
            column=1,
            sticky="w")
        ttk.Label(
            header,
            text="Ref / Custom",
            width=18).grid(
            row=0,
            column=2,
            sticky="w")
        ttk.Button(
            header,
            text="+ Add Payment",
            command=self.add_row).grid(
            row=0,
            column=3,
            padx=6)
        self.rows_frame = ttk.Frame(self)
        self.rows_frame.pack(fill="x", pady=(6, 0))
        self.total_var = tk.StringVar(value="Total Paid: Rs. 0")
        ttk.Label(
            self,
            textvariable=self.total_var,
            font=(
                "Segoe UI",
                10,
                "bold")).pack(
            anchor="e",
            pady=(
                6,
                0))
        self.add_row("Cash", "0", "")

    def add_row(self, method="Cash", amount="0", ref=""):
        rowf = ttk.Frame(self.rows_frame)
        rowf.pack(fill="x", pady=2)
        m = tk.StringVar(value=method)
        a = tk.StringVar(value=str(amount))
        r = tk.StringVar(value=ref)
        cmb = ttk.Combobox(
            rowf,
            textvariable=m,
            values=PAYMENT_METHODS,
            state="readonly",
            width=15)
        cmb.grid(row=0, column=0, padx=2)
        ent = ttk.Entry(rowf, textvariable=a, width=14)
        ent.grid(row=0, column=1, padx=2)
        refent = ttk.Entry(rowf, textvariable=r, width=20)
        refent.grid(row=0, column=2, padx=2)

        def remove():
            rowf.destroy()
            self.rows[:] = [x for x in self.rows if x["frame"] != rowf]
            self._update_total()
        ttk.Button(
            rowf,
            text="Remove",
            command=remove).grid(
            row=0,
            column=3,
            padx=2)
        a.trace_add("write", lambda *_: self._update_total())
        m.trace_add("write", lambda *_: self._update_total())
        r.trace_add("write", lambda *_: self._update_total())
        self.rows.append({"frame": rowf, "method": m,
                         "amount": a, "reference": r})
        self._update_total()

    def _update_total(self):
        self.total_var.set(f"Total Paid: {money(self.total())}")
        if self.on_change:
            # Run after Tk has committed the edited StringVar.  Calling the
            # bill refresh directly from a variable trace could read the
            # previous character on some Tk builds and left wholesale totals
            # looking stale.
            self.after_idle(self.on_change)

    def total(self):
        return sum(n(r["amount"].get()) for r in self.rows)

    def get_rows(self):
        out = []
        for r in self.rows:
            amount = n(r["amount"].get())
            if amount <= 0:
                continue
            method = r["method"].get()
            ref = r["reference"].get()
            custom = ref if method == "Custom" else ""
            if method == "Custom" and not custom:
                custom = "Custom Payment"
            out.append({"method": method, "amount": amount,
                       "reference": ref, "custom_method": custom})
        return out

    def clear(self):
        for r in list(self.rows):
            r["frame"].destroy()
        self.rows.clear()
        self.add_row("Cash", "0", "")

    def set_rows(self, rows):
        for r in list(self.rows):
            r["frame"].destroy()
        self.rows.clear()
        for row in rows or []:
            self.add_row(
                row.get(
                    "method", "Cash"), row.get(
                    "amount", "0"), row.get(
                    "reference", ""))
        if not self.rows:
            self.add_row("Cash", "0", "")


class LoginWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} Login")
        self.geometry("460x520")
        self.configure(bg=UI.BG)
        self.resizable(False, False)
        self.style_all()
        card = tk.Frame(
            self,
            bg=UI.SURFACE,
            highlightbackground=UI.BORDER,
            highlightthickness=1)
        card.place(relx=0.5, rely=0.5, anchor="center", width=380, height=420)
        tk.Label(
            card,
            text="ICON MOBILE",
            bg=UI.SURFACE,
            fg=UI.TEXT,
            font=(
                "Segoe UI",
                24,
                "bold")).pack(
            pady=(
                35,
                5))
        tk.Label(
            card,
            text="Real-world ERP System",
            bg=UI.SURFACE,
            fg=UI.MUTED,
            font=(
                "Segoe UI",
                10)).pack(
            pady=(
                0,
                25))
        self.user = tk.StringVar(value="admin")
        self.password = tk.StringVar()
        self._entry(card, "Username", self.user)
        self._entry(card, "Password", self.password, show="*")
        ttk.Button(
            card,
            text="Login",
            command=self.login).pack(
            fill="x",
            padx=45,
            pady=(
                20,
                8),
            ipady=6)
        tk.Label(
            card,
            text=f"Admin: {ADMIN_DEFAULT_PASSWORD}  |  Staff: {STAFF_DEFAULT_PASSWORD}",
            bg=UI.SURFACE,
            fg=UI.MUTED,
            font=(
                "Segoe UI",
                8)).pack(
            pady=8)
        self.bind("<Return>", lambda e: self.login())

    def _entry(self, parent, label, var, show=None):
        tk.Label(
            parent,
            text=label,
            bg=UI.SURFACE,
            fg=UI.MUTED,
            anchor="w",
            font=(
                "Segoe UI",
                9,
                "bold")).pack(
            fill="x",
            padx=45,
            pady=(
                8,
                 3))
        ttk.Entry(
            parent,
            textvariable=var,
            show=show,
            font=(
                "Segoe UI",
                12)).pack(
            fill="x",
            padx=45,
            ipady=7)

    def style_all(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure("TButton", font=("Segoe UI", 10, "bold"), padding=7)
        s.configure("TEntry", padding=6)

    def login(self):
        user = authenticate(self.user.get(), self.password.get())
        if not user:
            messagebox.showerror(
                "Login failed",
                "Invalid username or password")
            return
        self.destroy()
        app = ERPApp(user)
        app.mainloop()


class ERPApp(tk.Tk):
    def __init__(self, user):
        super().__init__()
        self.user = user
        self.title(f"{APP_NAME} - {APP_VERSION}")
        self.geometry("1440x900")
        # Remains usable on 1366x768 laptops and smaller remote-desktop views.
        self.minsize(960, 620)
        self.configure(bg=UI.BG)
        self.cart = []
        self.wh_cart = []
        self.selected_product_id = None
        self.selected_invoice_id = None
        self.selected_shop_id = None
        self.selected_wh_invoice_id = None
        self.sync_after_id = None
        self.style_all()
        self.build_layout()
        self.refresh_all()
        if backup_due():
            self.after(
                800,
                lambda: messagebox.showinfo(
                    "Weekly Backup Reminder",
                    "Please create a weekly backup from Sync & Backup tab. Real-world company data must be backed up weekly."))

    def style_all(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except Exception:
            pass
        default_font = ("Segoe UI", 10)
        s.configure("TFrame", background=UI.BG)
        s.configure("Card.TFrame", background=UI.SURFACE, relief="flat")
        s.configure(
            "TNotebook",
            background=UI.BG,
            borderwidth=0,
            tabmargins=(
                8,
                8,
                8,
                0))
        s.configure(
            "TNotebook.Tab",
            padding=(
                18,
                10),
            font=(
                "Segoe UI",
                10,
                "bold"),
            background=UI.MUTED_BG,
            foreground=UI.MUTED,
            borderwidth=0)
        s.map(
            "TNotebook.Tab", background=[
                ("selected", UI.SURFACE)], foreground=[
                ("selected", UI.TEXT)])
        s.configure(
            "Treeview",
            rowheight=34,
            font=(
                "Segoe UI",
                9),
            background="white",
            fieldbackground="white",
            foreground=UI.TEXT,
            borderwidth=0)
        s.configure(
            "Treeview.Heading",
            font=(
                "Segoe UI",
                9,
                "bold"),
            background=UI.MUTED_BG,
            foreground=UI.TEXT,
            padding=(
                8,
                8),
            borderwidth=0)
        s.map(
            "Treeview", background=[
                ("selected", "#dbeafe")], foreground=[
                ("selected", UI.TEXT)])
        s.configure(
            "TButton",
            font=(
                "Segoe UI",
                9,
                "bold"),
            padding=(
                12,
                8),
            background=UI.SURFACE,
            foreground=UI.TEXT,
            borderwidth=1,
            focusthickness=0)
        s.map("TButton", background=[("active", "#f2f2f7")])
        s.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(
            14, 10), background=UI.BLUE, foreground="white", borderwidth=0)
        s.map(
            "Accent.TButton", background=[
                ("active", UI.BLUE_DARK)], foreground=[
                ("active", "white")])
        s.configure(
            "Danger.TButton",
            font=(
                "Segoe UI",
                9,
                "bold"),
            background="#fff1f2",
            foreground=UI.RED)
        s.configure(
            "TLabel",
            font=default_font,
            background=UI.BG,
            foreground=UI.TEXT)
        s.configure(
            "Muted.TLabel",
            font=(
                "Segoe UI",
                9),
            foreground=UI.MUTED,
            background=UI.BG)
        s.configure(
            "Title.TLabel",
            font=(
                "Segoe UI",
                18,
                "bold"),
            foreground=UI.TEXT,
            background=UI.BG)
        s.configure(
            "TLabelframe",
            background=UI.BG,
            bordercolor=UI.BORDER,
            relief="solid")
        s.configure(
            "TLabelframe.Label",
            font=(
                "Segoe UI",
                10,
                "bold"),
            background=UI.BG,
            foreground=UI.TEXT)
        s.configure(
            "TEntry",
            padding=(
                8,
                7),
            fieldbackground="white",
            bordercolor=UI.BORDER)
        s.configure(
            "TCombobox",
            padding=(
                8,
                7),
            fieldbackground="white",
            bordercolor=UI.BORDER)

    def build_layout(self):
        shell = tk.Frame(self, bg=UI.BG)
        shell.pack(fill="both", expand=True)
        top = tk.Frame(
            shell,
            bg=UI.SURFACE,
            height=74,
            highlightbackground=UI.BORDER,
            highlightthickness=1)
        top.pack(fill="x")
        brand = tk.Frame(top, bg=UI.SURFACE)
        brand.pack(side="left", padx=22, pady=10)
        tk.Label(
            brand,
            text="ICON MOBILE",
            bg=UI.SURFACE,
            fg=UI.TEXT,
            font=(
                "Segoe UI",
                22,
                "bold")).pack(
            anchor="w")
        tk.Label(
            brand,
            text="macOS Style Retail + Wholesale ERP",
            bg=UI.SURFACE,
            fg=UI.MUTED,
            font=(
                "Segoe UI",
                9)).pack(
            anchor="w")
        pill = tk.Label(
            top,
            text=f"  {
                self.user['username']}  •  {
                self.user['role'].upper()}  ",
            bg=UI.MUTED_BG,
            fg=UI.TEXT,
            font=(
                "Segoe UI",
                10,
                "bold"),
            padx=12,
            pady=7)
        pill.pack(side="right", padx=22)

        self.notebook = ttk.Notebook(shell)
        self.notebook.pack(fill="both", expand=True, padx=14, pady=14)
        self.tab_billing = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_billing, text="Billing")
        self.tab_inventory = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_inventory, text="Inventory")
        self.tab_clients = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_clients, text="Clients")
        self.tab_partner = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_partner, text="Partner Shops")
        self.tab_finance = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_finance, text="Finance")
        self.tab_sync = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_sync, text="Sync & Backup")
        self.tab_settings = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_settings, text="Settings")
        self.build_billing_tab()
        self.build_inventory_tab()
        self.build_clients_tab()
        self.build_partner_tab()
        self.build_finance_tab()
        self.build_sync_tab()
        self.build_settings_tab()

    def labelled_entry(self, parent, label, var, width=22):
        f = ttk.Frame(parent)
        f.pack(fill="x", pady=3)
        ttk.Label(f, text=label, width=18).pack(side="left")
        e = ttk.Entry(f, textvariable=var, width=width)
        e.pack(side="left", fill="x", expand=True)
        return e

    def table(self, parent, columns, headings=None, height=10):
        wrap = ttk.Frame(parent)
        tree = ttk.Treeview(
            wrap,
            columns=columns,
            show="headings",
            height=height)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        numeric_cols = {
            "id",
            "qty",
            "sold",
            "wholesale",
            "price",
            "cost",
            "avg_cost",
            "unit_cost",
            "profit",
            "total",
            "paid",
            "due",
            "value",
            "stock_value"}
        wide_cols = {
            "item",
            "name",
            "client",
            "shop",
            "metric",
            "allocations",
            "description"}
        for col in columns:
            tree.heading(col, text=(headings or {}).get(col, col))
            width = 85 if col in numeric_cols else (
                220 if col in wide_cols else 120)
            tree.column(
                col,
                width=width,
                minwidth=60,
                anchor="e" if col in numeric_cols else "w",
                stretch=col in wide_cols)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        return wrap, tree

    # ---------------- Billing ----------------
    def build_billing_tab(self):
        root = tk.Frame(self.tab_billing, bg=UI.BG)
        root.pack(fill="both", expand=True)
        left_sf = ScrollFrame(root, bg=UI.BG)
        left_sf.pack(side="left", fill="both", expand=True, padx=(0, 8))
        left = left_sf.content
        right_sf = ScrollFrame(root, bg=UI.BG)
        right_sf.pack(side="right", fill="both", expand=True, padx=(8, 0))
        right = right_sf.content

        checkout_frame, checkout = mac_card(left, "Checkout Flow", padding=14)
        checkout_frame.pack(fill="x", padx=6, pady=6)
        tk.Label(
            checkout,
            text="Customer > Payment > Save PDF",
            bg=UI.SURFACE,
            fg=UI.MUTED,
            font=(
                "Segoe UI",
                9)).pack(
            anchor="w",
            pady=(
                0,
                10))

        self.bill_name = tk.StringVar()
        self.bill_phone = tk.StringVar()
        self.bill_email = tk.StringVar()
        self.labelled_entry(checkout, "Client Name", self.bill_name)
        self.labelled_entry(checkout, "WhatsApp Number", self.bill_phone)
        self.labelled_entry(checkout, "Email Optional", self.bill_email)

        # Warranty is now selected only in the per-item popup shown while
        # adding an item to cart.  These hidden defaults keep older cart code
        # safe without showing the old default-warranty controls.
        self.bill_general = tk.StringVar(value="No Warranty")
        self.bill_general_days = tk.StringVar(value="0")
        self.ext_option = tk.StringVar(value="No Extended")
        self.ext_days = tk.StringVar(value="0")
        self.ext_amount = tk.StringVar(value="0")
        self.ext_expiry_var = tk.StringVar(value="Extended expiry: -")
        self.item_warranty_note = tk.StringVar()

        payment_frame, payment_inner = mac_card(left, "Payment", padding=14)
        payment_frame.pack(fill="x", padx=6, pady=6)
        self.bill_discount = tk.StringVar(value="0")
        self.bill_note = tk.StringVar()
        self.bill_discount.trace_add("write", lambda *_: self.refresh_cart())
        self.labelled_entry(payment_inner, "Bill Discount", self.bill_discount)
        self.bill_payments = PaymentEditor(
            payment_inner, on_change=self.refresh_cart)
        self.bill_payments.pack(fill="x", pady=6)
        self.payment_total_var = tk.StringVar(
            value="Items + Extended Warranty: Rs. 0 | Paid: Rs. 0 | Remaining: Rs. 0")
        tk.Label(
            payment_inner,
            textvariable=self.payment_total_var,
            bg=UI.SURFACE,
            fg=UI.BLUE,
            font=(
                "Segoe UI",
                11,
                "bold")).pack(
            anchor="e",
            pady=(
                2,
                8))
        self.labelled_entry(payment_inner, "Invoice Note", self.bill_note)
        ttk.Button(
            payment_inner,
            text="Save Invoice + Open PDF",
            style="Accent.TButton",
            command=self.save_retail_bill).pack(
            fill="x",
            pady=(
                10,
                4),
            ipady=4)

        product_frame, products = mac_card(
            right, "Search & Add Items", padding=14)
        product_frame.pack(fill="both", expand=True, padx=6, pady=6)
        sf = ttk.Frame(products)
        sf.pack(fill="x", pady=(0, 8))
        self.pos_search = tk.StringVar()
        self.pos_type = tk.StringVar(value="All")
        pos_entry = ttk.Entry(sf, textvariable=self.pos_search)
        pos_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        pos_entry.bind("<KeyRelease>", lambda e: self.refresh_pos_products())
        ttk.Combobox(
            sf,
            textvariable=self.pos_type,
            values=["All"] +
            PRODUCT_TYPES,
            width=16,
            state="readonly").pack(
            side="left",
            padx=3)
        ttk.Button(
            sf,
            text="Search",
            command=self.refresh_pos_products).pack(
            side="left",
            padx=3)
        ttk.Button(
            sf,
            text="Quick Add by Last 5 / SKU",
            style="Accent.TButton",
            command=self.quick_add_by_search).pack(
            side="left",
            padx=3)
        ttk.Button(
            sf,
            text="Open All Items / Pick",
            command=self.open_item_picker).pack(
            side="left",
            padx=3)
        ttk.Button(
            sf,
            text="Add Direct Sale Item",
            style="Accent.TButton",
            command=self.add_direct_sale_item_to_cart).pack(
            side="left",
            padx=3)
        pos_entry.bind("<Return>", lambda e: self.quick_add_by_search())
        wrap, self.pos_tree = self.table(
            products, ["id", "sku", "type", "item", "qty", "price"], height=7)
        self.pos_tree.column("id", width=45)
        self.pos_tree.column("item", width=280)
        wrap.pack(fill="both", expand=True, pady=5)
        af = ttk.Frame(products)
        af.pack(fill="x", pady=4)
        self.cart_qty = tk.StringVar(value="1")
        self.cart_price = tk.StringVar()
        self.cart_unit = tk.StringVar()
        ttk.Label(af, text="Qty").pack(side="left")
        ttk.Entry(
            af,
            textvariable=self.cart_qty,
            width=6).pack(
            side="left",
            padx=3)
        ttk.Label(af, text="Price").pack(side="left")
        ttk.Entry(
            af,
            textvariable=self.cart_price,
            width=12).pack(
            side="left",
            padx=3)
        ttk.Label(af, text="Unit/IMEI").pack(side="left")
        ttk.Entry(
            af,
            textvariable=self.cart_unit,
            width=18).pack(
            side="left",
            padx=3)
        ttk.Button(
            af,
            text="Add to Cart",
            style="Accent.TButton",
            command=self.add_selected_to_cart).pack(
            side="left",
            padx=3)
        ttk.Button(
            af,
            text="Units",
            command=self.pick_unit_for_pos).pack(
            side="left",
            padx=3)

        cart_frame, cart = mac_card(right, "Cart Preview", padding=14)
        cart_frame.pack(fill="both", expand=True, padx=6, pady=6)
        wrap, self.cart_tree = self.table(
            cart, ["item", "unit", "qty", "price", "warranty", "ext", "total"], height=7)
        self.cart_tree.heading("warranty", text="Item Warranty")
        self.cart_tree.heading("ext", text="Ext. Warranty")
        self.cart_tree.column("item", width=260)
        self.cart_tree.column("warranty", width=210)
        wrap.pack(fill="both", expand=True)
        cf = ttk.Frame(cart)
        cf.pack(fill="x", pady=8)
        self.cart_total_var = tk.StringVar(
            value="Cart Total: Rs. 0 | Paid: Rs. 0 | Due: Rs. 0")
        tk.Label(
            cf,
            textvariable=self.cart_total_var,
            bg=UI.SURFACE,
            fg=UI.TEXT,
            font=(
                "Segoe UI",
                12,
                "bold")).pack(
            side="left")
        ttk.Button(
            cf,
            text="Remove",
            command=self.remove_cart_item).pack(
            side="right",
            padx=4)
        ttk.Button(
            cf,
            text="Edit Item Warranty",
            command=self.edit_cart_item_warranty).pack(
            side="right",
            padx=4)
        ttk.Button(
            cf,
            text="Clear",
            command=self.clear_cart).pack(
            side="right",
            padx=4)
        self.update_ext_warranty_expiry()

    def update_general_warranty_days(self):
        option = self.bill_general.get() if hasattr(
            self, "bill_general") else "No Warranty"
        days = warranty_days(option, self.bill_general_days.get())
        if option != "Manual Days" and hasattr(self, "bill_general_days"):
            self.bill_general_days.set(str(days))
        if hasattr(self, "general_manual_frame"):
            if option == "Manual Days":
                self.general_manual_frame.pack(fill="x", pady=3)
            else:
                self.general_manual_frame.pack_forget()

    def update_ext_warranty_expiry(self):
        option = self.ext_option.get() if hasattr(
            self, "ext_option") else "No Extended"
        if option == "No Extended":
            days = 0
        else:
            days = warranty_days(option, self.ext_days.get())
        if option != "Manual Days":
            self.ext_days.set(
                str(days)) if hasattr(
                self,
                "ext_days") and self.ext_days.get() != str(days) else None
        if hasattr(self, "ext_manual_frame"):
            if option == "Manual Days":
                self.ext_manual_frame.pack(fill="x", pady=3)
            else:
                self.ext_manual_frame.pack_forget()
        expiry = date_add(days)
        if hasattr(self, "ext_expiry_var"):
            self.ext_expiry_var.set(f"Extended expiry: {expiry or '-'}")
        self.refresh_cart() if hasattr(self, "cart_tree") else None

    def refresh_pos_products(self):
        self.pos_tree.delete(*self.pos_tree.get_children())
        for p in search_products(
                self.pos_search.get(),
                self.pos_type.get(),
                include_empty=False):
            price = n(p.get("offer_price")) or n(p.get("price"))
            self.pos_tree.insert(
                "", "end", values=(
                    p["id"], p["sku"], p["type"], product_display_name(p), p.get(
                        "available_qty", p.get("quantity")), f"{
                        price:,.0f}"))

    def pick_unit_for_pos(self):
        sel = self.pos_tree.selection()
        if not sel:
            return
        pid = int(self.pos_tree.item(sel[0], "values")[0])
        units = available_units(pid)
        if not units:
            messagebox.showinfo(
                "Units", "This item is bulk stock or no units available.")
            return
        choice = simpledialog.askstring(
            "Available Units", "Type/paste unit code:\n" + "\n".join([u["unit_code"] for u in units[:30]]))
        if choice:
            self.cart_unit.set(choice.strip())

    def add_selected_to_cart(self):
        sel = self.pos_tree.selection()
        if not sel:
            messagebox.showwarning("Select item", "Select an item first")
            return
        vals = self.pos_tree.item(sel[0], "values")
        pid = int(vals[0])
        p = query_one("SELECT * FROM products WHERE id=?", (pid,))
        if not p:
            return
        price = n(
            self.cart_price.get()) or n(
            p.get("offer_price")) or n(
            p.get("price"))
        qty_requested = max(1, i(self.cart_qty.get()))
        unit_text = self.cart_unit.get().strip()
        ext_name = self.ext_option.get().strip()
        if ext_name == "No Extended":
            ext_name = ""
        ext_price = n(self.ext_amount.get())
        ext_days = i(self.ext_days.get())

        def add_one(unit_code, qty=1):
            if unit_code and any(
                    c.get("unit_code") == unit_code for c in self.cart):
                raise ValueError(
                    f"Duplicate IMEI/unit already in cart: {unit_code}")
            self.cart.append({"product_id": pid,
                              "product_name": product_display_name(p),
                              "unit_code": unit_code,
                              "qty": qty,
                              "price": price,
                              "discount": 0,
                              "extended_warranty_name": ext_name,
                              "extended_warranty_price": ext_price,
                              "extended_warranty_days": ext_days})

        try:
            if p["is_serialized"]:
                # Supports exact serial, last 5 digits, comma/new-line list, or
                # auto-pick first available units by qty.
                typed_units = [
                    u.strip() for u in unit_text.replace(
                        ",", "\n").splitlines() if u.strip()]
                available = available_units(pid)
                if typed_units:
                    for typed in typed_units:
                        match = next((u for u in available if u["unit_code"] == typed), None) or next(
                            (u for u in available if str(u["unit_code"]).endswith(typed)), None)
                        add_one(match["unit_code"] if match else typed, 1)
                else:
                    if len(available) < qty_requested:
                        raise ValueError(
                            f"Only {
                                len(available)} serialized units available.")
                    for u in available[:qty_requested]:
                        add_one(u["unit_code"], 1)
            else:
                add_one(unit_text, qty_requested)
        except Exception as e:
            messagebox.showwarning("Cannot add item", str(e))
            return
        self.cart_price.set("")
        self.cart_unit.set("")
        self.refresh_cart()

    def refresh_cart(self):
        self.cart_tree.delete(*self.cart_tree.get_children())
        total = 0
        for idx, c in enumerate(self.cart):
            line = n(c["price"]) * i(c["qty"]) + \
                (n(c.get("extended_warranty_price")) * i(c["qty"]))
            total += line
            general = c.get("general_warranty") or "No Warranty"
            general_days = i(c.get("general_warranty_days"))
            warranty_text = "No warranty" if general == "No Warranty" or general_days <= 0 else f"{general} | exp {
                date_add(general_days)}"
            if c.get("warranty_note"):
                warranty_text += f" | {c.get('warranty_note')}"
            ext_name = c.get("extended_warranty_name") or "No Extended"
            ext_text = ext_name if ext_name == "No Extended" else f"{ext_name} | {
                money(
                    c.get('extended_warranty_price'))}"
            price_text = f"OFFER {n(c['price']):,.0f} (was {n(c.get('regular_price')):,.0f})" if c.get(
                "offer_applied") else f"{n(c['price']):,.0f}"
            self.cart_tree.insert("",
                                  "end",
                                  iid=str(idx),
                                  values=(c["product_name"],
                                          c.get("unit_code") or "-",
                                          c["qty"],
                                          price_text,
                                          warranty_text,
                                          ext_text,
                                          f"{line:,.0f}"))
        discount = n(self.bill_discount.get())
        grand = max(0, total - discount)
        paid = self.bill_payments.total()
        due = max(0, grand - paid)
        label = f"Items + Extended Warranty: {
            money(total)} | Discount: {
            money(discount)} | Payable: {
            money(grand)} | Paid: {
                money(paid)} | Remaining: {
                    money(due)}"
        self.cart_total_var.set(label)
        if hasattr(self, "payment_total_var"):
            self.payment_total_var.set(label)

    def prompt_item_warranty(self, item, parent=None):
        """Require explicit warranty confirmation before a cart line exists."""
        owner = parent or self
        win = tk.Toplevel(owner)
        win.title("Confirm Warranty Before Adding Item")
        win.geometry("680x540")
        win.transient(owner)
        win.configure(bg=UI.BG)
        result = {}
        card, inner = mac_card(
            win, "Warranty Details for This Item", padding=16)
        card.pack(fill="both", expand=True, padx=12, pady=12)
        tk.Label(
            inner,
            text=f"{
                item.get('product_name')} | {
                item.get('unit_code') or 'Bulk item'}",
            bg=UI.SURFACE,
            fg=UI.TEXT,
            font=(
                "Segoe UI",
                13,
                "bold")).pack(
                    anchor="w",
                    pady=(
                        0,
                        4))
        tk.Label(
            inner,
            text="Confirm these terms for this item only. They are not copied automatically to the next cart item.",
            bg=UI.SURFACE,
            fg=UI.MUTED,
            font=(
                "Segoe UI",
                9)).pack(
            anchor="w",
            pady=(
                0,
                10))
        general = tk.StringVar(value=item.get(
            "general_warranty") or "No Warranty")
        general_days = tk.StringVar(
            value=str(i(item.get("general_warranty_days"))))
        extended = tk.StringVar(value=item.get(
            "extended_warranty_name") or "No Extended")
        extended_days = tk.StringVar(
            value=str(i(item.get("extended_warranty_days"))))
        extended_amount = tk.StringVar(
            value=str(n(item.get("extended_warranty_price"))))
        note = tk.StringVar(value=item.get("warranty_note") or "")
        summary = tk.StringVar()
        form = ttk.Frame(inner)
        form.pack(fill="x")
        fields = [
            ("General Warranty",
             general,
             GENERAL_WARRANTIES),
            ("General Days",
             general_days,
             None),
            ("Extended Warranty",
             extended,
             EXTENDED_WARRANTIES),
            ("Extended Days",
             extended_days,
             None),
            ("Extended Amount / Unit",
             extended_amount,
             None),
            ("Warranty Note",
             note,
             None)]
        for row, (label, var, values) in enumerate(fields):
            ttk.Label(
                form,
                text=label,
                width=22).grid(
                row=row,
                column=0,
                sticky="w",
                pady=4)
            widget = ttk.Combobox(
                form,
                textvariable=var,
                values=values,
                state="readonly") if values else ttk.Entry(
                form,
                textvariable=var)
            widget.grid(row=row, column=1, sticky="ew", pady=4)
        form.columnconfigure(1, weight=1)
        ttk.Label(
            inner,
            textvariable=summary,
            style="Muted.TLabel",
            wraplength=620).pack(
            anchor="w",
            pady=8)
        updating = {"active": False}

        def recalc(*_):
            if updating["active"]:
                return
            updating["active"] = True
            try:
                if general.get() != "Manual Days":
                    general_days.set(
                        str(warranty_days(general.get(), general_days.get())))
                if extended.get() == "No Extended":
                    extended_days.set("0")
                    extended_amount.set("0")
                elif extended.get() != "Manual Days":
                    extended_days.set(
                        str(warranty_days(extended.get(), extended_days.get())))
                gd = i(general_days.get())
                ed = i(extended_days.get())
                summary.set(
                    f"General expiry: {
                        date_add(gd) or '-'} | Extended expiry: {
                        date_add(ed) or '-'} | Extended charge: {
                        money(
                            extended_amount.get())} per unit")
            finally:
                updating["active"] = False
        for variable in [
                general,
                general_days,
                extended,
                extended_days,
                extended_amount]:
            variable.trace_add("write", recalc)
        recalc()

        def confirm():
            gd = warranty_days(general.get(), general_days.get())
            ext = extended.get()
            ed = warranty_days(ext, extended_days.get()
                               ) if ext != "No Extended" else 0
            amount = n(extended_amount.get())
            if general.get() != "No Warranty" and gd <= 0:
                messagebox.showwarning(
                    "Warranty",
                    "General warranty days must be greater than zero.",
                    parent=win)
                return
            if ext != "No Extended" and ed <= 0:
                messagebox.showwarning(
                    "Warranty",
                    "Extended warranty days must be greater than zero.",
                    parent=win)
                return
            if amount < 0:
                messagebox.showwarning(
                    "Warranty",
                    "Extended warranty amount cannot be negative.",
                    parent=win)
                return
            result.update({"general_warranty": general.get(),
                           "general_warranty_days": gd,
                           "extended_warranty_name": "" if ext == "No Extended" else ext,
                           "extended_warranty_days": ed,
                           "extended_warranty_price": 0 if ext == "No Extended" else amount,
                           "warranty_note": note.get().strip()})
            win.destroy()
        buttons = ttk.Frame(inner)
        buttons.pack(fill="x", pady=10)
        ttk.Button(
            buttons,
            text="Confirm Warranty & Add Item",
            style="Accent.TButton",
            command=confirm).pack(
            side="right",
            padx=3)
        ttk.Button(
            buttons,
            text="Cancel Item",
            command=win.destroy).pack(
            side="right",
            padx=3)
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.grab_set()
        win.wait_window()
        return result or None

    def edit_cart_item_warranty(self):
        sel = self.cart_tree.selection()
        if not sel:
            messagebox.showwarning(
                "Select cart item",
                "Select a cart item before editing its warranty.")
            return
        idx = int(sel[0])
        item = self.cart[idx]
        win = tk.Toplevel(self)
        win.title(f"Item Warranty - {item.get('product_name')}")
        win.geometry("650x500")
        win.transient(self)
        win.configure(bg=UI.BG)
        card, inner = mac_card(win, "Warranty for This Item", padding=16)
        card.pack(fill="both", expand=True, padx=12, pady=12)
        tk.Label(
            inner,
            text=f"{
                item.get('product_name')} | {
                item.get('unit_code') or 'Bulk quantity'}",
            bg=UI.SURFACE,
            fg=UI.TEXT,
            font=(
                "Segoe UI",
                12,
                "bold")).pack(
                    anchor="w",
                    pady=(
                        0,
                        8))
        general = tk.StringVar(value=item.get(
            "general_warranty") or "No Warranty")
        general_days = tk.StringVar(
            value=str(i(item.get("general_warranty_days"))))
        extended = tk.StringVar(value=item.get(
            "extended_warranty_name") or "No Extended")
        extended_days = tk.StringVar(
            value=str(i(item.get("extended_warranty_days"))))
        extended_amount = tk.StringVar(
            value=str(n(item.get("extended_warranty_price"))))
        note = tk.StringVar(value=item.get("warranty_note") or "")
        summary = tk.StringVar()
        form = ttk.Frame(inner)
        form.pack(fill="x")
        fields = [
            ("General Warranty",
             general,
             GENERAL_WARRANTIES),
            ("General Days",
             general_days,
             None),
            ("Extended Warranty",
             extended,
             EXTENDED_WARRANTIES),
            ("Extended Days",
             extended_days,
             None),
            ("Extended Amount",
             extended_amount,
             None),
            ("Warranty Note",
             note,
             None)]
        for row, (label, var, values) in enumerate(fields):
            ttk.Label(
                form,
                text=label,
                width=20).grid(
                row=row,
                column=0,
                sticky="w",
                pady=4)
            widget = ttk.Combobox(
                form,
                textvariable=var,
                values=values,
                state="readonly") if values else ttk.Entry(
                form,
                textvariable=var)
            widget.grid(row=row, column=1, sticky="ew", pady=4)
        form.columnconfigure(1, weight=1)
        ttk.Label(
            inner,
            textvariable=summary,
            style="Muted.TLabel",
            wraplength=590).pack(
            anchor="w",
            pady=8)

        def recalc(*_):
            if general.get() != "Manual Days":
                general_days.set(
                    str(warranty_days(general.get(), general_days.get())))
            if extended.get() == "No Extended":
                extended_days.set("0")
                extended_amount.set("0")
            elif extended.get() != "Manual Days":
                extended_days.set(
                    str(warranty_days(extended.get(), extended_days.get())))
            gd = i(general_days.get())
            ed = i(extended_days.get())
            summary.set(
                f"General expires: {
                    date_add(gd) or '-'} | Extended expires: {
                    date_add(ed) or '-'} | Extended charge per unit: {
                    money(
                        extended_amount.get())}")
        general.trace_add("write", recalc)
        extended.trace_add("write", recalc)
        general_days.trace_add(
            "write", lambda *_: summary.set(
                f"General expires: {
                    date_add(
                        i(
                            general_days.get())) or '-'} | Extended expires: {
                    date_add(
                        i(
                            extended_days.get())) or '-'} | Extended charge per unit: {
                    money(
                        extended_amount.get())}"))
        extended_days.trace_add(
            "write", lambda *_: summary.set(
                f"General expires: {
                    date_add(
                        i(
                            general_days.get())) or '-'} | Extended expires: {
                    date_add(
                        i(
                            extended_days.get())) or '-'} | Extended charge per unit: {
                    money(
                        extended_amount.get())}"))
        recalc()

        def save():
            gd = warranty_days(general.get(), general_days.get())
            ext = extended.get()
            ed = warranty_days(ext, extended_days.get()
                               ) if ext != "No Extended" else 0
            if general.get() == "Manual Days" and gd <= 0:
                raise ValueError(
                    "Manual general warranty days must be greater than zero")
            if ext != "No Extended" and ed <= 0:
                raise ValueError(
                    "Extended warranty days must be greater than zero")
            item.update(
                {
                    "general_warranty": general.get(),
                    "general_warranty_days": gd,
                    "extended_warranty_name": "" if ext == "No Extended" else ext,
                    "extended_warranty_days": ed,
                    "extended_warranty_price": 0 if ext == "No Extended" else n(
                        extended_amount.get()),
                    "warranty_note": note.get().strip()})
            self.refresh_cart()
            win.destroy()
        buttons = ttk.Frame(inner)
        buttons.pack(fill="x", pady=8)
        ttk.Button(
            buttons,
            text="Save Item Warranty",
            style="Accent.TButton",
            command=lambda: safe_run(save)()).pack(
            side="right",
            padx=3)
        ttk.Button(
            buttons,
            text="Cancel",
            command=win.destroy).pack(
            side="right",
            padx=3)

    def remove_cart_item(self):
        sel = self.cart_tree.selection()
        if sel:
            idx = int(sel[0])
            self.cart.pop(idx)
            self.refresh_cart()

    def clear_cart(self):
        self.cart.clear()
        self.refresh_cart()

    @safe_run
    def save_retail_bill(self):
        self.refresh_cart()
        if not self.bill_name.get().strip() or not self.bill_phone.get().strip():
            messagebox.showwarning(
                "Client details",
                "Client name and WhatsApp number are required.")
            return
        customer = {
            "name": self.bill_name.get(),
            "phone": self.bill_phone.get(),
            "whatsapp": self.bill_phone.get(),
            "email": self.bill_email.get()}
        billing = {
            "general_warranty": self.bill_general.get(),
            "general_warranty_days": self.bill_general_days.get(),
            "payments": self.bill_payments.get_rows(),
            "discount": self.bill_discount.get(),
            "note": self.bill_note.get()}
        inv = create_retail_invoice(customer, self.cart, billing, self.user)
        pdf = build_retail_invoice_pdf(inv)
        set_invoice_pdf(inv["id"], pdf)
        inv = get_invoice(inv["id"])
        open_file(pdf)
        if messagebox.askyesno(
            "Invoice Saved", f"{
                inv['invoice_no']} saved successfully.\n\nPDF opened. Send invoice details to client with the PDF now?"):
            whatsapp_send(
                inv.get("customer_whatsapp") or inv.get("customer_phone"),
                client_statement_text(
                    inv["id"]),
                inv.get("pdf_path") or pdf)
        self.clear_cart()
        self.bill_payments.clear()
        self.refresh_all()

    # ---------------- Inventory ----------------
    def build_inventory_tab(self):
        root = ttk.PanedWindow(self.tab_inventory, orient="horizontal")
        root.pack(fill="both", expand=True)
        left_sf = ScrollFrame(root)
        right_sf = ScrollFrame(root)
        right = right_sf.content
        root.add(left_sf, weight=5)
        root.add(right_sf, weight=6)
        box = ttk.LabelFrame(
            left_sf.content,
            text="Inventory Manager - Scroll 1 | Advanced Product Group",
            padding=10)
        box.pack(fill="both", expand=True, padx=8, pady=8)
        self.build_product_group_form(box, compact=True)

        manage = ttk.LabelFrame(
            left_sf.content,
            text="Manage Selected Product",
            padding=10)
        manage.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(
            manage,
            text="Select a product in Scroll 2 before using these controls.",
            style="Muted.TLabel").pack(
            anchor="w",
            pady=(
                0,
                5))
        ttk.Button(
            manage,
            text="+ Add Supplier Stock / IMEIs",
            style="Accent.TButton",
            command=self.open_supplier_stock_dialog).pack(
            fill="x",
            pady=2)
        ttk.Button(
            manage,
            text="Find Supplier by IMEI / ID",
            command=self.find_unit_supplier).pack(
            fill="x",
            pady=2)
        ttk.Button(
            manage,
            text="Admin Offer Manager",
            style="Accent.TButton",
            command=self.open_offer_manager).pack(
            fill="x",
            pady=2)
        ttk.Button(
            manage,
            text="Edit Selected Product Info",
            command=self.update_inventory_product).pack(
            fill="x",
            pady=2)
        ttk.Button(
            manage,
            text="Detailed Stock / Sold Popup",
            command=self.show_inventory_details).pack(
            fill="x",
            pady=2)
        ttk.Button(
            manage,
            text="Delete Selected",
            style="Danger.TButton",
            command=self.delete_inventory_product).pack(
            fill="x",
            pady=2)
        # Table with its own scroll: Scroll 2
        top = ttk.LabelFrame(
            right,
            text="Inventory Table - Scroll 2 + Advanced Search",
            padding=8)
        top.pack(fill="both", expand=True, padx=8, pady=8)
        sf = ttk.Frame(top)
        sf.pack(fill="x")
        self.inv_search = tk.StringVar()
        self.inv_filter_type = tk.StringVar(value="All")
        self.inv_include_empty = tk.IntVar(value=1)
        ttk.Entry(sf, textvariable=self.inv_search).pack(
            side="left", fill="x", expand=True, padx=3)
        ttk.Combobox(
            sf,
            textvariable=self.inv_filter_type,
            values=["All"] +
            PRODUCT_TYPES,
            state="readonly",
            width=16).pack(
            side="left",
            padx=3)
        ttk.Checkbutton(
            sf,
            text="Show empty/sold",
            variable=self.inv_include_empty).pack(
            side="left",
            padx=3)
        ttk.Button(
            sf,
            text="Search",
            command=self.refresh_inventory).pack(
            side="left",
            padx=3)
        wrap, self.inv_tree = self.table(
            top, [
                "id", "sku", "type", "item", "qty", "sold", "wholesale", "avg_cost", "price", "status"], height=13)
        self.inv_tree.column("item", width=310)
        self.inv_tree.column("id", width=45)
        wrap.pack(fill="both", expand=True, pady=8)
        self.inv_tree.bind(
            "<<TreeviewSelect>>",
            lambda e: self.load_selected_inventory())
        self.inv_tree.bind(
            "<Double-1>",
            lambda e: self.show_inventory_details())
        hist = ttk.LabelFrame(
            right,
            text="Restock History / Financial Stock Audit",
            padding=8)
        hist.pack(fill="both", expand=True, padx=8, pady=8)
        wrap, self.restock_tree = self.table(
            hist, [
                "date", "sku", "added", "old", "new", "unit_cost", "avg_cost", "supplier"], height=7)
        wrap.pack(fill="both", expand=True)
        self.selected_product_id = None

    def build_product_group_form(self, parent, compact=False, on_saved=None):
        """Render the canonical advanced inventory entry workflow in any container."""
        header = ttk.Frame(parent)
        header.pack(fill="x", pady=(0, 6))
        ttk.Label(
            header,
            text="Add Product Group",
            style="Title.TLabel").pack(
            anchor="w")
        ttk.Label(
            header,
            text="One SKU can contain multiple supplier purchases. Every IMEI / ID keeps its supplier, batch and original buying price.",
            style="Muted.TLabel",
            wraplength=560 if compact else 1000,
        ).pack(
            anchor="w",
            pady=(
                2,
                0))

        group_box = ttk.LabelFrame(
            parent, text="Product Group Details", padding=10)
        group_box.pack(fill="x", pady=6)
        keys = [
            "type",
            "category",
            "brand",
            "model",
            "sku",
            "color",
            "condition",
            "price",
            "offer",
            "ram",
            "rom",
            "other",
            "notes",
            "low"]
        vars_ = {key: tk.StringVar() for key in keys}
        vars_["type"].set("Phone")
        vars_["category"].set("Smartphones")
        vars_["condition"].set("Brand New")
        vars_["low"].set("3")
        categories = [
            "Smartphones",
            "Feature Phones",
            "Tablets",
            "Laptops",
            "Earbuds",
            "Headphones",
            "Bluetooth Speakers",
            "Chargers & Adapters",
            "Cables",
            "Cases & Covers",
            "Screen Protectors",
            "Power Banks",
            "Smartwatches",
            "Fitness Bands",
            "Batteries",
            "Displays",
            "Motherboards",
            "Camera Modules",
            "Keyboards",
            "Mice",
            "Other"]
        brands = [
            "Apple",
            "Samsung",
            "Xiaomi",
            "Huawei",
            "Google",
            "OnePlus",
            "Oppo",
            "Vivo",
            "Sony",
            "Nokia",
            "Motorola",
            "Realme",
            "Infinix",
            "Tecno",
            "Asus",
            "Lenovo",
            "LG",
            "Nothing",
            "Honor",
            "Poco",
            "JBL",
            "Bose",
            "Beats",
            "Anker",
            "Baseus",
            "Spigen",
            "Ugreen",
            "Belkin"]
        colors = [
            "Black",
            "Midnight Black",
            "Phantom Black",
            "Space Black",
            "White",
            "Silver",
            "Titanium",
            "Gold",
            "Rose Gold",
            "Blue",
            "Red",
            "Green",
            "Yellow",
            "Purple",
            "Pink",
            "Orange",
            "Clear"]
        rams = [
            "1GB",
            "2GB",
            "3GB",
            "4GB",
            "6GB",
            "8GB",
            "12GB",
            "16GB",
            "24GB",
            "None"]
        roms = [
            "16GB",
            "32GB",
            "64GB",
            "128GB",
            "256GB",
            "512GB",
            "1TB",
            "2TB",
            "None"]
        fields = [
            ("Item Type", "type", PRODUCT_TYPES), ("Category", "category", categories),
            ("Brand *", "brand", brands), ("Model *", "model", None),
            ("Product Group Code / SKU *", "sku", None), ("Color", "color", colors),
            ("Condition", "condition", CONDITIONS), ("Selling Price *", "price", None),
            ("Offer Price", "offer", None), ("Low Stock Alert", "low", None),
            ("RAM", "ram", rams), ("Storage", "rom", roms),
            ("Other Details", "other", None), ("Notes", "notes", None),
        ]
        columns = 1 if compact else 2
        for idx, (label, key, values) in enumerate(fields):
            row, col = divmod(idx, columns)
            cell = ttk.Frame(group_box)
            cell.grid(row=row, column=col, sticky="ew", padx=5, pady=3)
            ttk.Label(cell, text=label, width=25).pack(side="left")
            widget = ttk.Combobox(
                cell,
                textvariable=vars_[key],
                values=values) if values else ttk.Entry(
                cell,
                textvariable=vars_[key])
            widget.pack(side="left", fill="x", expand=True)
        for col in range(columns):
            group_box.columnconfigure(col, weight=1)

        acquisition = ttk.LabelFrame(
            parent, text="Stock Acquisition - Supplier Batches", padding=10)
        acquisition.pack(fill="both", expand=True, pady=6)
        total_var = tk.StringVar(
            value="Total Stock: 0  |  Weighted Average: Rs. 0")
        ttk.Label(
            acquisition,
            text="Add the exact quantity, cost and unit IDs received from each supplier.",
            style="Muted.TLabel",
            wraplength=540 if compact else 1000).pack(
            anchor="w")
        ttk.Label(
            acquisition,
            textvariable=total_var,
            font=(
                "Segoe UI",
                10,
                "bold")).pack(
            anchor="e",
            pady=(
                2,
                6))
        batches_host = ttk.Frame(acquisition)
        batches_host.pack(fill="both", expand=True)
        controls = ttk.Frame(acquisition)
        controls.pack(fill="x", pady=(6, 0))
        batches = []

        def update_summary(*_):
            qty_total = sum(max(0, i(b["qty"].get())) for b in batches)
            value_total = sum(max(0,
                                  i(b["qty"].get())) * max(0,
                                                           n(b["cost"].get())) for b in batches)
            total_var.set(
                f"Total Stock: {
                    qty_total:,}  |  Weighted Average: {
                    money(
                        value_total / qty_total if qty_total else 0)}")

        def rebuild_units(batch):
            old = [v.get() for v in batch["units"]]
            for child in batch["unit_host"].winfo_children():
                child.destroy()
            batch["units"] = []
            qty = max(0, i(batch["qty"].get()))
            shown = min(qty, 200)
            if qty > 200:
                ttk.Label(
                    batch["unit_host"],
                    text="Maximum 200 exact units per batch; split this purchase into another batch.").grid(
                    row=0,
                    column=0,
                    sticky="w",
                    pady=4)
            unit_columns = 1 if compact else 2
            for idx in range(shown):
                unit_var = tk.StringVar(
                    value=old[idx] if idx < len(old) else "")
                cell = ttk.Frame(batch["unit_host"])
                cell.grid(
                    row=idx //
                    unit_columns,
                    column=idx %
                    unit_columns,
                    sticky="ew",
                    padx=4,
                    pady=2)
                ttk.Label(cell, text=f"#{idx + 1}", width=5).pack(side="left")
                ttk.Entry(
                    cell, textvariable=unit_var, font=(
                        "Consolas", 9)).pack(
                    side="left", fill="x", expand=True)
                batch["units"].append(unit_var)
            for col in range(unit_columns):
                batch["unit_host"].columnconfigure(col, weight=1)
            update_summary()

        def schedule_units(batch, *_):
            if batch.get("job"):
                try:
                    parent.after_cancel(batch["job"])
                except tk.TclError:
                    pass
            batch["job"] = parent.after(220, lambda: rebuild_units(batch))

        def renumber_batches():
            for idx, batch in enumerate(batches, 1):
                batch["frame"].configure(text=f"Supplier Batch {idx}")

        def remove_batch(batch):
            if len(batches) <= 1:
                messagebox.showwarning(
                    "Supplier batch",
                    "A product group requires at least one supplier batch.",
                    parent=parent.winfo_toplevel())
                return
            if batch.get("job"):
                try:
                    parent.after_cancel(batch["job"])
                except tk.TclError:
                    pass
            batch["frame"].destroy()
            batches.remove(batch)
            renumber_batches()
            update_summary()

        def add_batch():
            batch = {
                "supplier": tk.StringVar(),
                "cost": tk.StringVar(),
                "qty": tk.StringVar(
                    value="1"),
                "note": tk.StringVar(
                    value="Opening purchase"),
                "units": [],
                "job": None}
            frame = ttk.LabelFrame(
                batches_host, text=f"Supplier Batch {
                    len(batches) + 1}", padding=8)
            frame.pack(fill="x", pady=5)
            batch["frame"] = frame
            supplier_names = [s["name"] for s in list_suppliers()]
            fields_row = ttk.Frame(frame)
            fields_row.pack(fill="x")
            if compact:
                for row_no, (label, variable, values) in enumerate([("Supplier Name *", batch["supplier"], supplier_names), (
                        "Unit Cost (LKR) *", batch["cost"], None), ("Total Qty *", batch["qty"], None), ("Batch Note", batch["note"], None)]):
                    ttk.Label(
                        fields_row,
                        text=label,
                        width=19).grid(
                        row=row_no,
                        column=0,
                        sticky="w",
                        pady=2)
                    entry = ttk.Combobox(
                        fields_row,
                        textvariable=variable,
                        values=values) if values is not None else ttk.Entry(
                        fields_row,
                        textvariable=variable)
                    entry.grid(row=row_no, column=1, sticky="ew", pady=2)
                fields_row.columnconfigure(1, weight=1)
            else:
                ttk.Label(fields_row, text="Supplier Name *").pack(side="left")
                ttk.Combobox(
                    fields_row,
                    textvariable=batch["supplier"],
                    values=supplier_names,
                    width=24).pack(
                    side="left",
                    fill="x",
                    expand=True,
                    padx=3)
                ttk.Label(
                    fields_row, text="Unit Cost *").pack(side="left", padx=(8, 2))
                ttk.Entry(
                    fields_row,
                    textvariable=batch["cost"],
                    width=13).pack(
                    side="left")
                ttk.Label(
                    fields_row, text="Qty *").pack(side="left", padx=(8, 2))
                ttk.Entry(
                    fields_row,
                    textvariable=batch["qty"],
                    width=7).pack(
                    side="left")
            tools = ttk.Frame(frame)
            tools.pack(fill="x", pady=(5, 2))
            ttk.Label(
                tools,
                text="Individual IMEI / Serial / Internal ID",
                font=(
                    "Segoe UI",
                    9,
                    "bold")).pack(
                side="left")

            def generate():
                reserved = [
                    v.get() for other in batches for v in other["units"] if v.get().strip()]
                for value, code in zip(batch["units"], generate_internal_ids(
                        len(batch["units"]), reserved)):
                    value.set(code)
            ttk.Button(
                tools,
                text="Generate Internal IDs",
                command=generate).pack(
                side="right",
                padx=2)
            ttk.Button(
                tools,
                text="Remove Batch",
                style="Danger.TButton",
                command=lambda: remove_batch(batch)).pack(
                side="right",
                padx=2)
            unit_host = ttk.Frame(frame)
            unit_host.pack(fill="x", pady=(3, 0))
            batch["unit_host"] = unit_host
            batches.append(batch)
            batch["qty"].trace_add("write", lambda *_: schedule_units(batch))
            batch["cost"].trace_add("write", update_summary)
            rebuild_units(batch)

        def reset_form():
            defaults = {
                "type": "Phone",
                "category": "Smartphones",
                "condition": "Brand New",
                "low": "3"}
            for key, variable in vars_.items():
                variable.set(defaults.get(key, ""))
            for batch in list(batches):
                if batch.get("job"):
                    try:
                        parent.after_cancel(batch["job"])
                    except tk.TclError:
                        pass
                batch["frame"].destroy()
            batches.clear()
            add_batch()
            update_summary()

        def save_group():
            supplier_batches = []
            for idx, batch in enumerate(batches, 1):
                qty = i(batch["qty"].get())
                if qty > 200:
                    raise ValueError(
                        f"Supplier batch {idx} exceeds 200 units; split it into multiple batches")
                supplier_batches.append({"supplier": batch["supplier"].get(), "unit_cost": batch["cost"].get(
                ), "qty": qty, "units": [v.get().strip() for v in batch["units"]], "note": batch["note"].get()})
            description = " | ".join(
                x for x in [
                    vars_["other"].get().strip(),
                    vars_["notes"].get().strip()] if x)
            data = {
                "type": vars_["type"].get(),
                "category": vars_["category"].get(),
                "brand": vars_["brand"].get(),
                "model": vars_["model"].get(),
                "sku": vars_["sku"].get(),
                "color": vars_["color"].get(),
                "condition": vars_["condition"].get(),
                "price": vars_["price"].get(),
                "offer_price": vars_["offer"].get(),
                "ram": vars_["ram"].get(),
                "rom": vars_["rom"].get(),
                "description": description,
                "low_stock": vars_["low"].get()}
            product_id = create_product_group(
                data, supplier_batches, self.user)
            self.refresh_all()
            messagebox.showinfo(
                "Product Group Saved",
                f"Product group {
                    data['sku'].upper()} saved with ID {product_id}.\n{
                    total_var.get()}\nEvery unit is linked to its supplier, purchase batch and buying price.",
                parent=parent.winfo_toplevel())
            if on_saved:
                on_saved()
            else:
                reset_form()

        ttk.Button(
            controls,
            text="+ Add Supplier Batch",
            command=add_batch).pack(
            side="left",
            padx=2)
        ttk.Button(
            controls,
            text="Clear Form",
            command=reset_form).pack(
            side="right",
            padx=2)
        ttk.Button(
            controls,
            text="Save Product Group",
            style="Accent.TButton",
            command=lambda: safe_run(save_group)()).pack(
            side="right",
            padx=2)
        add_batch()
        self.advanced_inventory_vars = vars_
        self.advanced_inventory_batches = batches

    @safe_run
    def open_product_group_entry(self):
        """Reference-style product group entry with multiple supplier batches."""
        win = tk.Toplevel(self)
        win.title("Add Product Group - Advanced Inventory")
        win.geometry("1180x820")
        win.minsize(900, 640)
        win.configure(bg=UI.BG)
        win.transient(self)
        sf = ScrollFrame(win, bg=UI.BG)
        sf.pack(fill="both", expand=True)

        header = ttk.Frame(sf.content)
        header.pack(fill="x", padx=12, pady=(12, 6))
        ttk.Label(
            header,
            text="Add Product Group",
            style="Title.TLabel").pack(
            anchor="w")
        ttk.Label(
            header,
            text="Create one SKU, then add every supplier acquisition batch and its individual IMEI / ID values.",
            style="Muted.TLabel").pack(
            anchor="w",
            pady=(
                2,
                0))

        group_box = ttk.LabelFrame(
            sf.content,
            text="Product Group Details",
            padding=12)
        group_box.pack(fill="x", padx=12, pady=6)
        vars_ = {
            key: tk.StringVar() for key in [
                "type",
                "category",
                "brand",
                "model",
                "sku",
                "color",
                "condition",
                "price",
                "offer",
                "ram",
                "rom",
                "other",
                "notes",
                "low"]}
        vars_["type"].set("Phone")
        vars_["category"].set("Smartphones")
        vars_["condition"].set("Brand New")
        vars_["low"].set("3")
        categories = [
            "Smartphones",
            "Feature Phones",
            "Tablets",
            "Laptops",
            "Earbuds",
            "Headphones",
            "Bluetooth Speakers",
            "Chargers & Adapters",
            "Cables",
            "Cases & Covers",
            "Screen Protectors",
            "Power Banks",
            "Smartwatches",
            "Fitness Bands",
            "Batteries",
            "Displays",
            "Motherboards",
            "Camera Modules",
            "Keyboards",
            "Mice",
            "Other"]
        brands = [
            "Apple",
            "Samsung",
            "Xiaomi",
            "Huawei",
            "Google",
            "OnePlus",
            "Oppo",
            "Vivo",
            "Sony",
            "Nokia",
            "Motorola",
            "Realme",
            "Infinix",
            "Tecno",
            "Asus",
            "Lenovo",
            "LG",
            "Nothing",
            "Honor",
            "Poco",
            "JBL",
            "Bose",
            "Beats",
            "Anker",
            "Baseus",
            "Spigen",
            "Ugreen",
            "Belkin"]
        colors = [
            "Black",
            "Midnight Black",
            "Phantom Black",
            "Space Black",
            "White",
            "Silver",
            "Titanium",
            "Gold",
            "Rose Gold",
            "Blue",
            "Red",
            "Green",
            "Yellow",
            "Purple",
            "Pink",
            "Orange",
            "Clear"]
        rams = [
            "1GB",
            "2GB",
            "3GB",
            "4GB",
            "6GB",
            "8GB",
            "12GB",
            "16GB",
            "24GB",
            "None"]
        roms = [
            "16GB",
            "32GB",
            "64GB",
            "128GB",
            "256GB",
            "512GB",
            "1TB",
            "2TB",
            "None"]

        fields = [
            ("Item Type", "type", PRODUCT_TYPES), ("Category", "category", categories),
            ("Brand *", "brand", brands), ("Model *", "model", None),
            ("Product Group Code / SKU *", "sku", None), ("Color", "color", colors),
            ("Condition", "condition", CONDITIONS), ("Selling Price *", "price", None),
            ("Offer Price", "offer", None), ("Low Stock Alert", "low", None),
            ("RAM", "ram", rams), ("Storage", "rom", roms),
            ("Other Details", "other", None), ("Notes", "notes", None),
        ]
        for idx, (label, key, values) in enumerate(fields):
            row, col = divmod(idx, 2)
            cell = ttk.Frame(group_box)
            cell.grid(row=row, column=col, sticky="ew", padx=8, pady=4)
            ttk.Label(cell, text=label, width=24).pack(side="left")
            if values:
                ttk.Combobox(
                    cell,
                    textvariable=vars_[key],
                    values=values).pack(
                    side="left",
                    fill="x",
                    expand=True)
            else:
                ttk.Entry(
                    cell, textvariable=vars_[key]).pack(
                    side="left", fill="x", expand=True)
        group_box.columnconfigure(0, weight=1)
        group_box.columnconfigure(1, weight=1)

        acquisition = ttk.LabelFrame(
            sf.content, text="Stock Acquisition", padding=12)
        acquisition.pack(fill="both", expand=True, padx=12, pady=6)
        acq_top = ttk.Frame(acquisition)
        acq_top.pack(fill="x", pady=(0, 8))
        ttk.Label(
            acq_top,
            text="Each supplier has its own buying price, quantity, and exact unit identifiers.").pack(
            side="left")
        total_var = tk.StringVar(
            value="Total Stock: 0  |  Weighted Average: Rs. 0")
        ttk.Label(
            acq_top,
            textvariable=total_var,
            font=(
                "Segoe UI",
                10,
                "bold")).pack(
            side="right",
            padx=8)
        batches_host = ttk.Frame(acquisition)
        batches_host.pack(fill="both", expand=True)
        batches = []
        supplier_names = [s["name"] for s in list_suppliers()]

        def update_summary(*_):
            qty_total = sum(max(0, i(b["qty"].get())) for b in batches)
            value_total = sum(max(0,
                                  i(b["qty"].get())) * max(0,
                                                           n(b["cost"].get())) for b in batches)
            avg = value_total / qty_total if qty_total else 0
            total_var.set(
                f"Total Stock: {
                    qty_total:,}  |  Weighted Average: {
                    money(avg)}")

        def rebuild_units(batch):
            old = [v.get() for v in batch["units"]]
            for child in batch["unit_host"].winfo_children():
                child.destroy()
            batch["units"] = []
            qty = max(0, i(batch["qty"].get()))
            if qty > 200:
                ttk.Label(
                    batch["unit_host"],
                    text="Maximum 200 units per supplier batch. Split larger purchases into another batch.").grid(
                    row=0,
                    column=0,
                    sticky="w",
                    pady=4)
                qty = 200
            for idx in range(qty):
                unit_var = tk.StringVar(
                    value=old[idx] if idx < len(old) else "")
                cell = ttk.Frame(batch["unit_host"])
                cell.grid(
                    row=idx // 2, column=idx %
                    2, sticky="ew", padx=5, pady=3)
                ttk.Label(cell, text=f"#{idx + 1}", width=5).pack(side="left")
                ttk.Entry(
                    cell, textvariable=unit_var, font=(
                        "Consolas", 9)).pack(
                    side="left", fill="x", expand=True)
                batch["units"].append(unit_var)
            batch["unit_host"].columnconfigure(0, weight=1)
            batch["unit_host"].columnconfigure(1, weight=1)
            update_summary()

        def schedule_units(batch, *_):
            job = batch.get("job")
            if job:
                try:
                    win.after_cancel(job)
                except tk.TclError:
                    pass
            batch["job"] = win.after(220, lambda: rebuild_units(batch))

        def renumber_batches():
            for idx, batch in enumerate(batches, 1):
                batch["frame"].configure(text=f"Supplier Batch {idx}")

        def remove_batch(batch):
            if len(batches) <= 1:
                messagebox.showwarning(
                    "Supplier batch",
                    "A product group requires at least one supplier batch.",
                    parent=win)
                return
            batch["frame"].destroy()
            batches.remove(batch)
            renumber_batches()
            update_summary()

        def add_batch():
            batch = {
                "supplier": tk.StringVar(),
                "cost": tk.StringVar(),
                "qty": tk.StringVar(
                    value="1"),
                "note": tk.StringVar(
                    value="Opening purchase"),
                "units": [],
                "job": None}
            frame = ttk.LabelFrame(
                batches_host, text=f"Supplier Batch {
                    len(batches) + 1}", padding=10)
            frame.pack(fill="x", pady=6)
            batch["frame"] = frame
            row = ttk.Frame(frame)
            row.pack(fill="x")
            ttk.Label(row, text="Supplier Name", width=16).pack(side="left")
            ttk.Combobox(
                row,
                textvariable=batch["supplier"],
                values=supplier_names,
                width=24).pack(
                side="left",
                fill="x",
                expand=True,
                padx=3)
            ttk.Label(
                row, text="Unit Cost (LKR)").pack(
                side="left", padx=(
                    10, 2))
            ttk.Entry(
                row,
                textvariable=batch["cost"],
                width=14).pack(
                side="left")
            ttk.Label(row, text="Total Qty").pack(side="left", padx=(10, 2))
            ttk.Entry(
                row,
                textvariable=batch["qty"],
                width=8).pack(
                side="left")
            ttk.Button(
                row,
                text="Remove",
                style="Danger.TButton",
                command=lambda: remove_batch(batch)).pack(
                side="right",
                padx=3)
            note_row = ttk.Frame(frame)
            note_row.pack(fill="x", pady=(6, 2))
            ttk.Label(note_row, text="Batch Note", width=16).pack(side="left")
            ttk.Entry(
                note_row,
                textvariable=batch["note"]).pack(
                side="left",
                fill="x",
                expand=True)
            tools = ttk.Frame(frame)
            tools.pack(fill="x", pady=(5, 2))
            ttk.Label(
                tools,
                text="Individual Unit Identifiers (IMEI / Serial / ID)",
                font=(
                    "Segoe UI",
                    9,
                    "bold")).pack(
                side="left")

            def generate():
                reserved = [
                    v.get() for other in batches for v in other["units"] if v.get().strip()]
                for value, code in zip(batch["units"], generate_internal_ids(
                        len(batch["units"]), reserved)):
                    value.set(code)
            ttk.Button(
                tools,
                text="Generate Internal IDs",
                command=generate).pack(
                side="right")
            unit_host = ttk.Frame(frame)
            unit_host.pack(fill="x", pady=(4, 0))
            batch["unit_host"] = unit_host
            batches.append(batch)
            batch["qty"].trace_add("write", lambda *_: schedule_units(batch))
            batch["cost"].trace_add("write", update_summary)
            rebuild_units(batch)
            update_summary()

        ttk.Button(
            acq_top,
            text="+ Add Supplier Batch",
            style="Accent.TButton",
            command=add_batch).pack(
            side="right",
            padx=4)
        add_batch()

        def save_group():
            supplier_batches = []
            for idx, batch in enumerate(batches, 1):
                qty = i(batch["qty"].get())
                if qty > 200:
                    raise ValueError(
                        f"Supplier batch {idx} exceeds 200 units; split it into multiple batches")
                supplier_batches.append({
                    "supplier": batch["supplier"].get(), "unit_cost": batch["cost"].get(), "qty": qty,
                    "units": [v.get().strip() for v in batch["units"]], "note": batch["note"].get(),
                })
            description = " | ".join(
                x for x in [
                    vars_["other"].get().strip(),
                    vars_["notes"].get().strip()] if x)
            data = {
                "type": vars_["type"].get(),
                "category": vars_["category"].get(),
                "brand": vars_["brand"].get(),
                "model": vars_["model"].get(),
                "sku": vars_["sku"].get(),
                "color": vars_["color"].get(),
                "condition": vars_["condition"].get(),
                "price": vars_["price"].get(),
                "offer_price": vars_["offer"].get(),
                "ram": vars_["ram"].get(),
                "rom": vars_["rom"].get(),
                "description": description,
                "low_stock": vars_["low"].get(),
            }
            product_id = create_product_group(
                data, supplier_batches, self.user)
            self.refresh_all()
            messagebox.showinfo(
                "Product Group Saved",
                f"Product group {
                    data['sku'].upper()} saved with ID {product_id}.\n{
                    total_var.get()}\nEvery unit is linked to its supplier and buying price.",
                parent=win)
            win.destroy()

        footer = ttk.Frame(sf.content)
        footer.pack(fill="x", padx=12, pady=(6, 80))
        ttk.Button(
            footer,
            text="Cancel",
            command=win.destroy).pack(
            side="right",
            padx=4)
        ttk.Button(
            footer,
            text="Save Product Group",
            style="Accent.TButton",
            command=lambda: safe_run(save_group)()).pack(
            side="right",
            padx=4)

    @safe_run
    def open_supplier_stock_dialog(self):
        """Add one supplier purchase batch with exact unit ownership details."""
        pid = self.selected_inv_id()
        if not pid:
            messagebox.showwarning(
                "Select product",
                "Select the product in the Inventory table first, then press + Add Supplier Stock / IMEIs.")
            return
        p = query_one("SELECT * FROM products WHERE id=?", (pid,))
        if not p:
            raise ValueError("Selected product was not found")

        win = tk.Toplevel(self)
        win.title(f"Add Supplier Stock - {p.get('sku')}")
        win.geometry("900x760")
        win.minsize(720, 560)
        win.configure(bg=UI.BG)
        win.transient(self)
        sf = ScrollFrame(win, bg=UI.BG)
        sf.pack(fill="both", expand=True)
        card, inner = mac_card(
            sf.content, "+ New Supplier Stock Batch", padding=14)
        card.pack(fill="both", expand=True, padx=10, pady=10)

        tk.Label(
            inner,
            text=f"{
                product_display_name(p)}  |  SKU {
                p.get('sku')}  |  Current Qty {
                p.get('quantity')}  |  Current Average {
                    money(
                        p.get('cost'))}",
            bg=UI.SURFACE,
            fg=UI.BLUE,
            font=(
                "Segoe UI",
                11,
                "bold")).pack(
            anchor="w",
            pady=(
                0,
                8))
        tk.Label(
            inner,
            text="Every saved IMEI/ID keeps this supplier and buying price permanently, so a faulty or returned unit can be traced to its source.",
            bg=UI.SURFACE,
            fg=UI.MUTED,
            font=(
                "Segoe UI",
                9),
            wraplength=820,
            justify="left").pack(
            anchor="w",
            pady=(
                0,
                10))

        suppliers = [r["supplier"] for r in query(
            "SELECT DISTINCT supplier FROM restock_batches WHERE TRIM(COALESCE(supplier,''))<>'' ORDER BY supplier")]
        supplier_var = tk.StringVar(value=str(p.get("supplier") or ""))
        qty_var = tk.StringVar(value="1")
        price_var = tk.StringVar(value=str(n(p.get("cost")) or ""))
        note_var = tk.StringVar(value="Supplier purchase")
        must_track = bool(p.get("is_serialized"))
        can_start_tracking = i(p.get("quantity")) <= 0
        track_var = tk.BooleanVar(value=must_track or can_start_tracking)

        form = ttk.Frame(inner)
        form.pack(fill="x")
        ttk.Label(
            form,
            text="Supplier",
            width=18).grid(
            row=0,
            column=0,
            sticky="w",
            pady=3)
        ttk.Combobox(
            form,
            textvariable=supplier_var,
            values=suppliers).grid(
            row=0,
            column=1,
            sticky="ew",
            pady=3)
        ttk.Label(
            form,
            text="Quantity",
            width=18).grid(
            row=1,
            column=0,
            sticky="w",
            pady=3)
        ttk.Entry(
            form,
            textvariable=qty_var).grid(
            row=1,
            column=1,
            sticky="ew",
            pady=3)
        ttk.Label(
            form,
            text="Buying Price / Unit",
            width=18).grid(
            row=2,
            column=0,
            sticky="w",
            pady=3)
        ttk.Entry(
            form,
            textvariable=price_var).grid(
            row=2,
            column=1,
            sticky="ew",
            pady=3)
        ttk.Label(
            form,
            text="Batch Note",
            width=18).grid(
            row=3,
            column=0,
            sticky="w",
            pady=3)
        ttk.Entry(
            form,
            textvariable=note_var).grid(
            row=3,
            column=1,
            sticky="ew",
            pady=3)
        form.columnconfigure(1, weight=1)

        track = ttk.Checkbutton(
            inner,
            text="Track every unit separately with IMEI / Serial / Internal ID",
            variable=track_var)
        track.pack(anchor="w", pady=(10, 4))
        if must_track:
            track.state(["selected", "disabled"])
        elif not can_start_tracking:
            track.state(["disabled"])
            track_var.set(False)
            tk.Label(
                inner,
                text="This SKU already contains bulk stock, so this batch remains bulk. Create a separate exact-unit SKU if individual ID tracking is required.",
                bg=UI.SURFACE,
                fg=UI.RED,
                font=(
                    "Segoe UI",
                    9),
                wraplength=820,
                justify="left").pack(
                anchor="w",
                pady=(
                    0,
                    5))

        unit_box = ttk.LabelFrame(
            inner, text="Separate IMEI / ID Text Areas", padding=8)
        unit_box.pack(fill="both", expand=True, pady=8)
        unit_grid = ttk.Frame(unit_box)
        unit_grid.pack(fill="both", expand=True)
        unit_widgets = []

        def rebuild_fields(*_):
            old = [w.get("1.0", "end").strip() for w in unit_widgets]
            for child in unit_grid.winfo_children():
                child.destroy()
            unit_widgets.clear()
            if not track_var.get():
                ttk.Label(
                    unit_grid,
                    text="Bulk quantity mode: supplier, quantity and buying price will still be saved in the purchase history.").grid(
                    row=0,
                    column=0,
                    sticky="w",
                    pady=8)
                return
            qty = max(1, i(qty_var.get()) or 1)
            if qty > 200:
                ttk.Label(
                    unit_grid,
                    text="For safety this screen shows up to 200 separate unit fields per batch. Reduce the quantity or save in multiple batches.").grid(
                    row=0,
                    column=0,
                    columnspan=2,
                    sticky="w",
                    pady=8)
                qty = 200
            for idx in range(qty):
                ttk.Label(
                    unit_grid,
                    text=f"Unit {
                        idx + 1:03d}",
                    width=11).grid(
                    row=idx,
                    column=0,
                    sticky="nw",
                    padx=(
                        0,
                        6),
                    pady=3)
                txt = tk.Text(
                    unit_grid,
                    height=2,
                    width=66,
                    wrap="none",
                    font=(
                        "Consolas",
                        9))
                if idx < len(old):
                    txt.insert("1.0", old[idx])
                txt.grid(row=idx, column=1, sticky="ew", pady=3)
                unit_widgets.append(txt)
            unit_grid.columnconfigure(1, weight=1)

        rebuild_job = {"id": None}

        def schedule_rebuild(*_):
            if rebuild_job["id"]:
                try:
                    win.after_cancel(rebuild_job["id"])
                except tk.TclError:
                    pass
            rebuild_job["id"] = win.after(250, rebuild_fields)
        qty_var.trace_add("write", schedule_rebuild)
        track_var.trace_add("write", schedule_rebuild)
        rebuild_fields()

        def generate_ids():
            for txt, code in zip(
                unit_widgets, generate_internal_ids(
                    len(unit_widgets))):
                txt.delete("1.0", "end")
                txt.insert("1.0", code)

        def save_batch():
            supplier = supplier_var.get().strip()
            qty = i(qty_var.get())
            buying_price = n(price_var.get())
            if not supplier:
                raise ValueError("Supplier name is required")
            if qty <= 0:
                raise ValueError("Quantity must be greater than zero")
            if buying_price <= 0:
                raise ValueError("Buying price must be greater than zero")
            if track_var.get():
                if qty > 200:
                    raise ValueError(
                        "Save no more than 200 individually tracked units in one batch")
                codes = [w.get("1.0", "end").strip() for w in unit_widgets]
                if len(codes) != qty or any(not code for code in codes):
                    raise ValueError(
                        f"Enter one IMEI / ID in every field. Expected {qty}, completed {sum(bool(x) for x in codes)}")
                normalized = [code.casefold() for code in codes]
                if len(set(normalized)) != len(normalized):
                    raise ValueError(
                        "Duplicate IMEI / ID found in this supplier batch")
                qty_or_units = "\n".join(codes)
            else:
                qty_or_units = str(qty)
            added = restock_product(
                pid,
                qty_or_units,
                buying_price,
                supplier,
                note_var.get(),
                self.user)
            if added != qty:
                raise ValueError(
                    f"Expected to add {qty} units, but only {added} were saved")
            self.refresh_all()
            self.refresh_restock_history(pid)
            messagebox.showinfo(
                "Supplier Stock Added", f"Added {added} units from {supplier}.\nBuying price: {
                    money(buying_price)} each.\nSupplier and cost are now linked to every tracked IMEI / ID.")
            win.destroy()

        buttons = ttk.Frame(inner)
        buttons.pack(fill="x", pady=(4, 12))
        ttk.Button(
            buttons,
            text="Generate Internal IDs",
            command=generate_ids).pack(
            side="left",
            padx=3)
        ttk.Button(
            buttons,
            text="Clear IDs",
            command=lambda: [
                w.delete(
                    "1.0",
                    "end") for w in unit_widgets]).pack(
            side="left",
            padx=3)
        ttk.Button(
            buttons,
            text="Save Supplier Batch",
            style="Accent.TButton",
            command=lambda: safe_run(save_batch)()).pack(
            side="right",
            padx=3)
        ttk.Button(
            buttons,
            text="Cancel",
            command=win.destroy).pack(
            side="right",
            padx=3)

    @safe_run
    def find_unit_supplier(self):
        term = simpledialog.askstring(
            "Trace Unit Supplier",
            "Enter the full IMEI / ID or its last digits:",
            parent=self)
        if not term or not term.strip():
            return
        term = term.strip()
        rows = query("""
            SELECT u.id, u.unit_code, u.supplier, u.cost, u.status, u.created_at,
                   r.batch_code,
                   p.sku, p.brand, p.model,
                   i.invoice_no AS retail_invoice,
                   w.invoice_no AS wholesale_invoice,
                   w.shop_name
            FROM product_units u
            JOIN products p ON p.id=u.product_id
            LEFT JOIN restock_batches r ON r.id=u.purchase_batch_id
            LEFT JOIN invoices i ON i.id=u.invoice_id
            LEFT JOIN wholesale_invoices w ON w.id=u.wholesale_invoice_id
            WHERE lower(u.unit_code)=lower(?)
               OR lower(substr(u.unit_code, -?))=lower(?)
            ORDER BY CASE WHEN lower(u.unit_code)=lower(?) THEN 0 ELSE 1 END, u.id DESC
        """, (term, len(term), term, term))
        if not rows:
            messagebox.showinfo(
                "Unit Not Found",
                "No unit matches that IMEI / ID. Check the full value or try the last digits.")
            return

        win = tk.Toplevel(self)
        win.title(f"Supplier Trace - {term}")
        win.geometry("1120x500")
        win.configure(bg=UI.BG)
        card, inner = mac_card(
            win, "IMEI / ID Supplier and Sale Trace", padding=14)
        card.pack(fill="both", expand=True, padx=10, pady=10)
        tk.Label(
            inner,
            text="This is the permanent source record for warranty, return and supplier-claim investigation.",
            bg=UI.SURFACE,
            fg=UI.MUTED,
            font=(
                "Segoe UI",
                9)).pack(
            anchor="w",
            pady=(
                0,
                8))
        cols = [
            "imei",
            "item",
            "supplier",
            "batch",
            "buying",
            "status",
            "sale_ref",
            "shop",
            "added"]
        headings = {
            "imei": "IMEI / ID",
            "item": "Item / SKU",
            "supplier": "Original Supplier",
            "batch": "Purchase Batch",
            "buying": "Buying Price",
            "status": "Current Status",
            "sale_ref": "Invoice / Issue Bill",
            "shop": "Partner Shop",
            "added": "Stock Added"}
        wrap, tree = self.table(inner, cols, headings=headings, height=10)
        wrap.pack(fill="both", expand=True)
        tree.column("imei", width=220)
        tree.column("item", width=220)
        tree.column("supplier", width=170)
        tree.column("sale_ref", width=150)
        for row in rows:
            item = " ".join(str(row.get(x) or "").strip()
                            for x in ["brand", "model", "sku"]).strip()
            sale_ref = row.get("retail_invoice") or row.get(
                "wholesale_invoice") or "-"
            tree.insert("",
                        "end",
                        values=(row.get("unit_code"),
                                item,
                                row.get("supplier") or "Unknown",
                                row.get("batch_code") or "Legacy / Unlinked",
                                f"{n(row.get('cost')):,.2f}",
                                row.get("status"),
                                sale_ref,
                                row.get("shop_name") or "-",
                                row.get("created_at")))
        ttk.Button(
            inner,
            text="Close",
            command=win.destroy).pack(
            anchor="e",
            pady=(
                8,
                0))

    def update_serial_area_state(self):
        if not hasattr(
                self,
                "serial_panel") or not hasattr(
                self,
                "inv_units_text"):
            return
        self.serial_panel.configure(
            text="Serial / IMEI Units - realtime fields")
        self.inv_units_text.configure(state="normal", background="white")
        self.autofill_serial_slots(False)

    def _generated_serial_lines(self, sku, qty):
        return generate_internal_ids(qty)

    def _serial_text_lines(self):
        if not hasattr(self, "inv_units_text"):
            return []
        text = self.inv_units_text.get("1.0", "end")
        lines = []
        for raw in text.replace(",", "\n").splitlines():
            value = raw.strip()
            if value and not value.startswith("#"):
                lines.append(value)
        return lines

    def clear_serial_lines(self):
        if not hasattr(self, "inv_units_text"):
            return
        self.inv_units_text.configure(state="normal", background="white")
        self.inv_units_text.delete("1.0", "end")
        self._auto_serial_lines = []

    def autofill_serial_slots(self, force=False):
        if not hasattr(self, "inv_units_text"):
            return
        self.inv_units_text.configure(state="normal", background="white")
        qty = max(0, i(self.inv_vars["qty"].get()))
        if qty <= 0:
            if force:
                self.clear_serial_lines()
            return
        sku = (self.inv_vars["sku"].get().strip().upper() or "AUTO")
        current_lines = self._serial_text_lines()
        auto_lines = getattr(self, "_auto_serial_lines", [])
        current_is_auto = bool(current_lines) and current_lines == auto_lines
        # Only generate actual IDs when the staff presses Generate Auto IDs, or when existing lines are auto-generated.
        # This prevents accessories/bulk stock from accidentally becoming
        # serialized.
        if force:
            lines = self._generated_serial_lines(sku, qty)
            self._auto_serial_lines = list(lines)
            self.inv_units_text.delete("1.0", "end")
            self.inv_units_text.insert("end", "\n".join(lines))
            return
        if current_is_auto:
            lines = self._generated_serial_lines(sku, qty)
            self._auto_serial_lines = list(lines)
            self.inv_units_text.delete("1.0", "end")
            self.inv_units_text.insert("end", "\n".join(lines))

    def open_serial_fields_popup(self):
        qty = max(1, i(self.inv_vars["qty"].get()) or 1)
        sku = (self.inv_vars["sku"].get().strip().upper() or "AUTO")
        existing = self._serial_text_lines()
        while len(existing) < qty:
            existing.append("")
        existing = existing[:qty]
        win = tk.Toplevel(self)
        win.title(f"Serial / IMEI Fields - {qty} Units")
        win.geometry("720x640")
        win.configure(bg=UI.BG)
        sf = ScrollFrame(win, bg=UI.BG)
        sf.pack(fill="both", expand=True)
        card, inner = mac_card(
            sf.content, "Separate Serial / IMEI Fields", padding=14)
        card.pack(fill="both", expand=True, padx=10, pady=10)
        tk.Label(
            inner,
            text="Type one serial/IMEI per unit. Keep all fields empty if this is bulk/accessory stock.",
            bg=UI.SURFACE,
            fg=UI.MUTED,
            font=(
                "Segoe UI",
                9)).pack(
            anchor="w",
            pady=(
                0,
                8))
        entries = []
        grid = ttk.Frame(inner)
        grid.pack(fill="both", expand=True)
        for idx, value in enumerate(existing):
            ttk.Label(
                grid,
                text=f"Unit {
                    idx + 1:02d}",
                width=10).grid(
                row=idx,
                column=0,
                sticky="w",
                padx=(
                    0,
                    6),
                pady=2)
            var = tk.StringVar(value=value)
            ent = ttk.Entry(grid, textvariable=var, width=64)
            ent.grid(row=idx, column=1, sticky="ew", pady=2)
            entries.append(var)
        grid.columnconfigure(1, weight=1)

        def generate_ids():
            for var, code in zip(
                entries, self._generated_serial_lines(
                    sku, qty)):
                var.set(code)

        def apply():
            lines = [v.get().strip() for v in entries if v.get().strip()]
            self.inv_units_text.configure(state="normal", background="white")
            self.inv_units_text.delete("1.0", "end")
            self.inv_units_text.insert("end", "\n".join(lines))
            self._auto_serial_lines = list(lines) if lines else []
            win.destroy()
        btns = ttk.Frame(inner)
        btns.pack(fill="x", pady=10)
        ttk.Button(
            btns,
            text="Generate Auto IDs",
            command=generate_ids).pack(
            side="left",
            padx=3)
        ttk.Button(
            btns, text="Clear All", command=lambda: [
                v.set("") for v in entries]).pack(
            side="left", padx=3)
        ttk.Button(
            btns,
            text="Apply Serial Fields",
            style="Accent.TButton",
            command=apply).pack(
            side="right",
            padx=3)
        ttk.Button(
            btns,
            text="Cancel",
            command=win.destroy).pack(
            side="right",
            padx=3)

    @safe_run
    def add_inventory_product(self):
        serial_lines = self._serial_text_lines()
        data = {
            "sku": self.inv_vars["sku"].get(),
            "type": self.inv_type.get(),
            "category": self.inv_vars["category"].get(),
            "brand": self.inv_vars["brand"].get(),
            "model": self.inv_vars["model"].get(),
            "color": self.inv_vars["color"].get(),
            "ram": self.inv_vars["ram"].get(),
            "rom": self.inv_vars["rom"].get(),
            "condition": self.inv_condition.get(),
            "description": self.inv_vars["desc"].get(),
            "supplier": self.inv_vars["supplier"].get(),
            "cost": self.inv_vars["cost"].get(),
            "price": self.inv_vars["price"].get(),
            "offer_price": self.inv_vars["offer"].get(),
            "quantity": self.inv_vars["qty"].get(),
            "low_stock": self.inv_vars["low"].get(),
            "is_serialized": bool(serial_lines),
            "units": "\n".join(serial_lines)}
        add_product(data, self.user)
        self.refresh_all()
        messagebox.showinfo("Saved", "Product added")

    def selected_inv_id(self):
        sel = self.inv_tree.selection()
        return int(self.inv_tree.item(sel[0], "values")[0]) if sel else None

    def load_selected_inventory(self):
        pid = self.selected_inv_id()
        if not pid:
            return
        p = query_one("SELECT * FROM products WHERE id=?", (pid,))
        if not p:
            return
        self.selected_product_id = pid
        for k, col in [("sku", "sku"), ("category", "category"), ("brand", "brand"), ("model", "model"), ("color", "color"), ("ram", "ram"), ("rom", "rom"), (
                "supplier", "supplier"), ("cost", "cost"), ("price", "price"), ("offer", "offer_price"), ("qty", "quantity"), ("low", "low_stock"), ("desc", "description")]:
            self.inv_vars[k].set(str(p.get(col) or ""))
        self.inv_type.set(p.get("type") or "Phone")
        self.inv_condition.set(p.get("condition") or "Brand New")
        self.inv_serial.set("Auto")
        self.inv_units_text.delete("1.0", "end")
        if p.get("is_serialized"):
            self.inv_units_text.insert("end", "\n".join(
                [u["unit_code"] for u in available_units(pid)]))
        self.refresh_restock_history(pid)

    @safe_run
    def update_inventory_product(self):
        pid = self.selected_inv_id()
        if not pid:
            messagebox.showwarning(
                "Select product",
                "Select a product in Inventory Table - Scroll 2 first.")
            return
        p = query_one("SELECT * FROM products WHERE id=?", (pid,))
        if not p:
            raise ValueError("Selected product was not found")
        win = tk.Toplevel(self)
        win.title(f"Edit Product Info - {p['sku']}")
        win.geometry("720x650")
        win.transient(self)
        win.configure(bg=UI.BG)
        sf = ScrollFrame(win, bg=UI.BG)
        sf.pack(fill="both", expand=True)
        card, inner = mac_card(
            sf.content, "Edit Product Information", padding=14)
        card.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Label(
            inner,
            text=f"SKU {
                p['sku']} is permanent. Stock, suppliers, costs and IMEIs are managed through supplier batches.",
            style="Muted.TLabel",
            wraplength=650).pack(
            anchor="w",
            pady=(
                0,
                8))
        mapping = [
            ("Item Type",
             "type",
             PRODUCT_TYPES),
            ("Category",
             "category",
             None),
            ("Brand",
             "brand",
             None),
            ("Model",
             "model",
             None),
            ("Color",
             "color",
             None),
            ("RAM",
             "ram",
             None),
            ("Storage",
             "rom",
             None),
            ("Condition",
             "condition",
             CONDITIONS),
            ("Description",
             "description",
             None),
            ("Selling Price",
             "price",
             None),
            ("Offer Price",
             "offer_price",
             None),
            ("Low Stock Alert",
             "low_stock",
             None)]
        vars_ = {key: tk.StringVar(value=str(p.get(key) or ""))
                 for _, key, _ in mapping}
        form = ttk.Frame(inner)
        form.pack(fill="x")
        for row, (label, key, values) in enumerate(mapping):
            ttk.Label(
                form,
                text=label,
                width=22).grid(
                row=row,
                column=0,
                sticky="w",
                pady=3)
            widget = ttk.Combobox(
                form,
                textvariable=vars_[key],
                values=values,
                state="readonly") if values else ttk.Entry(
                form,
                textvariable=vars_[key])
            widget.grid(row=row, column=1, sticky="ew", pady=3)
        form.columnconfigure(1, weight=1)

        def save():
            data = {key: var.get() for key, var in vars_.items()}
            update_product(pid, data, self.user)
            self.refresh_all()
            messagebox.showinfo(
                "Updated", f"Product {
                    p['sku']} information updated.", parent=win)
            win.destroy()
        buttons = ttk.Frame(inner)
        buttons.pack(fill="x", pady=12)
        ttk.Button(
            buttons,
            text="Save Changes",
            style="Accent.TButton",
            command=lambda: safe_run(save)()).pack(
            side="right",
            padx=3)
        ttk.Button(
            buttons,
            text="Cancel",
            command=win.destroy).pack(
            side="right",
            padx=3)

    @safe_run
    def open_offer_manager(self):
        if self.user.get("role") != "admin":
            raise PermissionError("Only administrators can manage offers")
        win = tk.Toplevel(self)
        win.title("Admin Offer Manager")
        win.geometry("1080x720")
        win.minsize(850, 560)
        win.transient(self)
        win.configure(bg=UI.BG)
        card, inner = mac_card(win, "Product Offers", padding=14)
        card.pack(fill="both", expand=True, padx=10, pady=10)
        tk.Label(
            inner,
            text="Add a price below the regular selling price, or remove an existing offer instantly. Applied offers are recorded on invoice lines.",
            bg=UI.SURFACE,
            fg=UI.MUTED,
            font=(
                "Segoe UI",
                9)).pack(
            anchor="w",
            pady=(
                0,
                8))
        top = ttk.Frame(inner)
        top.pack(fill="x", pady=(0, 6))
        search = tk.StringVar()
        offer = tk.StringVar()
        selected = {"id": None}
        ttk.Label(top, text="Search").pack(side="left")
        entry = ttk.Entry(top, textvariable=search)
        entry.pack(side="left", fill="x", expand=True, padx=5)
        wrap, tree = self.table(
            inner, [
                "id", "sku", "item", "regular", "offer", "saving", "status"], height=18)
        wrap.pack(fill="both", expand=True)
        tree.column("item", width=330)
        form = ttk.Frame(inner)
        form.pack(fill="x", pady=10)
        selection_label = tk.StringVar(value="Select a product")
        ttk.Label(
            form,
            textvariable=selection_label,
            font=(
                "Segoe UI",
                10,
                "bold")).pack(
            side="left")
        ttk.Label(form, text="Offer Price").pack(side="left", padx=(20, 3))
        ttk.Entry(form, textvariable=offer, width=15).pack(side="left")

        def fill(*_):
            tree.delete(*tree.get_children())
            for p in search_products(search.get(), "All", True):
                regular = n(p.get("price"))
                current = n(p.get("offer_price"))
                saving = max(0, regular - current) if current else 0
                tree.insert("",
                            "end",
                            values=(p["id"],
                                    p["sku"],
                                    product_display_name(p),
                                    f"{regular:,.0f}",
                                    f"{current:,.0f}" if current else "-",
                                    f"{saving:,.0f}" if saving else "-",
                                    "Offer Active" if current else "Regular Price"))

        def select(_=None):
            sel = tree.selection()
            if not sel:
                return
            values = tree.item(sel[0], "values")
            selected["id"] = int(values[0])
            selection_label.set(
                f"{values[1]} | {values[2]} | Regular Rs. {values[3]}")
            offer.set("" if values[4] ==
                      "-" else str(values[4]).replace(",", ""))

        def apply_offer():
            if not selected["id"]:
                raise ValueError("Select a product first")
            set_product_offer(selected["id"], offer.get(), self.user)
            self.refresh_all()
            fill()
            messagebox.showinfo(
                "Offer Saved",
                "Offer price is active and will appear on new invoices.",
                parent=win)

        def remove_offer():
            if not selected["id"]:
                raise ValueError("Select a product first")
            set_product_offer(selected["id"], 0, self.user)
            offer.set("")
            self.refresh_all()
            fill()
            messagebox.showinfo(
                "Offer Removed",
                "The product now uses its regular selling price.",
                parent=win)
        search.trace_add("write", fill)
        tree.bind("<<TreeviewSelect>>", select)
        tree.bind("<Double-1>", select)
        ttk.Button(
            form,
            text="Apply Offer",
            style="Accent.TButton",
            command=lambda: safe_run(apply_offer)()).pack(
            side="right",
            padx=3)
        ttk.Button(
            form,
            text="Remove Offer",
            style="Danger.TButton",
            command=lambda: safe_run(remove_offer)()).pack(
            side="right",
            padx=3)
        ttk.Button(
            form,
            text="Close",
            command=win.destroy).pack(
            side="right",
            padx=3)
        fill()
        entry.focus_set()

    @safe_run
    def restock_selected_product(self):
        pid = self.selected_inv_id()
        if not pid:
            return
        serial_lines = self._serial_text_lines()
        qty_or_units = "\n".join(
            serial_lines) if serial_lines else self.inv_vars["qty"].get()
        added = restock_product(
            pid,
            qty_or_units,
            self.inv_vars["cost"].get(),
            self.inv_vars["supplier"].get(),
            "Manual restock",
            self.user)
        self.refresh_all()
        messagebox.showinfo(
            "Restocked",
            f"Added {added} units. Old stock data saved for finance.")

    @safe_run
    def delete_inventory_product(self):
        pid = self.selected_inv_id()
        if pid and messagebox.askyesno(
            "Delete",
                "Delete selected product? Only allowed if no sales history."):
            delete_product(pid, self.user)
            self.refresh_all()

    def refresh_inventory(self):
        self.inv_tree.delete(*self.inv_tree.get_children())
        for p in search_products(
            self.inv_search.get(),
            self.inv_filter_type.get(),
            bool(
                self.inv_include_empty.get())):
            self.inv_tree.insert("",
                                 "end",
                                 values=(p["id"],
                                         p["sku"],
                                         p["type"],
                                         product_display_name(p),
                                         p.get("available_qty",
                                               p.get("quantity")),
                                         p.get("sold_qty",
                                               0),
                                         p.get("wholesale_qty",
                                               0),
                                         f"{n(p['cost']):,.0f}",
                                         f"{n(p['price']):,.0f}",
                                         p.get("status")))
        self.refresh_restock_history(self.selected_product_id)

    def refresh_restock_history(self, pid=None):
        self.restock_tree.delete(*self.restock_tree.get_children())
        for r in restock_history(pid):
            self.restock_tree.insert("",
                                     "end",
                                     values=(r["created_at"],
                                             r["sku"],
                                             r["qty_added"],
                                             r["old_qty"],
                                             r["new_qty"],
                                             f"{n(r['unit_cost']):,.0f}",
                                             f"{n(r['new_average_cost']):,.0f}",
                                             r.get("supplier") or ""))

    def show_inventory_details(self):
        pid = self.selected_inv_id()
        if not pid:
            messagebox.showwarning("Select product", "Select a product first.")
            return
        try:
            d = product_unit_history(pid)
            suppliers = product_supplier_summary(pid)
            p = d["product"]
            rows = stock_detail_rows(pid)
            win = tk.Toplevel(self)
            win.title(f"Stock Details - {p['sku']}")
            win.geometry("1240x760")
            win.configure(bg=UI.BG)
            sf = ScrollFrame(win)
            sf.pack(fill="both", expand=True)
            header, head = mac_card(
                sf.content, "Stock Details - Full Unit Profit View", padding=14)
            header.pack(fill="x", padx=10, pady=(10, 6))
            title = f"{
                product_display_name(p)}   |   SKU {
                p['sku']}   |   Current Qty {
                p['quantity']}   |   Average Cost {
                money(
                    p['cost'])}   |   Selling {
                        money(
                            n(
                                p.get('offer_price')) or n(
                                    p.get('price')))}"
            tk.Label(
                head,
                text=title,
                bg=UI.SURFACE,
                fg=UI.TEXT,
                font=(
                    "Segoe UI",
                    14,
                    "bold")).pack(
                anchor="w")
            tk.Label(
                head,
                text="This popup shows every unit/status: ID, name, supplier, IMEI/SKU, cost, selling price, profit and sold/available status.",
                bg=UI.SURFACE,
                fg=UI.MUTED,
                font=(
                    "Segoe UI",
                    9)).pack(
                anchor="w",
                pady=(
                    4,
                    0))

            # Main exact stock table requested by user.
            main_lf = ttk.LabelFrame(
                sf.content, text="Unit / Stock Details", padding=8)
            main_lf.pack(fill="both", expand=True, padx=10, pady=6)
            cols = [
                "id",
                "name",
                "supplier",
                "batch",
                "imei",
                "cost",
                "selling",
                "profit",
                "status",
                "sold_ref",
                "date"]
            wrap, tree = self.table(main_lf, cols, headings={"id": "ID", "name": "Name", "supplier": "Supplier", "batch": "Purchase Batch", "imei": "IMEI / SKU",
                                    "cost": "Cost", "selling": "Selling", "profit": "Profit", "status": "Sold / Available", "sold_ref": "Invoice", "date": "Date"}, height=14)
            tree.column("name", width=250)
            tree.column("supplier", width=160)
            tree.column("imei", width=180)
            tree.column("status", width=210)
            wrap.pack(fill="both", expand=True)
            for r in rows:
                tree.insert("",
                            "end",
                            values=(r.get("id"),
                                    r.get("name"),
                                    r.get("supplier"),
                                    r.get("batch"),
                                    r.get("imei"),
                                    f"{n(r.get('cost')):,.0f}",
                                    f"{n(r.get('selling')):,.0f}",
                                    f"{n(r.get('profit')):,.0f}",
                                    r.get("status"),
                                    r.get("sold_ref"),
                                    r.get("date")))

            # Supplier / restock summary for financial average-cost proof.
            sup_lf = ttk.LabelFrame(
                sf.content,
                text="Supplier Average Cost Summary",
                padding=8)
            sup_lf.pack(fill="both", expand=True, padx=10, pady=6)
            wrap, sup_tree = self.table(sup_lf, ["supplier", "qty_added", "avg_cost", "stock_value"], headings={
                                        "qty_added": "Qty Added", "avg_cost": "Average Cost", "stock_value": "Total Stock Value"}, height=6)
            wrap.pack(fill="both", expand=True)
            for row in suppliers:
                sup_tree.insert("",
                                "end",
                                values=(row.get("supplier"),
                                        row.get("qty_added"),
                                        f"{n(row.get('avg_cost')):,.0f}",
                                        f"{n(row.get('stock_value')):,.0f}"))

            batch_lf = ttk.LabelFrame(
                sf.content, text="Restock Batches / Audit Trail", padding=8)
            batch_lf.pack(fill="both", expand=True, padx=10, pady=(6, 16))
            batch_cols = [
                "created_at",
                "supplier",
                "qty_added",
                "unit_cost",
                "old_qty",
                "new_qty",
                "old_average_cost",
                "new_average_cost"]
            wrap, bt = self.table(batch_lf, batch_cols, height=7)
            wrap.pack(fill="both", expand=True)
            for r in d.get("batches", []):
                bt.insert("",
                          "end",
                          values=(r.get("created_at"),
                                  r.get("supplier"),
                                  r.get("qty_added"),
                                  f"{n(r.get('unit_cost')):,.0f}",
                                  r.get("old_qty"),
                                  r.get("new_qty"),
                                  f"{n(r.get('old_average_cost')):,.0f}",
                                  f"{n(r.get('new_average_cost')):,.0f}"))
        except Exception as e:
            messagebox.showerror("Details Error", str(e))

    # ---------------- Clients ----------------

    def build_clients_tab(self):
        root_sf = ScrollFrame(self.tab_clients, bg=UI.BG)
        root_sf.pack(fill="both", expand=True)
        root = root_sf.content
        card, inner = mac_card(root, "Client Invoice Center", padding=14)
        card.pack(fill="both", expand=True, padx=8, pady=8)
        filter_bar = ttk.Frame(inner)
        filter_bar.pack(fill="x", pady=(0, 8))
        self.client_search = tk.StringVar()
        self.client_period = tk.StringVar(value="All")
        self.client_specific_date = tk.StringVar(
            value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Label(filter_bar, text="Search").pack(side="left")
        ttk.Entry(
            filter_bar,
            textvariable=self.client_search,
            width=28).pack(
            side="left",
            padx=5)
        ttk.Label(filter_bar, text="Filter").pack(side="left", padx=(10, 0))
        ttk.Combobox(
            filter_bar,
            textvariable=self.client_period,
            values=[
                "All",
                "Today",
                "Month",
                "Year",
                "Specific Date"],
            state="readonly",
            width=14).pack(
            side="left",
            padx=5)
        ttk.Entry(
            filter_bar,
            textvariable=self.client_specific_date,
            width=13).pack(
            side="left",
            padx=5)
        ttk.Button(
            filter_bar,
            text="Apply",
            command=self.refresh_clients).pack(
            side="left",
            padx=5)
        actions = ttk.Frame(inner)
        actions.pack(fill="x", pady=(0, 8))
        ttk.Button(
            actions,
            text="Open PDF",
            command=self.open_selected_invoice_pdf).pack(
            side="left",
            padx=3)
        ttk.Button(
            actions,
            text="Send WhatsApp + PDF",
            command=self.whatsapp_selected_invoice).pack(
            side="left",
            padx=3)
        ttk.Button(
            actions,
            text="Delete Invoice (Admin)",
            style="Danger.TButton",
            command=self.delete_selected_invoice).pack(
            side="left",
            padx=3)
        wrap, self.invoice_tree = self.table(
            inner, [
                "id", "invoice", "date", "client", "whatsapp", "email", "items", "total", "paid", "due", "warranty", "pdf"], height=17)
        for col, width in {"id": 45, "invoice": 140, "date": 140, "client": 180, "whatsapp": 120,
                           "email": 160, "items": 260, "total": 95, "paid": 95, "due": 95, "warranty": 170, "pdf": 60}.items():
            self.invoice_tree.column(col, width=width)
        wrap.pack(fill="both", expand=True)
        self.clients_tree = self.invoice_tree  # compatibility for refresh_all

    def _invoice_matches_client_filter(self, inv):
        q = (self.client_search.get() if hasattr(
            self, "client_search") else "").lower().strip()
        if q:
            hay = " ".join(
                str(
                    inv.get(k) or "") for k in [
                    "invoice_no",
                    "created_at",
                    "customer_name",
                    "customer_whatsapp",
                    "customer_phone",
                    "customer_email"]).lower()
            if q not in hay:
                return False
        period = self.client_period.get() if hasattr(self, "client_period") else "All"
        date_text = str(inv.get("created_at") or "")[:10]
        today = datetime.now().strftime("%Y-%m-%d")
        if period == "Today" and date_text != today:
            return False
        if period == "Month" and date_text[:7] != today[:7]:
            return False
        if period == "Year" and date_text[:4] != today[:4]:
            return False
        if period == "Specific Date" and date_text != self.client_specific_date.get().strip():
            return False
        return True

    def refresh_clients(self):
        if not hasattr(self, "invoice_tree"):
            return
        self.invoice_tree.delete(*self.invoice_tree.get_children())
        for inv0 in list_invoices(1000):
            if not self._invoice_matches_client_filter(inv0):
                continue
            inv = get_invoice(inv0["id"])
            items = "; ".join(
                [f"{x['product_name']} x{x['qty']}" for x in inv.get("items", [])])[:120]
            warranties = []
            general_items = [x for x in inv.get("items", []) if x.get(
                "general_warranty") and x.get("general_warranty") != "No Warranty"]
            if general_items:
                warranties.append(
                    "Gen: " +
                    ", ".join(
                        sorted(
                            set(
                                f"{
                                    x.get('general_warranty')} to {
                                    x.get('general_warranty_expire') or '-'}" for x in general_items))))
            ext = [
                x for x in inv.get(
                    "items",
                    []) if x.get("extended_warranty_expire")]
            if ext:
                warranties.append("Ext: " + ", ".join(sorted(set([x.get(
                    "extended_warranty_expire") for x in ext if x.get("extended_warranty_expire")]))))
            self.invoice_tree.insert("",
                                     "end",
                                     values=(inv["id"],
                                             inv["invoice_no"],
                                             inv["created_at"],
                                             inv["customer_name"],
                                             inv.get("customer_whatsapp") or inv.get("customer_phone") or "",
                                             inv.get("customer_email") or "",
                                             items,
                                             f"{n(inv['grand_total']):,.0f}",
                                             f"{n(inv['paid_total']):,.0f}",
                                             f"{n(inv['balance']):,.0f}",
                                             " | ".join(warranties),
                                             "Yes" if inv.get("pdf_path") else "No"))

    def load_client_invoices(self):
        self.refresh_clients()

    def refresh_invoices(self):
        self.refresh_clients()

    def selected_invoice_id_func(self):
        sel = self.invoice_tree.selection()
        return int(
            self.invoice_tree.item(
                sel[0],
                "values")[0]) if sel else None

    def open_selected_invoice_pdf(self):
        iid = self.selected_invoice_id_func()
        if iid:
            open_file(get_invoice(iid).get("pdf_path"))

    def whatsapp_selected_invoice(self):
        iid = self.selected_invoice_id_func()
        if not iid:
            return
        inv = get_invoice(iid)
        whatsapp_send(
            inv.get("customer_whatsapp") or inv.get("customer_phone"),
            client_statement_text(iid),
            inv.get("pdf_path"))

    @safe_run
    def delete_selected_invoice(self):
        iid = self.selected_invoice_id_func()
        if iid and messagebox.askyesno(
            "Delete Invoice",
                "Delete invoice and restore stock? Admin only."):
            delete_invoice(iid, self.user)
            self.refresh_all()

    # ---------------- Partner wholesale ----------------
    def build_partner_tab(self):
        root = tk.Frame(self.tab_partner, bg=UI.BG)
        root.pack(fill="both", expand=True)
        self.partner_nb = ttk.Notebook(root)
        self.partner_nb.pack(fill="both", expand=True, padx=6, pady=6)
        profile_tab = ttk.Frame(self.partner_nb)
        issue_tab = ttk.Frame(self.partner_nb)
        payments_tab = ttk.Frame(self.partner_nb)
        history_tab = ttk.Frame(self.partner_nb)
        self.partner_nb.add(profile_tab, text="Shop Profiles")
        self.partner_nb.add(issue_tab, text="Issue Items")
        self.partner_nb.add(payments_tab, text="Payments")
        self.partner_nb.add(history_tab, text="History & Due")

        # Shop profile page
        profile_left_sf = ScrollFrame(profile_tab, bg=UI.BG)
        profile_left_sf.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(
                0,
                6))
        profile_right_sf = ScrollFrame(profile_tab, bg=UI.BG)
        profile_right_sf.pack(
            side="right",
            fill="both",
            expand=True,
            padx=(
                6,
                0))
        left, right = profile_left_sf.content, profile_right_sf.content
        card, sbox = mac_card(left, "Create / Update Partner Shop", padding=14)
        card.pack(fill="x", padx=6, pady=6)
        self.shop_vars = {
            k: tk.StringVar() for k in [
                "name",
                "contact",
                "phone",
                "email",
                "address",
                "limit",
                "notes"]}
        for label, key in [("Shop Name", "name"), ("Contact Person", "contact"), ("WhatsApp", "phone"), (
                "Email", "email"), ("Address", "address"), ("Credit Limit", "limit"), ("Notes", "notes")]:
            self.labelled_entry(sbox, label, self.shop_vars[key])
        ttk.Button(
            sbox,
            text="Save / Update Shop",
            style="Accent.TButton",
            command=self.save_shop).pack(
            fill="x",
            pady=8)
        card2, listbox = mac_card(right, "Partner Shops", padding=14)
        card2.pack(fill="both", expand=True, padx=6, pady=6)
        wrap, self.shop_tree = self.table(
            listbox, [
                "id", "shop", "whatsapp", "invoices", "issued", "paid", "due", "progress"], height=14)
        wrap.pack(fill="both", expand=True)
        self.shop_tree.column("shop", width=240)
        self.shop_tree.bind("<<TreeviewSelect>>", lambda e: self.load_shop())
        self.shop_tree.bind(
            "<Double-1>",
            lambda e: self.open_partner_quick_profile())
        qbf = ttk.Frame(listbox)
        qbf.pack(fill="x", pady=(8, 0))
        ttk.Button(
            qbf,
            text="Open Shop Profile + Quick Payment",
            style="Accent.TButton",
            command=self.open_partner_quick_profile).pack(
            side="left",
            fill="x",
            expand=True,
            padx=3)
        ttk.Button(
            qbf,
            text="Send Due WhatsApp",
            command=self.send_shop_due_whatsapp).pack(
            side="left",
            fill="x",
            expand=True,
            padx=3)

        # Issue page
        issue_left_sf = ScrollFrame(issue_tab, bg=UI.BG)
        issue_left_sf.pack(side="left", fill="both", expand=True, padx=(0, 6))
        issue_left = issue_left_sf.content
        issue_right = ScrollFrame(issue_tab, bg=UI.BG)
        issue_right.pack(side="right", fill="both", expand=True, padx=(6, 0))
        card3, ibox = mac_card(
            issue_left, "Issue Items to Selected Shop", padding=14)
        card3.pack(fill="both", expand=True, padx=6, pady=6)
        self.issue_shop_label = tk.StringVar(
            value="Select a shop from Shop Profiles first")
        tk.Label(
            ibox,
            textvariable=self.issue_shop_label,
            bg=UI.SURFACE,
            fg=UI.BLUE,
            font=(
                "Segoe UI",
                11,
                "bold")).pack(
            anchor="w",
            pady=(
                0,
                8))
        ttk.Button(
            ibox,
            text="Open All Items / Pick Exact Unit",
            style="Accent.TButton",
            command=self.open_wholesale_item_picker).pack(
            fill="x",
            pady=(
                0,
                7))
        sf = ttk.Frame(ibox)
        sf.pack(fill="x")
        self.wh_search = tk.StringVar()
        wh_entry = ttk.Entry(sf, textvariable=self.wh_search)
        wh_entry.pack(side="left", fill="x", expand=True, padx=3)
        wh_entry.bind("<KeyRelease>", lambda e: self.refresh_wh_products())
        ttk.Button(
            sf,
            text="Search",
            command=self.refresh_wh_products).pack(
            side="left")
        wrap, self.wh_product_tree = self.table(
            ibox, ["id", "sku", "item", "qty", "retail"], height=7)
        wrap.pack(fill="both", expand=True, pady=6)
        af = ttk.Frame(ibox)
        af.pack(fill="x", pady=4)
        self.wh_qty = tk.StringVar(value="1")
        self.wh_price = tk.StringVar()
        self.wh_unit = tk.StringVar()
        ttk.Label(af, text="Qty").pack(side="left")
        ttk.Entry(
            af,
            textvariable=self.wh_qty,
            width=6).pack(
            side="left",
            padx=2)
        ttk.Label(af, text="Selling Price").pack(side="left")
        ttk.Entry(
            af,
            textvariable=self.wh_price,
            width=13).pack(
            side="left",
            padx=2)
        ttk.Label(af, text="Unit").pack(side="left")
        ttk.Entry(
            af,
            textvariable=self.wh_unit,
            width=16).pack(
            side="left",
            padx=2)
        ttk.Button(
            af,
            text="Add Issue Item",
            style="Accent.TButton",
            command=self.add_wh_item).pack(
            side="left",
            padx=2)
        card4, cartbox = mac_card(
            issue_right.content, "Issue Bill Preview", padding=14)
        card4.pack(fill="both", expand=True, padx=6, pady=6)
        wrap, self.wh_cart_tree = self.table(
            cartbox, ["item", "unit", "qty", "price", "total"], height=7)
        wrap.pack(fill="both", expand=True, pady=4)
        self.wh_discount = tk.StringVar(value="0")
        self.wh_note = tk.StringVar()
        self.wh_due_var = tk.StringVar(
            value="Issue Total: Rs.0 | Paid: Rs.0 | Due: Rs.0")
        self.wh_discount.trace_add("write", lambda *_: self.refresh_wh_cart())
        self.labelled_entry(cartbox, "Discount", self.wh_discount)
        self.labelled_entry(cartbox, "Note", self.wh_note)
        self.wh_payments = PaymentEditor(
            cartbox,
            "Paid at Issue / Installment",
            on_change=self.refresh_wh_cart)
        self.wh_payments.pack(fill="x", pady=4)
        tk.Label(
            cartbox,
            textvariable=self.wh_due_var,
            bg=UI.SURFACE,
            fg=UI.TEXT,
            font=(
                "Segoe UI",
                12,
                "bold")).pack(
            anchor="e",
            pady=4)
        ttk.Button(
            cartbox,
            text="Save Wholesale Issue + PDF",
            style="Accent.TButton",
            command=self.save_wholesale_issue).pack(
            fill="x",
            pady=6)
        ttk.Button(
            cartbox,
            text="Clear Issue Cart",
            command=lambda: (
                self.wh_cart.clear(),
                self.refresh_wh_cart())).pack(
            fill="x")

        # Payment page
        payments_sf = ScrollFrame(payments_tab, bg=UI.BG)
        payments_sf.pack(fill="both", expand=True)
        card5, paybox = mac_card(
            payments_sf.content, "Partner Payment / FIFO Allocation", padding=14)
        card5.pack(fill="x", padx=8, pady=8)
        self.pay_shop_label = tk.StringVar(
            value="Select a shop from dropdown or Shop Profiles")
        self.partner_payment_shop = tk.StringVar()
        ttk.Label(paybox, text="Select Partner Shop").pack(anchor="w")
        self.partner_payment_shop_combo = ttk.Combobox(
            paybox, textvariable=self.partner_payment_shop, state="readonly")
        self.partner_payment_shop_combo.pack(fill="x", pady=(2, 8))
        self.partner_payment_shop_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: self.select_payment_shop_from_combo())
        tk.Label(
            paybox,
            textvariable=self.pay_shop_label,
            bg=UI.SURFACE,
            fg=UI.BLUE,
            font=(
                "Segoe UI",
                11,
                "bold")).pack(
            anchor="w",
            pady=(
                0,
                8))
        self.partner_payment_editor = PaymentEditor(
            paybox, "Payment Breakdown")
        self.partner_payment_editor.pack(fill="x")
        self.partner_payment_note = tk.StringVar()
        self.labelled_entry(paybox, "Payment Note", self.partner_payment_note)
        ttk.Button(
            paybox,
            text="Save Partner Payment",
            style="Accent.TButton",
            command=self.save_partner_payment).pack(
            fill="x",
            pady=6)
        info = tk.Label(
            paybox,
            text="Payments are allocated to oldest unpaid bills first. The shop profile updates immediately with remaining due.",
            bg=UI.SURFACE,
            fg=UI.MUTED,
            font=(
                "Segoe UI",
                9))
        info.pack(anchor="w", pady=5)

        # History and due page
        history_sf = ScrollFrame(history_tab, bg=UI.BG)
        history_sf.pack(fill="both", expand=True)
        card6, prof = mac_card(
            history_sf.content, "Partner Full Profile / Past Details / Due Items", padding=14)
        card6.pack(fill="both", expand=True, padx=8, pady=8)
        top = ttk.Frame(prof)
        top.pack(fill="x")
        self.shop_summary = tk.StringVar(
            value="Select shop to view full history.")
        tk.Label(
            top,
            textvariable=self.shop_summary,
            bg=UI.SURFACE,
            fg=UI.TEXT,
            font=(
                "Segoe UI",
                12,
                "bold")).pack(
            side="left")
        ttk.Button(
            top,
            text="Send Due WhatsApp",
            command=self.send_shop_due_whatsapp).pack(
            side="right",
            padx=3)
        ttk.Button(
            top,
            text="Statement PDF",
            command=self.open_shop_statement_pdf).pack(
            side="right",
            padx=3)
        tables = ttk.Notebook(prof)
        tables.pack(fill="both", expand=True, pady=8)
        inv_page = ttk.Frame(tables)
        due_page = ttk.Frame(tables)
        tables.add(inv_page, text="Outstanding Invoices")
        tables.add(due_page, text="Due Items")
        wrap, self.wh_invoice_tree = self.table(
            inv_page, [
                "id", "invoice", "date", "total", "paid", "due", "status"], height=12)
        wrap.pack(fill="both", expand=True, pady=5)
        wrap, self.shop_due_items_tree = self.table(
            due_page, ["invoice", "item", "unit", "qty", "line", "invoice_due"], height=12)
        wrap.pack(fill="both", expand=True, pady=5)

    @safe_run
    def save_shop(self):
        data = {
            "name": self.shop_vars["name"].get(),
            "contact_person": self.shop_vars["contact"].get(),
            "phone": self.shop_vars["phone"].get(),
            "whatsapp": self.shop_vars["phone"].get(),
            "email": self.shop_vars["email"].get(),
            "address": self.shop_vars["address"].get(),
            "credit_limit": self.shop_vars["limit"].get(),
            "notes": self.shop_vars["notes"].get()}
        sid = add_shop(data, self.user)
        self.refresh_shops()
        messagebox.showinfo("Saved", f"Shop saved ID {sid}")

    def refresh_shops(self):
        self.shop_tree.delete(*self.shop_tree.get_children())
        shops = list_shops()
        for s in shops:
            issued = n(s.get("issued_total"))
            paid = n(s.get("paid_total"))
            progress = (paid / issued * 100) if issued else 0
            self.shop_tree.insert("",
                                  "end",
                                  values=(s["id"],
                                          s["name"],
                                          s.get("whatsapp") or s.get("phone") or "",
                                          s.get("invoice_count") or 0,
                                          f"{issued:,.0f}",
                                          f"{paid:,.0f}",
                                          f"{n(s.get('due_total')):,.0f}",
                                          f"{progress:.1f}%"))
        if hasattr(self, "partner_payment_shop_combo"):
            self.partner_payment_shop_combo["values"] = [
                f"{s['id']} | {s['name']} | Due {money(s.get('due_total'))}" for s in shops]

    def select_payment_shop_from_combo(self):
        val = self.partner_payment_shop.get().strip()
        if not val:
            return
        try:
            sid = int(val.split("|", 1)[0].strip())
            self.selected_shop_id = sid
            s = query_one("SELECT * FROM shops WHERE id=?", (sid,))
            if s:
                self.pay_shop_label.set(
                    f"Selected shop: {
                        s.get('name')} | payments update profile in realtime")
                if hasattr(self, "issue_shop_label"):
                    self.issue_shop_label.set(
                        f"Selected shop: {
                            s.get('name')} | WhatsApp: {
                            s.get('whatsapp') or s.get('phone') or '-'}")
            self.refresh_shop_profile()
        except Exception:
            pass

    def load_shop(self):
        sel = self.shop_tree.selection()
        if not sel:
            return
        sid = int(self.shop_tree.item(sel[0], "values")[0])
        self.selected_shop_id = sid
        s = query_one("SELECT * FROM shops WHERE id=?", (sid,))
        if s:
            for k, col in [("name", "name"), ("contact", "contact_person"), ("phone", "whatsapp"), (
                    "email", "email"), ("address", "address"), ("limit", "credit_limit"), ("notes", "notes")]:
                self.shop_vars[k].set(str(s.get(col) or ""))
            if hasattr(self, "issue_shop_label"):
                self.issue_shop_label.set(
                    f"Selected shop: {
                        s.get('name')} | WhatsApp: {
                        s.get('whatsapp') or s.get('phone') or '-'}")
            if hasattr(self, "pay_shop_label"):
                self.pay_shop_label.set(
                    f"Selected shop: {
                        s.get('name')} | payments update profile in realtime")
            if hasattr(self, "partner_payment_shop"):
                self.partner_payment_shop.set(
                    f"{s.get('id')} | {s.get('name')} | Due {money(s.get('due_total') or 0)}")
        self.refresh_shop_profile()

    def refresh_wh_products(self):
        self.wh_product_tree.delete(*self.wh_product_tree.get_children())
        for p in search_products(self.wh_search.get(), "All", False):
            self.wh_product_tree.insert("", "end", values=(p["id"], p["sku"], product_display_name(
                p), p.get("available_qty", p.get("quantity")), f"{n(p['price']):,.0f}"))

    def add_wh_item(self):
        sel = self.wh_product_tree.selection()
        if not sel:
            return
        pid = int(self.wh_product_tree.item(sel[0], "values")[0])
        p = query_one("SELECT * FROM products WHERE id=?", (pid,))
        if not p:
            return
        price = n(
            self.wh_price.get()) or n(
            p.get("offer_price")) or n(
            p.get("price"))
        qty_requested = max(1, i(self.wh_qty.get()))
        unit_text = self.wh_unit.get().strip()
        try:
            if p.get("is_serialized"):
                typed_units = [
                    u.strip() for u in unit_text.replace(
                        ",", "\n").splitlines() if u.strip()]
                units = available_units(pid)
                if typed_units:
                    for typed in typed_units:
                        match = next((u for u in units if u["unit_code"] == typed), None) or next(
                            (u for u in units if str(u["unit_code"]).endswith(typed)), None)
                        code = match["unit_code"] if match else typed
                        if any(
                                c.get("unit_code") == code for c in self.wh_cart):
                            raise ValueError(
                                f"Duplicate unit already in issue cart: {code}")
                        self.wh_cart.append({"product_id": pid, "product_name": product_display_name(
                            p), "unit_code": code, "qty": 1, "price": price, "discount": 0})
                else:
                    if len(units) < qty_requested:
                        raise ValueError(
                            f"Only {
                                len(units)} serialized units available.")
                    for u in units[:qty_requested]:
                        if any(
                                c.get("unit_code") == u["unit_code"] for c in self.wh_cart):
                            continue
                        self.wh_cart.append({"product_id": pid, "product_name": product_display_name(
                            p), "unit_code": u["unit_code"], "qty": 1, "price": price, "discount": 0})
            else:
                self.wh_cart.append({"product_id": pid, "product_name": product_display_name(
                    p), "unit_code": unit_text, "qty": qty_requested, "price": price, "discount": 0})
        except Exception as e:
            messagebox.showwarning("Cannot add issue item", str(e))
            return
        self.wh_price.set("")
        self.wh_unit.set("")
        self.refresh_wh_cart()

    def refresh_wh_cart(self):
        self.wh_cart_tree.delete(*self.wh_cart_tree.get_children())
        total = 0
        for idx, c in enumerate(self.wh_cart):
            line = n(c["price"]) * i(c["qty"])
            total += line
            self.wh_cart_tree.insert("", "end", iid=str(idx), values=(c["product_name"], c.get(
                "unit_code") or "-", c["qty"], f"{n(c['price']):,.0f}", f"{line:,.0f}"))
        grand = max(0, total - n(self.wh_discount.get()))
        paid = self.wh_payments.total()
        self.wh_due_var.set(
            f"Issue Total: {
                money(grand)} | Paid: {
                money(paid)} | Realtime Due: {
                money(
                    max(
                        0,
                        grand -
                        paid))}")

    @safe_run
    def save_wholesale_issue(self):
        self.refresh_wh_cart()
        if not self.selected_shop_id:
            messagebox.showwarning(
                "Select shop", "Select or save partner shop first")
            return
        billing = {
            "discount": self.wh_discount.get(),
            "payments": self.wh_payments.get_rows(),
            "note": self.wh_note.get()}
        inv = create_wholesale_invoice(
            self.selected_shop_id, self.wh_cart, billing, self.user)
        pdf = build_wholesale_invoice_pdf(inv)
        set_wholesale_pdf(inv["id"], pdf)
        open_file(pdf)
        if messagebox.askyesno(
            "Wholesale Issue Saved",
            f"Wholesale issue saved. Due: {
                money(
                inv['balance'])}.\n\nSend shop bill/details by WhatsApp now?"):
            prof = shop_profile(self.selected_shop_id)
            phone = prof["shop"].get("whatsapp") or prof["shop"].get("phone")
            whatsapp_send(
                phone, shop_statement_text(
                    self.selected_shop_id), pdf)
        self.wh_cart.clear()
        self.wh_payments.clear()
        self.refresh_all()
        self.refresh_shop_profile()

    def refresh_shop_profile(self):
        if not self.selected_shop_id:
            return
        prof = shop_profile(self.selected_shop_id)
        self.shop_summary.set(
            f"{
                prof['shop']['name']} | Total Due {
                money(
                    prof['balance'])} | Issued {
                    money(
                        prof['total_issued'])} | Paid {
                            money(
                                prof['total_paid'])}")
        self.wh_invoice_tree.delete(*self.wh_invoice_tree.get_children())
        for inv in prof["outstanding_invoices"]:
            self.wh_invoice_tree.insert("",
                                        "end",
                                        values=(inv["id"],
                                                inv["invoice_no"],
                                                inv["created_at"],
                                                f"{n(inv['grand_total']):,.0f}",
                                                f"{n(inv['paid_total']):,.0f}",
                                                f"{n(inv['balance']):,.0f}",
                                                inv["payment_status"]))
        self.shop_due_items_tree.delete(
            *self.shop_due_items_tree.get_children())
        for d in prof["due_items"]:
            self.shop_due_items_tree.insert("",
                                            "end",
                                            values=(d["invoice_no"],
                                                    d["product_name"],
                                                    d.get("unit_code") or "-",
                                                    d["qty"],
                                                    f"{n(d['line_total']):,.0f}",
                                                    f"{n(d['balance']):,.0f}"))

    @safe_run
    def save_partner_payment(self):
        if not self.selected_shop_id and hasattr(self, "partner_payment_shop"):
            self.select_payment_shop_from_combo()
        if not self.selected_shop_id:
            messagebox.showwarning("Select shop",
                                   "Select partner shop before saving payment.")
            return
        res = add_wholesale_payment(
            self.selected_shop_id,
            self.partner_payment_editor.get_rows(),
            self.partner_payment_note.get(),
            self.user)
        messagebox.showinfo(
            "Payment Saved", f"{
                res['payment_no']} saved and allocated. Amount {
                money(
                    res['amount'])}")
        self.partner_payment_editor.clear()
        self.refresh_all()
        self.refresh_shop_profile()

    def send_shop_due_whatsapp(self):
        if not self.selected_shop_id:
            return
        prof = shop_profile(self.selected_shop_id)
        phone = prof["shop"].get("whatsapp") or prof["shop"].get("phone")
        whatsapp_send(phone, shop_statement_text(self.selected_shop_id), "")

    def open_shop_statement_pdf(self):
        if not self.selected_shop_id:
            return
        prof = shop_profile(self.selected_shop_id)
        pdf = build_shop_statement_pdf(prof)
        open_file(pdf)

    # ---------------- Finance ----------------
    def build_finance_tab(self):
        sf = ScrollFrame(self.tab_finance)
        sf.pack(fill="both", expand=True)
        top = ttk.LabelFrame(
            sf.content,
            text="Admin Financial Dashboard / Staff Sold Report",
            padding=10)
        top.pack(fill="x", padx=8, pady=8)
        self.finance_period = tk.StringVar(value="month")
        self.finance_month = tk.StringVar(
            value=datetime.now().strftime("%Y-%m"))
        self.finance_date_from = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.finance_date_to = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        controls = ttk.Frame(top)
        controls.pack(fill="x")
        ttk.Label(controls, text="View").pack(side="left")
        ttk.Combobox(
            controls,
            textvariable=self.finance_period,
            values=[
                "today",
                "week",
                "month",
                "year",
                "custom"],
            state="readonly",
            width=12).pack(
            side="left",
            padx=3)
        ttk.Label(controls, text="Month").pack(side="left", padx=(12, 2))
        current = datetime.now()
        month_values = []
        for offset in range(36):
            total = current.year * 12 + (current.month - 1) - offset
            month_values.append(f"{total // 12:04d}-{total % 12 + 1:02d}")
        existing = [r["month"] for r in query(
            """SELECT DISTINCT substr(created_at,1,7) month FROM (
            SELECT created_at FROM invoices UNION ALL SELECT created_at FROM wholesale_invoices
        ) WHERE length(created_at)>=7 ORDER BY month DESC""")]
        month_values = list(dict.fromkeys(month_values + existing))
        self.finance_month_combo = ttk.Combobox(
            controls,
            textvariable=self.finance_month,
            values=month_values,
            width=11)
        self.finance_month_combo.pack(side="left", padx=3)
        ttk.Label(controls, text="Date From").pack(side="left", padx=(12, 2))
        ttk.Entry(controls, textvariable=self.finance_date_from, width=12).pack(side="left", padx=3)
        ttk.Label(controls, text="Date To").pack(side="left", padx=(8, 2))
        ttk.Entry(controls, textvariable=self.finance_date_to, width=12).pack(side="left", padx=3)
        ttk.Button(
            controls,
            text="Refresh Finance",
            command=self.refresh_finance).pack(
            side="left",
            padx=3)
        self.finance_summary = tk.StringVar(value="")
        ttk.Label(
            top,
            textvariable=self.finance_summary,
            font=(
                "Segoe UI",
                11,
                "bold"),
            anchor="w").pack(
            fill="x",
            padx=3,
            pady=(
                8,
                 0))
        self.chart_canvas = tk.Canvas(
            sf.content,
            height=220,
            bg="white",
            highlightthickness=1,
            highlightbackground=UI.BORDER)
        self.chart_canvas.pack(fill="x", padx=8, pady=8)
        income_box = ttk.LabelFrame(
            sf.content,
            text="Selected Period Income Details",
            padding=8)
        income_box.pack(fill="both", expand=True, padx=8, pady=8)
        wrap, self.finance_income_tree = self.table(
            income_box, [
                "source", "reference", "party", "date", "total", "paid", "due", "status"], headings={
                "party": "Customer / Partner", "status": "Payment Status"}, height=8)
        wrap.pack(fill="both", expand=True)
        self.finance_income_tree.column("party", width=230)
        self.finance_income_tree.column("date", width=145)
        metric_box = ttk.LabelFrame(
            sf.content, text="Financial Summary", padding=8)
        metric_box.pack(fill="both", expand=True, padx=8, pady=8)
        wrap, self.finance_tree = self.table(metric_box, ["metric", "value"], headings={
                                             "metric": "Metric", "value": "Amount / Value"}, height=8)
        wrap.pack(fill="both", expand=True)
        item_box = ttk.LabelFrame(
            sf.content,
            text="Sales and Profit by Item",
            padding=8)
        item_box.pack(fill="both", expand=True, padx=8, pady=8)
        wrap, self.finance_items_tree = self.table(item_box, ["item", "qty", "sales", "cost", "profit"], headings={
                                                   "item": "Item", "qty": "Sold Qty", "sales": "Sales", "cost": "Buying Cost", "profit": "Gross Profit"}, height=7)
        wrap.pack(fill="both", expand=True)
        asset_box = ttk.LabelFrame(
            sf.content,
            text="Current Inventory Assets (Weighted Average Cost)",
            padding=8)
        asset_box.pack(fill="both", expand=True, padx=8, pady=8)
        wrap, self.finance_assets_tree = self.table(asset_box, ["sku", "item", "qty", "avg_cost", "stock_value", "all_avg", "total_bought", "status"], headings={
                                                    "sku": "SKU", "item": "Item", "qty": "Available Qty", "avg_cost": "Live Avg Cost", "stock_value": "Live Stock Value", "all_avg": "All-Batch Avg Cost", "total_bought": "Total Bought Value", "status": "Status"}, height=7)
        wrap.pack(fill="both", expand=True)
        supplier_box = ttk.LabelFrame(
            sf.content,
            text="Supplier Quantity and Buying Price History",
            padding=8)
        supplier_box.pack(fill="both", expand=True, padx=8, pady=8)
        supplier_cols = [
            "sku",
            "item",
            "supplier",
            "qty",
            "buying_price",
            "value",
            "current_avg"]
        wrap, self.finance_supplier_tree = self.table(
            supplier_box, supplier_cols, headings={
                "sku": "SKU", "item": "Item", "supplier": "Supplier", "qty": "Supplier Qty", "buying_price": "Average Buying Price", "value": "Total Bought Value", "current_avg": "Current Weighted Avg"}, height=8)
        wrap.pack(fill="both", expand=True)
        due_box = ttk.LabelFrame(
            sf.content,
            text="Outstanding Receivables",
            padding=8)
        due_box.pack(fill="both", expand=True, padx=8, pady=(8, 24))
        wrap, self.finance_due_tree = self.table(due_box, ["type", "ref", "name", "date", "total", "paid", "due"], headings={
                                                 "type": "Sale Type", "ref": "Invoice", "name": "Customer / Shop", "date": "Date", "total": "Invoice Total", "paid": "Paid", "due": "Balance Due"}, height=7)
        wrap.pack(fill="both", expand=True)

    def draw_chart(self, rows, title="Daily Revenue"):
        self._chart_rows = list(rows or [])
        self._chart_title = title
        c = self.chart_canvas
        c.delete("all")
        w = max(c.winfo_width(), 800)
        h = max(c.winfo_height(), 220)
        c.create_text(
            18,
            17,
            anchor="w",
            text=title,
            font=(
                "Segoe UI",
                12,
                "bold"),
            fill=UI.TEXT)
        vals = [n(r.get("total")) for r in rows]
        if not vals:
            c.create_text(
                w / 2,
                h / 2,
                text="No chart data yet",
                fill=UI.MUTED)
            return
        left, top, right, bottom = 62, 42, w - 22, h - 34
        mx = max(vals) or 1
        for step in range(5):
            y = top + (bottom - top) * step / 4
            value = mx * (4 - step) / 4
            c.create_line(left, y, right, y, fill=UI.MUTED_BG)
            c.create_text(
                left -
                7,
                y,
                anchor="e",
                text=f"{
                    value /
                    1000:.0f}k" if value >= 1000 else f"{
                    value:.0f}",
                font=(
                    "Segoe UI",
                    7),
                fill=UI.MUTED)
        c.create_line(left, top, left, bottom, fill=UI.BORDER)
        c.create_line(left, bottom, right, bottom, fill=UI.BORDER)
        span = max(1, len(vals) - 1)
        points = []
        for idx, value in enumerate(vals):
            x = left + (right - left) * (idx / span if len(vals) > 1 else .5)
            y = bottom - (bottom - top) * (value / mx)
            points.extend([x, y])
        if len(points) >= 4:
            c.create_line(
                *points,
                fill=UI.BLUE,
                width=3,
                smooth=True,
                splinesteps=16)
        label_every = max(1, len(rows) // 8)
        for idx, (row, value) in enumerate(zip(rows, vals)):
            x, y = points[idx * 2], points[idx * 2 + 1]
            c.create_oval(
                x - 4,
                y - 4,
                x + 4,
                y + 4,
                fill="white",
                outline=UI.BLUE,
                width=2)
            if idx % label_every == 0 or idx == len(rows) - 1:
                c.create_text(x, bottom + 13, text=str(row.get("label"))
                              [-5:], font=("Segoe UI", 7), fill=UI.MUTED)
            c.create_text(
                x,
                y - 11,
                text=f"{
                    value:,.0f}",
                font=(
                    "Segoe UI",
                    7,
                    "bold"),
                fill=UI.TEXT)

    def refresh_finance(self):
        self.finance_tree.delete(*self.finance_tree.get_children())
        self.finance_items_tree.delete(*self.finance_items_tree.get_children())
        if hasattr(self, "finance_income_tree"):
            self.finance_income_tree.delete(
                *self.finance_income_tree.get_children())
        if hasattr(self, "finance_assets_tree"):
            self.finance_assets_tree.delete(
                *self.finance_assets_tree.get_children())
        if hasattr(self, "finance_supplier_tree"):
            self.finance_supplier_tree.delete(
                *self.finance_supplier_tree.get_children())
        if hasattr(self, "finance_due_tree"):
            self.finance_due_tree.delete(*self.finance_due_tree.get_children())
        if self.user["role"] != "admin":
            rows = staff_sold_items_month()
            self.finance_summary.set(
                "Staff monthly sold items report (no prices shown)")
            for r in rows:
                self.finance_tree.insert(
                    "", "end", values=(
                        f"{
                            r['product_name']} ({
                            r['sku']})", f"Sold Qty: {
                            r['qty']} | Invoices: {
                            r['invoices']}"))
            self.draw_chart([], "Admin finance hidden for staff")
            return
        d = financial_dashboard(
            self.finance_period.get(),
            admin=True,
            selected_month=self.finance_month.get(),
            date_from=self.finance_date_from.get(),
            date_to=self.finance_date_to.get())
        self.finance_summary.set(
            f"{
                d['period_label']} | Revenue {
                money(
                    d['gross_revenue'])} | Profit {
                    money(
                        d['gross_profit'])} | Collected {
                            money(
                                d['paid_cashflow'])} | Receivable {
                                    money(
                                        d['total_receivable'])}")
        metrics = [
            ("Retail Revenue",
             d['retail_revenue']),
            ("Retail Paid",
             d['retail_paid']),
            ("Wholesale Revenue",
             d['wholesale_revenue']),
            ("Wholesale Paid",
             d['wholesale_paid']),
            ("Gross Revenue",
             d['gross_revenue']),
            ("COGS",
             d['cogs']),
            ("Gross Profit",
             d['gross_profit']),
            ("Stock Assets",
             d['stock_assets']),
            ("Stock Qty",
             d['stock_qty']),
            ("Retail Receivable",
             d['retail_receivable']),
            ("Wholesale Receivable",
             d['wholesale_receivable']),
            ("Total Receivable",
             d['total_receivable'])]
        for k, v in metrics:
            self.finance_tree.insert(
                "", "end", values=(
                    k, money(v) if "Qty" not in k else f"{
                        v:,.0f}"))
        for m, val in d["payment_methods"].items():
            self.finance_tree.insert(
                "", "end", values=(
                    f"Payment - {m}", money(val)))
        for r in d["top_items"]:
            self.finance_items_tree.insert("",
                                           "end",
                                           values=(r["product_name"],
                                                   r["qty"],
                                                   f"{n(r['total']):,.0f}",
                                                   f"{n(r['cost']):,.0f}",
                                                   f"{(n(r['total']) - n(r['cost'])):,.0f}"))
        if hasattr(self, "finance_income_tree"):
            for r in d["income_details"]:
                self.finance_income_tree.insert("",
                                                "end",
                                                values=(r.get("source"),
                                                        r.get("reference"),
                                                        r.get("party"),
                                                        r.get("created_at"),
                                                        f"{n(r.get('total')):,.0f}",
                                                        f"{n(r.get('paid')):,.0f}",
                                                        f"{n(r.get('due')):,.0f}",
                                                        r.get("payment_status")))

        # Detailed real-world finance views: inventory assets and outstanding
        # receivables.
        if hasattr(self, "finance_assets_tree"):
            asset_rows = query("""
                SELECT p.sku,p.brand,p.model,p.color,p.ram,p.rom,p.quantity,p.cost,p.status,
                       COALESCE(SUM(r.qty_added),0) total_units,
                       COALESCE(SUM(r.qty_added*r.unit_cost),0) total_bought_value,
                       COALESCE(SUM(r.qty_added*r.unit_cost)/NULLIF(SUM(r.qty_added),0),p.cost,0) all_batch_avg
                  FROM products p
                  LEFT JOIN restock_batches r ON r.product_id=p.id
                 GROUP BY p.id
                 ORDER BY (p.quantity*p.cost) DESC, p.updated_at DESC
                 LIMIT 300
            """)
            for a in asset_rows:
                item_name = product_display_name(a)
                qty = n(a.get("quantity"))
                live_avg = n(
                    a.get("cost")) if qty > 0 else n(
                    a.get("all_batch_avg"))
                live_value = qty * live_avg if qty > 0 else 0
                status = a.get("status")
                if qty <= 0 and n(a.get("total_units")) > 0:
                    status = f"{status} | sold-out avg from {n(a.get('total_units')):,.0f} units"
                self.finance_assets_tree.insert("",
                                                "end",
                                                values=(a.get("sku"),
                                                        item_name,
                                                        f"{qty:,.0f}",
                                                        f"{live_avg:,.0f}",
                                                        f"{live_value:,.0f}",
                                                        f"{n(a.get('all_batch_avg')):,.0f}",
                                                        f"{n(a.get('total_bought_value')):,.0f}",
                                                        status))
        if hasattr(self, "finance_supplier_tree"):
            supplier_rows = query("""
                SELECT p.sku, p.brand, p.model, p.color, p.ram, p.rom,
                       COALESCE(NULLIF(r.supplier,''),'Unknown') supplier,
                       SUM(r.qty_added) qty,
                       SUM(r.qty_added*r.unit_cost)/NULLIF(SUM(r.qty_added),0) buying_price,
                       SUM(r.qty_added*r.unit_cost) total_value,
                       p.cost current_avg
                FROM restock_batches r JOIN products p ON p.id=r.product_id
                GROUP BY p.id, COALESCE(NULLIF(r.supplier,''),'Unknown')
                ORDER BY p.sku, qty DESC
            """)
            for r in supplier_rows:
                self.finance_supplier_tree.insert("",
                                                  "end",
                                                  values=(r.get("sku"),
                                                          product_display_name(r),
                                                          r.get("supplier"),
                                                          f"{n(r.get('qty')):,.0f}",
                                                          f"{n(r.get('buying_price')):,.2f}",
                                                          f"{n(r.get('total_value')):,.0f}",
                                                          f"{n(r.get('current_avg')):,.2f}"))
        if hasattr(self, "finance_due_tree"):
            retail_due = query("SELECT invoice_no ref, customer_name name, created_at, grand_total,total_due FROM (SELECT invoice_no, customer_name, created_at, grand_total, balance total_due, paid_total FROM invoices WHERE status='Active' AND balance>0) ORDER BY created_at DESC LIMIT 150")
            for r in retail_due:
                self.finance_due_tree.insert("",
                                             "end",
                                             values=("Retail",
                                                     r.get("ref"),
                                                     r.get("name"),
                                                     r.get("created_at"),
                                                     f"{n(r.get('grand_total')):,.0f}",
                                                     "-",
                                                     f"{n(r.get('total_due')):,.0f}"))
            wh_due = query("SELECT invoice_no ref, shop_name name, created_at, grand_total, paid_total, balance FROM wholesale_invoices WHERE status<>'Deleted' AND balance>0 ORDER BY created_at DESC LIMIT 150")
            for r in wh_due:
                self.finance_due_tree.insert("",
                                             "end",
                                             values=("Wholesale",
                                                     r.get("ref"),
                                                     r.get("name"),
                                                     r.get("created_at"),
                                                     f"{n(r.get('grand_total')):,.0f}",
                                                     f"{n(r.get('paid_total')):,.0f}",
                                                     f"{n(r.get('balance')):,.0f}"))
        self.draw_chart(d["daily"], f"Daily Income Line - {d['period_label']}")

    # ---------------- Sync & backup ----------------
    def build_sync_tab(self):
        sf = ScrollFrame(self.tab_sync)
        sf.pack(fill="both", expand=True)
        box = ttk.LabelFrame(
            sf.content,
            text="In-App Same-WiFi Sync Center",
            padding=12)
        box.pack(fill="x", padx=8, pady=8)
        self.sync_host = tk.StringVar(value="http://127.0.0.1:8787")
        self.sync_pass = tk.StringVar(value=SYNC_PASSWORD)
        self.auto_sync = tk.IntVar(value=0)
        ttk.Label(
            box,
            text="Connection password: 11111",
            font=(
                "Segoe UI",
                11,
                "bold")).pack(
            anchor="w")
        ttk.Button(
            box,
            text="Start Host Sync Server on This PC",
            command=self.start_sync_host).pack(
            fill="x",
            pady=4)
        self.labelled_entry(box, "Host URL", self.sync_host)
        self.labelled_entry(box, "Password", self.sync_pass)
        bf = ttk.Frame(box)
        bf.pack(fill="x", pady=6)
        ttk.Button(
            bf,
            text="Pull Database From Host",
            command=self.pull_sync).pack(
            side="left",
            padx=3)
        ttk.Button(
            bf,
            text="Push This Database To Host",
            command=self.push_sync).pack(
            side="left",
            padx=3)
        ttk.Checkbutton(
            bf,
            text="Auto pull every 15 seconds",
            variable=self.auto_sync,
            command=self.toggle_auto_sync).pack(
            side="left",
            padx=10)
        bbox = ttk.LabelFrame(sf.content, text="Weekly Backup", padding=12)
        bbox.pack(fill="x", padx=8, pady=8)
        ttk.Button(
            bbox,
            text="Create Backup ZIP Now",
            command=self.create_backup).pack(
            fill="x",
            pady=4)
        ttk.Button(
            bbox,
            text="Restore Backup ZIP (Admin)",
            command=self.restore_backup_dialog).pack(
            fill="x",
            pady=4)
        ttk.Label(
            bbox,
            text="Reminder: system reminds weekly. Backup includes database and saved PDFs.").pack(
            anchor="w")

    def start_sync_host(self):
        url = lan_sync.start_server(8787)
        self.sync_host.set(url)
        messagebox.showinfo(
            "Sync Host Started",
            f"Use this URL on other devices:\n{url}\nPassword: 11111")

    @safe_run
    def pull_sync(self):
        lan_sync.pull_database(self.sync_host.get(), self.sync_pass.get())
        self.refresh_all()
        messagebox.showinfo(
            "Synced",
            "Database pulled into this app and views refreshed.")

    @safe_run
    def push_sync(self):
        lan_sync.push_database(self.sync_host.get(), self.sync_pass.get())
        messagebox.showinfo("Synced", "This database pushed to host.")

    def toggle_auto_sync(self):
        if self.auto_sync.get():
            self.schedule_auto_sync()
        elif self.sync_after_id:
            self.after_cancel(self.sync_after_id)
            self.sync_after_id = None

    def schedule_auto_sync(self):
        if not self.auto_sync.get():
            return
        try:
            lan_sync.pull_database(self.sync_host.get(), self.sync_pass.get())
            self.refresh_all()
        except Exception:
            pass
        self.sync_after_id = self.after(15000, self.schedule_auto_sync)

    @safe_run
    def create_backup(self):
        path = export_backup(self.user)
        messagebox.showinfo("Backup Saved", path)
        open_parent_select(path)

    @safe_run
    def restore_backup_dialog(self):
        fn = filedialog.askopenfilename(filetypes=[("ZIP backups", "*.zip")])
        if fn and messagebox.askyesno(
            "Restore",
                "Restore backup? Current database will be backed up first."):
            restore_backup(fn, self.user)
            self.refresh_all()
            messagebox.showinfo("Restored",
                                "Backup restored. Restart app if needed.")

    # ---------------- Settings ----------------
    def build_settings_tab(self):
        sf = ScrollFrame(self.tab_settings)
        sf.pack(fill="both", expand=True)
        box = ttk.LabelFrame(
            sf.content,
            text="Company Settings / Passwords",
            padding=12)
        box.pack(fill="x", padx=8, pady=8)
        self.set_vars = {
            k: tk.StringVar(
                value=get_setting(
                    k,
                    "")) for k in [
                "company_name",
                "company_phone",
                "company_address",
                "company_email",
                "invoice_footer",
                "whatsapp_country_code",
                "sync_password"]}
        for label, key in [("Company Name", "company_name"), ("Phone", "company_phone"), ("Address", "company_address"), ("Email", "company_email"),
                           ("Invoice Footer", "invoice_footer"), ("WhatsApp Country Code", "whatsapp_country_code"), ("Sync Password", "sync_password")]:
            self.labelled_entry(box, label, self.set_vars[key], width=60)
        ttk.Button(
            box,
            text="Save Settings",
            command=self.save_settings).pack(
            fill="x",
            pady=6)
        pbox = ttk.LabelFrame(
            sf.content,
            text="Change User Passwords (Admin)",
            padding=12)
        pbox.pack(fill="x", padx=8, pady=8)
        self.p_user = tk.StringVar(value="admin")
        self.p_new = tk.StringVar()
        ttk.Combobox(
            pbox,
            textvariable=self.p_user,
            values=[
                "admin",
                "staff"],
            state="readonly").pack(
            fill="x",
            pady=3)
        ttk.Entry(pbox, textvariable=self.p_new,
                  show="*").pack(fill="x", pady=3)
        ttk.Button(
            pbox,
            text="Change Password",
            command=self.change_user_password).pack(
            fill="x",
            pady=4)

    @safe_run
    def save_settings(self):
        for k, v in self.set_vars.items():
            set_setting(k, v.get())
        messagebox.showinfo("Saved", "Settings saved")

    @safe_run
    def change_user_password(self):
        change_password(self.p_user.get(), self.p_new.get(), self.user)
        messagebox.showinfo("Saved", "Password changed")

    # ---------------- General refresh ----------------
    def refresh_all(self):
        self.refresh_pos_products()
        self.refresh_inventory()
        self.refresh_clients()
        self.refresh_shops()
        self.refresh_wh_products()
        self.refresh_finance()
        if self.selected_shop_id:
            self.refresh_shop_profile()


# ---------------- IM ERP PY SYS PRO workflow upgrades ----------------
def _erp_v2_find_product_by_search(text):
    """Find a product/unit by SKU, name or last 5 digits of IMEI/serial."""
    q = (text or "").strip()
    if not q:
        return None, None
    # First unit exact/last digits so IMEI last-5 instantly selects exact
    # phone/watch.
    unit = query_one("""
        SELECT u.*, p.* FROM product_units u JOIN products p ON p.id=u.product_id
        WHERE u.status='Available' AND (u.unit_code=? OR substr(u.unit_code, -?)=?)
        ORDER BY u.id ASC LIMIT 1
    """, (q, len(q), q))
    if unit:
        return query_one("SELECT * FROM products WHERE id=?",
                         (unit["product_id"],)), unit
    rows = search_products(q, "All", False)
    return (rows[0], None) if rows else (None, None)


def _quick_add_by_search(self):
    text = self.pos_search.get().strip()
    p, unit = _erp_v2_find_product_by_search(text)
    if not p:
        messagebox.showwarning(
            "Not Found",
            "No available item found for that SKU, name, or last 5 digits.")
        return
    # Select product in POS table when visible.
    self.refresh_pos_products()
    for iid in self.pos_tree.get_children():
        vals = self.pos_tree.item(iid, "values")
        if vals and int(vals[0]) == int(p["id"]):
            self.pos_tree.selection_set(iid)
            self.pos_tree.see(iid)
            break
    if unit:
        self.cart_unit.set(unit["unit_code"])
        self.cart_qty.set("1")
    self.add_selected_to_cart()


def _pick_unit_for_pos_v2(self):
    sel = self.pos_tree.selection()
    if not sel:
        messagebox.showwarning("Select product", "Select a product first.")
        return
    pid = int(self.pos_tree.item(sel[0], "values")[0])
    p = query_one("SELECT * FROM products WHERE id=?", (pid,))
    units = available_units(pid)
    if not units:
        messagebox.showinfo(
            "Units",
            "This is bulk stock or no serialized units are available.")
        return
    win = tk.Toplevel(self)
    win.title("Select Specific Unit / IMEI")
    win.geometry("860x560")
    win.configure(bg=UI.BG)
    sf = ScrollFrame(win, bg=UI.BG)
    sf.pack(fill="both", expand=True)
    card, inner = mac_card(
        sf.content, f"Select Unit - {product_display_name(p)}", padding=14)
    card.pack(fill="both", expand=True, padx=10, pady=10)
    search_var = tk.StringVar()
    ttk.Label(
        inner,
        text="Search by full IMEI or last 5 digits").pack(
        anchor="w")
    ent = ttk.Entry(inner, textvariable=search_var)
    ent.pack(fill="x", pady=5)
    wrap, tree = self.table(
        inner, [
            "id", "imei", "supplier", "cost", "status", "date"], headings={
            "imei": "IMEI / Serial", "date": "Added"}, height=16)
    tree.column("imei", width=240)
    tree.column("supplier", width=150)
    wrap.pack(fill="both", expand=True, pady=6)

    def fill():
        tree.delete(*tree.get_children())
        q = search_var.get().strip().lower()
        for u in units:
            code = str(u.get("unit_code") or "")
            if q and q not in code.lower() and not code.lower().endswith(q):
                continue
            tree.insert("",
                        "end",
                        values=(u.get("id"),
                                code,
                                u.get("supplier") or "-",
                                f"{n(u.get('cost')):,.0f}",
                                "Available",
                                u.get("created_at")))

    def use_selected():
        ss = tree.selection()
        if not ss:
            return
        vals = tree.item(ss[0], "values")
        self.cart_unit.set(vals[1])
        win.destroy()
    ent.bind("<KeyRelease>", lambda e: fill())
    tree.bind("<Double-1>", lambda e: use_selected())
    btns = ttk.Frame(inner)
    btns.pack(fill="x", pady=8)
    ttk.Button(
        btns,
        text="Use Selected Unit",
        style="Accent.TButton",
        command=use_selected).pack(
        side="right",
        padx=3)
    ttk.Button(
        btns,
        text="Close",
        command=win.destroy).pack(
        side="right",
        padx=3)
    fill()


def _open_wholesale_item_picker(self):
    if not self.selected_shop_id:
        messagebox.showwarning(
            "Select shop",
            "Select a partner shop before choosing issue items.")
        return
    shop = query_one("SELECT * FROM shops WHERE id=?",
                     (self.selected_shop_id,))
    win = tk.Toplevel(self)
    win.title(f"Exact Item Picker - {shop.get('name') if shop else 'Partner'}")
    win.geometry("1280x820")
    win.minsize(980, 650)
    win.configure(bg=UI.BG)
    win.transient(self)
    sf = ScrollFrame(win, bg=UI.BG)
    sf.pack(fill="both", expand=True)
    card, inner = mac_card(
        sf.content, "All Items / Exact Partner Issue Picker", padding=14)
    card.pack(fill="both", expand=True, padx=10, pady=10)
    tk.Label(
        inner,
        text="Search item, SKU, full IMEI or last digits. Select the product and its exact available unit, then add it to the partner issue cart.",
        bg=UI.SURFACE,
        fg=UI.MUTED,
        font=(
            "Segoe UI",
            9)).pack(
        anchor="w",
        pady=(
            0,
            8))
    top = ttk.Frame(inner)
    top.pack(fill="x", pady=(0, 8))
    q = tk.StringVar()
    ptype = tk.StringVar(value="All")
    ttk.Entry(
        top,
        textvariable=q,
        width=48).pack(
        side="left",
        fill="x",
        expand=True,
        padx=(
            0,
             6))
    ttk.Combobox(
        top,
        textvariable=ptype,
        values=["All"] +
        PRODUCT_TYPES,
        state="readonly",
        width=16).pack(
        side="left",
        padx=3)
    body = ttk.PanedWindow(inner, orient="horizontal")
    body.pack(fill="both", expand=True)
    left = ttk.Frame(body)
    right = ttk.Frame(body)
    body.add(left, weight=3)
    body.add(right, weight=2)
    wrap, p_tree = self.table(
        left, ["id", "sku", "type", "item", "available", "status", "price"], height=20)
    p_tree.column("item", width=360)
    wrap.pack(fill="both", expand=True, padx=(0, 6))
    unit_title = tk.StringVar(
        value="Select a product to see exact available units")
    ttk.Label(
        right,
        textvariable=unit_title,
        font=(
            "Segoe UI",
            10,
            "bold")).pack(
        anchor="w",
        pady=(
            0,
            5))
    unit_q = tk.StringVar()
    ttk.Entry(right, textvariable=unit_q).pack(fill="x", pady=(0, 5))
    wrap, u_tree = self.table(
        right, [
            "id", "status", "imei", "supplier", "reference"], headings={
            "imei": "IMEI / Serial / ID", "reference": "Invoice / Issue Ref"}, height=18)
    u_tree.column("imei", width=250)
    wrap.pack(fill="both", expand=True)
    form = ttk.Frame(inner)
    form.pack(fill="x", pady=10)
    qty = tk.StringVar(value="1")
    price = tk.StringVar()
    unit = tk.StringVar()
    selected = {"product": None}
    ttk.Label(form, text="Qty").pack(side="left")
    ttk.Entry(form, textvariable=qty, width=7).pack(side="left", padx=4)
    ttk.Label(form, text="Partner Price").pack(side="left")
    ttk.Entry(form, textvariable=price, width=13).pack(side="left", padx=4)
    ttk.Label(form, text="Exact Unit").pack(side="left")
    ttk.Entry(
        form,
        textvariable=unit,
        width=36,
        state="readonly").pack(
        side="left",
        padx=4)

    def fill_products(*_):
        p_tree.delete(*p_tree.get_children())
        u_tree.delete(*u_tree.get_children())
        unit.set("")
        selected["product"] = None
        rows = search_products(q.get(), ptype.get(), True)
        rows.sort(
            key=lambda row: (
                0 if i(
                    row.get(
                        "available_qty",
                        row.get("quantity"))) > 0 else 1,
                product_display_name(row).casefold()))
        for p in rows:
            default_price = n(p.get("offer_price")) or n(p.get("price"))
            available = i(p.get("available_qty", p.get("quantity")))
            p_tree.insert("",
                          "end",
                          values=(p["id"],
                                  p["sku"],
                                  p["type"],
                                  product_display_name(p),
                                  available,
                                  "Available" if available > 0 else "Sold / Out",
                                  f"{default_price:,.0f}"))

    def load_units(*_):
        u_tree.delete(*u_tree.get_children())
        unit.set("")
        sel = p_tree.selection()
        if not sel:
            return
        pid = int(p_tree.item(sel[0], "values")[0])
        p = query_one("SELECT * FROM products WHERE id=?", (pid,))
        selected["product"] = p
        if not p:
            return
        price.set(str(int(n(p.get("offer_price")) or n(p.get("price")))))
        unit_title.set(f"Available units - {product_display_name(p)}")
        term = unit_q.get().strip().casefold()
        in_cart = {str(c.get("unit_code") or "").casefold()
                   for c in self.wh_cart if c.get("unit_code")}
        units = stock_detail_rows(pid) if p.get("is_serialized") else []
        if units:
            units.sort(
                key=lambda row: (
                    0 if str(
                        row.get("status") or "").casefold() == "available" else 1, str(
                        row.get("imei") or "").casefold()))
            for row in units:
                code = str(row.get("imei") or "")
                status = str(row.get("status") or "")
                if status.casefold() == "available" and code.casefold() in in_cart:
                    continue
                if term and term not in code.casefold() and not code.casefold().endswith(term):
                    continue
                u_tree.insert(
                    "",
                    "end",
                    values=(
                        row.get("id"),
                        status,
                        code,
                        row.get("supplier") or "-",
                        row.get("sold_ref") or "-"))
        else:
            cart_qty = sum(i(c.get("qty")) for c in self.wh_cart if int(
                c.get("product_id") or 0) == pid)
            remaining = max(0, i(p.get("quantity")) - cart_qty)
            u_tree.insert(
                "",
                "end",
                values=(
                    "-",
                    f"Bulk Qty {remaining}",
                    "Bulk stock",
                    p.get("supplier") or "-",
                    "-"))

    def choose_unit(*_):
        sel = u_tree.selection()
        if not sel:
            return
        values = u_tree.item(sel[0], "values")
        if values and values[0] != "-" and str(
                values[1]).casefold() == "available":
            unit.set(values[2])
            qty.set("1")
        else:
            unit.set("")

    def add_selected(close=False):
        p = selected.get("product")
        if not p:
            messagebox.showwarning(
                "Select item",
                "Select an item first.",
                parent=win)
            return
        selling = n(price.get())
        if selling <= 0:
            messagebox.showwarning(
                "Partner price",
                "Enter a partner selling price greater than zero.",
                parent=win)
            return
        if p.get("is_serialized"):
            code = unit.get().strip()
            if not code:
                messagebox.showwarning(
                    "Select exact unit",
                    "Select an available IMEI / serial / ID.",
                    parent=win)
                return
            if any(str(c.get("unit_code") or "").casefold()
                   == code.casefold() for c in self.wh_cart):
                messagebox.showwarning(
                    "Already selected",
                    f"{code} is already in the issue cart.",
                    parent=win)
                return
            item_qty = 1
        else:
            code = ""
            item_qty = max(1, i(qty.get()))
            already = sum(i(c.get("qty")) for c in self.wh_cart if int(
                c.get("product_id") or 0) == int(p["id"]))
            if already + item_qty > i(p.get("quantity")):
                messagebox.showwarning(
                    "Not enough stock", f"Available bulk quantity: {
                        p.get('quantity')}. Already in cart: {already}.", parent=win)
                return
        self.wh_cart.append({"product_id": p["id"], "product_name": product_display_name(
            p), "unit_code": code, "qty": item_qty, "price": selling, "discount": 0})
        self.refresh_wh_cart()
        win.destroy()

    q.trace_add("write", fill_products)
    ptype.trace_add("write", fill_products)
    unit_q.trace_add("write", load_units)
    p_tree.bind("<<TreeviewSelect>>", load_units)
    p_tree.bind("<Double-1>", load_units)
    u_tree.bind("<<TreeviewSelect>>", choose_unit)
    u_tree.bind("<Double-1>", lambda e: add_selected(True))
    ttk.Button(
        form,
        text="Add to Issue Cart & Close",
        style="Accent.TButton",
        command=lambda: add_selected(True)).pack(
        side="right",
        padx=3)
    ttk.Button(
        form,
        text="Close",
        command=win.destroy).pack(
        side="right",
        padx=3)
    fill_products()


def _open_partner_quick_profile(self):
    if not self.selected_shop_id:
        self.load_shop()
    if not self.selected_shop_id:
        messagebox.showwarning("Select shop", "Select a partner shop first.")
        return
    prof = shop_profile(self.selected_shop_id)
    shop = prof["shop"]
    win = tk.Toplevel(self)
    win.title(f"Partner Profile - {shop['name']}")
    win.geometry("1180x780")
    win.configure(bg=UI.BG)
    sf = ScrollFrame(win, bg=UI.BG)
    sf.pack(fill="both", expand=True)
    header, h = mac_card(
        sf.content, "Fast Partner Profile + Payment", padding=14)
    header.pack(fill="x", padx=10, pady=(10, 6))
    title = f"{
        shop['name']}  |  Total Due {
        money(
            prof['balance'])}  |  Issued {
                money(
                    prof['total_issued'])}  |  Paid {
                        money(
                            prof['total_paid'])}"
    contact = shop.get("whatsapp") or shop.get("phone") or "-"
    tk.Label(
        h,
        text=title,
        bg=UI.SURFACE,
        fg=UI.TEXT,
        font=(
            "Segoe UI",
            16,
            "bold")).pack(
        anchor="w")
    tk.Label(
        h,
        text=f"Contact: {
            shop.get('contact_person') or '-'}  |  WhatsApp: {contact}  |  Address: {
            shop.get('address') or '-'}",
        bg=UI.SURFACE,
        fg=UI.MUTED,
        font=(
            "Segoe UI",
                9)).pack(
                    anchor="w",
                    pady=(
                        3,
                        4))
    progress_row = ttk.Frame(h)
    progress_row.pack(fill="x", pady=(2, 0))
    ttk.Label(
        progress_row,
        text=f"Account payment progress: {
            prof.get(
                'paid_percent',
                0):.1f}%",
        font=(
            "Segoe UI",
            9,
            "bold")).pack(
        side="left")
    ttk.Progressbar(
        progress_row,
        maximum=100,
        value=prof.get(
            "paid_percent",
            0)).pack(
        side="left",
        fill="x",
        expand=True,
        padx=(
            10,
            0))
    tk.Label(
        h,
        text=f"WhatsApp: {
            shop.get('whatsapp') or shop.get('phone') or '-'}  •  Past invoices, due items and FIFO payments are saved under this profile.",
        bg=UI.SURFACE,
        fg=UI.MUTED,
        font=(
            "Segoe UI",
            10)).pack(
                anchor="w",
                pady=(
                    3,
                    0))

    pay_card, pay = mac_card(sf.content, "Update Payment Quickly", padding=14)
    pay_card.pack(fill="x", padx=10, pady=6)
    due_var = tk.StringVar(value=f"Current Due: {money(prof['balance'])}")
    tk.Label(
        pay,
        textvariable=due_var,
        bg=UI.SURFACE,
        fg=UI.BLUE,
        font=(
            "Segoe UI",
            13,
            "bold")).pack(
        anchor="w",
        pady=(
            0,
            6))
    editor = PaymentEditor(pay, "Payment Breakdown")
    editor.pack(fill="x", pady=5)
    note = tk.StringVar(value="Partner payment")
    self.labelled_entry(pay, "Payment Note", note)

    def save_payment_from_popup():
        res = add_wholesale_payment(
            self.selected_shop_id,
            editor.get_rows(),
            note.get(),
            self.user)
        new_prof = shop_profile(self.selected_shop_id)
        due_var.set(f"Current Due: {money(new_prof['balance'])}")
        messagebox.showinfo(
            "Payment Saved", f"{
                res['payment_no']} saved. FIFO allocated {
                money(
                    res['amount'])}.")
        pdf = build_shop_statement_pdf(new_prof)
        open_file(pdf)
        if messagebox.askyesno(
            "Send WhatsApp",
                "Statement PDF opened. Send updated due statement to shop WhatsApp now?"):
            whatsapp_send(new_prof["shop"].get("whatsapp") or new_prof["shop"].get(
                "phone"), shop_statement_text(self.selected_shop_id), pdf)
        self.refresh_all()
        self.refresh_shop_profile()
        win.destroy()
    row = ttk.Frame(pay)
    row.pack(fill="x", pady=6)
    ttk.Button(
        row,
        text="Save Payment + Statement PDF",
        style="Accent.TButton",
        command=save_payment_from_popup).pack(
        side="left",
        fill="x",
        expand=True,
        padx=3)
    ttk.Button(
        row,
        text="Send Current Due WhatsApp",
        command=lambda: whatsapp_send(
            shop.get("whatsapp") or shop.get("phone"),
            shop_statement_text(
                self.selected_shop_id),
            "")).pack(
        side="left",
        fill="x",
        expand=True,
        padx=3)
    ttk.Button(
        row,
        text="Open Statement PDF",
        command=lambda: open_file(
            build_shop_statement_pdf(
                shop_profile(
                    self.selected_shop_id)))).pack(
        side="left",
        fill="x",
        expand=True,
        padx=3)
    if n(prof.get("balance")) <= 0:
        pay_card.pack_forget()
        settled_card, settled = mac_card(
            sf.content, "Account Settled", padding=14)
        settled_card.pack(fill="x", padx=10, pady=6)
        tk.Label(
            settled,
            text="This partner has no outstanding bills. Settled bills are removed from the active profile; complete paid history remains at the bottom of the statement PDF.",
            bg=UI.SURFACE,
            fg=UI.GREEN,
            font=(
                "Segoe UI",
                10,
                "bold"),
            wraplength=1050,
            justify="left").pack(
            anchor="w")
        ttk.Button(
            settled,
            text="Open Complete Statement PDF",
            command=lambda: open_file(
                build_shop_statement_pdf(
                    shop_profile(
                        self.selected_shop_id)))).pack(
            anchor="e",
            pady=(
                8,
                0))

    details = ttk.Notebook(sf.content)
    details.pack(fill="both", expand=True, padx=10, pady=(6, 20))
    inv_page = ttk.Frame(details)
    item_page = ttk.Frame(details)
    due_page = ttk.Frame(details)
    pay_page = ttk.Frame(details)
    details.add(inv_page, text="Outstanding Bills")
    details.add(item_page, text="Selected Due Bill")
    details.add(due_page, text="Due Items")
    details.add(pay_page, text="Payment Log")
    bill_cols = [
        "invoice",
        "date",
        "items",
        "qty",
        "total",
        "paid",
        "due",
        "progress",
        "last_paid",
        "status"]
    wrap, inv_tree = self.table(
        inv_page, bill_cols, headings={
            "items": "Item Lines", "qty": "Total Qty", "last_paid": "Last Paid Date"}, height=14)
    wrap.pack(fill="both", expand=True, padx=6, pady=6)
    inv_tree.column("invoice", width=125)
    inv_tree.column("progress", width=95)
    inv_tree.column("last_paid", width=145)
    invoices_by_no = {inv["invoice_no"]
        : inv for inv in prof["outstanding_invoices"]}
    for inv in prof["outstanding_invoices"]:
        inv_tree.insert("",
                        "end",
                        values=(inv["invoice_no"],
                                inv["created_at"],
                                inv.get("item_count",
                                        0),
                                inv.get("total_qty",
                                        0),
                                f"{n(inv['grand_total']):,.0f}",
                                f"{n(inv['paid_total']):,.0f}",
                                f"{n(inv['balance']):,.0f}",
                                f"{n(inv.get('paid_percent')):.1f}%",
                                inv.get("last_payment_date") or "-",
                                inv["payment_status"]))

    bill_summary = tk.StringVar(
        value="Select a bill to see every item and every dated payment applied to it.")
    ttk.Label(
        item_page,
        textvariable=bill_summary,
        font=(
            "Segoe UI",
            11,
            "bold")).pack(
        anchor="w",
        padx=6,
        pady=(
            8,
            2))
    item_box = ttk.LabelFrame(
        item_page,
        text="Items on Selected Bill",
        padding=6)
    item_box.pack(fill="both", expand=True, padx=6, pady=4)
    wrap, bill_item_tree = self.table(
        item_box, [
            "item", "unit", "qty", "price", "line"], headings={
            "unit": "IMEI / Unit", "price": "Each", "line": "Line Total"}, height=7)
    wrap.pack(fill="both", expand=True)
    bill_item_tree.column("item", width=330)
    bill_item_tree.column("unit", width=190)
    allocation_box = ttk.LabelFrame(
        item_page,
        text="Dated Payments Applied to Selected Bill",
        padding=6)
    allocation_box.pack(fill="both", expand=True, padx=6, pady=4)
    wrap, bill_pay_tree = self.table(
        allocation_box, [
            "payment", "date", "method", "applied", "before", "after", "note"], height=6)
    wrap.pack(fill="both", expand=True)
    bill_pay_tree.column("method", width=180)
    bill_pay_tree.column("note", width=220)

    def load_bill_details(_=None, open_tab=False):
        sel = inv_tree.selection()
        if not sel:
            return
        invoice_no = inv_tree.item(sel[0], "values")[0]
        inv = invoices_by_no.get(invoice_no)
        if not inv:
            return
        bill_summary.set(
            f"{invoice_no} | {
                inv.get(
                    'total_qty', 0)} items | Total {
                money(
                    inv.get('grand_total'))} | Paid {
                        money(
                            inv.get('paid_total'))} | Due {
                                money(
                                    inv.get('balance'))} | {
                                        n(
                                            inv.get('paid_percent')):.1f}% paid")
        bill_item_tree.delete(*bill_item_tree.get_children())
        for item in inv.get("items", []):
            bill_item_tree.insert("",
                                  "end",
                                  values=(item.get("product_name"),
                                          item.get("unit_code") or "-",
                                          item.get("qty"),
                                          f"{n(item.get('selling_price')):,.0f}",
                                          f"{n(item.get('line_total')):,.0f}"))
        bill_pay_tree.delete(*bill_pay_tree.get_children())
        for a in inv.get("payment_allocations", []):
            bill_pay_tree.insert("",
                                 "end",
                                 values=(a.get("payment_no"),
                                         a.get("payment_date"),
                                         a.get("payment_methods"),
                                         f"{n(a.get('applied')):,.0f}",
                                         f"{n(a.get('before')):,.0f}",
                                         f"{n(a.get('after')):,.0f}",
                                         a.get("payment_note") or "-"))
        if open_tab:
            details.select(item_page)
    inv_tree.bind("<<TreeviewSelect>>", load_bill_details)
    inv_tree.bind("<Double-1>", lambda e: load_bill_details(e, True))

    wrap, due_tree = self.table(
        due_page, [
            "invoice", "item", "unit", "qty", "line", "invoice_due"], height=14)
    wrap.pack(fill="both", expand=True, padx=6, pady=6)
    due_tree.column("item", width=320)
    due_tree.column("unit", width=170)
    for d in prof["due_items"]:
        due_tree.insert("",
                        "end",
                        values=(d["invoice_no"],
                                d["product_name"],
                                d.get("unit_code") or "-",
                                d["qty"],
                                f"{n(d['line_total']):,.0f}",
                                f"{n(d['balance']):,.0f}"))
    wrap, pay_tree = self.table(
        pay_page, [
            "payment", "date", "method", "amount", "note", "allocations"], headings={
            "method": "Method / Reference", "allocations": "Invoice Allocation Log"}, height=14)
    wrap.pack(fill="both", expand=True, padx=6, pady=6)
    pay_tree.column("method", width=250)
    pay_tree.column("note", width=190)
    pay_tree.column("allocations", width=520)
    for pmt in prof.get("payment_log", []):
        pay_tree.insert("",
                        "end",
                        values=(pmt.get("payment_no"),
                                pmt.get("created_at"),
                                pmt.get("method_detail") or pmt.get("method_summary"),
                                f"{n(pmt.get('amount')):,.0f}",
                                pmt.get("note") or "-",
                                pmt.get("allocations") or "-"))
    first = inv_tree.get_children()
    if first:
        inv_tree.selection_set(first[0])
        load_bill_details()


def _refresh_finance_v2_extra_safe(self):
    # Keep original implementation available through replaced method body in
    # class.
    return None


# Attach V2 methods to the app class.
ERPApp.quick_add_by_search = safe_run(_quick_add_by_search)
ERPApp.pick_unit_for_pos = _pick_unit_for_pos_v2
ERPApp.open_wholesale_item_picker = safe_run(_open_wholesale_item_picker)
ERPApp.open_partner_quick_profile = safe_run(_open_partner_quick_profile)


# ---------------- IM ERP PY SYS PRO final workflow patch ----------------
def _syspro_find_product_by_search(text):
    q = (text or "").strip()
    if not q:
        return None, None
    unit = query_one("""
        SELECT u.id AS unit_row_id, u.unit_code, u.product_id, u.cost AS unit_cost, u.supplier AS unit_supplier,
               p.*
        FROM product_units u JOIN products p ON p.id=u.product_id
        WHERE u.status='Available' AND (u.unit_code=? OR substr(u.unit_code, -?)=?)
        ORDER BY u.id ASC LIMIT 1
    """, (q, len(q), q))
    if unit:
        return query_one("SELECT * FROM products WHERE id=?",
                         (unit["product_id"],)), unit
    rows = search_products(q, "All", False)
    return (rows[0], None) if rows else (None, None)


def _syspro_quick_add_by_search(self):
    text = self.pos_search.get().strip()
    p, unit = _syspro_find_product_by_search(text)
    if not p:
        messagebox.showwarning(
            "Not Found",
            "No available item found for that SKU, item name, or last 5 digits of IMEI/serial.")
        return
    self.refresh_pos_products()
    for iid in self.pos_tree.get_children():
        vals = self.pos_tree.item(iid, "values")
        if vals and int(vals[0]) == int(p["id"]):
            self.pos_tree.selection_set(iid)
            self.pos_tree.see(iid)
            break
    if unit:
        self.cart_unit.set(unit["unit_code"])
        self.cart_qty.set("1")
    self.add_selected_to_cart()


def _syspro_open_item_picker(self):
    win = tk.Toplevel(self)
    win.title("Open All Items / Specific Unit Picker")
    win.geometry("1180x760")
    win.configure(bg=UI.BG)
    sf = ScrollFrame(win, bg=UI.BG)
    sf.pack(fill="both", expand=True)
    card, inner = mac_card(sf.content, "Fast Item Picker", padding=14)
    card.pack(fill="both", expand=True, padx=10, pady=10)
    tk.Label(
        inner,
        text="Search by item name, SKU, full IMEI or last 5 digits. Pick the exact unit and add to cart.",
        bg=UI.SURFACE,
        fg=UI.MUTED,
        font=(
            "Segoe UI",
            9)).pack(
        anchor="w",
        pady=(
            0,
            8))
    top = ttk.Frame(inner)
    top.pack(fill="x", pady=(0, 8))
    q = tk.StringVar(value=self.pos_search.get())
    ptype = tk.StringVar(value=self.pos_type.get())
    ttk.Entry(
        top,
        textvariable=q,
        width=46).pack(
        side="left",
        fill="x",
        expand=True,
        padx=(
            0,
             6))
    ttk.Combobox(
        top,
        textvariable=ptype,
        values=["All"] +
        PRODUCT_TYPES,
        state="readonly",
        width=16).pack(
        side="left",
        padx=3)
    ttk.Button(
        top,
        text="Search",
        command=lambda: fill_products()).pack(
        side="left",
        padx=3)
    body = ttk.PanedWindow(inner, orient="horizontal")
    body.pack(fill="both", expand=True)
    left = ttk.Frame(body)
    right = ttk.Frame(body)
    body.add(left, weight=3)
    body.add(right, weight=2)
    wrap, p_tree = self.table(
        left, ["id", "sku", "type", "item", "qty", "price"], height=18)
    p_tree.column("item", width=330)
    p_tree.column("id", width=50)
    wrap.pack(fill="both", expand=True, padx=(0, 6))
    wrap, u_tree = self.table(
        right, [
            "id", "imei", "supplier", "cost", "status"], headings={
            "imei": "IMEI / Serial"}, height=18)
    u_tree.column("imei", width=220)
    wrap.pack(fill="both", expand=True, padx=(6, 0))
    qty_var = tk.StringVar(value="1")
    price_var = tk.StringVar(value="")
    unit_var = tk.StringVar(value="")
    bottom = ttk.Frame(inner)
    bottom.pack(fill="x", pady=10)
    ttk.Label(bottom, text="Qty").pack(side="left")
    ttk.Entry(bottom, textvariable=qty_var, width=7).pack(side="left", padx=4)
    ttk.Label(bottom, text="Price").pack(side="left")
    ttk.Entry(
        bottom,
        textvariable=price_var,
        width=12).pack(
        side="left",
        padx=4)
    ttk.Label(bottom, text="Selected Unit").pack(side="left")
    ttk.Entry(
        bottom,
        textvariable=unit_var,
        width=28).pack(
        side="left",
        padx=4)

    state = {"product": None}

    def fill_products():
        p_tree.delete(*p_tree.get_children())
        u_tree.delete(*u_tree.get_children())
        state["product"] = None
        rows = search_products(q.get(), ptype.get(), include_empty=False)
        for p in rows:
            price = n(p.get("offer_price")) or n(p.get("price"))
            p_tree.insert(
                "", "end", values=(
                    p["id"], p["sku"], p["type"], product_display_name(p), p.get(
                        "available_qty", p.get("quantity")), f"{
                        price:,.0f}"))

    def load_units(_=None):
        u_tree.delete(*u_tree.get_children())
        unit_var.set("")
        sel = p_tree.selection()
        if not sel:
            return
        pid = int(p_tree.item(sel[0], "values")[0])
        p = query_one("SELECT * FROM products WHERE id=?", (pid,))
        state["product"] = p
        price_var.set(str(int(n(p.get("offer_price")) or n(p.get("price")))))
        units = available_units(pid)
        if units:
            for u in units:
                u_tree.insert("", "end", values=(u.get("id"), u.get("unit_code"), u.get(
                    "supplier") or "-", f"{n(u.get('cost')):,.0f}", "Available"))
        else:
            u_tree.insert("",
                          "end",
                          values=("-",
                                  "Bulk stock - no IMEI required",
                                  p.get("supplier") or "-",
                                  f"{n(p.get('cost')):,.0f}",
                                  f"Available Qty {p.get('quantity')}"))

    def select_unit(_=None):
        ss = u_tree.selection()
        if not ss:
            return
        vals = u_tree.item(ss[0], "values")
        if vals and vals[0] != "-":
            unit_var.set(vals[1])
            qty_var.set("1")

    def add_from_picker(close=False):
        p = state.get("product")
        if not p:
            load_units()
            p = state.get("product")
        if not p:
            messagebox.showwarning("Select item", "Select an item first.")
            return
        self.refresh_pos_products()
        for iid in self.pos_tree.get_children():
            vals = self.pos_tree.item(iid, "values")
            if vals and int(vals[0]) == int(p["id"]):
                self.pos_tree.selection_set(iid)
                self.pos_tree.see(iid)
                break
        self.cart_qty.set(qty_var.get() or "1")
        self.cart_price.set(price_var.get() or "")
        self.cart_unit.set(unit_var.get() or "")
        self.add_selected_to_cart()
        if close:
            win.destroy()
    p_tree.bind("<<TreeviewSelect>>", load_units)
    p_tree.bind("<Double-1>", lambda e: load_units())
    u_tree.bind("<<TreeviewSelect>>", select_unit)
    u_tree.bind("<Double-1>", lambda e: add_from_picker(False))
    q.trace_add("write", lambda *_: fill_products())
    ttk.Button(
        bottom,
        text="Add Selected to Cart",
        style="Accent.TButton",
        command=lambda: add_from_picker(False)).pack(
        side="right",
        padx=3)
    ttk.Button(
        bottom,
        text="Add & Close",
        command=lambda: add_from_picker(True)).pack(
        side="right",
        padx=3)
    ttk.Button(
        bottom,
        text="Close",
        command=win.destroy).pack(
        side="right",
        padx=3)
    fill_products()


# Override final methods after class definition.
ERPApp.quick_add_by_search = safe_run(_syspro_quick_add_by_search)
ERPApp.open_item_picker = safe_run(_syspro_open_item_picker)


# ---------------- IMERP V GM intelligent workflow + inventory logic patch
def _v6_resolve_available_unit_ui(product_id, typed=""):
    typed = (typed or "").strip()
    units = available_units(product_id)
    if typed:
        exact = [u for u in units if str(u.get("unit_code")) == typed]
        if exact:
            return exact[0]
        ending = [u for u in units if str(u.get("unit_code")).endswith(typed)]
        if ending:
            return ending[0]
        return None
    return units[0] if units else None


def _v6_product_needs_tracking(product):
    t = str(product.get("type") or "").lower()
    c = str(product.get("category") or "").lower()
    return t in {
        "phone",
        "laptop",
        "tablet",
        "smartwatch",
        "watch",
        "wearable",
        "gaming"} or any(
        x in c for x in [
            "phone",
            "mobile",
            "iphone",
            "laptop",
            "watch",
            "tablet",
            "console"])


def _v6_auto_serials(sku, qty):
    return generate_internal_ids(qty)


def _v6_refresh_pos_products(self):
    # Original refresh plus a double-click binding so the cashier can open
    # units instantly.
    self.pos_tree.delete(*self.pos_tree.get_children())
    for p in search_products(
            self.pos_search.get(),
            self.pos_type.get(),
            include_empty=False):
        price = n(p.get("offer_price")) or n(p.get("price"))
        qty = p.get("available_qty", p.get("quantity"))
        label = product_display_name(p)
        self.pos_tree.insert(
            "", "end", values=(
                p["id"], p["sku"], p["type"], label, qty, f"{
                    price:,.0f}"))
    if not getattr(self, "_v6_pos_double_bound", False):
        self.pos_tree.bind(
            "<Double-1>",
            lambda e: self.open_units_for_selected_product())
        self._v6_pos_double_bound = True


def _v6_open_units_for_product(self, product_id=None, close_after_add=False):
    if product_id is None:
        sel = self.pos_tree.selection()
        if not sel:
            messagebox.showwarning("Select product", "Select an item first.")
            return
        product_id = int(self.pos_tree.item(sel[0], "values")[0])
    p = query_one("SELECT * FROM products WHERE id=?", (product_id,))
    if not p:
        messagebox.showwarning("Missing item", "Product was not found.")
        return
    # Select product in main table before adding.
    self.refresh_pos_products()
    for iid in self.pos_tree.get_children():
        vals = self.pos_tree.item(iid, "values")
        if vals and int(vals[0]) == int(product_id):
            self.pos_tree.selection_set(iid)
            self.pos_tree.see(iid)
            break

    if not p.get("is_serialized"):
        # Bulk stock: no unit picker needed, but show a simple fast qty box.
        win = tk.Toplevel(self)
        win.title(f"Add Bulk Stock - {product_display_name(p)}")
        win.geometry("560x300")
        win.configure(bg=UI.BG)
        card, inner = mac_card(win, "Add Bulk / Accessories Item", padding=16)
        card.pack(fill="both", expand=True, padx=12, pady=12)
        tk.Label(
            inner,
            text=f"{
                product_display_name(p)} | Available Qty: {
                p.get('quantity')}",
            bg=UI.SURFACE,
            fg=UI.TEXT,
            font=(
                "Segoe UI",
                13,
                "bold")).pack(
                    anchor="w",
                    pady=(
                        0,
                        8))
        qv = tk.StringVar(value=self.cart_qty.get() or "1")
        pv = tk.StringVar(
            value=str(int(n(p.get('offer_price')) or n(p.get('price')))))
        row = ttk.Frame(inner)
        row.pack(fill="x", pady=5)
        ttk.Label(row, text="Qty", width=12).pack(side="left")
        ttk.Entry(
            row,
            textvariable=qv).pack(
            side="left",
            fill="x",
            expand=True,
            padx=4)
        row2 = ttk.Frame(inner)
        row2.pack(fill="x", pady=5)
        ttk.Label(row2, text="Price", width=12).pack(side="left")
        ttk.Entry(
            row2,
            textvariable=pv).pack(
            side="left",
            fill="x",
            expand=True,
            padx=4)

        def add_bulk():
            self.cart_qty.set(qv.get())
            self.cart_price.set(pv.get())
            self.cart_unit.set("")
            if self.add_selected_to_cart():
                win.destroy()
        ttk.Button(
            inner,
            text="Add to Cart",
            style="Accent.TButton",
            command=add_bulk).pack(
            fill="x",
            pady=12)
        return

    win = tk.Toplevel(self)
    win.title(f"All Units / IMEI Picker - {product_display_name(p)}")
    win.geometry("1120x740")
    win.configure(bg=UI.BG)
    sf = ScrollFrame(win, bg=UI.BG)
    sf.pack(fill="both", expand=True)
    header, h = mac_card(sf.content, "Specific Unit Picker", padding=14)
    header.pack(fill="x", padx=10, pady=(10, 6))
    tk.Label(
        h,
        text=f"{
            product_display_name(p)}  •  SKU {
            p.get('sku')}  •  Available {
                p.get('quantity')}",
        bg=UI.SURFACE,
        fg=UI.TEXT,
        font=(
            "Segoe UI",
            15,
            "bold")).pack(
        anchor="w")
    tk.Label(
        h,
        text="Double-click an available IMEI/serial to add the exact unit to cart. Sold/issued units are shown for checking but cannot be added.",
        bg=UI.SURFACE,
        fg=UI.MUTED,
        font=(
            "Segoe UI",
            9)).pack(
        anchor="w",
        pady=(
            3,
            0))
    card, inner = mac_card(sf.content, "All Unit Stock", padding=14)
    card.pack(fill="both", expand=True, padx=10, pady=6)
    bar = ttk.Frame(inner)
    bar.pack(fill="x", pady=(0, 8))
    q = tk.StringVar()
    show_all = tk.IntVar(value=1)
    ttk.Label(bar, text="Search IMEI / last 5").pack(side="left")
    ent = ttk.Entry(bar, textvariable=q, width=32)
    ent.pack(side="left", padx=6, fill="x", expand=True)
    ttk.Checkbutton(
        bar,
        text="Show sold/issued too",
        variable=show_all,
        command=lambda: fill()).pack(
        side="left",
        padx=8)
    cols = [
        "id",
        "status",
        "imei",
        "supplier",
        "cost",
        "selling",
        "profit",
        "invoice"]
    wrap, tree = self.table(
        inner, cols, headings={
            "imei": "Serial / IMEI", "invoice": "Invoice / Ref"}, height=18)
    tree.column("imei", width=260)
    tree.column("status", width=120)
    tree.column("supplier", width=160)
    wrap.pack(fill="both", expand=True)
    selected_unit = tk.StringVar(value="")
    foot = ttk.Frame(inner)
    foot.pack(fill="x", pady=10)
    ttk.Label(foot, text="Selected Unit").pack(side="left")
    ttk.Entry(
        foot,
        textvariable=selected_unit,
        width=32).pack(
        side="left",
        padx=5)

    def fill():
        tree.delete(*tree.get_children())
        term = q.get().strip().lower()
        rows = stock_detail_rows(product_id)
        rows.sort(
            key=lambda row: (
                0 if str(
                    row.get("status") or "").casefold() == "available" else 1, str(
                    row.get("imei") or "").casefold()))
        for r in rows:
            code = str(r.get("imei") or "")
            status = str(r.get("status") or "")
            if not show_all.get() and status.lower() != "available":
                continue
            if term and term not in code.lower() and not code.lower().endswith(term):
                continue
            tree.insert("",
                        "end",
                        values=(r.get("id"),
                                status,
                                code,
                                r.get("supplier"),
                                f"{n(r.get('cost')):,.0f}",
                                f"{n(r.get('selling')):,.0f}",
                                f"{n(r.get('profit')):,.0f}",
                                r.get("sold_ref") or ""))

    def select_row(_=None):
        ss = tree.selection()
        if not ss:
            return
        vals = tree.item(ss[0], "values")
        if vals:
            selected_unit.set(vals[2])

    def add_unit():
        code = selected_unit.get().strip()
        if not code:
            messagebox.showwarning(
                "Select unit", "Select an available unit first.")
            return
        # Make sure the unit is still available before adding to cart.
        match = _v6_resolve_available_unit_ui(product_id, code)
        if not match:
            messagebox.showwarning(
                "Sold / Not Available",
                "This IMEI/serial is already sold/issued or not available.")
            return
        self.cart_unit.set(match["unit_code"])
        self.cart_qty.set("1")
        self.cart_price.set(
            str(int(n(p.get("offer_price")) or n(p.get("price")))))
        if self.add_selected_to_cart():
            win.destroy()

    ent.bind("<KeyRelease>", lambda e: fill())
    tree.bind("<<TreeviewSelect>>", select_row)
    tree.bind("<Double-1>", lambda e: add_unit())
    ttk.Button(
        foot,
        text="Add Selected Unit to Cart",
        style="Accent.TButton",
        command=add_unit).pack(
        side="right",
        padx=3)
    ttk.Button(
        foot,
        text="Close",
        command=win.destroy).pack(
        side="right",
        padx=3)
    fill()
    ent.focus_set()


def _v6_pick_unit_for_pos(self):
    return self.open_units_for_selected_product()


def _v6_add_selected_to_cart(self):
    sel = self.pos_tree.selection()
    if not sel:
        messagebox.showwarning(
            "Select item",
            "Select an item first. Double-click a product to open all units.")
        return False
    vals = self.pos_tree.item(sel[0], "values")
    pid = int(vals[0])
    p = query_one("SELECT * FROM products WHERE id=?", (pid,))
    if not p:
        return False
    price = n(
        self.cart_price.get()) or n(
        p.get("offer_price")) or n(
            p.get("price"))
    qty_requested = max(1, i(self.cart_qty.get()))
    unit_text = self.cart_unit.get().strip()
    pending = []
    regular_price = n(p.get("price"))
    catalog_offer = n(p.get("offer_price"))
    offer_active = catalog_offer > 0 and catalog_offer < regular_price and abs(
        price - catalog_offer) < 0.01
    offer_meta = {
        "regular_price": regular_price,
        "catalog_offer_price": catalog_offer,
        "offer_applied": offer_active,
        "offer_saving": max(
            0,
            regular_price -
            price) if offer_active else 0}

    def cart_has_unit(code):
        return bool(code) and any(str(c.get("unit_code")) == str(code)
                                  for c in self.cart)

    try:
        if p.get("is_serialized"):
            typed_units = [
                u.strip() for u in unit_text.replace(
                    ",", "\n").splitlines() if u.strip()]
            if typed_units:
                for typed in typed_units:
                    match = _v6_resolve_available_unit_ui(pid, typed)
                    if not match:
                        raise ValueError(
                            f"IMEI/serial not available or already sold: {typed}")
                    code = match["unit_code"]
                    if cart_has_unit(code):
                        raise ValueError(
                            f"Duplicate IMEI/unit already in cart: {code}")
                    pending.append({"product_id": pid, "product_name": product_display_name(
                        p), "unit_code": code, "qty": 1, "price": price, "discount": 0, **offer_meta})
            else:
                # For exact items, do not hide the unit list.  If qty is 1,
                # open picker; if qty > 1, auto-pick first available units.
                units = [
                    u for u in available_units(pid) if not cart_has_unit(
                        u.get("unit_code"))]
                if qty_requested == 1:
                    self.open_units_for_selected_product(pid)
                    return False
                if len(units) < qty_requested:
                    raise ValueError(
                        f"Only {
                            len(units)} available units for {
                            product_display_name(p)}")
                for u in units[:qty_requested]:
                    code = u["unit_code"]
                    pending.append({"product_id": pid, "product_name": product_display_name(
                        p), "unit_code": code, "qty": 1, "price": price, "discount": 0, **offer_meta})
        else:
            already_in_cart = sum(i(c.get("qty")) for c in self.cart if int(
                c.get("product_id") or 0) == pid)
            if i(p.get("quantity")) < qty_requested + already_in_cart:
                raise ValueError(
                    f"Only {
                        p.get('quantity')} quantity available for this item.")
            # Keep every physical item as its own cart line so it can carry
            # different warranty terms, even when quantity was entered at once.
            for _ in range(qty_requested):
                pending.append({"product_id": pid, "product_name": product_display_name(
                    p), "unit_code": unit_text, "qty": 1, "price": price, "discount": 0, **offer_meta})
    except Exception as e:
        messagebox.showwarning("Cannot add item", str(e))
        return False
    confirmed = []
    focus = self.focus_get()
    warranty_parent = focus.winfo_toplevel() if focus else self
    for line_no, line in enumerate(pending, 1):
        display = dict(line)
        display.update(
            {
                "general_warranty": self.bill_general.get(),
                "general_warranty_days": self.bill_general_days.get(),
                "extended_warranty_name": "" if self.ext_option.get() == "No Extended" else self.ext_option.get(),
                "extended_warranty_days": self.ext_days.get(),
                "extended_warranty_price": 0 if self.ext_option.get() == "No Extended" else self.ext_amount.get(),
                "warranty_note": ""})
        if len(pending) > 1:
            display["product_name"] = f"{
                line.get('product_name')} ({line_no} of {
                len(pending)})"
        warranty = self.prompt_item_warranty(display, warranty_parent)
        if warranty is None:
            return False
        line.update(warranty)
        confirmed.append(line)
    self.cart.extend(confirmed)
    self.cart_price.set("")
    self.cart_unit.set("")
    self.refresh_cart()
    if hasattr(self, "item_warranty_note"):
        self.item_warranty_note.set("")
    return True


def _v6_open_item_picker(self):
    win = tk.Toplevel(self)
    win.title("All Items + Exact Unit Picker")
    win.geometry("1280x820")
    win.configure(bg=UI.BG)
    sf = ScrollFrame(win, bg=UI.BG)
    sf.pack(fill="both", expand=True)
    card, inner = mac_card(
        sf.content, "All Items / Fast Billing Picker", padding=14)
    card.pack(fill="both", expand=True, padx=10, pady=10)
    tk.Label(
        inner,
        text="Search item name, SKU, full IMEI or last 5 digits. Select product → select available unit → Add to Cart.",
        bg=UI.SURFACE,
        fg=UI.MUTED,
        font=(
            "Segoe UI",
            9)).pack(
        anchor="w",
        pady=(
            0,
            8))
    top = ttk.Frame(inner)
    top.pack(fill="x", pady=(0, 8))
    q = tk.StringVar(value=self.pos_search.get())
    ptype = tk.StringVar(value=self.pos_type.get())
    ttk.Entry(
        top,
        textvariable=q,
        width=48).pack(
        side="left",
        fill="x",
        expand=True,
        padx=(
            0,
             6))
    ttk.Combobox(
        top,
        textvariable=ptype,
        values=["All"] +
        PRODUCT_TYPES,
        state="readonly",
        width=16).pack(
        side="left",
        padx=3)
    ttk.Button(
        top,
        text="Search",
        command=lambda: fill_products()).pack(
        side="left",
        padx=3)
    body = ttk.PanedWindow(inner, orient="horizontal")
    body.pack(fill="both", expand=True)
    left = ttk.Frame(body)
    right = ttk.Frame(body)
    body.add(left, weight=3)
    body.add(right, weight=2)
    wrap, p_tree = self.table(
        left, ["id", "sku", "type", "item", "qty", "status", "price"], height=20)
    p_tree.column("item", width=370)
    p_tree.column("id", width=50)
    wrap.pack(fill="both", expand=True, padx=(0, 6))
    unit_card = ttk.Frame(right)
    unit_card.pack(fill="both", expand=True)
    unit_label = tk.StringVar(value="Select a product to see units")
    ttk.Label(
        unit_card,
        textvariable=unit_label,
        font=(
            "Segoe UI",
            10,
            "bold")).pack(
        anchor="w",
        pady=(
            0,
            5))
    unit_search = tk.StringVar()
    ttk.Entry(unit_card, textvariable=unit_search).pack(fill="x", pady=(0, 5))
    wrap, u_tree = self.table(
        unit_card, [
            "id", "status", "imei", "supplier", "reference"], headings={
            "imei": "IMEI / Serial", "reference": "Invoice / Issue Ref"}, height=18)
    u_tree.column("imei", width=250)
    wrap.pack(fill="both", expand=True)
    qty_var = tk.StringVar(value="1")
    price_var = tk.StringVar(value="")
    unit_var = tk.StringVar(value="")
    bottom = ttk.Frame(inner)
    bottom.pack(fill="x", pady=10)
    ttk.Label(bottom, text="Qty").pack(side="left")
    ttk.Entry(bottom, textvariable=qty_var, width=7).pack(side="left", padx=4)
    ttk.Label(bottom, text="Price").pack(side="left")
    ttk.Entry(
        bottom,
        textvariable=price_var,
        width=12).pack(
        side="left",
        padx=4)
    ttk.Label(bottom, text="Selected Unit").pack(side="left")
    ttk.Entry(
        bottom,
        textvariable=unit_var,
        width=34).pack(
        side="left",
        padx=4)
    state = {"product": None}

    def fill_products():
        p_tree.delete(*p_tree.get_children())
        u_tree.delete(*u_tree.get_children())
        unit_var.set("")
        state["product"] = None
        rows = search_products(q.get(), ptype.get(), include_empty=True)
        rows.sort(
            key=lambda row: (
                0 if i(
                    row.get(
                        "available_qty",
                        row.get("quantity"))) > 0 else 1,
                product_display_name(row).casefold()))
        for p in rows:
            price = n(p.get("offer_price")) or n(p.get("price"))
            available = i(p.get("available_qty", p.get("quantity")))
            state_text = "Available" if available > 0 else "Sold / Out"
            p_tree.insert("",
                          "end",
                          values=(p["id"],
                                  p["sku"],
                                  p["type"],
                                  product_display_name(p),
                                  available,
                                  state_text,
                                  f"{price:,.0f}"))

    def load_units(_=None):
        u_tree.delete(*u_tree.get_children())
        unit_var.set("")
        sel = p_tree.selection()
        if not sel:
            return
        pid = int(p_tree.item(sel[0], "values")[0])
        p = query_one("SELECT * FROM products WHERE id=?", (pid,))
        state["product"] = p
        price_var.set(str(int(n(p.get("offer_price")) or n(p.get("price")))))
        unit_label.set(f"Units for {product_display_name(p)}")
        term = unit_search.get().strip().lower()
        units = stock_detail_rows(pid) if p.get("is_serialized") else []
        if units:
            units.sort(
                key=lambda row: (
                    0 if str(
                        row.get("status") or "").casefold() == "available" else 1, str(
                        row.get("imei") or "").casefold()))
            for u in units:
                code = str(u.get("imei") or "")
                status = str(u.get("status") or "")
                if term and term not in code.lower() and not code.lower().endswith(term):
                    continue
                u_tree.insert(
                    "",
                    "end",
                    values=(
                        u.get("id"),
                        status,
                        code,
                        u.get("supplier") or "-",
                        u.get("sold_ref") or "-"))
        else:
            u_tree.insert(
                "",
                "end",
                values=(
                    "-",
                    f"Available Qty {
                        p.get('quantity')}",
                    "Bulk stock - no IMEI",
                    p.get("supplier") or "-",
                    "-"))

    def select_unit(_=None):
        ss = u_tree.selection()
        if not ss:
            return
        vals = u_tree.item(ss[0], "values")
        if vals and vals[0] != "-" and str(vals[1]).casefold() == "available":
            unit_var.set(vals[2])
            qty_var.set("1")
        else:
            unit_var.set("")

    def select_product_in_main(p):
        self.refresh_pos_products()
        for iid in self.pos_tree.get_children():
            vals = self.pos_tree.item(iid, "values")
            if vals and int(vals[0]) == int(p["id"]):
                self.pos_tree.selection_set(iid)
                self.pos_tree.see(iid)
                break

    def add_from_picker(close=False):
        p = state.get("product")
        if not p:
            load_units()
            p = state.get("product")
        if not p:
            messagebox.showwarning("Select item", "Select an item first.")
            return
        if p.get("is_serialized") and not unit_var.get().strip():
            messagebox.showwarning(
                "Select available unit",
                "Select an Available IMEI / serial. Sold and issued units are listed at the bottom for reference only.",
                parent=win)
            return
        select_product_in_main(p)
        self.cart_qty.set(qty_var.get() or "1")
        self.cart_price.set(price_var.get() or "")
        self.cart_unit.set(unit_var.get() or "")
        added = self.add_selected_to_cart()
        if added:
            win.destroy()

    q.trace_add("write", lambda *_: fill_products())
    unit_search.trace_add("write", lambda *_: load_units())
    p_tree.bind("<<TreeviewSelect>>", load_units)
    p_tree.bind("<Double-1>", lambda e: load_units())
    u_tree.bind("<<TreeviewSelect>>", select_unit)
    u_tree.bind("<Double-1>", lambda e: add_from_picker(True))
    ttk.Button(
        bottom,
        text="Add to Cart & Close",
        style="Accent.TButton",
        command=lambda: add_from_picker(True)).pack(
        side="right",
        padx=3)
    ttk.Button(
        bottom,
        text="Close",
        command=win.destroy).pack(
        side="right",
        padx=3)
    fill_products()


def _v6_open_serial_fields_popup(self):
    qty = max(1, i(self.inv_vars["qty"].get()) or 1)
    sku = (self.inv_vars["sku"].get().strip().upper() or "AUTO")
    existing = self._serial_text_lines()
    while len(existing) < qty:
        existing.append("")
    existing = existing[:qty]
    win = tk.Toplevel(self)
    win.title(f"Separate Serial / IMEI Text Areas - {qty} Units")
    win.geometry("820x720")
    win.configure(bg=UI.BG)
    sf = ScrollFrame(win, bg=UI.BG)
    sf.pack(fill="both", expand=True)
    card, inner = mac_card(
        sf.content, "Realtime Serial / IMEI Unit Fields", padding=14)
    card.pack(fill="both", expand=True, padx=10, pady=10)
    tk.Label(
        inner,
        text="Each unit has its own text area. Keep all empty for bulk/accessory stock. Generate Auto IDs for temporary tracking IDs.",
        bg=UI.SURFACE,
        fg=UI.MUTED,
        font=(
            "Segoe UI",
            9)).pack(
        anchor="w",
        pady=(
            0,
            8))
    vars_ = []
    grid = ttk.Frame(inner)
    grid.pack(fill="both", expand=True)
    for idx, value in enumerate(existing):
        ttk.Label(
            grid,
            text=f"Unit {
                idx + 1:02d}",
            width=10).grid(
            row=idx,
            column=0,
            sticky="nw",
            padx=(
                0,
                6),
            pady=3)
        txt = tk.Text(
            grid,
            height=2,
            width=70,
            wrap="word",
            font=(
                "Consolas",
                9))
        txt.insert("1.0", value)
        txt.grid(row=idx, column=1, sticky="ew", pady=3)
        vars_.append(txt)
    grid.columnconfigure(1, weight=1)

    def generate_ids():
        for txt, code in zip(vars_, _v6_auto_serials(sku, qty)):
            txt.delete("1.0", "end")
            txt.insert("1.0", code)

    def apply():
        lines = []
        for txt in vars_:
            val = txt.get("1.0", "end").strip()
            if val:
                lines.append(val)
        self.inv_units_text.configure(state="normal", background="white")
        self.inv_units_text.delete("1.0", "end")
        self.inv_units_text.insert("end", "\n".join(lines))
        self._auto_serial_lines = list(lines) if lines else []
        win.destroy()
    btns = ttk.Frame(inner)
    btns.pack(fill="x", pady=12)
    ttk.Button(
        btns,
        text="Generate Auto IDs",
        command=generate_ids).pack(
        side="left",
        padx=3)
    ttk.Button(
        btns,
        text="Clear All",
        command=lambda: [
            txt.delete(
                "1.0",
                "end") for txt in vars_]).pack(
        side="left",
        padx=3)
    ttk.Button(
        btns,
        text="Apply Serial Text Areas",
        style="Accent.TButton",
        command=apply).pack(
        side="right",
        padx=3)
    ttk.Button(
        btns,
        text="Cancel",
        command=win.destroy).pack(
        side="right",
        padx=3)


def _v6_load_selected_inventory(self):
    pid = self.selected_inv_id()
    if not pid:
        return
    p = query_one("SELECT * FROM products WHERE id=?", (pid,))
    if not p:
        return
    self.selected_product_id = pid
    self.refresh_restock_history(pid)


def _v6_add_inventory_product(self):
    serial_lines = self._serial_text_lines()
    qty = max(0, i(self.inv_vars["qty"].get()))
    ptype = self.inv_type.get()
    category = self.inv_vars["category"].get()
    # For phones/laptops/watches/tablets: if no IMEI typed, auto-generate IDs
    # so exact sold status still works.
    if not serial_lines and qty > 0 and _v6_product_needs_tracking(
            {"type": ptype, "category": category}):
        serial_lines = _v6_auto_serials(self.inv_vars["sku"].get(), qty)
        self.inv_units_text.configure(state="normal", background="white")
        self.inv_units_text.delete("1.0", "end")
        self.inv_units_text.insert("end", "\n".join(serial_lines))
    data = {
        "sku": self.inv_vars["sku"].get(),
        "type": ptype,
        "category": category,
        "brand": self.inv_vars["brand"].get(),
        "model": self.inv_vars["model"].get(),
        "color": self.inv_vars["color"].get(),
        "ram": self.inv_vars["ram"].get(),
        "rom": self.inv_vars["rom"].get(),
        "condition": self.inv_condition.get(),
        "description": self.inv_vars["desc"].get(),
        "supplier": self.inv_vars["supplier"].get(),
        "cost": self.inv_vars["cost"].get(),
        "price": self.inv_vars["price"].get(),
        "offer_price": self.inv_vars["offer"].get(),
        "quantity": self.inv_vars["qty"].get(),
        "low_stock": self.inv_vars["low"].get(),
        "is_serialized": bool(serial_lines),
        "units": "\n".join(serial_lines)}
    add_product(data, self.user)
    self.refresh_all()
    messagebox.showinfo(
        "Saved",
        "Product added with IMERP V GM intelligent inventory logic.")


def _v6_restock_selected_product(self):
    pid = self.selected_inv_id()
    if not pid:
        return
    p = query_one("SELECT * FROM products WHERE id=?", (pid,))
    if not p:
        return
    serial_lines = self._serial_text_lines()
    qty = max(0, i(self.inv_vars["qty"].get()))
    if p.get("is_serialized") and not serial_lines and qty > 0:
        serial_lines = _v6_auto_serials(p.get("sku"), qty)
        self.inv_units_text.configure(state="normal", background="white")
        self.inv_units_text.delete("1.0", "end")
        self.inv_units_text.insert("end", "\n".join(serial_lines))
    qty_or_units = "\n".join(
        serial_lines) if serial_lines else self.inv_vars["qty"].get()
    added = restock_product(
        pid,
        qty_or_units,
        self.inv_vars["cost"].get(),
        self.inv_vars["supplier"].get(),
        "Manual restock IMERP V GM",
        self.user)
    self.refresh_all()
    messagebox.showinfo(
        "Restocked",
        f"Added {added} units. Average cost and old stock data saved for finance.")


def _add_direct_sale_item_to_cart(self):
    win = tk.Toplevel(self)
    win.title("Add Direct Sale Item")
    win.geometry("620x560")
    win.configure(bg=UI.BG)
    win.transient(self)
    win.grab_set()

    card, inner = mac_card(win, "Direct Sale Item - Not Saved to Inventory", padding=14)
    card.pack(fill="both", expand=True, padx=12, pady=12)
    tk.Label(
        inner,
        text="Use this when you buy an item from another shop and sell it immediately. It saves on the invoice, client history and finance profit, but does not change inventory stock.",
        bg=UI.SURFACE,
        fg=UI.MUTED,
        font=("Segoe UI", 9),
        wraplength=560,
        justify="left").pack(anchor="w", pady=(0, 10))

    name = tk.StringVar()
    supplier = tk.StringVar()
    sku = tk.StringVar(value="DIRECT")
    unit_code = tk.StringVar()
    qty = tk.StringVar(value="1")
    buying_cost = tk.StringVar(value="0")
    selling_price = tk.StringVar(value="0")
    buying_note = tk.StringVar()

    self.labelled_entry(inner, "Item Name", name, width=42)
    self.labelled_entry(inner, "Bought From Shop", supplier, width=42)
    self.labelled_entry(inner, "SKU / Ref", sku, width=42)
    self.labelled_entry(inner, "Serial / IMEI Optional", unit_code, width=42)
    self.labelled_entry(inner, "Qty", qty, width=42)
    self.labelled_entry(inner, "Buying Cost Each", buying_cost, width=42)
    self.labelled_entry(inner, "Selling Price Each", selling_price, width=42)
    self.labelled_entry(inner, "Buying Note", buying_note, width=42)

    preview = tk.StringVar(value="Profit Preview: Rs. 0")
    tk.Label(
        inner,
        textvariable=preview,
        bg=UI.SURFACE,
        fg=UI.BLUE,
        font=("Segoe UI", 11, "bold")).pack(anchor="e", pady=(8, 4))

    def update_preview(*_):
        q = max(1, i(qty.get()))
        profit = (n(selling_price.get()) - n(buying_cost.get())) * q
        preview.set(f"Profit Preview: {money(profit)}")

    for var in (qty, buying_cost, selling_price):
        var.trace_add("write", update_preview)
    update_preview()

    def save():
        item_name = name.get().strip()
        q = max(1, i(qty.get()))
        cost = n(buying_cost.get())
        sell = n(selling_price.get())
        if not item_name:
            messagebox.showwarning("Missing item", "Enter the item name.", parent=win)
            return
        if sell <= 0:
            messagebox.showwarning("Missing price", "Selling price must be greater than zero.", parent=win)
            return
        if cost < 0:
            messagebox.showwarning("Invalid cost", "Buying cost cannot be negative.", parent=win)
            return
        if sell < cost and not messagebox.askyesno("Selling Below Cost", "Selling price is lower than buying cost. Add this item anyway?", parent=win):
            return

        direct_item = {
            "direct_sale": True,
            "item_source": "Direct Sale",
            "product_id": None,
            "product_name": item_name,
            "sku": sku.get().strip() or "DIRECT",
            "unit_code": unit_code.get().strip(),
            "qty": q,
            "price": sell,
            "unit_cost": cost,
            "cost": cost,
            "buying_price": cost,
            "discount": 0,
            "direct_supplier": supplier.get().strip(),
            "buying_note": buying_note.get().strip(),
            "general_warranty": self.bill_general.get(),
            "general_warranty_days": self.bill_general_days.get(),
            "extended_warranty_name": "" if self.ext_option.get() == "No Extended" else self.ext_option.get(),
            "extended_warranty_days": self.ext_days.get(),
            "extended_warranty_price": 0 if self.ext_option.get() == "No Extended" else self.ext_amount.get(),
            "warranty_note": self.item_warranty_note.get().strip() if hasattr(self, "item_warranty_note") else "",
        }
        warranty = self.prompt_item_warranty(direct_item, win)
        if warranty is None:
            return
        direct_item.update(warranty)
        self.cart.append(direct_item)
        self.refresh_cart()
        if hasattr(self, "item_warranty_note"):
            self.item_warranty_note.set("")
        win.destroy()

    buttons = ttk.Frame(inner)
    buttons.pack(fill="x", pady=(12, 0))
    ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right", padx=3)
    ttk.Button(buttons, text="Add Warranty + Add to Cart", style="Accent.TButton", command=save).pack(side="right", padx=3)
    win.wait_window()


# Attach V6 overrides.
ERPApp.refresh_pos_products = safe_run(_v6_refresh_pos_products)
ERPApp.open_units_for_selected_product = safe_run(_v6_open_units_for_product)
ERPApp.pick_unit_for_pos = safe_run(_v6_pick_unit_for_pos)
ERPApp.add_selected_to_cart = safe_run(_v6_add_selected_to_cart)
ERPApp.add_direct_sale_item_to_cart = safe_run(_add_direct_sale_item_to_cart)
ERPApp.open_item_picker = safe_run(_v6_open_item_picker)
ERPApp.open_serial_fields_popup = safe_run(_v6_open_serial_fields_popup)
ERPApp.load_selected_inventory = safe_run(_v6_load_selected_inventory)
ERPApp.add_inventory_product = safe_run(_v6_add_inventory_product)
ERPApp.restock_selected_product = safe_run(_v6_restock_selected_product)


def main():
    init_db()
    app = LoginWindow()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        LOG_DIR.mkdir(exist_ok=True)
        (LOG_DIR / "startup_error.log").write_text(traceback.format_exc(), encoding="utf-8")
        try:
            root = tk.Tk()
            root.withdraw()
            err = traceback.format_exc()[:900]
            messagebox.showerror(
                "Startup Error",
                f"Application failed to start. See logs/startup_error.log\n\n{err}")
        except Exception:
            print(traceback.format_exc())
