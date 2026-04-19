# -*- coding: utf-8 -*-
"""
MAESTRO 모바일 앱 v2.1  ─  보안 강화 / 자동 업데이트 / 개인 맞춤화

아키텍처:
  - FastAPI 서버 없음 → 직접 함수 호출 (열린 포트 없음)
  - API 키: AES-256 Fernet + 기기 바인딩 암호화
  - 자동 업데이트: GitHub → 앱 전용 저장소 (원자적 쓰기, 롤백)
  - 개인 맞춤화: custom.json ↔ personalizer.py 동기화
  - 최소 권한: INTERNET 만
  - 루팅·에뮬레이터·개발자 모드 감지
  - 설정·개인화 화면: FLAG_SECURE (스크린샷 차단)

화면:
  SplashScreen    보안 점검 + 업데이트 경로 설정 + 엔진 초기화
  ChatScreen      메인 채팅 (업데이트 배너 포함)
  SettingsScreen  API 키 입력 (암호화 저장)
  PersonalizeScreen  응답 스타일 / 도메인 / 언어 설정
  ModelsScreen    현재 모델 랭킹 조회
"""

import os, sys, json, threading, logging
from pathlib import Path
from datetime import datetime

# ── 프로덕션 로그 (민감 정보 출력 차단) ──────────────────────────────
logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")

# ── Kivy 환경 ──────────────────────────────────────────────────────
os.environ["KIVY_NO_ENV_CONFIG"] = "1"
os.environ["KIVY_LOG_LEVEL"]     = "warning"

import kivy
kivy.require("2.3.0")

from kivy.app               import App
from kivy.clock             import Clock
from kivy.core.window       import Window
from kivy.metrics           import dp, sp
from kivy.uix.boxlayout     import BoxLayout
from kivy.uix.button        import Button
from kivy.uix.label         import Label
from kivy.uix.popup         import Popup
from kivy.uix.progressbar   import ProgressBar
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.scrollview    import ScrollView
from kivy.uix.textinput     import TextInput
from kivy.uix.togglebutton  import ToggleButton
from kivy.utils             import get_color_from_hex, platform as _plat
from kivy.graphics          import Color, RoundedRectangle, Rectangle

_IS_ANDROID = _plat == "android"

# ── 앱 내부 모듈 경로 설정 ─────────────────────────────────────────
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

# 업데이트 경로를 가장 먼저 설정 (import 전에!)
from mobile_updater import setup_update_path, check_background as _upd_check_bg
setup_update_path()

import mobile_updater as _upd
from secure_storage import SecureStorage
from security_guard import run_security_check, set_screen_secure, enforce_https
import maestro_mobile as _mm

# ── 색상 팔레트 ────────────────────────────────────────────────────
BG       = get_color_from_hex("#0D1117")
SURFACE  = get_color_from_hex("#161B22")
BORDER   = get_color_from_hex("#30363D")
USER_CLR = get_color_from_hex("#1A4731")
AI_CLR   = get_color_from_hex("#0D2149")
TEXT     = get_color_from_hex("#E6EDF3")
MUTED    = get_color_from_hex("#8B949E")
ACCENT   = get_color_from_hex("#58A6FF")
GREEN    = get_color_from_hex("#3FB950")
RED      = get_color_from_hex("#F85149")
YELLOW   = get_color_from_hex("#D29922")
PURPLE   = get_color_from_hex("#BC8CFF")


# ══════════════════════════════════════════════════════════════════
#  공통 UI 헬퍼
# ══════════════════════════════════════════════════════════════════

def _bg(widget, color):
    with widget.canvas.before:
        Color(*color)
        rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda w, p: setattr(rect, "pos",  p),
                size=lambda w, s: setattr(rect, "size", s))


def _card(widget, color=None, radius=dp(10)):
    c = color or SURFACE
    with widget.canvas.before:
        Color(*c)
        rect = RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radius])
    widget.bind(pos=lambda w, p: setattr(rect, "pos",  p),
                size=lambda w, s: setattr(rect, "size", s))


def _btn(text, color=None, fg=None, h=dp(46), **kw) -> Button:
    return Button(
        text=text,
        size_hint_y=None, height=h,
        background_normal="",
        background_color=(*(color or ACCENT)[:3], 1),
        color=(*(fg or BG)[:3], 1),
        font_size=sp(14), **kw
    )


def _lbl(text, size=13, color=None, bold=False, **kw) -> Label:
    txt = f"[b]{text}[/b]" if bold else text
    return Label(text=txt, font_size=sp(size),
                 color=color or TEXT, markup=True, **kw)


def _section(title: str) -> Label:
    return _lbl(f"[color=#8B949E]{title}[/color]",
                size=11, size_hint_y=None, height=dp(20), halign="left")


# ══════════════════════════════════════════════════════════════════
#  대화 기록 관리 — 안정성: mkdir은 load/save 호출 시점에만
# ══════════════════════════════════════════════════════════════════

class ConversationStore:

    if _IS_ANDROID:
        _PATH = Path("/data/data/com.maestro.app/files/.maestro/history.json")
    else:
        _PATH = Path(os.path.expanduser("~")) / ".maestro" / "history.json"

    history: list = []

    @classmethod
    def _ensure_dir(cls):
        try:
            cls._PATH.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    @classmethod
    def add(cls, role: str, content: str):
        cls.history.append({
            "role": role, "content": content,
            "ts": datetime.now().isoformat()[:19]
        })
        if len(cls.history) > 200:
            cls.history = cls.history[-200:]

    @classmethod
    def save(cls):
        cls._ensure_dir()
        try:
            tmp = cls._PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(cls.history, ensure_ascii=False), encoding="utf-8")
            tmp.replace(cls._PATH)   # 원자적 교체 → 크래시 시 기존 파일 보존
        except Exception:
            pass

    @classmethod
    def load(cls):
        cls._ensure_dir()
        try:
            if cls._PATH.exists():
                cls.history = json.loads(cls._PATH.read_text(encoding="utf-8"))
        except Exception:
            cls.history = []

    @classmethod
    def clear(cls):
        cls.history = []
        cls._ensure_dir()
        try:
            cls._PATH.write_bytes(b"[]")
        except Exception:
            pass

    @classmethod
    def llm_history(cls) -> list:
        return [{"role": m["role"], "content": m["content"]}
                for m in cls.history[-40:]]


# ══════════════════════════════════════════════════════════════════
#  말풍선
# ══════════════════════════════════════════════════════════════════

class Bubble(BoxLayout):

    def __init__(self, text: str, role: str, meta: str = "", **kw):
        super().__init__(
            orientation="vertical",
            size_hint=(0.84, None),
            padding=[dp(12), dp(10)],
            spacing=dp(3), **kw
        )
        is_user = role == "user"
        _card(self, color=USER_CLR if is_user else AI_CLR, radius=dp(14))

        # 텍스트 너비를 Window.width에 안전하게 바인딩
        max_w = max(Window.width * 0.70, dp(200))
        txt = Label(
            text=text, font_size=sp(14), color=TEXT,
            halign="left", valign="top", markup=False,
            size_hint=(1, None), text_size=(max_w, None),
        )
        txt.bind(texture_size=lambda w, s: setattr(w, "height", s[1]))
        self.add_widget(txt)

        if meta:
            self.add_widget(
                Label(text=meta, font_size=sp(10), color=MUTED,
                      halign="right" if is_user else "left",
                      size_hint=(1, None), height=dp(14))
            )

        # Window 크기 변경 시 text_size 재조정
        Window.bind(width=lambda _, w: setattr(txt, "text_size", (w * 0.70, None)))
        self.bind(minimum_height=self.setter("height"))
        Clock.schedule_once(lambda dt: self._sync(txt), 0.05)

    def _sync(self, txt):
        extra = dp(30) + (dp(14) if len(self.children) > 1 else 0)
        self.height = txt.height + extra


# ══════════════════════════════════════════════════════════════════
#  채팅 목록
# ══════════════════════════════════════════════════════════════════

class ChatList(ScrollView):

    def __init__(self, **kw):
        super().__init__(do_scroll_x=False, **kw)
        self._col = BoxLayout(
            orientation="vertical", spacing=dp(10),
            padding=[dp(10), dp(12)], size_hint_y=None,
        )
        self._col.bind(minimum_height=self._col.setter("height"))
        self.add_widget(self._col)

    def push(self, text: str, role: str, meta: str = "") -> Bubble:
        bbl = Bubble(text=text, role=role, meta=meta)
        bbl.pos_hint = {"right": 1} if role == "user" else {"x": 0}
        self._col.add_widget(bbl)
        Clock.schedule_once(lambda dt: setattr(self, "scroll_y", 0), 0.12)
        return bbl

    def remove_bubble(self, bbl: Bubble):
        try:
            self._col.remove_widget(bbl)
        except Exception:
            pass

    def clear_all(self):
        self._col.clear_widgets()


# ══════════════════════════════════════════════════════════════════
#  업데이트 배너 위젯
# ══════════════════════════════════════════════════════════════════

class UpdateBanner(BoxLayout):
    """채팅 화면 상단에 붙는 업데이트 알림 배너"""

    def __init__(self, on_update, **kw):
        super().__init__(
            size_hint_y=None, height=dp(42),
            padding=[dp(10), dp(6)], spacing=dp(8), **kw
        )
        _bg(self, YELLOW)
        self.add_widget(_lbl("🔄 새 버전 업데이트 가능",
                              size=12, color=BG, size_hint_x=0.65))
        btn = Button(
            text="업데이트", font_size=sp(12),
            size_hint_x=0.35,
            background_normal="", background_color=(*BG[:3], 1),
            color=(*YELLOW[:3], 1),
        )
        btn.bind(on_press=lambda x: on_update())
        self.add_widget(btn)


# ══════════════════════════════════════════════════════════════════
#  스플래시 화면
# ══════════════════════════════════════════════════════════════════

class SplashScreen(Screen):

    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical", padding=dp(44), spacing=dp(18))
        _bg(root, BG)

        root.add_widget(Label())

        root.add_widget(_lbl("[color=#58A6FF][b]MAESTRO[/b][/color]",
                              size=42, halign="center"))
        root.add_widget(_lbl("현존 최강 AI 오케스트레이터",
                              size=14, color=MUTED, halign="center",
                              size_hint_y=None, height=dp(22)))

        root.add_widget(Label(size_hint_y=None, height=dp(16)))

        self._bar = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(5))
        root.add_widget(self._bar)

        self._msg = _lbl("초기화 중...", size=12, color=MUTED, halign="center",
                          size_hint_y=None, height=dp(22))
        root.add_widget(self._msg)

        self._warns = BoxLayout(orientation="vertical", size_hint_y=None,
                                spacing=dp(3), padding=[0, dp(6)])
        self._warns.bind(minimum_height=self._warns.setter("height"))
        root.add_widget(self._warns)
        root.add_widget(Label())
        self.add_widget(root)

    def on_enter(self):
        threading.Thread(target=self._init_seq, daemon=True).start()

    def _set(self, msg: str, pct: int):
        def _do(dt):
            self._msg.text  = msg
            self._bar.value = pct
        Clock.schedule_once(_do)

    def _init_seq(self):
        self._set("보안 점검 중...", 8)
        enforce_https()

        report = run_security_check()
        if report.warnings:
            Clock.schedule_once(lambda dt: self._show_warns(report))

        self._set("저장된 데이터 로드 중...", 25)
        keys = SecureStorage.load()
        ConversationStore.load()

        self._set("업데이트 확인 중...", 40)
        _upd_check_bg()   # 백그라운드 — 완료 전에 앱은 계속 진행

        has_keys = bool(keys.get("OPENAI_API_KEY") or keys.get("ANTHROPIC_API_KEY"))
        if not has_keys:
            self._set("API 키를 입력해 주세요.", 100)
            Clock.schedule_once(
                lambda dt: setattr(self.manager, "current", "settings"), 0.9)
            return

        self._set("MAESTRO 엔진 로드 중...", 55)
        ok = _mm.engine.initialize(keys)

        if ok:
            self._set("준비 완료 ✓", 100)
            Clock.schedule_once(
                lambda dt: setattr(self.manager, "current", "chat"), 0.5)
        else:
            err = _mm.engine.init_error()[:50]
            self._set(f"초기화 실패: {err}", 100)
            Clock.schedule_once(
                lambda dt: setattr(self.manager, "current", "settings"), 1.2)

    def _show_warns(self, report):
        for w in report.warnings[:3]:
            self._warns.add_widget(
                _lbl(f"⚠ {w}", size=11, color=YELLOW,
                      size_hint_y=None, height=dp(18)))
        if report.risk_level == "high":
            Clock.schedule_once(lambda dt: self._high_risk_popup(report))

    def _high_risk_popup(self, report):
        box = BoxLayout(orientation="vertical", padding=dp(18), spacing=dp(10))
        box.add_widget(_lbl("⚠ 보안 위험 감지", size=15, color=RED, bold=True))
        for w in report.warnings:
            box.add_widget(_lbl(f"• {w}", size=12, color=YELLOW))
        box.add_widget(_lbl("\nAPI 키 노출 위험이 있습니다. 계속 사용하시겠습니까?",
                             size=12, color=TEXT))
        btn_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        pop = Popup(title="", content=box, size_hint=(0.9, None),
                    height=dp(280), separator_height=0)
        q = _btn("종료", color=RED, fg=TEXT, h=dp(44))
        q.bind(on_press=lambda x: App.get_running_app().stop())
        c = _btn("계속", color=SURFACE, fg=TEXT, h=dp(44))
        c.bind(on_press=lambda x: pop.dismiss())
        btn_row.add_widget(q)
        btn_row.add_widget(c)
        box.add_widget(btn_row)
        pop.open()


# ══════════════════════════════════════════════════════════════════
#  채팅 화면
# ══════════════════════════════════════════════════════════════════

class ChatScreen(Screen):

    def __init__(self, **kw):
        super().__init__(**kw)
        self._busy           = False
        self._thinking_bbl   = None   # 생각 중 말풍선 참조
        self._banner_shown   = False
        self._update_banner  = None
        self._build()

    def _build(self):
        self._root = BoxLayout(orientation="vertical")
        _bg(self._root, BG)

        # ── 헤더 ─────────────────────────────────────────────────
        hdr = BoxLayout(size_hint_y=None, height=dp(52),
                        padding=[dp(14), dp(8)], spacing=dp(6))
        _bg(hdr, SURFACE)

        logo = _lbl("[b][color=#58A6FF]M[/color]AESTRO[/b]",
                     size=17, halign="left", size_hint_x=0.38)
        self._status = _lbl("", size=11, color=GREEN,
                              halign="right", size_hint_x=0.3)

        hdr.add_widget(logo)
        hdr.add_widget(self._status)
        for icon, dest in [("🎨", "personalize"), ("📊", "models"), ("⚙", "settings")]:
            b = Button(text=icon, font_size=sp(18), size_hint_x=None, width=dp(40),
                       background_color=(0, 0, 0, 0), color=(*ACCENT[:3], 1))
            b.bind(on_press=lambda x, d=dest: setattr(self.manager, "current", d))
            hdr.add_widget(b)

        # ── 채팅 목록 ─────────────────────────────────────────────
        self._chat = ChatList()

        # ── 입력 ─────────────────────────────────────────────────
        inp_row = BoxLayout(size_hint_y=None, height=dp(58),
                            padding=[dp(10), dp(7)], spacing=dp(8))
        _bg(inp_row, SURFACE)

        self._inp = TextInput(
            hint_text="마에스트로에게 물어보세요...",
            multiline=False, font_size=sp(14),
            background_color=BG, foreground_color=TEXT,
            hint_text_color=MUTED, cursor_color=ACCENT,
            padding=[dp(12), dp(10)],
        )
        self._inp.bind(on_text_validate=self._send)
        send_btn = _btn("▶", color=ACCENT, fg=BG, h=dp(44),
                         size_hint_x=None, size_hint_y=None, width=dp(50))
        send_btn.bind(on_press=self._send)

        inp_row.add_widget(self._inp)
        inp_row.add_widget(send_btn)

        self._root.add_widget(hdr)
        self._root.add_widget(self._chat)
        self._root.add_widget(inp_row)
        self.add_widget(self._root)

        Clock.schedule_interval(self._tick, 4.0)

    def on_enter(self):
        self._refresh_status()
        # 이전 대화 표시 (최근 10턴)
        if ConversationStore.history and not self._chat._col.children:
            for m in ConversationStore.history[-20:]:
                self._chat.push(
                    m["content"], m["role"],
                    meta=m.get("ts", "")[:16] if m["role"] == "assistant" else ""
                )
        # 업데이트 배너 확인
        Clock.schedule_once(lambda dt: self._check_update_banner(), 2.0)

    def _tick(self, dt):
        self._refresh_status()
        self._check_update_banner()

    def _refresh_status(self):
        avail = _mm.engine.available_keys()
        n = sum(avail.values())
        ready = _mm.engine.is_ready()
        txt   = f"● {n}개 키 활성" if ready else "● 미초기화"
        color = GREEN if ready else RED
        self._status.text  = txt
        self._status.color = color

    def _check_update_banner(self):
        state = _upd.get_state()
        if state["available"] and not self._banner_shown:
            self._banner_shown = True
            banner = UpdateBanner(on_update=self._start_update)
            self._update_banner = banner
            # 헤더 아래에 삽입 (index = 루트 children 순서상 1번)
            self._root.add_widget(banner, index=len(self._root.children) - 1)

    def _start_update(self):
        if self._update_banner:
            # 배너를 진행 중 상태로 변경
            self._update_banner.clear_widgets()
            self._update_banner.add_widget(
                _lbl("다운로드 중...", size=12, color=BG))

        _upd.download_and_apply(
            on_done=self._on_update_done,
            on_error=self._on_update_error,
        )

    def _on_update_done(self, files):
        def _ui(dt):
            if self._update_banner:
                self._root.remove_widget(self._update_banner)
                self._update_banner = None
            n = len(files)
            self._show_popup(
                f"✓ {n}개 파일 업데이트 완료",
                "앱을 완전히 종료 후 재시작하면 적용됩니다.",
                color=GREEN
            )
        Clock.schedule_once(_ui)

    def _on_update_error(self, msg):
        Clock.schedule_once(lambda dt: self._show_popup("업데이트 실패", msg, color=RED))

    def _show_popup(self, title: str, body: str, color=TEXT):
        box = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        box.add_widget(_lbl(title, size=14, color=color, bold=True))
        box.add_widget(_lbl(body, size=12, color=TEXT))
        pop = Popup(title="", content=box, size_hint=(0.85, None),
                    height=dp(180), separator_height=0)
        ok = _btn("확인", color=SURFACE, fg=TEXT, h=dp(44))
        ok.bind(on_press=lambda x: pop.dismiss())
        box.add_widget(ok)
        pop.open()

    def _send(self, *_):
        if self._busy:
            return
        msg = self._inp.text.strip()
        if not msg:
            return
        self._inp.text = ""
        self._busy = True

        self._chat.push(msg, "user")
        ConversationStore.add("user", msg)

        # 생각 중 말풍선 — 참조 안전하게 보관
        self._thinking_bbl = self._chat.push("생각 중...", "assistant")

        # LLM 호출 (백그라운드 스레드)
        hist = ConversationStore.llm_history()[:-1]  # 현재 메시지 제외
        threading.Thread(target=self._do_chat, args=(msg, hist), daemon=True).start()

    def _do_chat(self, msg: str, hist: list):
        try:
            result = _mm.engine.chat(msg, hist)
        except Exception as e:
            result = {"answer": f"오류: {type(e).__name__}", "tier": "", "model_used": ""}

        answer = result.get("answer", "[빈 응답]")
        tier   = result.get("tier", "")
        model  = result.get("model_used", "")
        meta   = " | ".join(x for x in [tier, model] if x)

        def _ui(dt):
            self._chat.remove_bubble(self._thinking_bbl)
            self._thinking_bbl = None
            self._chat.push(answer, "assistant", meta=meta)
            ConversationStore.add("assistant", answer)
            ConversationStore.save()
            self._busy = False

        Clock.schedule_once(_ui)


# ══════════════════════════════════════════════════════════════════
#  설정 화면 (API 키 + 암호화 저장)
# ══════════════════════════════════════════════════════════════════

class SettingsScreen(Screen):

    _KEYS = [
        ("OPENAI_API_KEY",    "OpenAI API Key (필수)",      "sk-..."),
        ("ANTHROPIC_API_KEY", "Anthropic Claude Key",       "sk-ant-..."),
        ("DEEPSEEK_API_KEY",  "DeepSeek API Key",           "sk-..."),
        ("GEMINI_API_KEY",    "Google Gemini API Key",      "AIza..."),
        ("GROK_KEY",          "xAI Grok API Key",           "xai-..."),
        ("VERCEL_TOKEN",      "Vercel 토큰 (배포용, 선택)", "..."),
    ]

    def __init__(self, **kw):
        super().__init__(**kw)
        self._fields = {}
        self._build()

    def _build(self):
        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        _bg(root, BG)

        back = _btn("← 채팅", color=SURFACE, fg=ACCENT, h=dp(40))
        back.bind(on_press=self._go_chat)
        root.add_widget(back)
        root.add_widget(_lbl("[b]API 키 설정[/b]", size=16, bold=False,
                              size_hint_y=None, height=dp(26)))
        root.add_widget(_lbl(
            "🔒 AES-256 암호화 · 기기 바인딩 · 외부 전송 없음",
            size=11, color=GREEN, size_hint_y=None, height=dp(18)))

        scroll = ScrollView()
        inner = BoxLayout(orientation="vertical", spacing=dp(8),
                          size_hint_y=None, padding=[0, dp(4)])
        inner.bind(minimum_height=inner.setter("height"))

        for env_key, label, hint in self._KEYS:
            row = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(66))
            row.add_widget(_lbl(label, size=11, color=MUTED,
                                 size_hint_y=None, height=dp(18), halign="left"))
            ti = TextInput(
                hint_text=hint, password=True, multiline=False,
                font_size=sp(13),
                background_color=SURFACE, foreground_color=TEXT,
                hint_text_color=BORDER, size_hint_y=None, height=dp(40),
                padding=[dp(12), dp(10)],
            )
            row.add_widget(ti)
            inner.add_widget(row)
            self._fields[env_key] = ti

        scroll.add_widget(inner)
        root.add_widget(scroll)

        btn_row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        sv = _btn("저장 및 적용", color=GREEN, fg=BG, h=dp(46))
        sv.bind(on_press=self._save)
        cl = _btn("초기화", color=RED, fg=TEXT, h=dp(46), size_hint_x=0.38)
        cl.bind(on_press=self._confirm_clear)
        btn_row.add_widget(sv)
        btn_row.add_widget(cl)
        root.add_widget(btn_row)

        self._msg = _lbl("", size=12, color=MUTED, size_hint_y=None, height=dp(22))
        root.add_widget(self._msg)
        self.add_widget(root)

    def on_enter(self):
        set_screen_secure(True)
        saved = SecureStorage.load()
        for k, ti in self._fields.items():
            ti.hint_text = "✓ 저장됨 (변경하려면 입력)" if saved.get(k) else "..."
            ti.text = ""

    def on_leave(self):
        set_screen_secure(False)

    def _save(self, *_):
        new_keys = {k: ti.text.strip() for k, ti in self._fields.items() if ti.text.strip()}
        if not new_keys:
            self._msg.text = "변경 없음"
            return
        existing = SecureStorage.load()
        existing.update(new_keys)
        if SecureStorage.save(existing):
            self._msg.text  = f"✓ {len(new_keys)}개 저장 완료"
            self._msg.color = GREEN
        else:
            self._msg.text  = "저장 실패"
            self._msg.color = RED
            return
        for ti in self._fields.values():
            ti.text = ""
        def _reinit():
            _mm.engine.initialize(existing)
            Clock.schedule_once(lambda dt: setattr(
                self._msg, "text", "✓ 엔진 재시작 완료"))
        threading.Thread(target=_reinit, daemon=True).start()

    def _confirm_clear(self, *_):
        box = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        box.add_widget(_lbl("저장된 API 키를 모두 삭제하시겠습니까?", size=13))
        pop = Popup(title="키 삭제 확인", content=box,
                    size_hint=(0.85, None), height=dp(180))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        n  = _btn("취소", color=SURFACE, fg=TEXT, h=dp(44))
        n.bind(on_press=lambda x: pop.dismiss())
        y  = _btn("삭제", color=RED, fg=TEXT, h=dp(44))
        y.bind(on_press=lambda x: (pop.dismiss(), self._clear()))
        row.add_widget(n); row.add_widget(y)
        box.add_widget(row); pop.open()

    def _clear(self):
        SecureStorage.clear()
        _mm.engine.clear_keys_from_env()
        self._msg.text  = "키 초기화 완료"
        self._msg.color = YELLOW
        for ti in self._fields.values():
            ti.text = ""; ti.hint_text = "..."

    def _go_chat(self, *_):
        if not _mm.engine.is_ready():
            self._msg.text  = "API 키를 저장 후 이동하세요"
            self._msg.color = YELLOW
            return
        self.manager.current = "chat"


# ══════════════════════════════════════════════════════════════════
#  개인 맞춤화 화면  ←  custom.json ↔ personalizer.py
# ══════════════════════════════════════════════════════════════════

class PersonalizeScreen(Screen):

    _STYLE_OPTS   = [("간결하게", "concise"), ("균형", "balanced"), ("상세하게", "detailed")]
    _FORMAT_OPTS  = [("자동",     "auto"),    ("표",   "table"),    ("목록",     "bullet")]
    _FORMAL_OPTS  = [("존댓말",   "formal"),  ("반말", "casual")]
    _DOMAIN_OPTS  = [
        ("마케팅",    "marketing"),   ("이커머스", "ecommerce"),
        ("스타트업",  "startup"),     ("개발자",   "developer"),
        ("디자이너",  "designer"),    ("컨설턴트", "consultant"),
    ]

    def __init__(self, **kw):
        super().__init__(**kw)
        self._tg_style  = {}
        self._tg_format = {}
        self._tg_formal = {}
        self._tg_domain = {}
        self._custom    = {}
        self._build()

    def _build(self):
        root = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
        _bg(root, BG)

        back = _btn("← 채팅", color=SURFACE, fg=ACCENT, h=dp(40))
        back.bind(on_press=lambda x: setattr(self.manager, "current", "chat"))
        root.add_widget(back)
        root.add_widget(_lbl("[b]개인 맞춤화[/b]", size=16, bold=False,
                              size_hint_y=None, height=dp(26)))

        scroll = ScrollView()
        inner  = BoxLayout(orientation="vertical", spacing=dp(14),
                           size_hint_y=None, padding=[0, dp(6)])
        inner.bind(minimum_height=inner.setter("height"))

        # ── 응답 스타일 ───────────────────────────────────────────
        inner.add_widget(_section("응답 길이"))
        row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        for label, val in self._STYLE_OPTS:
            tb = ToggleButton(text=label, group="style", font_size=sp(13),
                              size_hint_x=1, height=dp(42),
                              background_normal="",
                              background_down="",
                              background_color=(*BORDER[:3], 1),
                              color=TEXT)
            tb.bind(on_press=lambda x, v=val: self._on_toggle("response_style", v, x))
            row.add_widget(tb)
            self._tg_style[val] = tb
        inner.add_widget(row)

        # ── 출력 형식 ──────────────────────────────────────────────
        inner.add_widget(_section("출력 형식"))
        row2 = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        for label, val in self._FORMAT_OPTS:
            tb = ToggleButton(text=label, group="fmt", font_size=sp(13),
                              size_hint_x=1, height=dp(42),
                              background_normal="", background_down="",
                              background_color=(*BORDER[:3], 1), color=TEXT)
            tb.bind(on_press=lambda x, v=val: self._on_toggle("output_format", v, x))
            row2.add_widget(tb)
            self._tg_format[val] = tb
        inner.add_widget(row2)

        # ── 언어 격식 ──────────────────────────────────────────────
        inner.add_widget(_section("언어 스타일"))
        row3 = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        for label, val in self._FORMAL_OPTS:
            tb = ToggleButton(text=label, group="formal", font_size=sp(13),
                              size_hint_x=1, height=dp(42),
                              background_normal="", background_down="",
                              background_color=(*BORDER[:3], 1), color=TEXT)
            tb.bind(on_press=lambda x, v=val: self._on_toggle("language_formality", v, x))
            row3.add_widget(tb)
            self._tg_formal[val] = tb
        inner.add_widget(row3)

        # ── 도메인 전문성 ──────────────────────────────────────────
        inner.add_widget(_section("내 전문 분야 (복수 선택)"))
        grid = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        grid.bind(minimum_height=grid.setter("height"))
        row_d = None
        for i, (label, val) in enumerate(self._DOMAIN_OPTS):
            if i % 3 == 0:
                row_d = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
                grid.add_widget(row_d)
            tb = ToggleButton(text=label, font_size=sp(12),
                              size_hint_x=1, height=dp(40),
                              background_normal="", background_down="",
                              background_color=(*BORDER[:3], 1), color=TEXT)
            tb.bind(on_press=lambda x, v=val: self._on_domain(v, x))
            row_d.add_widget(tb)
            self._tg_domain[val] = tb
        inner.add_widget(grid)

        # ── 사용자 정의 규칙 ───────────────────────────────────────
        inner.add_widget(_section("추가 맞춤 규칙 (자유 입력)"))
        self._extra_inp = TextInput(
            hint_text="예: 항상 예시 코드를 포함해줘",
            multiline=False, font_size=sp(13),
            background_color=SURFACE, foreground_color=TEXT,
            hint_text_color=MUTED, size_hint_y=None, height=dp(42),
            padding=[dp(12), dp(10)],
        )
        inner.add_widget(self._extra_inp)

        add_rule = _btn("규칙 추가", color=SURFACE, fg=ACCENT, h=dp(38))
        add_rule.bind(on_press=self._add_extra)
        inner.add_widget(add_rule)

        self._rules_box = BoxLayout(orientation="vertical", size_hint_y=None,
                                    spacing=dp(4))
        self._rules_box.bind(minimum_height=self._rules_box.setter("height"))
        inner.add_widget(self._rules_box)

        scroll.add_widget(inner)
        root.add_widget(scroll)

        self._msg = _lbl("", size=12, color=MUTED, size_hint_y=None, height=dp(22))
        root.add_widget(self._msg)
        self.add_widget(root)

    # ── 데이터 ────────────────────────────────────────────────────

    def on_enter(self):
        set_screen_secure(True)
        threading.Thread(target=self._load_custom, daemon=True).start()

    def on_leave(self):
        set_screen_secure(False)

    def _load_custom(self):
        try:
            import personalizer as pers
            custom = pers.load_custom()
            Clock.schedule_once(lambda dt: self._apply_custom(custom))
        except Exception:
            pass

    def _apply_custom(self, custom: dict):
        self._custom = custom

        # 토글 버튼 상태 동기화
        style  = custom.get("response_style", "balanced")
        fmt    = custom.get("output_format", "auto")
        formal = custom.get("language_formality", "formal")
        domains = custom.get("domain_expertise", [])

        self._set_toggle(self._tg_style,  style)
        self._set_toggle(self._tg_format, fmt)
        self._set_toggle(self._tg_formal, formal)
        for val, tb in self._tg_domain.items():
            tb.state = "down" if val in domains else "normal"
            tb.background_color = (*PURPLE[:3], 1) if val in domains else (*BORDER[:3], 1)

        # 추가 규칙 표시
        self._rules_box.clear_widgets()
        for rule in custom.get("system_prompt_extras", []):
            self._add_rule_chip(rule)

    def _set_toggle(self, group: dict, active_val: str):
        for val, tb in group.items():
            is_active = (val == active_val)
            tb.state = "down" if is_active else "normal"
            tb.background_color = (*ACCENT[:3], 0.8) if is_active else (*BORDER[:3], 1)

    def _on_toggle(self, key: str, val: str, btn):
        self._custom[key] = val
        group = {
            "response_style":    self._tg_style,
            "output_format":     self._tg_format,
            "language_formality": self._tg_formal,
        }.get(key, {})
        self._set_toggle(group, val)
        self._persist()

    def _on_domain(self, val: str, btn):
        domains = self._custom.setdefault("domain_expertise", [])
        if val in domains:
            domains.remove(val)
            btn.state = "normal"
            btn.background_color = (*BORDER[:3], 1)
        else:
            domains.append(val)
            btn.state = "down"
            btn.background_color = (*PURPLE[:3], 1)
        self._persist()

    def _add_extra(self, *_):
        rule = self._extra_inp.text.strip()
        if not rule or len(rule) > 200:
            return
        extras = self._custom.setdefault("system_prompt_extras", [])
        if rule not in extras:
            extras.append(rule)
            self._add_rule_chip(rule)
            self._persist()
        self._extra_inp.text = ""

    def _add_rule_chip(self, rule: str):
        row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        row.add_widget(_lbl(rule[:60], size=11, color=MUTED, size_hint_x=0.85))
        del_btn = Button(text="✕", font_size=sp(12), size_hint_x=0.15,
                         background_normal="", background_color=(*RED[:3], 0.5),
                         color=TEXT)
        def _del(x, r=rule, w=row):
            self._custom.get("system_prompt_extras", []).remove(r)
            self._rules_box.remove_widget(w)
            self._persist()
        del_btn.bind(on_press=_del)
        row.add_widget(del_btn)
        self._rules_box.add_widget(row)

    def _persist(self):
        """변경 즉시 custom.json 저장 + 엔진 프롬프트 갱신"""
        def _save():
            try:
                import personalizer as pers
                pers.save_custom(self._custom)
                # 엔진의 시스템 프롬프트도 즉시 갱신
                if _mm.engine.is_ready() and _mm.engine._module:
                    _mm.engine._module._custom = self._custom
                Clock.schedule_once(lambda dt: setattr(
                    self._msg, "text", "✓ 저장됨"))
            except Exception:
                Clock.schedule_once(lambda dt: setattr(
                    self._msg, "text", "저장 오류"))
        threading.Thread(target=_save, daemon=True).start()


# ══════════════════════════════════════════════════════════════════
#  모델 현황 화면
# ══════════════════════════════════════════════════════════════════

class ModelsScreen(Screen):

    def __init__(self, **kw):
        super().__init__(**kw)
        self._build()

    def _build(self):
        root = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
        _bg(root, BG)

        back = _btn("← 채팅", color=SURFACE, fg=ACCENT, h=dp(40))
        back.bind(on_press=lambda x: setattr(self.manager, "current", "chat"))
        root.add_widget(back)
        root.add_widget(_lbl("[b]현재 모델 랭킹[/b]", size=16, bold=False,
                              size_hint_y=None, height=dp(26)))

        self._inner = BoxLayout(orientation="vertical", spacing=dp(6),
                                size_hint_y=None, padding=[0, dp(4)])
        self._inner.bind(minimum_height=self._inner.setter("height"))
        scroll = ScrollView()
        scroll.add_widget(self._inner)
        root.add_widget(scroll)

        rf = _btn("새로고침", color=SURFACE, fg=ACCENT, h=dp(40))
        rf.bind(on_press=lambda x: self._load())
        root.add_widget(rf)
        self.add_widget(root)

    def on_enter(self):
        self._load()

    def _load(self):
        def _fetch():
            db = _mm.engine.model_status()
            Clock.schedule_once(lambda dt: self._render(db))
        threading.Thread(target=_fetch, daemon=True).start()

    def _render(self, db: dict):
        self._inner.clear_widgets()
        if not db:
            self._inner.add_widget(
                _lbl("모델 DB 없음 (오케스트레이터 미실행)", size=12, color=MUTED))
            return
        for cat, info in db.items():
            row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(8),
                            padding=[dp(10), dp(4)])
            _card(row, color=SURFACE, radius=dp(8))
            model = (info.get("best_model", str(info))
                     if isinstance(info, dict) else str(info))
            row.add_widget(_lbl(cat,   size=11, color=MUTED, size_hint_x=0.38, halign="left"))
            row.add_widget(_lbl(model, size=12, color=ACCENT, size_hint_x=0.62, halign="left"))
            self._inner.add_widget(row)


# ══════════════════════════════════════════════════════════════════
#  앱 루트
# ══════════════════════════════════════════════════════════════════

class MAESTROApp(App):

    def build(self):
        Window.clearcolor = BG
        if _IS_ANDROID:
            Window.softinput_mode = "below_target"

        sm = ScreenManager(transition=SlideTransition())
        sm.add_widget(SplashScreen(name="splash"))
        sm.add_widget(ChatScreen(name="chat"))
        sm.add_widget(SettingsScreen(name="settings"))
        sm.add_widget(PersonalizeScreen(name="personalize"))
        sm.add_widget(ModelsScreen(name="models"))
        sm.current = "splash"
        return sm

    def on_pause(self):
        """앱 백그라운드 전환 → 대화 저장, True = 종료 안 함"""
        ConversationStore.save()
        return True

    def on_resume(self):
        """앱 복귀 → 엔진 미초기화 시 재로드"""
        if not _mm.engine.is_ready():
            keys = SecureStorage.load()
            if keys:
                threading.Thread(
                    target=_mm.engine.initialize, args=(keys,), daemon=True
                ).start()

    def on_stop(self):
        ConversationStore.save()


if __name__ == "__main__":
    MAESTROApp().run()
