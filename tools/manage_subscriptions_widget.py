import os, sys, json, re, platform, socket, uuid, hashlib, requests
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QPushButton,
    QMessageBox, QInputDialog, QProgressDialog,
    QHBoxLayout, QGridLayout, QSizePolicy, QButtonGroup
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QObject, QSize
from PyQt5.QtGui import QIcon

# ================== Cấu hình ==================
DEFAULT_SERVER_URL = os.getenv("LICENSE_SERVER_URL", "https://tkt-fastapi.onrender.com")
APP_VERSION = os.getenv("APP_VERSION", "0.0.0")
try:
    import winreg
except Exception:
    winreg = None

from verify_license import verify_license_string

# ================== Validate & tiện ích ==================
SHORT_KEY_RE = re.compile(r"^[A-Z0-9]{3}(?:-[A-Z2-7]{4}){3,4}$")
def is_short_key(s: str) -> bool:
    return bool(SHORT_KEY_RE.match((s or "").strip().upper()))

def collect_machine_info() -> dict:
    parts = []
    if winreg:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
                guid, _ = winreg.QueryValueEx(k, "MachineGuid")
                if guid: parts.append(str(guid))
        except Exception:
            pass
    try:
        parts.append(f"{uuid.getnode():012x}")
    except Exception:
        pass
    node = platform.node() or socket.gethostname() or "unknown-host"
    parts += [node, platform.platform()]
    raw = "|".join(parts).encode("utf-8", "ignore")
    hwid = hashlib.sha256(raw).hexdigest()[:32].upper()
    return {"hwid": hwid, "hostname": node, "platform": f"{platform.system()} {platform.release()}", "app_ver": APP_VERSION}

def get_resource_path(filename: str) -> str:
    """
    Trả về đường dẫn resource (ưu tiên thư mục exe → _MEIPASS → thư mục code).
    """
    exe_dir = Path(sys.executable).resolve().parent
    candidate = exe_dir / "tools" / filename
    if candidate.exists():
        return str(candidate)

    if hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / filename
        if candidate.exists():
            return str(candidate)

    return str(Path(__file__).resolve().parent / filename)

def get_license_path() -> Path:
    base_dir = Path.home() / ".tktapp"; base_dir.mkdir(exist_ok=True)
    return base_dir / "license.json"

def save_license_info(license_data):
    path = get_license_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(license_data, f, ensure_ascii=False, indent=2)

# ================== Worker kích hoạt ==================
class ActivateWorker(QObject):
    success = pyqtSignal(dict)
    error = pyqtSignal(str)
    def __init__(self, short_key: str, server_url: str, app_version: str, pub_key_path: str):
        super().__init__()
        self.short_key = short_key
        self.server_url = server_url.rstrip("/")
        self.app_version = app_version
        self.pub_key_path = pub_key_path

    def run(self):
        try:
            info = collect_machine_info()

            r = requests.post(self.server_url + "/devices/register",
                              json={"key": self.short_key, **info}, timeout=12)
            if r.status_code == 403:
                try: msg = r.json().get("detail", "Forbidden")
                except Exception: msg = "Forbidden"
                self.error.emit(f"Không thể đăng ký thiết bị: {msg}"); return
            if r.status_code >= 400:
                self.error.emit(f"Lỗi đăng ký thiết bị {r.status_code}: {r.text}"); return

            r = requests.get(self.server_url + f"/licenses/{self.short_key}/public",
                             params={"app_ver": self.app_version}, timeout=12)
            if r.status_code == 404: self.error.emit("Key không tồn tại (404)."); return
            if r.status_code == 403:
                try: msg = r.json().get("detail", "License invalid")
                except Exception: msg = "License invalid"
                self.error.emit(f"Key không hợp lệ: {msg}"); return
            if r.status_code >= 400:
                self.error.emit(f"Lỗi API {r.status_code}: {r.text}"); return

            try:
                data = r.json()
            except ValueError:
                self.error.emit("Phản hồi máy chủ không phải JSON hợp lệ."); return

            if data.get("status") != "active": self.error.emit("License không ở trạng thái active."); return
            if data.get("expired"): self.error.emit("License đã hết hạn."); return
            if "app_allowed" in data and not data["app_allowed"]:
                self.error.emit(f"Phiên bản ứng dụng ({self.app_version}) vượt quá max_version ({data.get('max_version')})."); return

            lic_str = data.get("license")
            if not lic_str:
                self.error.emit("Máy chủ không trả về 'license'. Hãy đảm bảo key đã được gắn license."); return

            ok, payload = verify_license_string(lic_str, pub_key_path=self.pub_key_path)
            if not ok:
                err = payload.get("error") if isinstance(payload, dict) else str(payload)
                self.error.emit(f"License không hợp lệ: {err or 'Verify thất bại.'}"); return

            normalized = {
                "customer": payload.get("sub", "Unknown"),
                "plan": payload.get("plan", "N/A"),
                "valid_until": payload.get("exp", "N/A"),
                "issued_at": payload.get("issued_at", "N/A"),
                "max_version": payload.get("max_version", "N/A"),
                "license_key": lic_str,
                "short_key": self.short_key,
                "nonce": payload.get("nonce"),
                "server": self.server_url,
                "server_plan": data.get("plan"),
                "server_max_devices": data.get("max_devices"),
                "server_used_devices": data.get("used_devices"),
                "server_max_version": data.get("max_version"),
                "server_expires_at": data.get("expires_at"),
                "kid": data.get("kid"),
                "hwid": info["hwid"], "hostname": info["hostname"],
                "platform": info["platform"], "app_ver": info["app_ver"],
                "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            self.success.emit(normalized)

        except requests.exceptions.RequestException as e:
            self.error.emit(f"Lỗi mạng: {e}")
        except Exception as e:
            self.error.emit(str(e))

# ================== Widget 2-pane ==================
class ManageSubscriptionsWidget(QWidget):
    license_changed = pyqtSignal(dict)

    def __init__(self, license_info=None, license_path="license.json"):
        super().__init__()
        self.license_info = license_info
        self.license_path = license_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "license.json")

        self._thread = None
        self._worker = None
        self._progress = None
        self.pub_key_path = get_resource_path("license_public_key.pem")

        self._build_ui()
        self._apply_data_to_ui()

    # --------- UI ----------
    def _build_ui(self):
        self.setStyleSheet("""
            QFrame#sidebar { border-right:1px solid #e5e7eb; }
            QPushButton[role="nav"] {
                text-align:left; border:none; border-radius:8px; padding:14px 16px;
                background:transparent; color:#333; font-size:18px;
            }
            QPushButton[role="nav"]:hover   { background:#f2f4f7; }
            QPushButton[role="nav"]:checked { background:#e8f0fe; }
            QFrame#line { background:#e5e7eb; max-height:1px; min-height:1px; }
        """)

        root = QHBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # ----- LEFT: Sidebar -----
        self.sidebar = QFrame(); self.sidebar.setObjectName("sidebar"); self.sidebar.setFixedWidth(320)
        side = QVBoxLayout(self.sidebar); side.setContentsMargins(12,12,12,12); side.setSpacing(8)

        lbl = QLabel("SUBSCRIPTIONS")
        lbl.setAlignment(Qt.AlignLeft)
        lbl.setStyleSheet("color:#6b7280; font-size:12px; letter-spacing:0.5px; margin:6px 12px 6px;")
        side.addWidget(lbl)

        self.btn_ide = self._make_nav_button("TKT Tools", icon_name="app.png")
        side.addWidget(self.btn_ide)
        side.addStretch(1)

        # ----- RIGHT: Detail -----
        self.detail = QFrame()
        right = QVBoxLayout(self.detail)
        # vẫn giữ margin/spacing hợp lý, nhưng nội dung bên phải phóng lớn hơn
        right.setContentsMargins(24, 16, 24, 12)
        right.setSpacing(6)
        right.setAlignment(Qt.AlignTop)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)  # nới nhẹ vì chữ to hơn

        self.detail_title = QLabel("TKT Tools")
        self.detail_title.setMargin(0)
        self.detail_title.setIndent(0)
        # +4px: 22px -> 26px
        self.detail_title.setStyleSheet("font-size:26px; font-weight:600; color:#0f172a;")

        self.detail_badge = QLabel("Pro")
        self.detail_badge.setContentsMargins(0, 0, 0, 0)
        # +4px: 13px -> 17px
        self.detail_badge.setStyleSheet(
            "padding:6px 12px; border-radius:999px; font-size:17px; font-weight:700; "
            "color:white; background:#0c7bdc;"
        )
        self.detail_badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.detail_badge.setMaximumHeight(30)

        title_row.addWidget(self.detail_title, alignment=Qt.AlignVCenter)
        title_row.addWidget(self.detail_badge, alignment=Qt.AlignVCenter)
        title_row.addStretch(1)
        right.addLayout(title_row)

        # Grid chi tiết
        self.detail_info = QFrame()
        self.detail_info_layout = QGridLayout(self.detail_info)
        self.detail_info_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_info_layout.setHorizontalSpacing(28)
        self.detail_info_layout.setVerticalSpacing(8)  # tăng chút vì line cao hơn
        self.detail_info_layout.setColumnMinimumWidth(0, 300)  # nới cột key cho chữ lớn
        self.detail_info_layout.setColumnStretch(1, 1)
        right.addWidget(self.detail_info)

        # Separator
        line = QFrame(); line.setObjectName("line"); right.addWidget(line)

        # Actions
        actions = QHBoxLayout()
        self.btn_activate_another = QPushButton("Kích hoạt key khác")
        icon_key = self._icon("key.png")
        if icon_key:
            self.btn_activate_another.setIcon(QIcon(icon_key))
            self.btn_activate_another.setIconSize(QSize(18,18))
        # +4px: 14px -> 18px
        self.btn_activate_another.setStyleSheet(
            "QPushButton{background:#0ea5e9; color:white; border:none; border-radius:10px; "
            "padding:12px 20px; font-weight:600; font-size:18px;} "
            "QPushButton:hover{background:#0284c7;}"
        )

        self.btn_deactivate = QPushButton("Gỡ kích hoạt")
        icon_trash = self._icon("trash.png")
        if icon_trash:
            self.btn_deactivate.setIcon(QIcon(icon_trash))
            self.btn_deactivate.setIconSize(QSize(18,18))
        # +4px: 14px -> 18px
        self.btn_deactivate.setStyleSheet(
            "QPushButton{background:#f3f4f6; border:1px solid #d1d5db; border-radius:10px; "
            "padding:12px 20px; font-size:18px;} "
            "QPushButton:hover{background:#e5e7eb;}"
        )

        actions.addWidget(self.btn_activate_another)
        actions.addWidget(self.btn_deactivate)
        actions.addStretch(1)
        right.addLayout(actions)

        # Compose
        root.addWidget(self.sidebar)
        root.addWidget(self.detail, 1)

        # Nav group (chỉ 1 nút)
        self.group = QButtonGroup(self); self.group.setExclusive(True)
        self.group.addButton(self.btn_ide, 0)
        self.btn_ide.setCheckable(True)
        self.btn_ide.setProperty("role", "nav")
        self.btn_ide.setChecked(True)

        # Signals
        self.group.buttonClicked[int].connect(self._on_nav_changed)
        self.btn_activate_another.clicked.connect(self.change_license)
        self.btn_deactivate.clicked.connect(self.deactivate_license)

    def _make_nav_button(self, title: str, icon_name: str = "") -> QPushButton:
        btn = QPushButton(); btn.setProperty("role", "nav"); btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(72)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QHBoxLayout(btn); lay.setContentsMargins(16, 12, 16, 12); lay.setSpacing(14)

        ico_lbl = QLabel()
        path = self._icon(icon_name)
        if path: ico_lbl.setPixmap(QIcon(path).pixmap(32, 32))
        ico_lbl.setFixedSize(32, 32)

        col = QVBoxLayout(); col.setSpacing(2)
        t = QLabel(title); t.setStyleSheet("font-size:17px; font-weight:600; color:#111;")
        s = QLabel("Chưa kích hoạt"); s.setStyleSheet("color:#6b7280; font-size:14px;")
        col.addWidget(t); col.addWidget(s)

        lay.addWidget(ico_lbl); lay.addLayout(col); lay.addStretch(1)

        btn._title_lbl = t; btn._sub_lbl = s
        return btn

    def _icon(self, name: str) -> str:
        for p in [
            os.path.join("TKT_Tools", "assets", "icon", name),
            os.path.join(os.path.dirname(__file__), "assets", "icon", name),
            get_resource_path(os.path.join("TKT_Tools", "assets", "icon", name)),
            name,
        ]:
            if p and os.path.exists(p): return p
        return ""

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()

    def _status_line(self) -> str:
        if not self.license_info:
            return "Chưa kích hoạt"
        vu = self.format_date(self.license_info.get("valid_until"))
        return f"Kích hoạt đến {vu}" if vu and vu != "N/A" else "Đã kích hoạt"

    def _add_row(self, row: int, key: str, value: str, mono=False):
        k = QLabel(key)
        # +4px: 14px -> 18px
        k.setStyleSheet("color:#334155; font-size:18px; font-weight:400;")
        v = QLabel(value if value else "—")
        v.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # +4px: 16px -> 20px
        if mono:
            v.setStyleSheet("font-family:Consolas, 'Courier New', monospace; color:#0f172a; font-size:20px;")
        else:
            v.setStyleSheet("color:#0f172a; font-size:20px;")

        self.detail_info_layout.addWidget(k, row, 0, alignment=Qt.AlignLeft|Qt.AlignVCenter)
        self.detail_info_layout.addWidget(v, row, 1, alignment=Qt.AlignLeft|Qt.AlignVCenter)

    def _apply_data_to_ui(self):
        # Sidebar trạng thái
        self.btn_ide._sub_lbl.setText(self._status_line())

        # Badge theo gói
        plan = (self.license_info or {}).get("plan") or "Trial"
        plan_lower = str(plan).lower()
        if plan_lower == "pro":
            badge_bg = "#0c7bdc"
        elif plan_lower in ("trial", "free"):
            badge_bg = "#16a34a"
        else:
            badge_bg = "#6b7280"
        # giữ đồng bộ +4px ở badge
        self.detail_badge.setText(plan.title())
        self.detail_badge.setStyleSheet(
            f"padding:6px 12px; border-radius:999px; font-size:17px; font-weight:700; color:white; background:{badge_bg};"
        )

        # Lưới thông tin
        self._clear_layout(self.detail_info_layout)
        if not self.license_info:
            self._add_row(0, "Trạng thái", "Chưa kích hoạt")
            self.btn_deactivate.setEnabled(False)
            return

        d = self.license_info
        rows = [
            ("👤 Khách hàng",        d.get("customer")),
            ("⭐ Gói",               d.get("plan")),
            ("📅 Ngày cấp",          self.format_date(d.get("issued_at"))),
            ("⏳ Hạn sử dụng",       self.format_date(d.get("valid_until"))),
            ("🛠️ Phiên bản tối đa", str(d.get("max_version", "—"))),
            ("🔒 Short Key",         d.get("short_key","—"), True),
            ("📦 Server plan",       str(d.get("server_plan","—"))),
            ("🔢 Tối đa thiết bị",   str(d.get("server_max_devices","—"))),
            ("🔢 Đã dùng thiết bị",  str(d.get("server_used_devices","—"))),
            ("⛔ Max app version",   str(d.get("server_max_version","—"))),
            ("📦 App version",       d.get("app_ver","—")),
        ]
        r = 0
        for key, val, *rest in rows:
            self._add_row(r, key, val, mono=bool(rest and rest[0])); r += 1

        self.btn_deactivate.setEnabled(True)

    def _on_nav_changed(self, idx: int):
        # Chỉ có 1 mục
        self.detail_title.setText("TKT Tools")
        self._apply_data_to_ui()

    # --------- Định dạng ngày ----------
    @staticmethod
    def format_date(date_str: str) -> str:
        if not date_str: return "N/A"
        from datetime import datetime, timezone, timedelta
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("Asia/Bangkok")
        except Exception:
            tz = timezone(timedelta(hours=7))
        s = str(date_str).strip()
        if s.endswith("Z"): s = s[:-1] + "+00:00"
        dt = None
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            pass
        if dt is None:
            for fmt in ["%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%S.%f%z","%Y-%m-%dT%H:%M%z","%Y-%m-%d %H:%M:%S%z","%Y-%m-%dT%H:%M:%S","%Y-%m-%dT%H:%M","%Y-%m-%d %H:%M:%S"]:
                try: dt = datetime.strptime(s, fmt); break
                except Exception: continue
        if dt is None: return date_str
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz).strftime("%d/%m/%Y %H:%M")

    # --------- Actions ----------
    def change_license(self):
        if self._thread is not None:
            return
        key, ok = QInputDialog.getText(self, "Kích hoạt", "Nhập Short key (vd: TKT-XXXX-XXXX-XXXX):")
        if not ok or not key.strip(): return
        short_key = key.strip().upper()
        if not is_short_key(short_key):
            QMessageBox.critical(self, "Sai định dạng", "Chỉ chấp nhận Short key (vd: TKT-XXXX-XXXX-XXXX)."); return

        self._progress = QProgressDialog("Đang kích hoạt, vui lòng đợi...", None, 0, 0, self)
        self._progress.setWindowModality(Qt.ApplicationModal); self._progress.setCancelButton(None)
        self._progress.setMinimumDuration(0); self._progress.setWindowTitle("Đang xử lý"); self._progress.show()

        self._thread = QThread(self)
        self._worker = ActivateWorker(short_key, DEFAULT_SERVER_URL, APP_VERSION, self.pub_key_path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.success.connect(self._on_activation_success)
        self._worker.error.connect(self._on_activation_error)
        self._worker.success.connect(self._teardown_worker)
        self._worker.error.connect(self._teardown_worker)
        self._thread.start()

    def _teardown_worker(self, *args):
        try:
            if self._progress: self._progress.close()
        except Exception: pass
        if self._thread:
            self._thread.quit(); self._thread.wait()
        self._thread = None; self._worker = None; self._progress = None

    def _on_activation_success(self, normalized: dict):
        save_license_info(normalized)
        self.license_info = {
            "customer": normalized.get("customer"),
            "plan": normalized.get("plan"),
            "valid_until": normalized.get("valid_until"),
            "issued_at": normalized.get("issued_at"),
            "max_version": normalized.get("max_version"),
            "license_key": normalized.get("license_key"),
            "short_key": normalized.get("short_key"),
            "nonce": normalized.get("nonce"),
            "server": normalized.get("server"),
            "server_plan": normalized.get("server_plan"),
            "server_max_devices": normalized.get("server_max_devices"),
            "server_used_devices": normalized.get("server_used_devices"),
            "server_max_version": normalized.get("server_max_version"),
            "server_expires_at": normalized.get("server_expires_at"),
            "hwid": normalized.get("hwid"),
            "hostname": normalized.get("hostname"),
            "platform": normalized.get("platform"),
            "app_ver": normalized.get("app_ver"),
        }
        QMessageBox.information(self, "Thành công", "✅ Key hợp lệ. Đã cập nhật license trên máy.")
        self.license_changed.emit(self.license_info)
        self._apply_data_to_ui()

    def _on_activation_error(self, message: str):
        QMessageBox.critical(self, "Kích hoạt thất bại", message or "Không thể kích hoạt.")

    def deactivate_license(self):
        if not self.license_info:
            QMessageBox.information(self, "Thông báo", "Chưa có license để hủy."); return
        ret = QMessageBox.question(self, "Xác nhận", "Hủy kích hoạt license trên máy này?",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes: return
        try:
            p = get_license_path()
            if p.exists(): p.unlink()
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể xóa license: {e}"); return
        self.license_info = None
        QMessageBox.information(self, "Đã hủy", "Đã hủy kích hoạt trên máy này.")
        self.license_changed.emit({})
        self._apply_data_to_ui()
