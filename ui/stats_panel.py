# =============================================================================
#  ui/stats_panel.py — لوحة الإحصائيات والمراقبة الشاملة (v5.0 Enterprise APM)
# =============================================================================
import os
import json
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from typing import Dict, Any, Optional, Callable

from ui.theme import C


class StatsPanel:
    """
    لوحة إحصائيات متطورة جداً تعرض:
    - 8 بطاقات KPI تفاعلية (بوتات، توكنات، إعلانات Monetag، مستخدمين، أخطاء)
    - فلاتر سريعة بنقرة واحدة + شريط بحث فوري
    - جدول تفاعلي شامل (التوكن، إعلانات Monetag، تطبيق الويب، النقرات، المشاهدات)
    - أزرار إجراءات سريعة لضبط الإعلانات، إدخال التوكن، واستعراض مركز الأخطاء
    """

    def __init__(self, parent, on_edit_token: Optional[Callable] = None,
                 on_edit_ads: Optional[Callable] = None):
        self.frame = parent
        self.on_edit_token = on_edit_token
        self.on_edit_ads = on_edit_ads

        self._all_records = []
        self._current_filter = "all"
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())

        parent.configure(bg=C["bg"])
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)

        self._build_kpi_cards(parent)
        self._build_filter_bar(parent)
        self._build_table(parent)
        self._build_action_bar(parent)

    # ── بطاقات KPI العلوية (8 كروت احترافية) ──────────────────────────────────
    def _build_kpi_cards(self, parent):
        cards_frame = tk.Frame(parent, bg=C["bg"])
        cards_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))

        # صفين من 4 كروت
        cards_defs = [
            # الصف الأول
            ("total_val",     "0", "🤖 إجمالي البوتات",        C["accent"],   0, 0),
            ("with_token_val","0", "🟢 تعمل بتوكن موثّق",      C["success"],  0, 1),
            ("no_token_val",  "0", "🟡 بانتظار التوكن",        C["warning"],  0, 2),
            ("with_ads_val",  "0", "📢 إعلانات Monetag",       "#2ecc71",     0, 3),
            # الصف الثاني
            ("no_ads_val",    "0", "⚠️ ينقصها إعلانات",       "#e67e22",     1, 0),
            ("users_val",     "0", "👥 إجمالي المستخدمين",     "#9b59b6",     1, 1),
            ("ad_clicks_val", "0", "🎯 نقرات Monetag",        "#3498db",     1, 2),
            ("errors_val",    "0", "🚨 الأخطاء المسجلة",       C["danger"],   1, 3),
        ]

        for attr, val, label, color, r, c in cards_defs:
            card = tk.Frame(cards_frame, bg=C["card"],
                            highlightthickness=1,
                            highlightbackground=color)
            card.grid(row=r, column=c, padx=4, pady=4, sticky="nsew", ipadx=10, ipady=6)

            val_lbl = tk.Label(card, text=val,
                               font=("Segoe UI", 18, "bold"),
                               bg=C["card"], fg=color)
            val_lbl.pack(anchor="center")

            tk.Label(card, text=label,
                     font=("Segoe UI", 8, "bold"),
                     bg=C["card"], fg=C["text_dim"]).pack(anchor="center")

            setattr(self, attr, val_lbl)

        for i in range(4):
            cards_frame.columnconfigure(i, weight=1)

    # ── شريط الفلاتر والبحث ──────────────────────────────────────────────────
    def _build_filter_bar(self, parent):
        bar = tk.Frame(parent, bg=C["panel"], padx=12, pady=6)
        bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))
        bar.columnconfigure(1, weight=1)

        # أزرار الفلترة
        btns_box = tk.Frame(bar, bg=C["panel"])
        btns_box.grid(row=0, column=0, sticky="w")

        filters = [
            ("all",       "الكل (34)"),
            ("token_ok",  "🟢 بتوكن"),
            ("token_no",  "🟡 بدون توكن"),
            ("ads_ok",    "📢 به إعلانات"),
            ("ads_no",    "⚠️ بدون إعلانات"),
            ("errors",    "🚨 به أخطاء"),
        ]

        self._filter_buttons = {}
        for f_key, f_title in filters:
            btn = tk.Button(
                btns_box, text=f_title, font=("Segoe UI", 8),
                bg=C["card"] if f_key != "all" else C["accent"],
                fg="white", relief="flat", padx=8, pady=3, cursor="hand2",
                command=lambda k=f_key: self._set_filter(k)
            )
            btn.pack(side="left", padx=2)
            self._filter_buttons[f_key] = btn

        # خانة البحث
        search_box = tk.Frame(bar, bg=C["panel"])
        search_box.grid(row=0, column=2, sticky="e")

        tk.Label(search_box, text="🔍", font=("Segoe UI Emoji", 10),
                 bg=C["panel"], fg=C["text_dim"]).pack(side="left", padx=(0, 4))
        search_entry = tk.Entry(search_box, textvariable=self._search_var,
                                font=("Segoe UI", 9), width=22,
                                bg=C["bg"], fg=C["text_bright"], insertbackground="white",
                                highlightthickness=1, highlightbackground=C["border"])
        search_entry.pack(side="left")

    def _set_filter(self, filter_key: str):
        self._current_filter = filter_key
        for k, btn in self._filter_buttons.items():
            btn.configure(bg=C["accent"] if k == filter_key else C["card"])
        self._apply_filter()

    # ── جدول التفاصيل الشامل ──────────────────────────────────────────────────
    def _build_table(self, parent):
        tree_frame = tk.Frame(parent, bg=C["bg"])
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 6))
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        style = ttk.Style()
        style.configure("MasterStats.Treeview",
                        background=C["card"],
                        foreground=C["text_bright"],
                        rowheight=26,
                        fieldbackground=C["card"],
                        font=("Segoe UI", 9))
        style.configure("MasterStats.Treeview.Heading",
                        background=C["panel"],
                        foreground=C["text_dim"],
                        font=("Segoe UI", 9, "bold"),
                        relief="flat")
        style.map("MasterStats.Treeview",
                  background=[("selected", C["accent2"])],
                  foreground=[("selected", "white")])

        columns = (
            "name", "id", "token", "ads", "miniapp",
            "users", "impressions", "clicks", "ctr", "errors", "status"
        )
        self.tree = ttk.Treeview(tree_frame,
                                 columns=columns,
                                 show="headings",
                                 style="MasterStats.Treeview",
                                 selectmode="browse")

        col_defs = [
            ("name",        "البوت",                 160, "w"),
            ("id",          "المعرف",               95,  "center"),
            ("token",       "حالة التوكن",          105, "center"),
            ("ads",         "إعلانات Monetag",      125, "center"),
            ("miniapp",     "تطبيق الويب",          85,  "center"),
            ("users",       "المستخدمين",           75,  "center"),
            ("impressions", "مشاهدات",              70,  "center"),
            ("clicks",      "نقرات",                65,  "center"),
            ("ctr",         "CTR %",                60,  "center"),
            ("errors",      "الأخطاء",              60,  "center"),
            ("status",      "الحالة",               75,  "center"),
        ]

        for col_id, heading, width, anchor in col_defs:
            self.tree.heading(col_id, text=heading)
            self.tree.column(col_id, width=width, anchor=anchor)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # ألوان الصفوف الدلالية
        self.tree.tag_configure("tok_ok",  foreground=C["text_bright"])
        self.tree.tag_configure("tok_no",  foreground=C["warning"])
        self.tree.tag_configure("has_err", foreground=C["danger"])

    # ── شريط الإجراءات السفلي ────────────────────────────────────────────────
    def _build_action_bar(self, parent):
        action_bar = tk.Frame(parent, bg=C["panel"], padx=12, pady=8)
        action_bar.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 10))
        action_bar.columnconfigure(1, weight=1)

        # يسار: أزرار سريعة للبوت المحدد
        left_box = tk.Frame(action_bar, bg=C["panel"])
        left_box.grid(row=0, column=0, sticky="w")

        btn_ads = tk.Button(
            left_box, text="📢 ضبط إعلانات Monetag", font=("Segoe UI", 9, "bold"),
            bg="#27ae60", fg="white", relief="flat", padx=10, pady=4, cursor="hand2",
            command=self._on_action_ads
        )
        btn_ads.pack(side="left", padx=(0, 6))

        btn_tok = tk.Button(
            left_box, text="🔑 إدخال / تحديث التوكن", font=("Segoe UI", 9, "bold"),
            bg=C["accent"], fg="white", relief="flat", padx=10, pady=4, cursor="hand2",
            command=self._on_action_token
        )
        btn_tok.pack(side="left", padx=(0, 6))

        btn_err = tk.Button(
            left_box, text="🚨 مركز الأخطاء المباشر", font=("Segoe UI", 9),
            bg=C["danger"], fg="white", relief="flat", padx=10, pady=4, cursor="hand2",
            command=self._open_error_center_dialog
        )
        btn_err.pack(side="left", padx=(0, 6))

        # يمين: تصدير وآخر تحديث
        right_box = tk.Frame(action_bar, bg=C["panel"])
        right_box.grid(row=0, column=2, sticky="e")

        btn_exp = tk.Button(
            right_box, text="📑 تصدير تقرير CSV", font=("Segoe UI", 8),
            bg=C["border"], fg=C["text_bright"], relief="flat", padx=8, pady=3, cursor="hand2",
            command=self._export_csv_report
        )
        btn_exp.pack(side="left", padx=(0, 10))

        self._last_update_lbl = tk.Label(
            right_box, text="آخر تحديث: —", font=("Segoe UI", 8),
            bg=C["panel"], fg=C["text_dim"]
        )
        self._last_update_lbl.pack(side="left")

    def _get_selected_bot_id(self) -> Optional[str]:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("تنبيه", "يرجى تحديد بوت من الجدول أولاً!")
            return None
        item = self.tree.item(sel[0])
        return item["values"][1]  # column 1 = bot id

    def _on_action_ads(self):
        bid = self._get_selected_bot_id()
        if bid and self.on_edit_ads:
            self.on_edit_ads(bid)

    def _on_action_token(self):
        bid = self._get_selected_bot_id()
        if bid and self.on_edit_token:
            self.on_edit_token(f"bot_{bid}")

    # ── نافذة مركز الأخطاء المتقدم (Error Center Dialog) ─────────────────────
    def _open_error_center_dialog(self):
        try:
            from database import get_db
            db = get_db()
            errors = db.get_recent_errors(limit=60) if db else []
        except Exception:
            errors = []

        dlg = tk.Toplevel(self.frame)
        dlg.title("🚨 مركز تشخيص الأخطاء المباشر (Boda Error Center)")
        dlg.geometry("780x500")
        dlg.configure(bg=C["panel"])
        dlg.transient(self.frame)

        top_box = tk.Frame(dlg, bg=C["panel"], padx=14, pady=10)
        top_box.pack(fill="x")

        tk.Label(top_box, text=f"🚨 أحدث {len(errors)} خطأ مسجل في النظام",
                 font=("Segoe UI", 12, "bold"), bg=C["panel"], fg=C["danger"]).pack(side="left")

        table_box = tk.Frame(dlg, bg=C["bg"])
        table_box.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        e_cols = ("time", "bot", "type", "msg", "user")
        e_tree = ttk.Treeview(table_box, columns=e_cols, show="headings", height=12)
        e_tree.heading("time", text="الوقت")
        e_tree.heading("bot",  text="البوت")
        e_tree.heading("type", text="النوع")
        e_tree.heading("msg",  text="الرسالة")
        e_tree.heading("user", text="المستخدم")

        e_tree.column("time", width=120, anchor="center")
        e_tree.column("bot",  width=90,  anchor="center")
        e_tree.column("type", width=140, anchor="w")
        e_tree.column("msg",  width=320, anchor="w")
        e_tree.column("user", width=70,  anchor="center")

        e_vsb = ttk.Scrollbar(table_box, orient="vertical", command=e_tree.yview)
        e_tree.configure(yscrollcommand=e_vsb.set)
        e_tree.pack(side="left", fill="both", expand=True)
        e_vsb.pack(side="right", fill="y")

        err_map = {}
        for err in errors:
            iid = e_tree.insert("", "end", values=(
                err.get("occurred_at", "")[:19].replace("T", " "),
                err.get("bot_name", ""),
                err.get("error_type", ""),
                err.get("error_message", "")[:120],
                err.get("user_id") or "—"
            ))
            err_map[iid] = err

        # عرض تفاصيل الخطأ عند النقر
        details_txt = tk.Text(dlg, height=6, bg=C["bg"], fg=C["text_bright"],
                              font=("Consolas", 8), relief="flat", padx=10, pady=6)
        details_txt.pack(fill="x", padx=14, pady=(0, 10))
        details_txt.insert("1.0", "💡 اضغط على أي خطأ في الجدول أعلاه لعرض الـ Traceback والتفاصيل التشخيصية الكاملة.")
        details_txt.configure(state="disabled")

        def on_select(evt):
            sel = e_tree.selection()
            if not sel:
                return
            err_obj = err_map.get(sel[0], {})
            details_txt.configure(state="normal")
            details_txt.delete("1.0", "end")
            tb = err_obj.get("traceback") or "لا يوجد Traceback محفوظ"
            msg = f"البوت: {err_obj.get('bot_name')} | النوع: {err_obj.get('error_type')} | البصمة: {err_obj.get('fingerprint')}\n"
            msg += f"الرسالة: {err_obj.get('error_message')}\n\nTraceback:\n{tb}"
            details_txt.insert("1.0", msg)
            details_txt.configure(state="disabled")

        e_tree.bind("<<TreeviewSelect>>", on_select)

    # ── تصدير تقرير CSV ──────────────────────────────────────────────────────
    def _export_csv_report(self):
        if not self._all_records:
            messagebox.showinfo("تنبيه", "لا توجد بيانات متاحة للتصدير حالياً!")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"boda_bot_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "البوت", "المعرف", "حالة التوكن", "إعلانات Monetag",
                    "تطبيق الويب", "المستخدمين", "مشاهدات الإعلانات",
                    "نقرات الإعلانات", "CTR %", "الأخطاء", "الحالة"
                ])
                for r in self._all_records:
                    writer.writerow([
                        r["name"], r["id"], r["token_status"], r["ads_status"],
                        r["miniapp"], r["users"], r["impressions"], r["clicks"],
                        r["ctr"], r["errors"], r["status"]
                    ])
            messagebox.showinfo("نجاح", f"✅ تم تصدير التقرير بنجاح إلى:\n{path}")
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل تصدير التقرير: {e}")

    # ── تطبيق الفلاتر والبحث ─────────────────────────────────────────────────
    def _apply_filter(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        q = self._search_var.get().strip().lower()
        f = self._current_filter

        for r in self._all_records:
            # تصفية البحث
            if q and (q not in r["name"].lower() and q not in r["id"].lower()):
                continue

            # تصفية الفئات
            if f == "token_ok" and not r["has_token"]:
                continue
            elif f == "token_no" and r["has_token"]:
                continue
            elif f == "ads_ok" and not r["has_ad"]:
                continue
            elif f == "ads_no" and r["has_ad"]:
                continue
            elif f == "errors" and r["errors"] == 0:
                continue

            tag = "tok_ok" if r["has_token"] else "tok_no"
            if r["errors"] > 0:
                tag = "has_err"

            self.tree.insert("", "end", values=(
                r["name"],
                r["id"],
                r["token_status"],
                r["ads_status"],
                r["miniapp"],
                r["users"],
                r["impressions"],
                r["clicks"],
                f"{r['ctr']}%",
                r["errors"] or "—",
                r["status"]
            ), tags=(tag,))

    # ── تحديث البيانات الشامل (Full Refresh) ──────────────────────────────────
    def refresh(self, bots: dict):
        """
        تحديث شامل للوحة الإحصائيات مع استدعاء إحصائيات Monetag وقاعدة البيانات المركزية.
        
        Args:
            bots: dict[name -> BotEntry]
        """
        # جلب حالات إعلانات Monetag
        monetag_map = {}
        try:
            from ad_manager import get_ad_manager
            mgr = get_ad_manager()
            monetag_map = mgr.get_all_monetag_statuses()
        except Exception:
            pass

        # جلب إحصائيات المستخدمين والأخطاء من قاعدة البيانات
        user_counts = {}
        error_counts = {}
        try:
            from database import get_db
            db = get_db()
            if db:
                user_counts = db.get_all_users_count()
                err_summary = db.get_error_summary(days=30)
                error_counts = err_summary.get("by_bot", {})
        except Exception:
            pass

        self._all_records = []
        count_with_token = 0
        count_no_token = 0
        count_with_ads = 0
        count_no_ads = 0
        total_users = 0
        total_clicks = 0
        total_errors = 0

        # فحص وجود تطبيقات الويب في webapps/ أو webroot/
        webapps_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webapps")

        for name, bot in bots.items():
            clean_id = name.replace("bot_", "")
            has_token = bool(getattr(bot, "has_token", False))
            if has_token:
                count_with_token += 1
                token_status = "🟢 مجهّز"
            else:
                count_no_token += 1
                token_status = "❌ مفقود"

            # حالة Monetag
            m_stat = monetag_map.get(clean_id, {})
            has_ad = bool(m_stat.get("has_ad"))
            if has_ad:
                count_with_ads += 1
                ads_status = "🟢 مركّب"
                if m_stat.get("is_custom"):
                    ads_status = "🟢 مخصّص"
            else:
                count_no_ads += 1
                ads_status = "⚠️ غير مركّب"

            # تطبيق الويب
            has_html = os.path.exists(os.path.join(webapps_dir, f"{clean_id}.html"))
            miniapp_status = "🟢 متاح" if has_html else "—"

            users = user_counts.get(clean_id, 0)
            total_users += users

            imp = m_stat.get("impressions", 0)
            clicks = m_stat.get("clicks", 0)
            ctr = m_stat.get("ctr_percent", 0.0)
            total_clicks += clicks

            errs = error_counts.get(clean_id, 0)
            total_errors += errs

            # حالة التشغيل
            if bot.status == "running":
                status_txt = "🟢 شغال"
            elif bot.status == "error":
                status_txt = "⚠️ خطأ"
            else:
                status_txt = "⚪ متوقف"

            self._all_records.append({
                "name": bot.display_name,
                "id": clean_id,
                "has_token": has_token,
                "token_status": token_status,
                "has_ad": has_ad,
                "ads_status": ads_status,
                "miniapp": miniapp_status,
                "users": users,
                "impressions": imp,
                "clicks": clicks,
                "ctr": ctr,
                "errors": errs,
                "status": status_txt
            })

        # تحديث كروت الـ KPI العلوية
        self.total_val.config(text=str(len(bots)))
        self.with_token_val.config(text=str(count_with_token))
        self.no_token_val.config(text=str(count_no_token))
        self.with_ads_val.config(text=str(count_with_ads))
        self.no_ads_val.config(text=str(count_no_ads))
        self.users_val.config(text=str(total_users))
        self.ad_clicks_val.config(text=str(total_clicks))
        self.errors_val.config(text=str(total_errors))

        # تحديث الجدول مع تطبيق الفلاتر
        self._apply_filter()

        self._last_update_lbl.config(
            text=f"آخر تحديث: {datetime.now().strftime('%H:%M:%S')}")
