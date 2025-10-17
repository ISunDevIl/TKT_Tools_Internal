import os, sys, json, re
from pathlib import Path
import requests
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox,
    QSpacerItem, QSizePolicy, QApplication, QFrame
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont
from verify_license import verify_license_string
from datetime import datetime
import platform, socket, uuid, hashlib

try:
    import winreg  # Windows
except Exception:
    winreg = None

# ---- Time utils (giữ nguyên theo dự án của bạn)
from utilities.tkt_time import to_iso_z, utc_now_floor_minute

# ========== Cấu hình ==========
DEFAULT_SERVER_URL = os.getenv("LICENSE_SERVER_URL", "https://tkt-fastapi.onrender.com")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")  # đồng bộ với label hiển thị

# Server URL cố định trong code (không cho người dùng nhập)
SERVER_URL = DEFAULT_SERVER_URL.strip()

# Chỉ chấp nhận Short key dạng: TKT-XXXX-XXXX-XXXX (base32 A-Z,2-7)
SHORT_KEY_RE = re.compile(r"^[A-Z0-9]{3}(?:-[A-Z2-7]{4}){3,4}$")
WEBSITE_URL = "https://tkt-fastapi.onrender.com"

# ======= OFFLINE FALLBACK CONFIG & HELPERS =======
OFFLINE_GRACE_DAYS = int(os.getenv("OFFLINE_GRACE_DAYS", "1"))

_VERSION_RE = re.compile(r"[0-9]+")
def _version_tuple(s: str):
    nums = list(map(int, _VERSION_RE.findall(s or "")))[:3]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)

def _app_version_ok(app_version: str, max_version: str) -> bool:
    if not max_version:
        return True
    try:
        return _version_tuple(app_version) <= _version_tuple(max_version)
    except Exception:
        # Nếu parse lỗi, cho qua để tránh chặn oan
        return True

def _parse_iso_dt(s: str):
    if not s:
        return None
    from datetime import datetime, timezone
    ss = s.strip()
    if ss.endswith("Z"):
        ss = ss[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(ss)
    except Exception:
        dt = None
    if dt is None:
        for fmt in [
            "%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%S.%f%z","%Y-%m-%dT%H:%M%z",
            "%Y-%m-%d %H:%M:%S%z","%Y-%m-%dT%H:%M:%S","%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
        ]:
            try:
                dt = datetime.strptime(ss, fmt)
                break
            except Exception:
                dt = None
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def _offline_verify_cached_license(cached: dict, pub_key_path: str) -> tuple[bool, dict]:
    """
    Kiểm tra license khi offline (từ cache).
    Điều kiện pass:
      - verify chữ ký license_key OK
      - chưa hết hạn (exp / server_expires_at / valid_until)
      - APP_VERSION <= max_version (nếu có)
      - hwid trong cache khớp máy hiện tại (nếu có)
      - không vượt quá OFFLINE_GRACE_DAYS kể từ checked_at_utc
    """
    from datetime import datetime, timezone, timedelta

    lic_str = cached.get("license_key")
    if not lic_str:
        return False, {"error": "Thiếu 'license_key' trong cache."}

    # 1) Verify chữ ký
    ok, payload = verify_license_string(lic_str, pub_key_path=pub_key_path)
    if not ok:
        err = payload.get("error") if isinstance(payload, dict) else str(payload)
        return False, {"error": f"License trong cache không hợp lệ: {err}"}

    # 2) Hết hạn
    exp = payload.get("exp") or cached.get("server_expires_at") or cached.get("valid_until")
    dt_exp = _parse_iso_dt(str(exp)) if exp else None
    now = datetime.now(timezone.utc)
    if dt_exp and now > dt_exp:
        return False, {"error": "License đã hết hạn (offline)."}

    # 3) Giới hạn phiên bản
    max_ver = payload.get("max_version") or cached.get("server_max_version") or cached.get("max_version")
    if not _app_version_ok(APP_VERSION, str(max_ver or "")):
        return False, {"error": f"Phiên bản ứng dụng ({APP_VERSION}) vượt quá max_version ({max_ver})."}

    # 4) Khóa theo máy (nếu có thông tin)
    info = collect_machine_info()
    cached_hwid = cached.get("hwid")
    if cached_hwid and cached_hwid != info.get("hwid"):
        return False, {"error": "License này thuộc máy khác (HWID không khớp)."}

    # 5) Grace offline
    checked_at = cached.get("checked_at_utc")
    if checked_at:
        dt_checked = _parse_iso_dt(checked_at)
        if dt_checked and (now - dt_checked) > timedelta(days=OFFLINE_GRACE_DAYS):
            return False, {"error": f"Đã quá {OFFLINE_GRACE_DAYS} ngày chưa xác thực online. Vui lòng kết nối internet để kiểm tra lại."}

    # 6) Chuẩn hóa dữ liệu trả về cho phần còn lại dùng
    normalized = LicenseWidget.normalize_license(payload, lic_str)
    normalized.update({
        # giữ lại metadata trước đó để UI hiển thị đầy đủ
        "server": cached.get("server"),
        "short_key": cached.get("short_key"),
        "server_plan": cached.get("server_plan"),
        "server_max_devices": cached.get("server_max_devices"),
        "server_used_devices": cached.get("server_used_devices"),
        "server_max_version": cached.get("server_max_version"),
        "server_expires_at": cached.get("server_expires_at"),
        "kid": cached.get("kid"),
        "checked_at_utc": cached.get("checked_at_utc"),
        "hwid": info.get("hwid") or cached.get("hwid"),
        "hostname": info.get("hostname") or cached.get("hostname"),
        "platform": info.get("platform") or cached.get("platform"),
        "app_ver": info.get("app_ver") or cached.get("app_ver"),
        "offline_mode": True,  # flag để UI biết đang dùng offline
    })
    return True, normalized
# ================================================

def format_date(date_str: str) -> str:
    """
    Nhận chuỗi thời gian ISO 8601 và trả về 'dd/MM/YYYY HH:MM' theo Asia/Bangkok.
    """
    if not date_str:
        return "N/A"

    from datetime import datetime, timezone, timedelta
    try:
        from zoneinfo import ZoneInfo
        BKK = ZoneInfo("Asia/Bangkok")
    except Exception:
        BKK = timezone(timedelta(hours=7))

    s = date_str.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    dt = None
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        pass

    if dt is None:
        patterns = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M%z",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
        ]
        for fmt in patterns:
            try:
                dt = datetime.strptime(date_str, fmt)
                break
            except Exception:
                continue

    if dt is None:
        return date_str

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_local = dt.astimezone(BKK)
    return dt_local.strftime("%d/%m/%Y %H:%M")


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
    base_dir = Path.home() / ".tktapp"
    base_dir.mkdir(exist_ok=True)
    return base_dir / "license.json"


def save_license_info(license_data: dict):
    path = get_license_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(license_data, f, ensure_ascii=False, indent=2)


def is_short_key(s: str) -> bool:
    return bool(SHORT_KEY_RE.match(s.strip().upper()))


def collect_machine_info():
    """Tạo HWID ổn định theo máy; thu thập hostname, platform, app_ver."""
    parts = []
    if winreg:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
                guid, _ = winreg.QueryValueEx(k, "MachineGuid")
                if guid:
                    parts.append(str(guid))
        except Exception:
            pass

    try:
        parts.append(f"{uuid.getnode():012x}")
    except Exception:
        pass

    node = platform.node() or socket.gethostname() or "unknown-host"
    parts.append(node)
    parts.append(platform.platform())

    raw = "|".join(parts).encode("utf-8", "ignore")
    hwid = hashlib.sha256(raw).hexdigest()[:32].upper()

    return {
        "hwid": hwid,
        "hostname": node,
        "platform": f"{platform.system()} {platform.release()}",
        "app_ver": APP_VERSION,
    }


class LicenseWidget(QWidget):
    licenseAccepted = pyqtSignal(dict)

    # ------- Tham số cơ sở để scale -------
    BASE_W, BASE_H = 1200, 700

    def __init__(self, pub_key_filename="license_public_key.pem"):
        super().__init__()
        self.pub_key_path = get_resource_path(pub_key_filename)
        self.server_url = SERVER_URL  # cố định (không có UI nhập)

        # ====== Layout gốc ======
        self.layout_root = QVBoxLayout(self)
        self.layout_root.setSpacing(8)
        self.layout_root.setContentsMargins(16, 12, 16, 12)

        # ===== (1) TITLE =====
        self.header_frame = QFrame()
        self.header_frame.setObjectName("headerFrame")
        header_lay = QVBoxLayout(self.header_frame)
        header_lay.setContentsMargins(0, 0, 0, 0)
        header_lay.setSpacing(4)

        self.title = QLabel("TKT MULTIFORM\n One Tool – All Forms – Flexible Entry")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setWordWrap(True)
        header_lay.addWidget(self.title)

        self.layout_root.addWidget(self.header_frame)

        # ===== (2) NHẬP KEY =====
        self.key_frame = QFrame()
        self.key_frame.setObjectName("keyFrame")
        self.key_frame.setStyleSheet("""
            QFrame#keyFrame {
                background: #f8f9fb;
                border: 1px solid #dcdfe3;
                border-radius: 12px;
            }
            QLineEdit {
                border: 1px solid #c9ccd1;
                border-radius: 8px;
                padding: 8px 10px;
                background: #ffffff;
            }
            QPushButton {
                border: 1px solid #2d6cdf;
                background: #2f6fdf;
                color: #fff;
                border-radius: 8px;
            }
            QPushButton:hover { background: #255dcc; }
            QPushButton:disabled { background:#9db4ef; }
        """)
        key_lay = QVBoxLayout(self.key_frame)
        key_lay.setContentsMargins(16, 16, 16, 16)
        key_lay.setSpacing(10)

        self.label = QLabel("🔑 Vui lòng nhập key để tiếp tục")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        key_lay.addWidget(self.label)

        self.input = QLineEdit()
        self.input.setPlaceholderText("TKT-ABCD-EFGH-IJKL")
        self.input.setAlignment(Qt.AlignCenter)
        key_lay.addWidget(self.input, alignment=Qt.AlignCenter)

        self.btn_check = QPushButton("✅ Kích hoạt")
        self.btn_check.clicked.connect(self.check_license)
        key_lay.addWidget(self.btn_check, alignment=Qt.AlignCenter)
        
        self.subtitle = QLabel()
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setWordWrap(True)
        self.subtitle.setTextFormat(Qt.RichText)
        self.subtitle.setOpenExternalLinks(True)
        self.subtitle.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.subtitle.setStyleSheet("color:#666;")

        self.subtitle.setText(
            f'<span style="font-style:italic;">'
            f'Liên hệ ngay: <b>0974567728</b> để nhận key active'
            f'</span><br>'
            f'<a href="{WEBSITE_URL}">{WEBSITE_URL}</a>'
        )
        key_lay.addWidget(self.subtitle)

        # ===== (3) FOOTER =====   (TẠO TRƯỚC RỒI MỚI ADD)
        self.footer_frame = QFrame()
        self.footer_frame.setObjectName("footerFrame")
        foot_lay = QVBoxLayout(self.footer_frame)
        foot_lay.setContentsMargins(0, 0, 0, 0)
        foot_lay.setSpacing(4)

        self.info = QLabel(f"Bản quyền thuộc TKT Technology Solutions — Version: {APP_VERSION}")
        self.info.setAlignment(Qt.AlignCenter)
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color:#444;")
        foot_lay.addWidget(self.info)

        # ===== KHU TRUNG TÂM: Đặt key_frame vào GIỮA màn hình =====
        self.center_layout = QVBoxLayout()
        self.center_layout.setContentsMargins(0, 0, 0, 0)
        self.center_layout.setSpacing(0)
        self.center_layout.addStretch(1)
        self.center_layout.addWidget(self.key_frame, 0, Qt.AlignHCenter)
        self.center_layout.addStretch(1)

        # layout giữa chiếm toàn bộ khoảng trống giữa header và footer
        self.layout_root.addLayout(self.center_layout, 1)

        # Footer ở đáy
        self.layout_root.addWidget(self.footer_frame)


    # =================== Responsive helpers ===================
    def _dpi_scale(self) -> float:
        scr = QApplication.primaryScreen()
        dpi = scr.logicalDotsPerInch() if scr else 96
        return max(0.85, dpi / 96.0)

    def _w_scale(self) -> float:
        w = max(1, self.width() or self.BASE_W)
        return max(0.6, min(1.8, w / float(self.BASE_W)))

    def _h_scale(self) -> float:
        h = max(1, self.height() or self.BASE_H)
        return max(0.6, min(1.8, h / float(self.BASE_H)))

    def sp(self, pt: int) -> int:
        s = ((self._w_scale() + self._h_scale()) / 2.0) * self._dpi_scale()
        return max(9, int(pt * s))

    def _compact(self) -> bool:
        return (self.width() <= 1400) or (self.height() <= 820)

    def _apply_compact_layout(self, compact: bool):
        if compact:
            self.layout_root.setContentsMargins(12, 8, 12, 8)
            self.layout_root.setSpacing(6)
        else:
            self.layout_root.setContentsMargins(16, 12, 16, 12)
            self.layout_root.setSpacing(8)

        # viền/margin trong card nhập key
        key_lay = self.key_frame.layout()
        if compact:
            key_lay.setContentsMargins(12, 12, 12, 12)
            key_lay.setSpacing(8)
        else:
            key_lay.setContentsMargins(16, 16, 16, 16)
            key_lay.setSpacing(10)

    def apply_responsive(self):
        compact = self._compact()
        self._apply_compact_layout(compact)

        # Cỡ chữ cơ sở (nhỏ hơn khi compact)
        title_sz = 36 if compact else 24
        sub_sz   = 12 if compact else 10
        body_sz  = 12 if compact else 10
        input_sz = 11 if compact else 9
        btn_sz   = 13 if compact else 10
        foot_sz  = 10 if compact else 8

        # Title
        f = self.title.font(); f.setPointSize(self.sp(title_sz)); f.setBold(True)
        self.title.setFont(f)

        # Subtitle + label
        self.subtitle.setFont(QFont("Arial", self.sp(sub_sz)))
        self.label.setFont(QFont("Arial", self.sp(body_sz)))

        # Giới hạn bề rộng card nhập key để nhìn gọn trên màn nhỏ
        card_base_max = 520 if compact else 640
        self.key_frame.setMaximumWidth(int(card_base_max * self._w_scale()))
        self.key_frame.setMinimumWidth(int(min(360, card_base_max) * self._w_scale()))

        # Input
        self.input.setFont(QFont("Arial", self.sp(input_sz)))
        base_min_w = 260 if compact else 360
        base_max_w = 400 if compact else 500
        self.input.setMinimumWidth(int(base_min_w * self._w_scale()))
        self.input.setMaximumWidth(int(base_max_w * self._w_scale()))
        self.input.setFixedHeight(int(36 * self._h_scale()))

        # Button
        self.btn_check.setFont(QFont("Arial", self.sp(btn_sz)))
        btn_min_w = 170 if compact else 220
        btn_min_h = 34 if compact else 40
        self.btn_check.setMinimumWidth(int(btn_min_w * self._w_scale()))
        self.btn_check.setMinimumHeight(int(btn_min_h * self._h_scale()))
        self.btn_check.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Footer
        self.info.setFont(QFont("Arial", self.sp(foot_sz)))

    # =================== Hooks ===================
    def showEvent(self, e):
        super().showEvent(e)
        self.apply_responsive()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.apply_responsive()

    # =================== Logic gốc ===================
    @staticmethod
    def normalize_license(parsed: dict, license_key: str) -> dict:
        return {
            "customer": parsed.get("sub", "Unknown"),
            "plan": parsed.get("plan", "N/A"),
            "valid_until": parsed.get("exp", "N/A"),
            "issued_at": parsed.get("issued_at", "N/A"),
            "max_version": parsed.get("max_version", "N/A"),
            "license_key": license_key,
            "nonce": parsed.get("nonce"),
            "file": parsed.get("file")
        }

    def _lookup_from_server(self, short_key: str, server_url: str) -> tuple[bool, dict]:
        base = server_url.rstrip("/")
        info = collect_machine_info()

        # B1: register device
        url_reg = base + "/devices/register"
        try:
            r = requests.post(url_reg, json={"key": short_key, **info}, timeout=12)
        except requests.exceptions.RequestException as e:
            return False, {"error": f"Không kết nối được máy chủ khi đăng ký thiết bị: {e}"}

        if r.status_code == 403:
            try:
                msg = r.json().get("detail", "Forbidden")
            except Exception:
                msg = "Forbidden"
            return False, {"error": f"Không thể đăng ký thiết bị: {msg}"}
        if r.status_code >= 400:
            return False, {"error": f"Lỗi API đăng ký thiết bị {r.status_code}: {r.text}"}

        # B2: lấy license + metadata
        url_pub = base + f"/licenses/{short_key}/public"
        try:
            r = requests.get(url_pub, params={"app_ver": APP_VERSION}, timeout=12)
        except requests.exceptions.RequestException as e:
            return False, {"error": f"Không kết nối được máy chủ: {e}"}

        if r.status_code == 404:
            return False, {"error": "Key không tồn tại (404)."}
        if r.status_code == 403:
            try:
                msg = r.json().get("detail", "License invalid")
            except Exception:
                msg = "License invalid"
            return False, {"error": f"Key không hợp lệ: {msg}"}
        if r.status_code >= 400:
            return False, {"error": f"Lỗi API {r.status_code}: {r.text}"}

        data = r.json() or {}
        if data.get("status") != "active":
            return False, {"error": "License không ở trạng thái active.", "data": data}
        if data.get("expired"):
            return False, {"error": "License đã hết hạn.", "data": data}
        if "app_allowed" in data and not data["app_allowed"]:
            return False, {"error": f"Phiên bản ứng dụng ({APP_VERSION}) vượt quá max_version ({data.get('max_version')}).", "data": data}

        lic_str = data.get("license")
        if not lic_str:
            return False, {"error": "Máy chủ không trả về 'license'. Hãy đảm bảo đã lưu chuỗi license khi tạo key.", "data": data}

        # B3: verify license string
        ok, payload = verify_license_string(lic_str, pub_key_path=self.pub_key_path)
        if not ok:
            err = payload.get("error") if isinstance(payload, dict) else str(payload)
            return False, {"error": f"License từ server không hợp lệ: {err}"}

        normalized = self.normalize_license(payload, lic_str)
        normalized.update({
            "server": server_url,
            "short_key": short_key,
            "server_plan": data.get("plan"),
            "server_max_devices": data.get("max_devices"),
            "server_used_devices": data.get("used_devices"),
            "server_max_version": data.get("max_version"),
            "server_expires_at": data.get("expires_at"),
            "kid": data.get("kid"),
            **{k: info[k] for k in ("hwid", "hostname", "platform", "app_ver")},
            "checked_at_utc": to_iso_z(utc_now_floor_minute()),
        })
        return True, normalized

    def check_license(self):
        value = self.input.text().strip()
        if not value:
            QMessageBox.warning(self, "Lỗi", "Bạn chưa nhập Short key.")
            return

        server_url = self.server_url
        if not (server_url.startswith("http://") or server_url.startswith("https://")):
            QMessageBox.warning(self, "Lỗi", "Server URL trong code không hợp lệ. Hãy kiểm tra hằng SERVER_URL.")
            return

        self.btn_check.setEnabled(False)
        self.setCursor(Qt.WaitCursor)
        try:
            if not is_short_key(value):
                QMessageBox.critical(self, "Sai định dạng", "Chỉ chấp nhận Short key (vd: TKT-XXXX-XXXX-XXXX).")
                return

            short_key = value.upper()
            ok, data = self._lookup_from_server(short_key, server_url)
            if not ok:
                msg = data.get("error") if isinstance(data, dict) else str(data)
                QMessageBox.critical(self, "Kích hoạt thất bại", msg or "Không thể kích hoạt bằng short key.")
                return

            save_license_info(data)
            hsd = format_date(data.get("server_expires_at") or data.get("valid_until"))
            QMessageBox.information(
                self, "Thành công",
                f"✅ Đã kích hoạt!\nKhách hàng: {data.get('customer','N/A')}\nHSD: {hsd}"
            )
            self.licenseAccepted.emit(data)

        finally:
            self.unsetCursor()
            self.btn_check.setEnabled(True)


def load_license_info():
    """
    Nếu có ~/.tktapp/license.json:
      - Thử gọi API /licenses/{short_key}/public để kiểm tra lại.
      - Nếu lỗi mạng / 5xx: fallback kiểm tra OFFLINE từ cache.
      - Nếu 4xx (403/404/...): coi là license invalid (không fallback).
    """
    path = get_license_path()
    if not path.exists():
        return False, None

    try:
        with open(path, "r", encoding="utf-8") as f:
            cached = json.load(f)

        server_url = cached.get("server") or SERVER_URL
        short_key = (cached.get("short_key") or "").upper()
        if not short_key:
            return False, {"error": "Thiếu short_key trong license. Vui lòng kích hoạt lại bằng short key."}

        url = server_url.rstrip("/") + f"/licenses/{short_key}/public"

        # ---- Thử online
        try:
            r = requests.get(url, params={"app_ver": APP_VERSION}, timeout=12)
            status = r.status_code
            # 5xx => coi là sự cố server → fallback offline
            if 500 <= status <= 599:
                pub_key_path = get_resource_path("license_public_key.pem")
                ok, normalized = _offline_verify_cached_license(cached, pub_key_path)
                if ok:
                    save_license_info(normalized)
                    return True, normalized
                return False, normalized
        except requests.exceptions.RequestException:
            # Lỗi mạng → fallback offline
            pub_key_path = get_resource_path("license_public_key.pem")
            ok, normalized = _offline_verify_cached_license(cached, pub_key_path)
            if ok:
                save_license_info(normalized)
                return True, normalized
            return False, normalized

        # ---- Online response xử lý như cũ
        if r.status_code == 404:
            return False, {"error": "Key không tồn tại (404)."}
        if r.status_code == 403:
            try:
                msg = r.json().get("detail", "License invalid")
            except Exception:
                msg = "License invalid"
            return False, {"error": f"Key không hợp lệ: {msg}"}
        if r.status_code >= 400:
            return False, {"error": f"Lỗi API {r.status_code}: {r.text}"}

        srv = r.json() or {}
        if srv.get("status") != "active":
            return False, {"error": "License không ở trạng thái active.", "data": srv}
        if srv.get("expired"):
            return False, {"error": "License đã hết hạn.", "data": srv}
        if "app_allowed" in srv and not srv["app_allowed"]:
            return False, {"error": f"Phiên bản ứng dụng ({APP_VERSION}) vượt quá max_version ({srv.get('max_version')}).", "data": srv}

        lic_str = srv.get("license")
        if not lic_str:
            return False, {"error": "Máy chủ không trả về 'license'."}

        pub_key_path = get_resource_path("license_public_key.pem")
        ok, payload = verify_license_string(lic_str, pub_key_path=pub_key_path)
        if not ok:
            error_msg = payload.get("error") if isinstance(payload, dict) else str(payload)
            return False, {"error": f"License từ server không hợp lệ: {error_msg}"}

        normalized = LicenseWidget.normalize_license(payload, lic_str)
        normalized.update({
            "server": server_url,
            "short_key": short_key,
            "server_plan": srv.get("plan"),
            "server_max_devices": srv.get("max_devices"),
            "server_used_devices": srv.get("used_devices"),
            "server_max_version": srv.get("max_version"),
            "server_expires_at": srv.get("expires_at"),
            "kid": srv.get("kid"),
            "checked_at_utc": to_iso_z(utc_now_floor_minute()),
            "offline_mode": False,
        })
        save_license_info(normalized)
        return True, normalized

    except Exception as e:
        return False, {"error": str(e)}
