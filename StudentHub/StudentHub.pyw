
# -*- coding: utf-8 -*-
"""
StudentHub — неофициальный настольный клиент электронного журнала TOP Academy.
Расписание, домашние задания, оценки, рейтинг группы и профиль в одном окне.
Не связан с TOP Academy / IT Step; использует публичный API журнала под вашей учётной записью.
"""
import asyncio
import json
import os
import sys
import datetime
import re
import math
from html import unescape
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal, QObject, QSize, QRectF, QPointF
from PySide6.QtGui import (QColor, QIcon, QDesktopServices, QTextCursor, QFont,
                           QPainter, QPen, QPixmap, QPolygonF)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QFrame, QScrollArea, QGridLayout, QLineEdit,
    QTextEdit, QMessageBox, QComboBox, QDialog, QFormLayout, QDialogButtonBox,
    QToolButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFileDialog, QInputDialog, QTabWidget
)

# --- [KEEP] Импорты и проверки модулей ---
try:
    from qasync import QEventLoop
    HAS_QASYNC = True
except ImportError:
    HAS_QASYNC = False

try:
    from top_academy_api import TopAcademyClient
    HAS_API = True
except ImportError:
    HAS_API = False

# [MOD] Свой API-ключ журнала (APP_KEY). Перекрывает ключ, вшитый в SDK, чтобы
# не редактировать .whl вручную. Задаётся переменной окружения STUDENTHUB_APP_KEY.
APP_KEY_OVERRIDE = os.environ.get("STUDENTHUB_APP_KEY", "").strip()
if APP_KEY_OVERRIDE and HAS_API:
    try:
        import top_academy_api.config as _api_config
        _api_config.APP_KEY = APP_KEY_OVERRIDE
        import top_academy_api.auth as _api_auth          # AuthManager держит свою копию
        _api_auth.APP_KEY = APP_KEY_OVERRIDE
    except Exception:
        pass

# ### --- СЕКЦИЯ КОНФИГУРАЦИИ И ПУТЕЙ --- ###
def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent

BASE = app_dir()
LOCAL = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "StudentHub"
LOCAL.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE = LOCAL / "settings.json"
AUTH_FILE = LOCAL / "auth.json"
SCHEDULE_CACHE = LOCAL / "schedule_cache.json"
HW_CACHE = LOCAL / "homework_cache.json"
PROFILE_CACHE = LOCAL / "profile.json"
ERROR_LOG = LOCAL / "last_error.log"
GRADES_CACHE = LOCAL / "grades_cache.json"

# [MOD] Цветовая схема и Шрифты (Увеличены размеры)
DARK = {
    "BG": "#07101f", "BG_SOFT": "#0a1426", "CARD": "#0d1a2e",
    "FIELD": "#101f36",
    "CARD_HI": "#142644", "LINE": "#1b3150", "INK": "#edf3ff",
    "MUTED": "#8fa6ca", "META": "#b4c5e2",
    "TEAL": "#315cff", "TEAL_HOVER": "#244be8",
    "TEAL_SOFT": "#14285a", "ON_TEAL": "#ffffff", "ORANGE": "#f2a93b",
    "ORANGE_SOFT": "#33260f", "DANGER": "#ff5f7e", "FAINT": "#35477f",
    "GREEN": "#2fd38a",
    "DANGER_SOFT": "#3a1527", "GREEN_SOFT": "#0d3a38",
    "VIOLET": "#7658ff", "VIOLET_SOFT": "#211d50",
    "BLUE": "#3994ff", "BLUE_SOFT": "#102d51",
    "PINK": "#f0589f", "PINK_SOFT": "#3a1640",
    "YELLOW": "#f2b84b", "YELLOW_SOFT": "#352a12",
}
LIGHT = {
    "BG": "#eef1fb", "BG_SOFT": "#f6f8ff", "CARD": "#ffffff",
    "FIELD": "#f1f4fd",
    "CARD_HI": "#e8edfb", "LINE": "#d6def2", "INK": "#17224a",
    "MUTED": "#5f6e9c", "META": "#434f7a",
    "TEAL": "#3050e8", "TEAL_HOVER": "#2640c8",
    "TEAL_SOFT": "#e0e6ff", "ON_TEAL": "#ffffff", "ORANGE": "#d4800a",
    "ORANGE_SOFT": "#fdecd0", "DANGER": "#d6334f", "FAINT": "#b4bfdc",
    "GREEN": "#13a46a",
    "DANGER_SOFT": "#fde1e7", "GREEN_SOFT": "#d6f4e8",
    "VIOLET": "#7240e0", "VIOLET_SOFT": "#ebe3ff",
    "BLUE": "#2278e8", "BLUE_SOFT": "#dbeaff",
    "PINK": "#d03a85", "PINK_SOFT": "#fddff0",
    "YELLOW": "#b98505", "YELLOW_SOFT": "#faf0c8",
}

C = dict(DARK)

# --- [KEEP] Вспомогательные функции JSON и Логирования ---
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

def log_error(msg):
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now()}: {msg}\n")
    except OSError:
        pass

def describe_exc(e):
    parts = [f"{type(e).__name__}: {e}"]
    seen = set()
    cur = e
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        resp = getattr(cur, "response", None)
        if resp is not None:
            try:
                parts.append(f"HTTP {resp.status_code} {resp.request.method} {resp.request.url} body={resp.text[:300]!r}")
            except Exception:
                pass
        cur = cur.__cause__ or cur.__context__
    return " | ".join(parts)

settings = load_json(SETTINGS_FILE, {"theme": "dark", "lang": "ru"})
# Ссылка для раздела «Поддержка автора»: пусто = раздел скрыт. Задаётся переменной окружения STUDENTHUB_DONATE_URL.
DONATE_URL = os.environ.get("STUDENTHUB_DONATE_URL", "").strip()
C.update(LIGHT if settings.get("theme") == "light" else DARK)

# [MOD] Переводы (Убраны БЕТА и добавлены Общие группы)
TR = {
    "ru": {
        "sched": "Расписание", "homework": "Домашние задания",
        "profile": "Профиль", "settings": "Настройки",
        "support": "Поддержка",
        "donate": "Поддержка автора", "all_groups": "Общие группы",
        "page_sched": "Моё расписание", "page_sched_sub": "Расписание твоей группы",
        "sched_all_btn": "Общее расписание", "sched_my_btn": "Моя группа",
        "page_all_groups": "Общее расписание", "page_all_groups_sub": "Расписание всех групп колледжа",
        "page_hw": "Домашние задания", "page_hw_sub": "Список заданий из журнала",
        "page_prof": "Профиль", "page_prof_sub": "Твои данные из журнала",
        "page_set": "Настройки", "page_set_sub": "Тема, язык, аккаунт",
        "page_sup": "Поддержка", "page_sup_sub": "Отправить обращение в поддержку журнала",
        "page_don": "Поддержать автора", "page_don_sub": "Спасибо, что пользуешься StudentHub",
        "login_title": "Вход в журнал",
        "login_sub": "Введи логин и пароль от журнала. Пароль не сохраняется — только refresh-токен (30 дней).",
        "login_user": "Логин", "login_pass": "Пароль",
        "login_btn": "Войти", "logout": "Выйти",
        "login_loading": "Проверяем...",
        "login_error": "Неверный логин или пароль",
        "login_no_api": "Модуль top_academy_api не установлен.",
        "login_no_qasync": "Модуль qasync не установлен.",
        "today": "Сегодня", "prev": "←", "next": "→",
        "refresh": "Обновить", "download": "Скачать", "upload": "Отправить",
        "subject": "Предмет", "topic": "Тема", "teacher": "Преподаватель",
        "issued": "Выдано", "due": "Срок", "status": "Статус", "actions": "Действия",
        "theme": "Тема", "theme_dark": "Тёмная", "theme_light": "Светлая",
        "lang": "Язык", "save": "Сохранить", "saved": "Сохранено",
        "group": "Группа", "stream": "Поток", "points": "Очки",
        "sup_subject": "Тема обращения", "sup_text": "Текст обращения",
        "sup_send": "Отправить", "sup_sent": "Обращение отправлено",
        "sup_error": "Не удалось отправить обращение",
        "select_file": "Выберите файл для отправки",
        "answer_text": "Комментарий (от 5 до 500 символов)",
        "sent": "Работа отправлена",
        "send_error": "Ошибка отправки",
        "no_data": "Нет данных. Нажми «Обновить».",
        "loading": "Загрузка...",
        "mode_api": "Моя группа (API)", "mode_manual": "Все группы (ручной)",
        "dept": "Отделение", "change_group": "Сменить группу",
        "donate_link": "Ссылка на донаты",
        "donate_open": "Открыть в браузере",
        "donate_saved": "Ссылка сохранена",
        "empty_hw": "Сервер вернул 0 заданий.",
        "hw_err": "Ошибка загрузки",
        "hw_all": "Все", "hw_todo": "К выполнению", "hw_review": "На проверке",
        "hw_checked": "Проверено", "hw_overdue": "Просрочено",
        "hw_search": "Поиск по предмету, теме или преподавателю",
        "hw_all_subjects": "Все предметы",
        "hw_due_today": "срок сегодня", "hw_due_tomorrow": "срок завтра",
        "hw_due_in": "осталось {n}", "hw_overdue_by": "просрочено на {n}",
        "hw_issued": "Выдано", "hw_deadline": "Срок",
        "hw_my_work": "Моя работа", "hw_task_file": "Файл задания",
        "hw_resend": "Отправить заново",
        "hw_partial": "Часть заданий не загрузилась, показаны сохранённые данные",
        "hw_delete_draft": "Удалить черновик", "hw_delete_confirm": "Удалить сданную работу?",
        "hw_stud_answer": "Мой ответ", "hw_spent": "Затрачено",
        "hw_teacher_comment": "Комментарий преподавателя", "hw_mark": "Оценка",
        "hw_more": "Показать ещё", "hw_nothing": "По этим фильтрам ничего не найдено",
        "hw_updated": "Обновлено в {time} · заданий: {n}",
        "hw_session": "Сессия истекла или журнал недоступен. Выйди из аккаунта в настройках и войди заново.",
        "don_head": "Нравится StudentHub?",
        "don_text": "Приложение создаётся, чтобы расписание и домашние задания всегда были под рукой и выглядели красиво. На разработку и поддержку уходит много времени и сил. Если StudentHub тебе пригодился, поддержи автора любой суммой — это мотивирует исправлять ошибки и добавлять новые функции.",
        "don_note": "Это совершенно добровольно. Даже простое «спасибо» и рассказ друзьям о приложении очень помогают.",
        "don_btn": "Поддержать автора",
        "don_hint": "Откроется страница в браузере",
        "don_bugs": "Исправление ошибок", "don_bugs_t": "Быстрее чинить баги и подстраиваться под обновления журнала",
        "don_features": "Новые функции", "don_features_t": "Больше возможностей в приложении",
        "don_growth": "Развитие проекта", "don_growth_t": "Больше времени и сил на StudentHub",
        "pick_file": "Выбрать файл", "no_file": "Файл не выбран", "cancel": "Отмена",
    },
    "en": {
        "sched": "Schedule", "homework": "Homework",
        "profile": "Profile", "settings": "Settings",
        "support": "Support",
        "donate": "Support the author", "all_groups": "General Groups",
        "sched_all_btn": "All schedules", "sched_my_btn": "My group",
        "page_sched": "My Schedule", "page_sched_sub": "Your group schedule",
        "page_all_groups": "General Groups", "page_all_groups_sub": "All college group schedules",
        "page_hw": "Homework", "page_hw_sub": "Tasks list from journal",
        "page_prof": "Profile", "page_prof_sub": "Your journal data",
        "page_set": "Settings", "page_set_sub": "Theme, language, account",
        "page_sup": "Support", "page_sup_sub": "Send a message to the journal support",
        "page_don": "Support the author", "page_don_sub": "Thank you for using StudentHub",
        "login_title": "Log in to the journal",
        "login_sub": "Enter journal credentials. Password is not stored — only refresh-token (30 days) is saved.",
        "login_user": "Login", "login_pass": "Password",
        "login_btn": "Sign in", "logout": "Log out",
        "login_loading": "Checking...",
        "login_error": "Wrong login or password",
        "login_no_api": "top_academy_api not installed.",
        "login_no_qasync": "qasync not installed.",
        "today": "Today", "prev": "←", "next": "→",
        "refresh": "Refresh", "download": "Download", "upload": "Submit",
        "subject": "Subject", "topic": "Topic", "teacher": "Teacher",
        "issued": "Issued", "due": "Due", "status": "Status", "actions": "Actions",
        "theme": "Theme", "theme_dark": "Dark", "theme_light": "Light",
        "lang": "Language", "save": "Save", "saved": "Saved",
        "group": "Group", "stream": "Stream", "points": "Points",
        "sup_subject": "Subject", "sup_text": "Message",
        "sup_send": "Send", "sup_sent": "Message sent",
        "sup_error": "Failed to send message",
        "select_file": "Select file to upload",
        "answer_text": "Comment (5 to 500 characters)",
        "sent": "Submitted",
        "send_error": "Submit error",
        "no_data": "No data. Press Refresh.",
        "loading": "Loading...",
        "mode_api": "My group (API)", "mode_manual": "All groups (manual)",
        "dept": "Department", "change_group": "Change group",
        "donate_link": "Donate link",
        "donate_open": "Open in browser",
        "donate_saved": "Link saved",
        "empty_hw": "Server returned 0 tasks.",
        "hw_err": "Load error",
        "hw_all": "All", "hw_todo": "To do", "hw_review": "In review",
        "hw_checked": "Graded", "hw_overdue": "Overdue",
        "hw_search": "Search by subject, topic or teacher",
        "hw_all_subjects": "All subjects",
        "hw_due_today": "due today", "hw_due_tomorrow": "due tomorrow",
        "hw_due_in": "{n} left", "hw_overdue_by": "overdue by {n}",
        "hw_issued": "Issued", "hw_deadline": "Due",
        "hw_my_work": "My work", "hw_task_file": "Task file",
        "hw_resend": "Submit again",
        "hw_partial": "Some tasks failed to load, showing saved data",
        "hw_delete_draft": "Delete draft", "hw_delete_confirm": "Delete submitted work?",
        "hw_stud_answer": "My answer", "hw_spent": "Spent",
        "hw_teacher_comment": "Teacher's comment", "hw_mark": "Mark",
        "hw_more": "Show more", "hw_nothing": "Nothing matches these filters",
        "hw_updated": "Updated at {time} · tasks: {n}",
        "hw_session": "Session expired or the journal is unavailable. Log out in Settings and sign in again.",
        "don_head": "Enjoying StudentHub?",
        "don_text": "This app is built to keep your schedule and homework at hand and looking good. Development and maintenance take a lot of time and effort. If StudentHub is useful to you, please support the author with any amount — it keeps the bugs getting fixed and the new features coming.",
        "don_note": "It is completely optional. Even a simple thank-you and telling friends about the app helps a lot.",
        "don_btn": "Support the author",
        "don_hint": "A page will open in your browser",
        "don_bugs": "Bug fixes", "don_bugs_t": "Fix issues faster and keep up with journal changes",
        "don_features": "New features", "don_features_t": "More things the app can do",
        "don_growth": "Project growth", "don_growth_t": "More time and energy for StudentHub",
        "pick_file": "Choose file", "no_file": "No file chosen", "cancel": "Cancel",
    },
}

def t(key):
    lang = settings.get("lang", "ru")
    return TR.get(lang, TR["ru"]).get(key, key)

# --- [KEEP] Данные расписания ---
DAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
DAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
SLOTS = [("08:30", "10:00"), ("10:10", "11:40"), ("12:20", "13:50"),
         ("14:00", "15:30"), ("15:40", "17:10")]
DEMO_ROOM = "Ауд. 101"
# Демонстрационные данные (вымышленные). Реальное расписание подгружается из журнала через API.
# Свои локальные группы можно описать здесь в том же формате: 5 дней × 5 пар, пара = [предмет, аудитория, преподаватель].
SCHEDULE_MINE = [
    [["Математика", DEMO_ROOM, "Иванов И. И."], ["Информатика", "Ауд. 202", "Петров П. П."],
     ["Английский язык", "Ауд. 303", "Сидорова А. А."], None, None],
    [["Программирование", "Лаборатория", "Петров П. П."], ["Программирование", "Лаборатория", "Петров П. П."],
     ["История", DEMO_ROOM, "Смирнова О. О."], None, None],
    [["Базы данных", "Лаборатория", "Орлов О. О."], ["Базы данных", "Лаборатория", "Орлов О. О."], None, None, None],
    [["Математика", DEMO_ROOM, "Иванов И. И."], ["Физкультура", "Спортзал", "Кузнецов К. К."], None, None, None],
    [["Информатика", "Ауд. 202", "Петров П. П."], None, None, None, None],
]
_DEMO_B = [
    [None, ["Алгоритмы", "Ауд. 404", "Орлов О. О."], ["Алгоритмы", "Ауд. 404", "Орлов О. О."], None, None],
    [["Философия", "Ауд. 303", "Смирнова О. О."], None, None, None, None],
    [None, None, ["Математика", DEMO_ROOM, "Иванов И. И."], ["Математика", DEMO_ROOM, "Иванов И. И."], None],
    [None, None, None, None, None],
    [["Программирование", "Лаборатория", "Петров П. П."], None, None, None, None],
]
GROUPS_JSON = json.dumps([
    {"dept": "Колледж", "label": "Группа 1", "days": SCHEDULE_MINE},
    {"dept": "Вуз", "label": "Группа 2", "days": _DEMO_B},
], ensure_ascii=False)

def clone(days):
    return [[list(p) if p else None for p in day] for day in days]

def load_groups():
    out = []
    for g in json.loads(GROUPS_JSON):
        days = clone(g["days"]) + [[None] * 5, [None] * 5]
        out.append({"id": f'{g["dept"]}|{g["label"]}', "dept": g["dept"], "label": g["label"], "days": days})
    return out

GROUPS = load_groups()
GROUP_BY_ID = {g["id"]: g for g in GROUPS}
DEFAULT_MINE_ID = "Колледж|Группа 1"
DEPTS = ["Колледж", "Вуз"]
REAL_DEPTS = ["Колледж", "Вуз"]

# [MOD] Новый стиль интерфейса (Увеличены шрифты и размеры)
def build_style():
    return f"""
QWidget {{ background-color: {C['BG']}; color: {C['INK']};
    font-family: 'Segoe UI Variable Text', 'Segoe UI', 'Noto Sans', 'Helvetica Neue', Arial, sans-serif; font-size: 14px; }}
QMainWindow, QDialog {{ background-color: {C['BG']}; }}
QLabel {{ background: transparent; }}
QFrame#Flat {{ background: transparent; border: none; }}
QToolTip {{ background-color: {C['CARD_HI']}; color: {C['INK']}; border: 1px solid {C['LINE']};
    border-radius: 6px; padding: 5px 8px; }}

#Sidebar {{ background-color: {C['BG_SOFT']}; border: none; border-right: 1px solid {C['LINE']}; }}
QLabel#LogoMark {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C['BLUE']}, stop:1 {C['VIOLET']});
    color: #ffffff; border-radius: 10px; font-size: 15px; font-weight: 700; }}
#Logo {{ font-size: 20px; font-weight: 700; color: {C['INK']}; padding: 0; }}
#LogoSub {{ font-size: 12px; color: {C['MUTED']}; padding: 0 24px 14px 24px; }}
#TopBar {{ background-color: {C['BG']}; border: none; border-bottom: 1px solid {C['LINE']}; }}
QLineEdit#GlobalSearch {{ background-color: {C['FIELD']}; border: 1px solid {C['LINE']}; border-radius: 10px; padding: 8px 14px; color: {C['INK']}; font-size: 13px; }}
QLineEdit#GlobalSearch:focus {{ border-color: {C['TEAL']}; }}
QLabel#TopIcon {{ background-color: {C['CARD']}; color: {C['META']}; border: 1px solid {C['LINE']}; border-radius: 17px; font-size: 17px; }}
QLabel#TopAvatar {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {C['TEAL']},stop:1 {C['VIOLET']}); color: white; border-radius: 17px; font-size: 11px; font-weight: 700; }}
QLabel#TopUser {{ color: {C['INK']}; font-size: 12px; font-weight: 600; padding-left: 2px; }}

QPushButton#NavBtn {{ background: transparent; border: none; color: {C['MUTED']};
    text-align: left; padding: 10px 14px; margin: 2px 8px; border-radius: 10px;
    font-size: 14px; font-weight: 600; }}
QPushButton#NavBtn:hover {{ background-color: {C['CARD']}; color: {C['INK']}; }}
QPushButton#NavBtn[active="true"] {{ background-color: {C['TEAL']}; color: {C['ON_TEAL']}; font-weight: 700; }}

QFrame#UserChip {{ background-color: {C['CARD']}; border: 1px solid {C['LINE']}; border-radius: 14px; }}
QLabel#Avatar {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C['TEAL']}, stop:1 {C['VIOLET']});
    color: #ffffff; border-radius: 18px; font-size: 13px; font-weight: 700; }}
QLabel#UserName {{ font-size: 13px; font-weight: 700; color: {C['INK']}; }}
QLabel#UserGroup {{ font-size: 11px; color: {C['GREEN']}; }}

#PageTitle {{ font-size: 24px; font-weight: 700; color: {C['INK']}; }}
#PageSub {{ font-size: 13px; color: {C['MUTED']}; }}
#Card {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {C['CARD']},stop:1 {C['BG_SOFT']}); border: 1px solid {C['LINE']}; border-radius: 12px; }}
QFrame#Toolbar {{ background-color: {C['CARD']}; border: 1px solid {C['LINE']}; border-radius: 12px; }}
QLabel#WeekLabel {{ font-size: 14px; font-weight: 600; color: {C['INK']}; padding: 0 10px; }}
QLabel#GroupLabel {{ font-size: 16px; font-weight: 700; color: {C['INK']}; }}

#DeptBtn {{ background-color: {C['CARD']}; border: 1px solid {C['LINE']};
    border-radius: 11px; padding: 9px 20px; color: {C['INK']}; font-weight: 600; font-size: 14px; }}
#DeptBtn:hover {{ border-color: {C['TEAL']}; }}
#DeptBtnOn {{ background-color: {C['TEAL']}; border: 1px solid {C['TEAL']};
    border-radius: 11px; padding: 9px 20px; color: {C['ON_TEAL']}; font-weight: 700; font-size: 14px; }}
#Chip {{ background-color: {C['CARD']}; border: 1px solid {C['LINE']};
    border-radius: 15px; padding: 6px 16px; color: {C['META']}; font-size: 13px; font-weight: 600; }}
#Chip:hover {{ border-color: {C['TEAL']}; }}
#ChipOn {{ background-color: {C['TEAL_SOFT']}; border: 1px solid {C['TEAL']};
    border-radius: 15px; padding: 6px 16px; color: {C['TEAL']}; font-size: 13px; font-weight: 700; }}

#DayHead {{ background-color: {C['CARD']}; border: 1px solid {C['LINE']};
    border-radius: 10px; color: {C['MUTED']}; font-weight: 600; padding: 8px 4px; font-size: 13px; }}
#DayHeadToday {{ background-color: {C['TEAL']}; border: 1px solid {C['TEAL']};
    border-radius: 10px; color: {C['ON_TEAL']}; font-weight: 700; padding: 8px 4px; font-size: 13px; }}
#SlotHead {{ background-color: {C['CARD']}; border: 1px solid {C['LINE']}; color: {C['MUTED']};
    border-radius: 10px; font-weight: 600; padding: 6px 2px; font-size: 12px; }}

#PairCard {{ background-color: {C['CARD']}; border: 1px solid {C['LINE']}; border-radius: 12px; }}
#PairCard:hover {{ background-color: {C['CARD_HI']}; border: 1px solid {C['TEAL']}; }}
#PairCardNow {{ background-color: {C['TEAL_SOFT']}; border: 2px solid {C['TEAL']}; border-radius: 12px; }}
#PairEmpty {{ background: transparent; border: 1px dashed {C['LINE']}; border-radius: 12px; }}
#PairEmpty:hover {{ border: 1px dashed {C['TEAL']}; }}
#PairTime {{ font-size: 12px; font-weight: 600; color: {C['TEAL']}; background: transparent; }}
#PairSubject {{ font-size: 13px; font-weight: 700; color: {C['INK']}; background: transparent; padding: 0; }}
#PairMeta {{ font-size: 12px; color: {C['META']}; background: transparent; }}
QLabel#SubjTile {{ border-radius: 8px; color: #ffffff; font-size: 14px; font-weight: 700; }}
QLabel#IconTile {{ border-radius: 11px; }}
QToolButton#AddBtn {{ color: {C['FAINT']}; font-size: 20px; background: transparent; border: none; }}
QToolButton#AddBtn:hover {{ color: {C['TEAL']}; }}
#Badge {{ background-color: {C['TEAL_SOFT']}; color: {C['TEAL']}; border-radius: 10px;
    padding: 6px 14px; font-size: 13px; font-weight: 600; }}

QPushButton {{ background-color: {C['CARD']}; color: {C['INK']}; border: 1px solid {C['LINE']};
    border-radius: 10px; padding: 9px 18px; font-size: 14px; }}
QPushButton:hover {{ border-color: {C['TEAL']}; background-color: {C['CARD_HI']}; }}
QPushButton:pressed {{ background-color: {C['TEAL_SOFT']}; }}
QPushButton:disabled {{ color: {C['FAINT']}; border-color: {C['LINE']}; }}
QPushButton#Primary {{ background-color: {C['TEAL']}; color: {C['ON_TEAL']};
    border: 1px solid {C['TEAL']}; border-radius: 10px; padding: 9px 20px; font-weight: 700; font-size: 14px; }}
QPushButton#Primary:hover {{ background-color: {C['TEAL_HOVER']}; border-color: {C['TEAL_HOVER']}; }}
QPushButton#Accent {{ background-color: {C['TEAL_SOFT']}; color: {C['TEAL']};
    border: 1px solid {C['TEAL']}; border-radius: 10px; padding: 9px 20px; font-weight: 700; font-size: 14px; }}
QPushButton#Accent:hover {{ background-color: {C['TEAL']}; color: {C['ON_TEAL']}; }}
QPushButton#Ghost {{ background: transparent; color: {C['INK']};
    border: 1px solid {C['LINE']}; border-radius: 10px; padding: 8px 16px; font-size: 14px; }}
QPushButton#Ghost:hover {{ background-color: {C['CARD_HI']}; border-color: {C['TEAL']}; }}
QPushButton#Danger {{ background: transparent; color: {C['DANGER']};
    border: 1px solid {C['LINE']}; border-radius: 10px; padding: 8px 16px; font-size: 14px; }}
QPushButton#Danger:hover {{ background-color: {C['DANGER_SOFT']}; border-color: {C['DANGER']}; }}
QPushButton#Link {{ background: transparent; border: none; color: {C['TEAL']}; padding: 0; font-size: 12px; font-weight: 600; }}
QPushButton#Link:hover {{ color: {C['INK']}; background: transparent; }}

QLineEdit, QTextEdit, QComboBox {{ background-color: {C['FIELD']};
    border: 1px solid {C['LINE']}; border-radius: 10px; padding: 9px 14px; color: {C['INK']};
    font-size: 14px; selection-background-color: {C['TEAL']}; selection-color: {C['ON_TEAL']}; }}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{ border: 1px solid {C['TEAL']}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox QAbstractItemView {{ background-color: {C['CARD']}; color: {C['INK']};
    border: 1px solid {C['LINE']}; selection-background-color: {C['TEAL_SOFT']};
    selection-color: {C['TEAL']}; outline: 0; padding: 4px; }}

QTableWidget {{ background-color: {C['CARD']}; border: 1px solid {C['LINE']};
    border-radius: 12px; gridline-color: {C['LINE']}; color: {C['INK']}; font-size: 14px; }}
QTableWidget::item {{ padding: 6px 10px; border-bottom: 1px solid {C['LINE']}; }}
QTableWidget::item:selected {{ background-color: {C['TEAL_SOFT']}; color: {C['INK']}; }}
QHeaderView::section {{ background-color: {C['BG_SOFT']}; color: {C['MUTED']};
    border: none; border-bottom: 1px solid {C['LINE']}; padding: 12px;
    font-weight: 600; font-size: 13px; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {C['LINE']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {C['TEAL']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {C['LINE']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {C['TEAL']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QFrame#HomeTile {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {C['CARD']},stop:1 {C['BG_SOFT']}); border: 1px solid {C['LINE']}; border-radius: 12px; }}
QFrame#HomeTile:hover {{ border: 1px solid {C['TEAL']}; background-color: {C['CARD_HI']}; }}
QLabel#HomeTileCap {{ font-size: 12px; color: {C['MUTED']}; font-weight: 600; }}
QLabel#HomeTileNum {{ font-size: 24px; font-weight: 700; color: {C['INK']}; }}
QLabel#HomeTileHint {{ font-size: 12px; color: {C['DANGER']}; font-weight: 600; }}
QLabel#DatePill {{ background-color: {C['CARD']}; border: 1px solid {C['LINE']}; border-radius: 10px;
    padding: 8px 14px; color: {C['META']}; font-size: 13px; }}
QLabel#SectionTitle {{ font-size: 16px; font-weight: 700; color: {C['INK']}; }}
QFrame#HomeRow {{ background: transparent; border: none; border-bottom: 1px solid {C['LINE']}; }}
QLabel#RowTitle {{ font-size: 13px; font-weight: 600; color: {C['INK']}; }}
QLabel#RowSub {{ font-size: 12px; color: {C['MUTED']}; }}
QLabel#RowTime {{ font-size: 13px; font-weight: 600; color: {C['META']}; }}
QFrame#Banner {{ border: 1px solid {C['LINE']}; border-radius: 12px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10275a, stop:0.48 {C['VIOLET_SOFT']}, stop:1 {C['CARD']}); }}
QLabel#BannerTitle {{ font-size: 17px; font-weight: 700; color: {C['INK']}; }}
QLabel#BannerSub {{ font-size: 13px; color: {C['META']}; }}

QFrame#StatTile {{ background-color: {C['CARD']}; border: 1px solid {C['LINE']}; border-radius: 14px; }}
QFrame#StatTile:hover {{ border: 1px solid {C['TEAL']}; }}
QFrame#StatTile[on="true"] {{ background-color: {C['TEAL_SOFT']}; border: 1px solid {C['TEAL']}; }}
QLabel#StatNum {{ font-size: 30px; font-weight: 700; color: {C['INK']}; }}
QLabel#StatCap {{ font-size: 13px; color: {C['MUTED']}; font-weight: 600; }}
QLabel#StatNum[state="todo"] {{ color: {C['BLUE']}; }}
QLabel#StatNum[state="overdue"] {{ color: {C['DANGER']}; }}
QLabel#StatNum[state="review"] {{ color: {C['ORANGE']}; }}
QLabel#StatNum[state="checked"] {{ color: {C['GREEN']}; }}
QLabel#StatNum[state="all"] {{ color: {C['VIOLET']}; }}

QFrame#HwCard {{ background-color: {C['CARD']}; border: 1px solid {C['LINE']}; border-radius: 14px; }}
QLabel#HwSubject {{ font-size: 13px; font-weight: 600; color: {C['TEAL']}; }}
QLabel#HwTheme {{ font-size: 17px; font-weight: 700; color: {C['INK']}; }}
QLabel#HwDesc {{ font-size: 14px; color: {C['META']}; }}
QLabel#HwMeta {{ font-size: 13px; color: {C['MUTED']}; }}
QLabel#Pill {{ border-radius: 9px; padding: 3px 12px; font-size: 12px; font-weight: 600;
    background-color: {C['CARD_HI']}; color: {C['MUTED']}; }}
QLabel#Pill[state="todo"] {{ background-color: {C['BLUE_SOFT']}; color: {C['BLUE']}; }}
QLabel#Pill[state="overdue"] {{ background-color: {C['DANGER_SOFT']}; color: {C['DANGER']}; }}
QLabel#Pill[state="review"] {{ background-color: {C['ORANGE_SOFT']}; color: {C['ORANGE']}; }}
QLabel#Pill[state="checked"] {{ background-color: {C['GREEN_SOFT']}; color: {C['GREEN']}; }}
QLabel#MarkBadge {{ border-radius: 9px; padding: 3px 12px; font-size: 12px; font-weight: 600;
    background-color: {C['YELLOW_SOFT']}; color: {C['YELLOW']}; }}
QLabel#HwDue[state="todo"] {{ color: {C['BLUE']}; font-weight: 600; }}
QLabel#HwDue[state="overdue"] {{ color: {C['DANGER']}; font-weight: 600; }}
QFrame#HwReview {{ background-color: {C['BG_SOFT']}; border: 1px solid {C['LINE']}; border-radius: 10px; }}
QLabel#HwReviewText {{ font-size: 13px; color: {C['INK']}; }}
QLabel#HwEmpty {{ font-size: 15px; color: {C['MUTED']}; padding: 40px; }}

QToolButton#GearBtn {{ background-color: {C['CARD']}; border: 1px solid {C['LINE']}; border-radius: 10px; padding: 8px; }}
QToolButton#GearBtn:hover {{ border-color: {C['TEAL']}; background-color: {C['CARD_HI']}; }}
QPushButton#SegBtn {{ background-color: transparent; border: 1px solid {C['LINE']}; border-radius: 12px;
    padding: 8px 18px; color: {C['META']}; font-size: 13px; font-weight: 600; }}
QPushButton#SegBtn:hover {{ border-color: {C['TEAL']}; color: {C['INK']}; background-color: {C['CARD']}; }}
QPushButton#SegBtn[on="true"] {{ background-color: {C['TEAL']}; border: 1px solid {C['TEAL']}; color: {C['ON_TEAL']}; font-weight: 700; }}
QLabel#ProfAvatar {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C['TEAL']}, stop:1 {C['VIOLET']});
    color: #ffffff; border-radius: 42px; font-size: 30px; font-weight: 700; }}
QLabel#ProfName {{ font-size: 20px; font-weight: 700; color: {C['INK']}; }}
QFrame#SettingRow {{ background: transparent; border: none; border-bottom: 1px solid {C['LINE']}; border-radius: 0px; }}
QFrame#SettingRow:hover {{ background-color: {C['CARD_HI']}; }}

QFrame#SupportHero {{ border: 1px solid {C['LINE']}; border-radius: 20px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C['TEAL_SOFT']}, stop:1 {C['CARD']}); }}
QLabel#SupportHead {{ font-size: 26px; font-weight: 700; color: {C['INK']}; }}
QLabel#SupportText {{ font-size: 15px; color: {C['META']}; }}
QPushButton#SupportBtn {{ color: {C['ON_TEAL']}; border: none; border-radius: 12px;
    padding: 14px 36px; font-size: 15px; font-weight: 700;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {C['TEAL']}, stop:1 {C['VIOLET']}); }}
QFrame#SupportTile {{ background-color: {C['CARD']}; border: 1px solid {C['LINE']}; border-radius: 14px; }}
QLabel#SupportTileTitle {{ font-size: 15px; font-weight: 600; color: {C['VIOLET']}; }}
QLabel#SupportTileText {{ font-size: 13px; color: {C['META']}; }}
"""


# ### --- ИКОНКИ --- ###
def make_pixmap(kind, color, size=20):
    sc = 2
    pm = QPixmap(size * sc, size * sc); pm.fill(Qt.transparent); pm.setDevicePixelRatio(sc)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    k = size / 20.0
    pen = QPen(QColor(color)); pen.setWidthF(1.7 * k)
    pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen); p.setBrush(Qt.NoBrush)
    P = lambda x, y: QPointF(x * k, y * k)
    R = lambda x, y, w, h: QRectF(x * k, y * k, w * k, h * k)
    ln = lambda a, b, c, d: p.drawLine(P(a, b), P(c, d))
    if kind == "home":
        p.drawPolyline(QPolygonF([P(3, 10), P(10, 3.5), P(17, 10)]))
        p.drawPolyline(QPolygonF([P(5, 9), P(5, 16.5), P(15, 16.5), P(15, 9)]))
    elif kind == "calendar":
        p.drawRoundedRect(R(3, 4.5, 14, 12.5), 3 * k, 3 * k)
        ln(3, 8.5, 17, 8.5); ln(7, 3, 7, 6); ln(13, 3, 13, 6)
    elif kind == "hw":
        p.drawRoundedRect(R(4.5, 3, 11, 14), 2.5 * k, 2.5 * k)
        ln(7.5, 7.5, 12.5, 7.5); ln(7.5, 10.5, 12.5, 10.5); ln(7.5, 13.5, 10.5, 13.5)
    elif kind == "grades":
        ln(5.5, 16, 5.5, 11); ln(10, 16, 10, 5); ln(14.5, 16, 14.5, 8.5)
    elif kind == "profile":
        p.drawEllipse(R(7, 3.5, 6, 6))
        p.drawArc(R(4, 11.5, 12, 10), 0, 180 * 16)
    elif kind == "support":
        p.drawRoundedRect(R(3, 4, 14, 10), 3 * k, 3 * k)
        p.drawPolyline(QPolygonF([P(7, 14), P(7, 17.5), P(10.5, 14)]))
    elif kind == "donate":
        p.drawRoundedRect(R(3.5, 8, 13, 9), 2 * k, 2 * k)
        ln(3.5, 11.5, 16.5, 11.5); ln(10, 8, 10, 17)
        p.drawArc(R(5.5, 3.5, 4.5, 4.5), 0, 270 * 16); p.drawArc(R(10, 3.5, 4.5, 4.5), -90 * 16, 270 * 16)
    elif kind == "settings":
        p.drawEllipse(R(6.8, 6.8, 6.4, 6.4))
        for n in range(8):
            ang = math.radians(n * 45)
            ln(10 + 5.4 * math.cos(ang), 10 + 5.4 * math.sin(ang),
               10 + 7.6 * math.cos(ang), 10 + 7.6 * math.sin(ang))
    elif kind == "trophy":
        p.drawPolygon(QPolygonF([P(6, 3.5), P(14, 3.5), P(14, 8), P(10, 12), P(6, 8)]))
        p.drawArc(R(2.5, 4.5, 4, 4), 90 * 16, 180 * 16); p.drawArc(R(13.5, 4.5, 4, 4), -90 * 16, 180 * 16)
        ln(10, 12, 10, 15); ln(6.5, 16.5, 13.5, 16.5)
    elif kind == "cap":
        p.drawPolygon(QPolygonF([P(10, 4), P(18, 8), P(10, 12), P(2, 8)]))
        p.drawPolyline(QPolygonF([P(5.5, 10.5), P(5.5, 14), P(10, 16), P(14.5, 14), P(14.5, 10.5)]))
        ln(18, 8, 18, 13)
    elif kind == "chevron":
        p.drawPolyline(QPolygonF([P(7.5, 5), P(12.5, 10), P(7.5, 15)]))
    elif kind == "users":
        p.drawEllipse(R(4.5, 4, 5, 5)); p.drawArc(R(2.5, 11.5, 9, 9), 0, 180 * 16)
        p.drawEllipse(R(11.5, 5.5, 3.6, 3.6)); p.drawArc(R(11, 12, 6.5, 7), 0, 180 * 16)
    elif kind == "layers":
        p.drawPolygon(QPolygonF([P(10, 3.5), P(17, 7), P(10, 10.5), P(3, 7)]))
        p.drawPolyline(QPolygonF([P(3, 10.5), P(10, 14), P(17, 10.5)]))
        p.drawPolyline(QPolygonF([P(3, 13.5), P(10, 17), P(17, 13.5)]))
    elif kind == "star":
        pts = []
        for n in range(10):
            ang = math.radians(-90 + n * 36); rad = 7.2 if n % 2 == 0 else 3.1
            pts.append(P(10 + rad * math.cos(ang), 10.5 + rad * math.sin(ang)))
        p.drawPolygon(QPolygonF(pts))
    elif kind == "palette":
        p.drawEllipse(R(3.5, 3.5, 13, 13))
        for dx, dy in ((7, 7.5), (11.5, 7), (12.5, 11.5)): p.drawPoint(P(dx, dy))
    elif kind == "globe":
        p.drawEllipse(R(3.5, 3.5, 13, 13)); ln(3.5, 10, 16.5, 10); p.drawEllipse(R(7, 3.5, 6, 13))
    else:
        p.drawEllipse(R(4, 4, 12, 12))
    p.end()
    return pm

def make_icon(kind, color, size=20):
    return QIcon(make_pixmap(kind, color, size))

def icon_tile(kind, key, size=44, icon=22):
    """Цветная плитка с иконкой."""
    lbl = QLabel(); lbl.setObjectName("IconTile"); lbl.setFixedSize(size, size)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(f"background-color:{C[key + '_SOFT']};border:1px solid {C[key]};")
    lbl.setPixmap(make_pixmap(kind, C[key], icon))
    return lbl

def letter_tile(name, size=34, font_px=15):
    lbl = QLabel((name or "?").strip()[:1].upper()); lbl.setObjectName("SubjTile")
    lbl.setFixedSize(size, size); lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(f"background-color:{_subject_color(name)};font-size:{font_px}px;")
    return lbl

def _rgba(hexcol, a):
    h = hexcol.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{int(a * 255)})"


# ### --- СЕКЦИЯ API --- ###
class ApiBridge(QObject):
    logged_in = Signal(dict)
    login_failed = Signal(str)
    schedule_loaded = Signal(list)
    homework_loaded = Signal(list, str)
    profile_loaded = Signal(dict)
    support_sent = Signal(bool, str)
    upload_done = Signal(bool, str)
    delete_done = Signal(bool, str)
    grades_loaded = Signal(dict)

    def __init__(self):
        super().__init__()
        self._client = None
        self._ctx = None
        self._refresh_lock = None
        self.auth_data = load_json(AUTH_FILE, {})

    def is_logged_in(self):
        return bool(self.auth_data.get("refresh_token")) and HAS_API and HAS_QASYNC

    async def _get_client(self):
        if self._client is not None:
            return self._client
        self._ctx = TopAcademyClient()
        self._client = await self._ctx.__aenter__()
        return self._client

    async def _close_client(self):
        if self._ctx is not None:
            try:
                await self._ctx.__aexit__(None, None, None)
            except Exception:
                pass
        self._client = None
        self._ctx = None

    async def login(self, username: str, password: str):
        if not HAS_API:
            self.login_failed.emit(t("login_no_api")); return
        if not HAS_QASYNC:
            self.login_failed.emit(t("login_no_qasync")); return
        try:
            client = await self._get_client()
            await client.auth.login(username, password)
            a = client.auth.model
            self.auth_data = {
                "access_token": a.access_token,
                "refresh_token": a.refresh_token,
                "expires_in_access": a.expires_in_access,
                "expires_in_refresh": a.expires_in_refresh,
            }
            save_json(AUTH_FILE, self.auth_data)
            info = await client.user.get_info()
            prof = info.model_dump() if hasattr(info, "model_dump") else dict(info)
            save_json(PROFILE_CACHE, prof)
            self.logged_in.emit(prof)
        except Exception as e:
            log_error(f"login: {e}")
            self.login_failed.emit(str(e))

    async def try_refresh(self):
        if not self.auth_data.get("refresh_token"):
            return False
        try:
            await self._close_client()
            client = await self._get_client()
            await client.auth.refresh(self.auth_data["refresh_token"])
            a = client.auth.model
            self.auth_data.update({
                "access_token": a.access_token,
                "refresh_token": a.refresh_token,
                "expires_in_access": a.expires_in_access,
                "expires_in_refresh": a.expires_in_refresh,
            })
            save_json(AUTH_FILE, self.auth_data)
            return True
        except Exception as e:
            log_error(f"refresh: {describe_exc(e)}")
            return False

    async def logout(self):
        try:
            client = await self._get_client()
            await client.auth.logout()
        except Exception:
            pass
        self.auth_data = {}
        save_json(AUTH_FILE, {})
        await self._close_client()

    async def load_schedule_month(self, date_str: str):
        try:
            client = await self._get_client()
            data = await client.schedule.get_schedule_month(date_str)
            items = [x.model_dump() if hasattr(x, "model_dump") else dict(x) for x in data]
            save_json(SCHEDULE_CACHE, items)
            self.schedule_loaded.emit(items)
        except Exception as e:
            log_error(f"schedule: {e}")
            self.schedule_loaded.emit(load_json(SCHEDULE_CACHE, []))

    async def _refresh_locked(self):
        if self._refresh_lock is None:
            self._refresh_lock = asyncio.Lock()
        async with self._refresh_lock:
            return await self.try_refresh()

    async def _throttled_get(self, client, path, params=None):
        """GET с ограничением скорости: запросы идут строго по одному с паузой между ними.
        После HTTP 429 общая «пауза» действует на все запросы сразу, повтор — с растущим ожиданием."""
        import time
        if getattr(self, "_hw_sem", None) is None:
            self._hw_sem = asyncio.Semaphore(1)
            self._hw_block_until = 0.0
        delay = 3.0
        resp = None
        for attempt in range(5):
            async with self._hw_sem:
                wait = self._hw_block_until - time.monotonic()
                if wait > 0: await asyncio.sleep(wait)
                resp = await client._client.get(path, params=params)
                await asyncio.sleep(0.6)
                if resp.status_code != 429:
                    return resp
                try: ra = float(resp.headers.get("Retry-After") or 0)
                except ValueError: ra = 0
                pause = min(max(ra, delay), 40)
                self._hw_block_until = time.monotonic() + pause
            delay *= 2
        return resp

    async def _hw_list(self, client, status, group_id=None, known=None):
        """Все страницы одного статуса. Не полагаемся на размер страницы:
        идём, пока сервер отдаёт новые записи."""
        items, seen = [], set()
        for page in range(1, 61):
            params = {"page": page, "status": status, "type": 0}
            if group_id is not None:
                params["group_id"] = group_id
            resp = await self._throttled_get(client, "/homework/operations/list", params)
            if resp.is_error:
                # ошибка на любой странице = неполный список: сообщаем, а не молча обрезаем
                raise RuntimeError(f"HTTP {resp.status_code}: {(resp.text or '').strip()[:200]}")
            data = resp.json()
            if not isinstance(data, list) or not data:
                break
            fresh = [d for d in data if isinstance(d, dict) and d.get("id") not in seen]
            if not fresh:
                break
            for d in fresh:
                seen.add(d.get("id"))
            items.extend(fresh)
            # проверенные работы не меняются: если вся страница уже есть в кэше, дальше листать незачем
            if known and status == 1 and all(d.get("id") in known for d in fresh):
                self._hw_early = True
                break
        return items

    async def _hw_statuses(self, client):
        """Базовые статусы 0-3 плюс любые, по которым счётчик сервера не пуст."""
        statuses = {0, 1, 2, 3}
        try:
            resp = await self._throttled_get(client, "/count/homework")
            if not resp.is_error:
                for c in resp.json() or []:
                    if isinstance(c, dict) and (c.get("counter") or 0) > 0 and isinstance(c.get("counter_type"), int):
                        statuses.add(c["counter_type"])
        except Exception as e:
            log_error(f"homework counters: {describe_exc(e)}")
        return sorted(statuses)

    async def _hw_group_ids(self, client):
        """Все группы пользователя: из профиля и из истории групп журнала."""
        ids = []
        def add(v):
            if isinstance(v, int) and not isinstance(v, bool) and v > 0 and v not in ids:
                ids.append(v)
        prof = load_json(PROFILE_CACHE, {})
        add(prof.get("current_group_id"))
        for g in prof.get("groups") or []:
            if isinstance(g, dict): add(g.get("id"))
        try:
            hist = await client.homework.get_group_history()
            log_error(f"info homework group-history: {str(hist)[:300]}")
            for g in hist or []:
                if isinstance(g, dict):
                    for k in ("group_id", "id_group", "id_grp", "groupId", "id"):
                        if isinstance(g.get(k), int):
                            add(g[k]); break
                else:
                    add(g)
        except Exception as e:
            log_error(f"homework group history: {describe_exc(e)}")
        return ids

    async def _fetch_homework(self, client, parallel):
        statuses = await self._hw_statuses(client)
        groups = await self._hw_group_ids(client)
        known = {d.get("id") for d in load_json(HW_CACHE, []) if isinstance(d, dict) and d.get("id")}
        cur = load_json(PROFILE_CACHE, {}).get("current_group_id")
        # текущая группа уже покрыта запросом без group_id — повторно её не качаем
        groups = [g for g in groups if g != cur]
        async def fetch(st, gid=None):
            try:
                return await self._hw_list(client, st, gid, known), None
            except Exception as e:
                log_error(f"homework status={st} group={gid}: {describe_exc(e)}")
                # ошибки по отдельным группам не считаем сбоем загрузки
                return [], (f"status={st}: {e}" if gid is None else None)
        self._hw_early = False
        results = list(await asyncio.gather(*[fetch(st) for st in statuses]))
        extra = [fetch(st, gid) for gid in groups for st in statuses]
        if extra:
            results += list(await asyncio.gather(*extra))
        # base_n возвращаем явно: общий атрибут перетирался параллельной загрузкой
        return results, len(statuses)

    async def load_homework(self):
        # Несколько загрузок могут идти одновременно (кнопка «Обновить», страница «Оценки»,
        # перезагрузка после сдачи/удаления). Раньше более медленная старая загрузка
        # приходила последней и затирала свежие данные (например, возвращала удалённый черновик).
        # Теперь результат принимается только от самой новой загрузки.
        self._hw_gen = getattr(self, "_hw_gen", 0) + 1
        gen = self._hw_gen
        def emit(items, err):
            if gen == self._hw_gen:
                self.homework_loaded.emit(items, err)
        try:
            client = await self._get_client()
            results, base_n = await asyncio.wait_for(self._fetch_homework(client, parallel=False), 120)
            base = results[:base_n]
            if all(err for _, err in base) and not any("HTTP 401" in e for _, e in base):
                if all("HTTP 429" in e for _, e in base):
                    msg = "Журнал ограничил частоту запросов. Подожди минуту и нажми «Обновить» — показаны сохранённые данные"
                else:
                    msg = t("hw_err") + ": " + base[0][1][:200]
                emit(load_json(HW_CACHE, []), msg)
                return
            if all(err for _, err in base):
                await self._refresh_locked()
                client = await self._get_client()
                results, base_n = await asyncio.wait_for(self._fetch_homework(client, parallel=False), 120)
                base = results[:base_n]
                if all(err for _, err in base):
                    emit(load_json(HW_CACHE, []), t("hw_session"))
                    return

            all_items, seen, errs = [], set(), []
            for items, err in results:
                if err: errs.append(err)
                for d in items:
                    hid = d.get("id")
                    if hid and hid not in seen:
                        seen.add(hid); all_items.append(d)
            if errs or getattr(self, "_hw_early", False):
                # часть статусов не загрузилась или список проверенных остановлен на уже известных —
                # не теряем ранее сохранённые задания
                for d in load_json(HW_CACHE, []):
                    hid = d.get("id")
                    if hid and hid not in seen:
                        seen.add(hid); all_items.append(d)
            all_items.sort(key=lambda x: (x.get("completion_time") or ""), reverse=False)
            try:
                _rt = lambda d: any(str(d.get(k) or "").lstrip().startswith("{\\rtf") for k in ("comment", "homework_comment", "theme"))
                log_error(f"hw-diag total={len(all_items)} comment={sum(1 for d in all_items if d.get('comment'))} "
                          f"homework_comment={sum(1 for d in all_items if d.get('homework_comment'))} "
                          f"rtf_like={sum(1 for d in all_items if _rt(d))} file_path={sum(1 for d in all_items if d.get('file_path'))}")
            except Exception: pass
            if gen == self._hw_gen:
                save_json(HW_CACHE, all_items)
                if not errs:
                    import time; self._hw_last_ok = time.time()
            emit(all_items, f"{t('hw_partial')} ({len(errs)})" if errs else "")
        except Exception as e:
            log_error(f"homework: {e}")
            if isinstance(e, asyncio.TimeoutError): e = "превышено время ожидания журнала"
            emit(load_json(HW_CACHE, []), f"{t('hw_err')}: {e}")

    async def upload_homework(self, homework_id: int, file_path: str, answer_text: str = "",
                              spent_hours: str = "00", spent_minutes: str = "00"):
        try:
            if not (5 <= len((answer_text or "").strip()) <= 500):
                raise ValueError("комментарий должен быть от 5 до 500 символов")
            client = await self._get_client()
            args = dict(
                id_=homework_id,
                file_path=file_path if file_path else None,
                answer_text=answer_text or None,
                spent_hours=spent_hours,
                spent_minutes=spent_minutes,
            )
            try:
                await client.homework.create_homework(**args)
            except Exception:
                if not await self._refresh_locked(): raise
                client = await self._get_client()
                await client.homework.create_homework(**args)
            self.upload_done.emit(True, t("sent"))
        except Exception as e:
            log_error(f"upload: {e}")
            self.upload_done.emit(False, f"{t('send_error')}: {e}")

    async def delete_homework(self, stud_id: int):
        """Удалить сданный черновик ДЗ."""
        try:
            client = await self._get_client()
            try:
                await client.homework.delete_homework(stud_id)
            except Exception:
                if not await self._refresh_locked(): raise
                client = await self._get_client()
                await client.homework.delete_homework(stud_id)
            self.delete_done.emit(True, "Черновик удалён")
        except Exception as e:
            log_error(f"delete_homework: {e}")
            self.delete_done.emit(False, f"Ошибка: {e}")

    async def load_grades(self):
        out = {"errors": []}
        calls = (
            ("group", "/dashboard/progress/leader-group"),
            ("group_pts", "/dashboard/progress/leader-group-points"),
            ("visits", "/progress/operations/student-visits"),
            ("avg", "/dashboard/chart/average-progress"),
            ("attendance", "/dashboard/chart/attendance"),
        )
        try:
            import time
            if time.time() - getattr(self, "_hw_last_ok", 0) > 60:
                await self.load_homework()
            for attempt in (1, 2):
                client = await self._get_client()
                out = {"errors": []}
                for key, path in calls:
                    try:
                        resp = await client._client.get(path)
                        if resp.is_error: raise RuntimeError(f"HTTP {resp.status_code}")
                        out[key] = resp.json()
                    except Exception as e:
                        out["errors"].append(f"{key}: {e}")
                if attempt == 1 and len(out["errors"]) == len(calls) and all("HTTP 401" in e for e in out["errors"]):
                    await self._refresh_locked()
                    continue
                break
            save_json(GRADES_CACHE, out)
        except Exception as e:
            out = load_json(GRADES_CACHE, {})
            out["errors"] = [str(e)]
        self.grades_loaded.emit(out)

    async def load_profile(self):
        """Обновить данные профиля из журнала."""
        try:
            client = await self._get_client()
            try:
                info = await client.user.get_info()
            except Exception:
                if not await self._refresh_locked(): raise
                client = await self._get_client()
                info = await client.user.get_info()
            prof = info.model_dump() if hasattr(info, "model_dump") else dict(info)
            save_json(PROFILE_CACHE, prof)
            self.profile_loaded.emit(prof)
        except Exception as e:
            log_error(f"profile: {describe_exc(e)}")
            self.profile_loaded.emit(load_json(PROFILE_CACHE, {}))

    async def send_support(self, subject: str, text: str):
        try:
            client = await self._get_client()
            await client.signal.create({"subject": subject, "message": text})
            self.support_sent.emit(True, t("sup_sent"))
        except Exception as e:
            log_error(f"support: {e}")
            self.support_sent.emit(False, f"{t('sup_error')}: {e}")

# ### --- СЕКЦИЯ ДИАЛОГОВ --- ###
class PairDialog(QDialog):
    def __init__(self, parent, day_idx, slot_idx, existing=None, group_title=""):
        super().__init__(parent)
        self.setWindowTitle("Изменить пару" if existing else "Добавить пару")
        self.setMinimumWidth(460)
        self.setStyleSheet(build_style())
        self.deleted = False
        outer = QVBoxLayout(self)
        title = QLabel("Изменить пару" if existing else "Добавить пару")
        title.setStyleSheet(f"font-size:17px;font-weight:600;color:{C['INK']};")
        outer.addWidget(title)
        sub = QLabel(f"Группа: {group_title}")
        sub.setStyleSheet(f"color:{C['MUTED']};font-size:11px;")
        outer.addWidget(sub)
        card = QFrame(); card.setObjectName("Card"); outer.addWidget(card)
        form = QFormLayout(card)
        form.setContentsMargins(14, 12, 14, 12); form.setSpacing(8)
        self.day_combo = QComboBox(); self.day_combo.addItems(DAYS)
        self.day_combo.setCurrentIndex(day_idx); form.addRow("День", self.day_combo)
        self.slot_combo = QComboBox()
        self.slot_combo.addItems([f"{i+1} пара · {a}–{b}" for i, (a, b) in enumerate(SLOTS)])
        self.slot_combo.setCurrentIndex(slot_idx); form.addRow("Пара", self.slot_combo)
        self.subject = QLineEdit(existing[0] if existing else "")
        self.subject.setPlaceholderText("Например: Математика"); form.addRow("Предмет", self.subject)
        self.room = QLineEdit(existing[1] if existing else "")
        self.room.setPlaceholderText("Ауд. 101"); form.addRow("Аудитория", self.room)
        self.teacher = QLineEdit(existing[2] if existing else "")
        self.teacher.setPlaceholderText("Иванов Иван"); form.addRow("Преподаватель", self.teacher)
        btns = QDialogButtonBox()
        save = btns.addButton("Сохранить", QDialogButtonBox.AcceptRole)
        save.setObjectName("Primary")
        btns.addButton("Отмена", QDialogButtonBox.RejectRole).setObjectName("Ghost")
        if existing:
            d = btns.addButton("Удалить", QDialogButtonBox.DestructiveRole)
            d.setObjectName("Danger"); d.clicked.connect(self._delete)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        outer.addWidget(btns)

    def _delete(self):
        self.deleted = True; self.accept()

    def values(self):
        return (self.day_combo.currentIndex(), self.slot_combo.currentIndex(),
                self.subject.text().strip(), self.room.text().strip(),
                self.teacher.text().strip())

class RegisterDialog(QDialog):
    def __init__(self, parent, current_gid):
        super().__init__(parent)
        self.setWindowTitle("Сменить группу")
        self.setMinimumWidth(560)
        self.setStyleSheet(build_style())
        self.gid = current_gid
        self.dept = GROUP_BY_ID[current_gid]["dept"]
        outer = QVBoxLayout(self)
        title = QLabel("Сменить группу")
        title.setStyleSheet(f"font-size:19px;font-weight:600;color:{C['INK']};")
        outer.addWidget(title)
        card = QFrame(); card.setObjectName("Card"); outer.addWidget(card)
        form = QVBoxLayout(card); form.setContentsMargins(14, 12, 14, 12); form.setSpacing(8)
        form.addWidget(QLabel("Отделение"))
        row = QHBoxLayout(); self.dept_btns = {}
        for d in REAL_DEPTS:
            b = QPushButton(d); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _, d=d: self.pick_dept(d))
            row.addWidget(b); self.dept_btns[d] = b
        row.addStretch(); form.addLayout(row)
        form.addWidget(QLabel("Группа"))
        self.chips_holder = QWidget()
        self.chips_layout = QGridLayout(self.chips_holder)
        form.addWidget(self.chips_holder)
        self.chosen = QLabel("")
        self.chosen.setStyleSheet(f"color:{C['TEAL']};font-weight:600;font-size:12px;")
        form.addWidget(self.chosen)
        btns = QDialogButtonBox()
        ok = btns.addButton("Сохранить", QDialogButtonBox.AcceptRole)
        ok.setObjectName("Primary")
        btns.addButton("Отмена", QDialogButtonBox.RejectRole).setObjectName("Ghost")
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        outer.addWidget(btns)
        self.render()

    def pick_dept(self, d):
        self.dept = d
        if GROUP_BY_ID[self.gid]["dept"] != d:
            self.gid = next(g["id"] for g in GROUPS if g["dept"] == d)
        self.render()

    def pick_group(self, gid):
        self.gid = gid; self.render()

    def render(self):
        for d, b in self.dept_btns.items():
            on = d == self.dept
            b.setObjectName("DeptBtnOn" if on else "DeptBtn")
            b.setStyleSheet(build_style()); b.style().unpolish(b); b.style().polish(b)
        while self.chips_layout.count():
            it = self.chips_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        groups = [g for g in GROUPS if g["dept"] == self.dept]
        for i, g in enumerate(groups):
            on = g["id"] == self.gid
            chip = QPushButton(g["label"])
            chip.setObjectName("ChipOn" if on else "Chip")
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda _, gid=g["id"]: self.pick_group(gid))
            self.chips_layout.addWidget(chip, i // 3, i % 3)
        g = GROUP_BY_ID[self.gid]
        self.chosen.setText(f"Выбрано: {g['dept']} · {g['label']}")

# ### --- СЕКЦИЯ СТРАНИЦ (UI) --- ###

class LoginPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        root = QVBoxLayout(self)
        root.setContentsMargins(60, 60, 60, 60)
        root.addStretch()
        card = QFrame(); card.setObjectName("Card"); card.setMaximumWidth(520)
        lay = QVBoxLayout(card); lay.setContentsMargins(28, 24, 28, 24); lay.setSpacing(12)
        title = QLabel(t("login_title"))
        title.setStyleSheet(f"font-size:22px;font-weight:600;color:{C['INK']};")
        lay.addWidget(title)
        sub = QLabel(t("login_sub"))
        sub.setStyleSheet(f"color:{C['MUTED']};font-size:12px;")
        sub.setWordWrap(True); lay.addWidget(sub)
        self.user = QLineEdit(); self.user.setPlaceholderText(t("login_user")); lay.addWidget(self.user)
        self.pwd = QLineEdit(); self.pwd.setPlaceholderText(t("login_pass"))
        self.pwd.setEchoMode(QLineEdit.Password); lay.addWidget(self.pwd)
        self.err = QLabel("")
        self.err.setStyleSheet(f"color:{C['DANGER']};font-size:11px;")
        self.err.setWordWrap(True); lay.addWidget(self.err)
        self.btn = QPushButton(t("login_btn"))
        self.btn.setObjectName("Primary"); self.btn.clicked.connect(self.do_login)
        lay.addWidget(self.btn)
        h = QHBoxLayout(); h.addStretch(); h.addWidget(card); h.addStretch()
        root.addLayout(h); root.addStretch()
        self.pwd.returnPressed.connect(self.do_login)

    def do_login(self):
        u = self.user.text().strip(); p = self.pwd.text()
        if not u or not p:
            self.err.setText("Введи логин и пароль"); return
        self.err.setText(t("login_loading")); self.btn.setEnabled(False)
        asyncio.ensure_future(self.app.api.login(u, p))

    def on_failed(self, msg):
        self.err.setText(f"{t('login_error')}: {msg[:200]}"); self.btn.setEnabled(True)

    def on_success(self):
        self.err.setText(""); self.btn.setEnabled(True); self.pwd.setText("")

def _hhmm(s):
    m = re.search(r"(\d{1,2}):(\d{2})", str(s or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None

def _fmt_time(s):
    m = re.search(r"\d{1,2}:\d{2}", str(s or ""))
    return m.group(0) if m else str(s or "")

def _norm_days(days):
    days = clone(days or [])
    while len(days) < 7:
        days.append([None] * 5)
    out = []
    for day in days[:7]:
        day = list(day) + [None] * (5 - len(day))
        out.append(day[:5])
    return out


_SUBJECT_KEYS = ("TEAL", "VIOLET", "BLUE", "PINK", "GREEN", "ORANGE")
DEPT_COLORS = {"Колледж": "TEAL", "Вуз": "VIOLET"}

def _subject_key(name):
    return _SUBJECT_KEYS[sum(ord(ch) for ch in (name or "")) % len(_SUBJECT_KEYS)]

def _subject_color(name):
    """Стабильный цвет для предмета: одинаковый предмет — одинаковый цвет."""
    return C[_subject_key(name)]


class _WeekBase(QWidget):
    """Общая «шапка» и сетка недели для страниц расписания."""
    def __init__(self, app, hub, title, sub):
        super().__init__()
        self.app = app; self.hub = hub; self.offset = 0
        root = QVBoxLayout(self); root.setContentsMargins(32, 28, 32, 24); root.setSpacing(14)

        self.top = QHBoxLayout(); self.top.setSpacing(10)
        tb = QVBoxLayout(); tb.setSpacing(2)
        self.title_lbl = QLabel(title); self.title_lbl.setObjectName("PageTitle")
        self.sub_lbl = QLabel(sub); self.sub_lbl.setObjectName("PageSub")
        tb.addWidget(self.title_lbl); tb.addWidget(self.sub_lbl)
        self.top.addLayout(tb); self.top.addStretch()
        self.badge = QLabel(""); self.badge.setObjectName("Badge")
        self.top.addWidget(self.badge)
        root.addLayout(self.top)

        bar = QFrame(); bar.setObjectName("Toolbar")
        bl = QHBoxLayout(bar); bl.setContentsMargins(10, 8, 10, 8); bl.setSpacing(8)
        prev = QPushButton("‹"); prev.setObjectName("Ghost"); prev.setFixedWidth(46)
        prev.setCursor(Qt.PointingHandCursor); prev.clicked.connect(lambda: self.shift(-1))
        nxt = QPushButton("›"); nxt.setObjectName("Ghost"); nxt.setFixedWidth(46)
        nxt.setCursor(Qt.PointingHandCursor); nxt.clicked.connect(lambda: self.shift(1))
        self.week_lbl = QLabel(""); self.week_lbl.setObjectName("WeekLabel")
        self.week_lbl.setAlignment(Qt.AlignCenter); self.week_lbl.setMinimumWidth(190)
        today = QPushButton(t("today")); today.setObjectName("Primary")
        today.setCursor(Qt.PointingHandCursor); today.clicked.connect(self.go_today)
        refresh = QPushButton(t("refresh")); refresh.setObjectName("Ghost")
        refresh.setCursor(Qt.PointingHandCursor); refresh.clicked.connect(lambda: self.reload())
        bl.addWidget(prev); bl.addWidget(self.week_lbl); bl.addWidget(nxt); bl.addWidget(today)
        bl.addStretch(); bl.addWidget(refresh)
        root.addWidget(bar)

        self.extra = QVBoxLayout(); self.extra.setSpacing(10)
        root.addLayout(self.extra)

        self.group_lbl = QLabel(""); self.group_lbl.setObjectName("GroupLabel")
        root.addWidget(self.group_lbl)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        self.holder = QWidget()
        self.grid = QGridLayout(self.holder)
        self.grid.setSpacing(8); self.grid.setContentsMargins(0, 0, 8, 0)
        scroll.setWidget(self.holder)
        root.addWidget(scroll, 1)

    # --- навигация по неделям ---
    def reload(self): self.render()
    def render(self): pass

    def shift(self, d):
        self.offset += d
        self.reload()

    def go_today(self):
        self.offset = 0
        self.reload()

    def dates(self):
        today = datetime.date.today()
        mon = today - datetime.timedelta(days=today.weekday())
        mon += datetime.timedelta(days=7 * self.offset)
        return [mon + datetime.timedelta(days=i) for i in range(7)]

    # --- сетка ---
    def _clear_grid(self):
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None); w.deleteLater()

    def _setup_grid(self, rows):
        self.grid.setColumnStretch(0, 0)
        for i in range(7):
            self.grid.setColumnStretch(i + 1, 10 if i < 5 else 6)
        for r in range(0, 14):
            self.grid.setRowStretch(r, 0)
        self.grid.setRowStretch(rows + 1, 1)

    def _day_head(self, i, date, is_today):
        name = DAYS[i] if i < 5 else DAYS_SHORT[i]
        lbl = QLabel(f"{name}\n{date.strftime('%d.%m')}")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setObjectName("DayHeadToday" if is_today else "DayHead")
        if i >= 5 and not is_today:
            lbl.setStyleSheet(f"color:{C['PINK']};")
        return lbl

    def _slot_head(self, n, a, b):
        txt = f"{n}\n{a}\n{b}" if a else f"{n}"
        lbl = QLabel(txt); lbl.setAlignment(Qt.AlignCenter)
        lbl.setObjectName("SlotHead"); lbl.setFixedWidth(70)
        return lbl

    def _card(self, subject, room="", teacher="", head="", now=False):
        key = _subject_key(subject)
        col, soft = C[key], C[key + "_SOFT"]
        f = QFrame(); f.setObjectName("PairCardNow" if now else "PairCard")
        f.setMinimumHeight(96)
        if not now:
            f.setStyleSheet(f"QFrame#PairCard{{background-color:{soft};border:1px solid {_rgba(col, 0.45)};}} "
                            f"QFrame#PairCard:hover{{border:1px solid {col};}}")
        outer = QHBoxLayout(f); outer.setContentsMargins(10, 9, 10, 9); outer.setSpacing(9)
        tile = QLabel((subject or "?").strip()[:1].upper()); tile.setObjectName("SubjTile")
        tile.setFixedSize(28, 28); tile.setAlignment(Qt.AlignCenter)
        tile.setStyleSheet(f"background-color:{col};")
        outer.addWidget(tile, 0, Qt.AlignTop)
        lay = QVBoxLayout(); lay.setSpacing(2); outer.addLayout(lay, 1)
        labels = [tile]
        if head:
            h = QLabel(head); h.setObjectName("PairTime"); lay.addWidget(h); labels.append(h)
            if not now: h.setStyleSheet(f"color:{col};")
        sl = QLabel(subject); sl.setObjectName("PairSubject"); sl.setWordWrap(True)
        lay.addWidget(sl); labels.append(sl)
        for txt in (room, teacher):
            if txt:
                l = QLabel(txt); l.setObjectName("PairMeta"); l.setWordWrap(True)
                lay.addWidget(l); labels.append(l)
        for l in labels:
            l.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay.addStretch()
        return f

    def _empty_cell(self, on_click=None):
        f = QFrame(); f.setObjectName("PairEmpty"); f.setMinimumHeight(96)
        if on_click is not None:
            lay = QVBoxLayout(f); lay.setContentsMargins(4, 4, 4, 4)
            btn = QToolButton(); btn.setObjectName("AddBtn"); btn.setText("+")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False: on_click())
            lay.addWidget(btn, alignment=Qt.AlignCenter)
        return f

    # --- локальное (редактируемое) расписание ---
    def _fill_manual(self, gid):
        sched = self.hub.schedules[gid]
        dates = self.dates(); today = datetime.date.today()
        nowdt = datetime.datetime.now(); now = nowdt.hour * 60 + nowdt.minute
        self._setup_grid(5)
        for i in range(7):
            self.grid.addWidget(self._day_head(i, dates[i], dates[i] == today), 0, i + 1)
        for r, (a, b) in enumerate(SLOTS):
            self.grid.addWidget(self._slot_head(r + 1, a, b), r + 1, 0)
        total = 0
        for d in range(7):
            for r in range(5):
                pair = sched[d][r]
                self.grid.addWidget(self._manual_cell(gid, d, r, pair, dates[d] == today, now), r + 1, d + 1)
                if pair: total += 1
        self.week_lbl.setText(f"{dates[0].strftime('%d.%m')} — {dates[6].strftime('%d.%m.%Y')}")
        return total

    def _manual_cell(self, gid, d, r, pair, is_today, now_min):
        if not pair:
            return self._empty_cell(lambda: self.edit_pair(gid, d, r))
        a, b = SLOTS[r]
        is_now = is_today and _hhmm(a) <= now_min < _hhmm(b)
        subject, room, teacher = (list(pair) + ["", "", ""])[:3]
        f = self._card(subject, room, teacher, "Сейчас" if is_now else "", is_now)
        f.setCursor(Qt.PointingHandCursor)
        f.mousePressEvent = lambda e: self.edit_pair(gid, d, r)
        return f

    def edit_pair(self, gid, d, r):
        g = GROUP_BY_ID[gid]
        sched = self.hub.schedules[gid]
        dlg = PairDialog(self, d, r, sched[d][r], f"{g['dept']} · {g['label']}")
        if dlg.exec() == QDialog.Accepted:
            if dlg.deleted:
                sched[d][r] = None
            else:
                nd, ns, subj, room, teacher = dlg.values()
                if not subj: return
                if (nd, ns) != (d, r): sched[d][r] = None
                sched[nd][ns] = [subj, room, teacher]
            self.hub.save()
            self.render()


class SchedulePage(_WeekBase):
    """Главный экран: расписание группы из учётной записи пользователя."""
    def __init__(self, app, hub):
        super().__init__(app, hub, t("page_sched"), t("page_sched_sub"))
        self.api_items = []
        self.api_loaded = False
        self.switch_btn = QPushButton(t("sched_all_btn")); self.switch_btn.setObjectName("Accent")
        self.switch_btn.setCursor(Qt.PointingHandCursor)
        self.switch_btn.clicked.connect(self.hub.show_all)
        self.top.addWidget(self.switch_btn)
        self.reload()
        QTimer(self, timeout=self.render).start(60000)

    def _api_mode(self):
        return self.app.api.is_logged_in() and self.api_loaded

    def reload(self):
        if self.app.api.is_logged_in():
            d = self.dates()[0].strftime("%Y-%m-%d")
            asyncio.ensure_future(self.app.api.load_schedule_month(d))
        else:
            self.render()

    def on_loaded(self, items):
        self.api_items = items or []
        self.api_loaded = True
        self.render()

    def _fill_api(self):
        dates = self.dates(); today = datetime.date.today()
        nowdt = datetime.datetime.now(); now = nowdt.hour * 60 + nowdt.minute
        day_idx = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(dates)}
        by, times, total, max_lesson = {}, {}, 0, 5
        for x in self.api_items:
            i = day_idx.get((x.get("date") or "")[:10])
            if i is None: continue
            try: n = int(x.get("lesson") or 0)
            except (TypeError, ValueError): n = 0
            if n < 1 or n > 8: continue
            by.setdefault((i, n), []).append(x); total += 1
            max_lesson = max(max_lesson, n)
            if x.get("started_at") and x.get("finished_at"):
                times.setdefault(n, (_fmt_time(x["started_at"]), _fmt_time(x["finished_at"])))
        self._setup_grid(max_lesson)
        for i in range(7):
            self.grid.addWidget(self._day_head(i, dates[i], dates[i] == today), 0, i + 1)
        for n in range(1, max_lesson + 1):
            a, b = times.get(n) or (SLOTS[n - 1] if n <= len(SLOTS) else ("", ""))
            self.grid.addWidget(self._slot_head(n, a, b), n, 0)
            for i in range(7):
                items = by.get((i, n))
                if not items:
                    self.grid.addWidget(self._empty_cell(), n, i + 1); continue
                cards = []
                for it in items:
                    s_m, e_m = _hhmm(it.get("started_at")), _hhmm(it.get("finished_at"))
                    is_now = dates[i] == today and s_m is not None and e_m is not None and s_m <= now < e_m
                    head = f"{_fmt_time(it.get('started_at'))}–{_fmt_time(it.get('finished_at'))}"
                    cards.append(self._card(it.get("subject_name", ""), it.get("room_name", ""),
                                            it.get("teacher_name") or it.get("teacher") or "", head, is_now))
                if len(cards) == 1:
                    self.grid.addWidget(cards[0], n, i + 1)
                else:
                    box = QWidget(); bl = QVBoxLayout(box)
                    bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(6)
                    for c in cards: bl.addWidget(c)
                    self.grid.addWidget(box, n, i + 1)
        self.week_lbl.setText(f"{dates[0].strftime('%d.%m')} — {dates[6].strftime('%d.%m.%Y')}")
        return total

    def render(self):
        self._clear_grid()
        prof = load_json(PROFILE_CACHE, {})
        gname = prof.get("group_name") or ""
        if self._api_mode():
            total = self._fill_api()
            self.group_lbl.setText(f"Моя группа: {gname}" if gname else "Моя группа")
            self.sub_lbl.setText("Расписание из TOP Academy")
        else:
            g = GROUP_BY_ID[DEFAULT_MINE_ID]
            total = self._fill_manual(DEFAULT_MINE_ID)
            self.group_lbl.setText(f"{g['dept']} · {g['label']}")
            if self.app.api.is_logged_in():
                self.sub_lbl.setText("Загружаем расписание твоей группы…")
            else:
                self.sub_lbl.setText("Локальное расписание. Войди в аккаунт, чтобы видеть расписание своей группы")
        self.badge.setText(f"{total} пар")


class AllGroupsPage(_WeekBase):
    """Общее расписание всех групп (открывается кнопкой из «Расписания»)."""
    def __init__(self, app, hub):
        super().__init__(app, hub, t("page_all_groups"), t("page_all_groups_sub"))
        self.gid = DEFAULT_MINE_ID
        self.dept = GROUP_BY_ID[self.gid]["dept"]
        back = QPushButton(t("sched_my_btn")); back.setObjectName("Accent")
        back.setCursor(Qt.PointingHandCursor); back.clicked.connect(self.hub.show_mine)
        self.top.addWidget(back)

        self.dept_row = QWidget()
        dr = QHBoxLayout(self.dept_row); dr.setContentsMargins(0, 0, 0, 0); dr.setSpacing(10)
        self.dept_btns = {}
        for name in DEPTS:
            b = QPushButton(name); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, n=name: self.select_dept(n))
            dr.addWidget(b); self.dept_btns[name] = b
        dr.addStretch()
        self.extra.addWidget(self.dept_row)

        self.chip_holder = QWidget()
        self.chip_layout = QHBoxLayout(self.chip_holder)
        self.chip_layout.setContentsMargins(0, 0, 0, 0); self.chip_layout.setSpacing(8)
        self.extra.addWidget(self.chip_holder)

        self.render_depts(); self.render_chips(); self.render()

    def _repolish(self, w, name):
        w.setObjectName(name); w.style().unpolish(w); w.style().polish(w)

    def render_depts(self):
        for name, b in self.dept_btns.items():
            on = name == self.dept
            self._repolish(b, "DeptBtnOn" if on else "DeptBtn")
            col = C[DEPT_COLORS.get(name, "TEAL")]
            if on:
                b.setStyleSheet(f"QPushButton{{background-color:{col};border:1px solid {col};color:{C['ON_TEAL']};}}")
            else:
                b.setStyleSheet(f"QPushButton:hover{{border:1px solid {col};}}")

    def select_dept(self, name):
        self.dept = name
        ids = [g["id"] for g in GROUPS if g["dept"] == name]
        self.gid = ids[0] if ids else DEFAULT_MINE_ID
        self.render_depts(); self.render_chips(); self.render()

    def select_group(self, gid):
        self.gid = gid
        self.render_chips(); self.render()

    def render_chips(self):
        while self.chip_layout.count():
            it = self.chip_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        for g in GROUPS:
            if g["dept"] != self.dept: continue
            chip = QPushButton(g["label"])
            on = g["id"] == self.gid
            chip.setObjectName("ChipOn" if on else "Chip")
            dkey = DEPT_COLORS.get(self.dept, "TEAL")
            if on:
                chip.setStyleSheet(f"QPushButton{{background-color:{C[dkey + '_SOFT']};border:1px solid {C[dkey]};color:{C[dkey]};}}")
            else:
                chip.setStyleSheet(f"QPushButton:hover{{border:1px solid {C[dkey]};}}")
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda _=False, gid=g["id"]: self.select_group(gid))
            self.chip_layout.addWidget(chip)
        self.chip_layout.addStretch()

    def render(self):
        self._clear_grid()
        g = GROUP_BY_ID[self.gid]
        total = self._fill_manual(self.gid)
        self.group_lbl.setText(f"{g['dept']} · {g['label']}")
        self.badge.setText(f"{total} пар")


class ScheduleHub(QWidget):
    """Раздел «Расписание»: по умолчанию — моя группа, кнопкой открывается общее расписание."""
    def __init__(self, app):
        super().__init__()
        self.schedules = {g["id"]: _norm_days(g["days"]) for g in GROUPS}
        saved = load_json(LOCAL / "schedule_data.json", {})
        if isinstance(saved, dict):
            for gid, days in saved.items():
                if gid in self.schedules and isinstance(days, list):
                    self.schedules[gid] = _norm_days(days)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget(); lay.addWidget(self.stack)
        self.mine = SchedulePage(app, self)
        self.all = AllGroupsPage(app, self)
        self.stack.addWidget(self.mine); self.stack.addWidget(self.all)

    def save(self):
        save_json(LOCAL / "schedule_data.json", self.schedules)

    def show_mine(self):
        self.stack.setCurrentWidget(self.mine)

    def show_all(self):
        self.all.render()
        self.stack.setCurrentWidget(self.all)

    def on_show(self):
        self.show_mine()

    def reload(self): self.mine.reload()
    def on_loaded(self, items): self.mine.on_loaded(items)


# ### --- СЕКЦИЯ ДОМАШНИХ ЗАДАНИЙ (БЕЗ ИЗМЕНЕНИЙ) --- ###
HW_PAGE = 50
HW_CARD_MIN_W = 460   # минимальная ширина карточки ДЗ: сколько влезет — столько колонок
HW_MAX_COLS = 3

class _BtnSink:
    """Собирает кнопки карточки, чтобы потом разложить их по строкам."""
    def __init__(self): self.items = []
    def addWidget(self, w): self.items.append(w)
HW_STATES = ("todo", "overdue", "review", "checked")
HW_STATUS_HINT = {1: "checked", 2: "review"}

def clear_layout(lay):
    while lay.count():
        item = lay.takeAt(0)
        w = item.widget()
        if w is not None: w.setParent(None); w.deleteLater()
        elif item.layout() is not None: clear_layout(item.layout())

def hw_parse_date(raw):
    raw = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try: return datetime.datetime.strptime(raw[:10], fmt).date()
        except ValueError: continue
    return None

def hw_fmt_date(d): return d.strftime("%d.%m.%Y") if d else "—"

def rtf_to_text(data):
    """Простое преобразование RTF в обычный текст (кириллица через \\'xx и \\uN)."""
    if isinstance(data, bytes): data = data.decode("latin-1")
    m = re.search(r"\\ansicpg(\d+)", data); cp = "cp" + m.group(1) if m else "cp1251"
    skip_dest = {"fonttbl", "colortbl", "stylesheet", "info", "pict", "header", "footer", "themedata",
                 "colorschememapping", "latentstyles", "datastore", "listtable", "listoverridetable",
                 "rsidtbl", "generator", "xmlnstbl", "fldinst", "object"}
    out, stack = [], []; skip = False; uc = 1; pend = 0; opened = False; i, n = 0, len(data)
    while i < n:
        c = data[i]
        if c == "{": stack.append((skip, uc)); i += 1; opened = True; continue
        if c == "}": skip, uc = stack.pop() if stack else (False, 1); i += 1; opened = False; continue
        if c == "\\":
            i += 1
            if i >= n: break
            d = data[i]
            if d in "\\{}":
                if not skip: out.append(d)
                i += 1
            elif d == "'":
                hx = data[i + 1:i + 3]; i += 3
                if pend: pend -= 1
                elif not skip:
                    try: out.append(bytes([int(hx, 16)]).decode(cp, "replace"))
                    except ValueError: pass
            elif d == "*":
                i += 1
                if opened: skip = True
                continue
            elif d == "~":
                if not skip: out.append(" ")
                i += 1
            elif d.isalpha():
                mm = re.match(r"([a-zA-Z]+)(-?\d+)? ?", data[i:]); word, arg = mm.group(1), mm.group(2); i += mm.end()
                if word in skip_dest and opened: skip = True
                elif skip: pass
                elif word in ("par", "line", "sect"): out.append("\n")
                elif word == "tab": out.append("\t")
                elif word == "emdash": out.append("—")
                elif word == "endash": out.append("–")
                elif word == "uc" and arg: uc = int(arg)
                elif word == "u" and arg:
                    v = int(arg); out.append(chr(v + 65536 if v < 0 else v)); pend = uc
            else:
                i += 1
            opened = False
            continue
        if c in "\r\n": i += 1; continue
        if not skip:
            if pend: pend -= 1
            else: out.append(c)
        i += 1; opened = False
    return re.sub(r"\n{3,}", "\n\n", "".join(out)).strip()

def hw_text(text):
    """Текст поля журнала с сохранением переносов строк; RTF и HTML превращаются в обычный текст."""
    raw = str(text or "")
    if raw.lstrip().startswith("{\\rtf"): raw = rtf_to_text(raw)
    raw = re.sub(r"<br\s*/?>|</p>", "\n", raw, flags=re.I)
    s = unescape(re.sub(r"<[^>]+>", "", raw))
    return re.sub(r"[ \t]+", " ", s).strip()

class HwTextDialog(QDialog):
    def __init__(self, parent, title, text):
        super().__init__(parent)
        self.setWindowTitle("StudentHub"); self.setStyleSheet(build_style()); self.resize(720, 480)
        lay = QVBoxLayout(self); lay.setContentsMargins(22, 20, 22, 18); lay.setSpacing(10)
        ttl = QLabel(title); ttl.setObjectName("HwTheme"); ttl.setWordWrap(True); ttl.setTextFormat(Qt.PlainText)
        lay.addWidget(ttl)
        box = QTextEdit(); box.setReadOnly(True); box.setPlainText(text); lay.addWidget(box, 1)
        row = QHBoxLayout(); row.addStretch()
        cl = QPushButton("Закрыть"); cl.setObjectName("Primary"); cl.clicked.connect(self.accept)
        row.addWidget(cl); lay.addLayout(row)

HW_IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

def hw_abs_url(path):
    path = (path or "").strip()
    return path if path.startswith(("http://", "https://", "data:")) else f"https://fs.top-academy.ru/{path.lstrip('/')}"

def hw_image_sources(it):
    """Картинки, прикреплённые преподавателем: файл задания-картинка и <img> в описании/комментарии."""
    out = []
    def add(u):
        u = unescape((u or "").strip())
        if u:
            u = hw_abs_url(u)
            if u not in out: out.append(u)
    fp = (it.get("file_path") or "").strip()
    names = [fp.split("?")[0].lower(), str(it.get("filename") or "").lower()]
    if fp and any(n.endswith(HW_IMG_EXT) for n in names): add(fp)
    for key in ("comment", "homework_comment", "theme"):
        for src in re.findall(r"<img[^>]+src\s*=\s*[\"']([^\"']+)[\"']", str(it.get(key) or ""), re.I):
            add(src)
    return out

async def hw_fetch_image(url):
    if url.startswith("data:"):
        import base64
        return base64.b64decode(url.partition(",")[2])
    import httpx
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as cl:
        r = await cl.get(url); r.raise_for_status()
        return r.content

class HwImageDialog(QDialog):
    def __init__(self, parent, pm, url):
        super().__init__(parent); self.pm = pm; self.url = url
        self.setWindowTitle("StudentHub"); self.setStyleSheet(build_style()); self.resize(920, 700)
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 16, 18, 16); lay.setSpacing(10)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setAlignment(Qt.AlignCenter)
        lb = QLabel(); lb.setAlignment(Qt.AlignCenter)
        lb.setPixmap(pm if pm.width() <= 860 else pm.scaledToWidth(860, Qt.SmoothTransformation))
        scroll.setWidget(lb); lay.addWidget(scroll, 1)
        row = QHBoxLayout(); row.addStretch()
        sv = QPushButton("Сохранить…"); sv.setObjectName("Ghost"); sv.clicked.connect(self.save)
        cl = QPushButton("Закрыть"); cl.setObjectName("Primary"); cl.clicked.connect(self.accept)
        row.addWidget(sv); row.addWidget(cl); lay.addLayout(row)

    def save(self):
        from urllib.parse import unquote, urlparse
        name = unquote(Path(urlparse(self.url).path).name) if not self.url.startswith("data:") else "photo.png"
        if not Path(name).suffix: name += ".png"
        start = Path.home() / "Downloads"
        dest, _ = QFileDialog.getSaveFileName(self, "Сохранить фото", str((start if start.exists() else Path.home()) / name))
        if dest and not self.pm.save(dest):
            QMessageBox.warning(self, "StudentHub", "Не удалось сохранить фото")

def hw_clean(text, limit=0):
    raw = str(text or "")
    if raw.lstrip().startswith("{\\rtf"): raw = rtf_to_text(raw)
    s = unescape(re.sub(r"<[^>]+>", " ", raw))
    s = re.sub(r"\s+", " ", s).strip()
    if limit and len(s) > limit: s = s[:limit].rstrip() + "…"
    return s

def hw_days_word(n):
    if settings.get("lang", "ru") == "en":
        return f"{n} day" if n == 1 else f"{n} days"
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11: word = "день"
    elif 2 <= n10 <= 4 and not 12 <= n100 <= 14: word = "дня"
    else: word = "дней"
    return f"{n} {word}"

def hw_state(it, today=None):
    today = today or datetime.date.today()
    hs = it.get("homework_stud") or {}
    if (hs.get("mark") or 0) > 0: return "checked"
    if hs.get("id"): return "review"
    hint = HW_STATUS_HINT.get(it.get("status"))
    if hint: return hint
    due = hw_parse_date(it.get("completion_time"))
    if due and due < today: return "overdue"
    return "todo"

def hw_sort_key(it, state):
    due = hw_parse_date(it.get("completion_time")) or datetime.date.max
    rank = {"todo": 0, "overdue": 1, "review": 2, "checked": 3}[state]
    ordinal = due.toordinal()
    return (rank, ordinal if state == "todo" else -ordinal)

def hw_due_hint(due, state, today):
    if not due or state in ("review", "checked"): return ""
    d = (due - today).days
    if d < 0: return t("hw_overdue_by").format(n=hw_days_word(-d))
    if d == 0: return t("hw_due_today")
    if d == 1: return t("hw_due_tomorrow")
    return t("hw_due_in").format(n=hw_days_word(d))

def hw_mark(it):
    """Оценка за ДЗ или None, если работа не проверена. Сервер отдаёт None или 0
    для непроверенных работ — в средний балл и счётчики они попадать не должны."""
    hs = (it.get("homework_stud") or {}) if isinstance(it, dict) else {}
    try:
        m = float(hs.get("mark"))
    except (TypeError, ValueError):
        return None
    if m <= 0: return None
    return int(m) if m == int(m) else m

def hw_sniff_ext(data):
    """Настоящее расширение файла по его содержимому (None, если не удалось определить)."""
    h = data[:8]
    if data[:4] == b"%PDF": return ".pdf"
    if data[:5] == b"{\\rtf": return ".rtf"
    if h[:4] == b"PK\x03\x04":
        try:
            import zipfile, io
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
            if "word/document.xml" in names: return ".docx"
            if "xl/workbook.xml" in names: return ".xlsx"
            if "ppt/presentation.xml" in names: return ".pptx"
        except Exception: pass
        return ".zip"
    if h[:4] == b"\xd0\xcf\x11\xe0":
        if b"W\x00o\x00r\x00k\x00b\x00o\x00o\x00k" in data[:200000] or b"Workbook" in data[:200000]: return ".xls"
        if b"PowerPoint Document" in data[:200000] or b"P\x00o\x00w\x00e\x00r\x00P\x00o\x00i\x00n\x00t" in data[:200000]: return ".ppt"
        return ".doc"
    if h[:4] == b"Rar!": return ".rar"
    if h[:4] == b"7z\xbc\xaf": return ".7z"
    if h[:8] == b"\x89PNG\r\n\x1a\n": return ".png"
    if h[:3] == b"\xff\xd8\xff": return ".jpg"
    if h[:3] == b"GIF": return ".gif"
    return None

def hw_fix_filename(name, data):
    """Имя файла с правильным расширением: сервер/браузер подставляли .rtf к любым файлам."""
    name = re.sub(r'[\\/:*?"<>|]+', "_", (name or "").strip()) or "задание"
    stem, dot, ext = name.rpartition(".")
    if not dot: stem, ext = name, ""
    ext = "." + ext.lower() if ext else ""
    real = hw_sniff_ext(data)
    if real and ext != real:
        zip_like = {".odt", ".ods", ".odp", ".jar", ".apk", ".epub"}
        if not (real == ".zip" and ext in zip_like):
            return stem + real
    return name

class StatTile(QFrame):
    clicked = Signal()
    def __init__(self, key, value, caption, on):
        super().__init__()
        self.setObjectName("StatTile")
        self.setProperty("on", "true" if on else "false")
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 11, 16, 11); lay.setSpacing(0)
        num = QLabel(str(value)); num.setObjectName("StatNum"); num.setProperty("state", key)
        cap = QLabel(caption); cap.setObjectName("StatCap")
        lay.addWidget(num); lay.addWidget(cap)
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self.clicked.emit()
        super().mousePressEvent(e)

class HwUploadDialog(QDialog):
    MIN_LEN = 5; LIMIT = 500
    def __init__(self, parent, item):
        super().__init__(parent)
        self.setWindowTitle(t("upload"))
        self.setStyleSheet(build_style())
        self.setMinimumWidth(480); self.file = ""
        outer = QVBoxLayout(self); outer.setContentsMargins(22, 20, 22, 18); outer.setSpacing(10)
        subj = QLabel(hw_clean(item.get("name_spec"))); subj.setObjectName("HwSubject")
        theme = QLabel(hw_clean(item.get("theme")) or t("upload")); theme.setObjectName("HwTheme")
        subj.setTextFormat(Qt.PlainText); theme.setTextFormat(Qt.PlainText)
        theme.setWordWrap(True); outer.addWidget(subj); outer.addWidget(theme)
        row = QHBoxLayout(); row.setSpacing(10)
        pick = QPushButton(t("pick_file")); pick.setObjectName("Ghost")
        pick.setCursor(Qt.PointingHandCursor); pick.clicked.connect(self.pick)
        self.file_lbl = QLabel(t("no_file")); self.file_lbl.setObjectName("HwMeta")
        row.addWidget(pick); row.addWidget(self.file_lbl, 1); outer.addLayout(row)
        self.comment = QTextEdit(); self.comment.setFixedHeight(100)
        self.comment.setPlaceholderText(t("answer_text")); self.comment.textChanged.connect(self._sync)
        outer.addWidget(self.comment)
        self.counter = QLabel(f"0 / {self.LIMIT}"); self.counter.setObjectName("HwMeta")
        self.counter.setAlignment(Qt.AlignRight); outer.addWidget(self.counter)
        # --- затраченное время ---
        time_row = QHBoxLayout(); time_row.setSpacing(8)
        time_lbl = QLabel(f"{t('hw_spent')}:"); time_lbl.setObjectName("HwMeta")
        self.hours = QComboBox()
        self.hours.addItems([f"{h:02d}" for h in range(0, 24)])
        self.hours.setFixedWidth(72)
        sep = QLabel("ч"); sep.setObjectName("HwMeta")
        self.minutes = QComboBox()
        self.minutes.addItems([f"{m:02d}" for m in range(0, 60, 5)])
        self.minutes.setFixedWidth(72)
        sep2 = QLabel("мин"); sep2.setObjectName("HwMeta")
        time_row.addWidget(time_lbl); time_row.addWidget(self.hours); time_row.addWidget(sep)
        time_row.addWidget(self.minutes); time_row.addWidget(sep2); time_row.addStretch()
        outer.addLayout(time_row)
        # --------------------------------
        btns = QDialogButtonBox()
        self.ok = btns.addButton(t("upload"), QDialogButtonBox.AcceptRole)
        self.ok.setObjectName("Primary")
        cancel = btns.addButton(t("cancel"), QDialogButtonBox.RejectRole)
        cancel.setObjectName("Ghost")
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        outer.addWidget(btns); self._sync()
    def pick(self):
        f, _ = QFileDialog.getOpenFileName(self, t("select_file"), str(Path.home()))
        if f: self.file = f; self.file_lbl.setText(Path(f).name); self._sync()
    def _sync(self):
        txt = self.comment.toPlainText()
        if len(txt) > self.LIMIT:
            txt = txt[: self.LIMIT]
            self.comment.blockSignals(True); self.comment.setPlainText(txt)
            self.comment.moveCursor(QTextCursor.End); self.comment.blockSignals(False)
        n = len(txt.strip())
        too_short = n < self.MIN_LEN
        hint = f"  (мин. {self.MIN_LEN})" if too_short else ""
        self.counter.setText(f"{len(txt)} / {self.LIMIT}{hint}")
        self.counter.setStyleSheet(f"color:{C['DANGER']};" if too_short else "")
        self.ok.setEnabled(not too_short)
    def values(self): return self.file, self.comment.toPlainText().strip(), self.hours.currentText(), self.minutes.currentText()

class HomeworkPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.items = load_json(HW_CACHE, [])
        self.rows = []
        self.counts = {k: 0 for k in HW_STATES}
        self.filter = "all"; self.limit = HW_PAGE; self._auto_loaded = False
        self._sending = False; self._img_cache = {}; self._cols_used = 1
        self._relayout_timer = QTimer(self); self._relayout_timer.setSingleShot(True)
        self._relayout_timer.timeout.connect(self._maybe_relayout)
        root = QVBoxLayout(self); root.setContentsMargins(28, 22, 28, 18); root.setSpacing(14)
        header = QHBoxLayout()
        tb = QVBoxLayout(); tb.setSpacing(2)
        title = QLabel(t("page_hw")); title.setObjectName("PageTitle")
        sub = QLabel(t("page_hw_sub")); sub.setObjectName("PageSub")
        tb.addWidget(title); tb.addWidget(sub); header.addLayout(tb); header.addStretch()
        self.status = QLabel(""); self.status.setObjectName("HwMeta")
        self.status.setWordWrap(True); self.status.setMaximumWidth(420)
        self.status.setAlignment(Qt.AlignRight | Qt.AlignVCenter); header.addWidget(self.status)
        self.refresh_btn = QPushButton(t("refresh")); self.refresh_btn.setObjectName("Primary")
        self.refresh_btn.setCursor(Qt.PointingHandCursor); self.refresh_btn.clicked.connect(self.reload)
        header.addWidget(self.refresh_btn); root.addLayout(header)
        self.tiles_lay = QHBoxLayout(); self.tiles_lay.setSpacing(10); root.addLayout(self.tiles_lay)
        bar = QHBoxLayout(); bar.setSpacing(10)
        self.search = QLineEdit(); self.search.setObjectName("Search")
        self.search.setPlaceholderText(t("hw_search")); self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filters_changed); bar.addWidget(self.search, 1)
        self.subject_cb = QComboBox(); self.subject_cb.setMinimumWidth(260)
        self.subject_cb.currentIndexChanged.connect(self._filters_changed); bar.addWidget(self.subject_cb)
        root.addLayout(bar)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QFrame(); holder.setObjectName("Flat")
        self.list_lay = QVBoxLayout(holder); self.list_lay.setContentsMargins(0, 0, 8, 0); self.list_lay.setSpacing(10)
        self.scroll.setWidget(holder); root.addWidget(self.scroll, 1)
        self._apply_data()

    def showEvent(self, e):
        super().showEvent(e)
        if not self._auto_loaded and self.app.api.is_logged_in():
            self._auto_loaded = True; QTimer.singleShot(0, self.reload)
        self._relayout_timer.start(50)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout_timer.start(150)

    def _calc_cols(self):
        w = self.scroll.viewport().width()
        return max(1, min(HW_MAX_COLS, w // HW_CARD_MIN_W))

    def _maybe_relayout(self):
        if self._calc_cols() != self._cols_used: self._render_list()

    def reload(self):
        self._img_cache = {k: v for k, v in self._img_cache.items() if v is not None}  # неудачные загрузки фото повторим
        self.refresh_btn.setEnabled(False); self.status.setStyleSheet(""); self.status.setText(t("loading"))
        asyncio.ensure_future(self.app.api.load_homework())

    def on_loaded(self, items, err):
        self.items = items or []; self.refresh_btn.setEnabled(True)
        # раньше после первой ошибки подпись оставалась красной навсегда
        self.status.setStyleSheet("")
        if err: self.status.setStyleSheet(f"color:{C['DANGER']};"); self.status.setText(err)
        elif not self.items: self.status.setText(t("empty_hw"))
        else: self.status.setText(t("hw_updated").format(time=datetime.datetime.now().strftime("%H:%M"), n=len(self.items)))
        self._apply_data()

    def _apply_data(self):
        today = datetime.date.today()
        rows = [(it, hw_state(it, today)) for it in self.items]
        rows.sort(key=lambda r: hw_sort_key(r[0], r[1]))
        self.rows = rows; self.counts = {k: 0 for k in HW_STATES}
        for _, st in rows: self.counts[st] += 1
        prev = self.subject_cb.currentData() or ""
        names = sorted({(it.get("name_spec") or "").strip() for it, _ in rows} - {""})
        self.subject_cb.blockSignals(True); self.subject_cb.clear()
        self.subject_cb.addItem(t("hw_all_subjects"), ""); [self.subject_cb.addItem(n, n) for n in names]
        idx = self.subject_cb.findData(prev); self.subject_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self.subject_cb.blockSignals(False); self.limit = HW_PAGE
        self._render_tiles(); self._render_list()

    def _filters_changed(self, *_):
        self.limit = HW_PAGE; self._render_list()

    def set_filter(self, key):
        self.filter = key; self.limit = HW_PAGE; QTimer.singleShot(0, self._refresh_view)

    def _refresh_view(self):
        self._render_tiles(); self._render_list()

    def _more(self):
        self.limit += HW_PAGE; QTimer.singleShot(0, self._render_list)

    def _visible_rows(self):
        q = self.search.text().strip().lower(); subj = self.subject_cb.currentData() or ""
        out = []
        for it, st in self.rows:
            if self.filter != "all" and st != self.filter: continue
            if subj and (it.get("name_spec") or "").strip() != subj: continue
            if q:
                hay = f"{it.get('name_spec', '')} {it.get('theme', '')} {it.get('fio_teach', '')}".lower()
                if q not in hay: continue
            out.append((it, st))
        return out

    def _render_tiles(self):
        clear_layout(self.tiles_lay)
        defs = [("all", len(self.rows))] + [(k, self.counts[k]) for k in HW_STATES]
        for key, n in defs:
            tile = StatTile(key, n, t("hw_all") if key == "all" else t(f"hw_{key}"), self.filter == key)
            tile.clicked.connect(lambda k=key: self.set_filter(k)); self.tiles_lay.addWidget(tile, 1)

    def _render_list(self):
        clear_layout(self.list_lay)
        rows = self._visible_rows()
        if not rows:
            lbl = QLabel(t("hw_nothing") if self.items else t("no_data"))
            lbl.setObjectName("HwEmpty"); lbl.setAlignment(Qt.AlignCenter); self.list_lay.addWidget(lbl)
            self.list_lay.addStretch(); return
        today = datetime.date.today()
        shown = rows[: self.limit]
        cols = self._cols_used = self._calc_cols()
        host = QWidget(); grid = QGridLayout(host); grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12); grid.setVerticalSpacing(12)
        for c in range(cols): grid.setColumnStretch(c, 1)
        for n, (it, st) in enumerate(shown): grid.addWidget(self._make_card(it, st, today), n // cols, n % cols)
        self.list_lay.addWidget(host)
        if len(rows) > len(shown):
            more = QPushButton(f"{t('hw_more')} ({len(rows) - len(shown)})")
            more.setObjectName("Ghost"); more.clicked.connect(self._more); self.list_lay.addWidget(more, 0, Qt.AlignHCenter)
        self.list_lay.addStretch()

    def _make_card(self, it, state, today):
        hs = it.get("homework_stud") or {}
        card = QFrame(); card.setObjectName("HwCard"); row = QHBoxLayout(card)
        row.setContentsMargins(16, 14, 18, 14); row.setSpacing(14)
        row.addWidget(letter_tile(it.get("name_spec"), 42, 18), 0, Qt.AlignTop); body = QVBoxLayout(); body.setSpacing(7); row.addLayout(body, 1)
        top = QHBoxLayout(); top.setSpacing(8)
        subj = QLabel(hw_clean(it.get("name_spec")) or "—"); subj.setObjectName("HwSubject")
        subj.setTextFormat(Qt.PlainText)
        subj.setStyleSheet(f"color:{_subject_color(it.get('name_spec'))};")
        subj.setWordWrap(True); top.addWidget(subj, 1)
        mark = hs.get("mark") or 0
        if mark > 0:
            mb = QLabel(f"{t('hw_mark')}: {mark}"); mb.setObjectName("MarkBadge"); top.addWidget(mb)
        pill = QLabel(t(f"hw_{state}")); pill.setObjectName("Pill"); pill.setProperty("state", state); top.addWidget(pill)
        body.addLayout(top)
        theme = QLabel(hw_clean(it.get("theme")) or "—"); theme.setObjectName("HwTheme"); theme.setWordWrap(True)
        theme.setTextFormat(Qt.PlainText); body.addWidget(theme)
        desc = hw_clean(it.get("comment"))
        if desc:
            dl = QLabel(hw_clean(desc, 240)); dl.setObjectName("HwDesc"); dl.setWordWrap(True)
            body.addWidget(dl)
        for url in hw_image_sources(it)[:4]:
            img = QLabel("Загрузка фото…"); img.setObjectName("HwMeta"); body.addWidget(img, 0, Qt.AlignLeft)
            asyncio.ensure_future(self._fill_image(url, img))
        issued = hw_parse_date(it.get("creation_time")); due = hw_parse_date(it.get("completion_time"))
        compact = self._cols_used > 1          # в сетке карточка уже, поэтому строки метаданных переносим
        meta = QVBoxLayout(); meta.setSpacing(2)
        row1 = QHBoxLayout(); row1.setSpacing(8); row2 = QHBoxLayout(); row2.setSpacing(8)
        row3 = row2 if not compact else QHBoxLayout()
        if compact: row3.setSpacing(8)
        def add_meta(row, text, name="HwMeta", st=None):
            lb = QLabel(text); lb.setObjectName(name)
            if st: lb.setProperty("state", st)
            row.addWidget(lb)
        teacher = hw_clean(it.get("fio_teach"))
        if teacher: add_meta(row1, teacher)
        add_meta(row2, f"{t('hw_issued')} {hw_fmt_date(issued)}")
        if not compact: add_meta(row2, "·")
        due_txt = f"{t('hw_deadline')} {hw_fmt_date(due)}"
        hint = hw_due_hint(due, state, today)
        if hint: due_txt += f" · {hint}"
        add_meta(row3, due_txt, "HwDue", state if state in ("todo", "overdue") else None)
        for r in (row1, row2) + ((row3,) if compact else ()):
            r.addStretch(); meta.addLayout(r)
        body.addLayout(meta)
        review = hw_clean(it.get("homework_comment"))
        # показываем мой ответ (stud_answer), если есть
        stud_ans = hw_clean(hs.get("stud_answer") if hs else "")
        if stud_ans:
            sa = QFrame(); sa.setObjectName("HwReview"); sl = QVBoxLayout(sa); sl.setContentsMargins(12, 8, 12, 8); sl.setSpacing(2)
            sa_cap = QLabel(t("hw_stud_answer")); sa_cap.setObjectName("HwMeta")
            sa_txt = QLabel(hw_clean(stud_ans, 300)); sa_txt.setObjectName("HwReviewText"); sa_txt.setWordWrap(True)
            sl.addWidget(sa_cap); sl.addWidget(sa_txt); body.addWidget(sa)
        if review:
            rv = QFrame(); rv.setObjectName("HwReview"); rl = QVBoxLayout(rv); rl.setContentsMargins(12, 8, 12, 8); rl.setSpacing(2)
            cap = QLabel(t("hw_teacher_comment")); cap.setObjectName("HwMeta")
            txt = QLabel(review); txt.setObjectName("HwReviewText"); txt.setWordWrap(True)
            rl.addWidget(cap); rl.addWidget(txt); body.addWidget(rv)
        btns = _BtnSink()
        path = it.get("file_path")
        if path:
            dl = QPushButton(t("hw_task_file")); dl.setObjectName("Ghost")
            dl.clicked.connect(lambda _, p=path, fn=it.get("filename"): self.download(p, fn)); btns.addWidget(dl)
        my_path = hs.get("file_path")
        if my_path:
            mw = QPushButton(t("hw_my_work")); mw.setObjectName("Ghost")
            mw.clicked.connect(lambda _, p=my_path, fn=hs.get("filename"): self.download(p, fn)); btns.addWidget(mw)
        # кнопка удаления черновика (если работа уже сдана, но не проверена)
        if hs.get("id") and state == "review":
            del_btn = QPushButton(t("hw_delete_draft")); del_btn.setObjectName("Danger")
            del_btn.clicked.connect(lambda _, i=it: self.delete_draft(i)); btns.addWidget(del_btn)
        if not review and hs.get("id"):
            cm = QPushButton("Комментарий преподавателя"); cm.setObjectName("Ghost")
            cm.clicked.connect(lambda _, i=it: asyncio.ensure_future(self._show_details(i))); btns.addWidget(cm)
        up = QPushButton(t("hw_resend") if hs.get("id") else t("upload"))
        up.setObjectName("Primary" if state in ("todo", "overdue") else "Ghost")
        up.clicked.connect(lambda _, i=it: self.upload(i)); btns.addWidget(up)
        body.addStretch(1)   # кнопки прижаты к низу карточки, карточки в ряду одной высоты
        for k in range(0, len(btns.items), 3):
            r = QHBoxLayout(); r.setSpacing(8); r.addStretch()
            for w in btns.items[k:k + 3]: r.addWidget(w)
            body.addLayout(r)
        # Переносимые подписи не должны задавать минимальную ширину по самой длинной теме —
        # иначе колонка раздувается и карточка уходит за край окна
        for lb in card.findChildren(QLabel):
            if lb.wordWrap(): lb.setMinimumWidth(1)
        card.setMinimumWidth(1)
        return card

    async def _fill_image(self, url, label):
        """Подгрузить фото преподавателя в карточку (миниатюра, по клику — на весь экран)."""
        pm = self._img_cache.get(url)
        if pm is None and url not in self._img_cache:
            try:
                pm = QPixmap()
                if not pm.loadFromData(await hw_fetch_image(url)): pm = None
            except Exception as e:
                log_error(f"image {url[:120]}: {describe_exc(e)}"); pm = None
            self._img_cache[url] = pm
        try:
            if pm is None or pm.isNull():
                label.setText("Не удалось загрузить фото"); return
            label.setText(""); label.setPixmap(pm.scaled(380, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            label.setCursor(Qt.PointingHandCursor)
            label.mousePressEvent = lambda e, p=pm, u=url: HwImageDialog(self, p, u).exec()
        except RuntimeError:
            pass  # карточку уже перерисовали

    async def _show_details(self, it):
        """Запросить у журнала полную карточку задания: комментарий преподавателя, ответ, описание."""
        hid = it.get("id"); title = hw_clean(it.get("theme")) or t("hw_teacher_comment")
        path = "/homework/evaluation/operations/get"
        try:
            api = self.app.api
            client = await api._get_client()
            try:
                data = await client._request("GET", path, params={"id": hid})
            except Exception:
                if not await api._refresh_locked(): raise
                client = await api._get_client()
                data = await client._request("GET", path, params={"id": hid})
        except Exception as e:
            log_error(f"hw-details {hid}: {describe_exc(e)}")
            QMessageBox.warning(self, "StudentHub", "Не удалось получить комментарий: " + describe_exc(e)); return
        d = data if isinstance(data, dict) else {}
        log_error(f"hw-details {hid} keys={sorted(d.keys())}")
        hs = d.get("homework_stud") if isinstance(d.get("homework_stud"), dict) else {}
        parts = []
        for label, val in (("Комментарий преподавателя", d.get("homework_comment")), ("Описание задания", d.get("comment")),
                           ("Мой ответ", hs.get("stud_answer"))):
            txt = hw_text(val)
            if txt: parts.append(f"{label}:\n{txt}")
        HwTextDialog(self, title, "\n\n".join(parts) or "Преподаватель не оставил комментария.").exec()

    def download(self, path, filename=""):
        url = path if path.startswith("http") else f"https://fs.top-academy.ru/{path.lstrip('/')}"
        asyncio.ensure_future(self._save_file(url, filename))

    async def _save_file(self, url, filename):
        try:
            import httpx
            from urllib.parse import unquote, urlparse
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as cl:
                r = await cl.get(url); r.raise_for_status()
            data = r.content
            name = hw_clean(filename)
            if not name:
                cd = r.headers.get("content-disposition", "")
                m = re.search(r"filename\*=UTF-8''([^;]+)", cd, re.I) or re.search(r'filename="?([^";]+)', cd, re.I)
                name = unquote(m.group(1)) if m else unquote(Path(urlparse(url).path).name)
            name = hw_fix_filename(name, data)
        except Exception as e:
            log_error(f"download {url}: {describe_exc(e)}")
            QDesktopServices.openUrl(QUrl(url)); return
        start = Path.home() / "Downloads"
        dest, _ = QFileDialog.getSaveFileName(self, "Сохранить файл", str((start if start.exists() else Path.home()) / name))
        if not dest: return
        try:
            Path(dest).write_bytes(data)
        except OSError as e:
            QMessageBox.warning(self, "StudentHub", f"Не удалось сохранить файл: {e}"); return
        QDesktopServices.openUrl(QUrl.fromLocalFile(dest))

    def upload(self, item):
        hid = item.get("id")
        if not hid or self._sending: return
        dlg = HwUploadDialog(self, item)
        if dlg.exec() == QDialog.Accepted:
            f, comment, hours, minutes = dlg.values()
            # пока идёт отправка, повторные нажатия игнорируем — иначе работа уходила дважды
            self._sending = True; self.status.setStyleSheet(""); self.status.setText(t("loading"))
            asyncio.ensure_future(self.app.api.upload_homework(hid, f, comment, hours, minutes))

    def action_finished(self):
        self._sending = False

    def delete_draft(self, item):
        hs = item.get("homework_stud") or {}
        sid = hs.get("id")
        if not sid: return
        if self._sending: return
        if QMessageBox.question(self, "StudentHub", t("hw_delete_confirm")) == QMessageBox.Yes:
            self._sending = True
            asyncio.ensure_future(self.app.api.delete_homework(sid))

# --- ЖУРНАЛ: краткая сводка успеваемости в едином стиле ---
class JournalPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Журнал")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Успеваемость, последние оценки и прогресс")
        subtitle.setObjectName("PageSub")
        titles.addWidget(title); titles.addWidget(subtitle)
        header.addLayout(titles); header.addStretch()
        refresh = QPushButton(t("refresh")); refresh.setObjectName("Primary")
        refresh.clicked.connect(self.refresh_data)
        header.addWidget(refresh)
        root.addLayout(header)

        cards = QHBoxLayout(); cards.setSpacing(12)
        self.avg_value = QLabel("—")
        self.count_value = QLabel("0")
        self.good_value = QLabel("0")
        self.todo_value = QLabel("0")
        for value, caption, accent in [
            (self.avg_value, "Средний балл", "TEAL"),
            (self.count_value, "Оценок выставлено", "BLUE"),
            (self.good_value, "Оценок «5»", "GREEN"),
            (self.todo_value, "Заданий без оценки", "ORANGE"),
        ]:
            card = QFrame(); card.setObjectName("Card")
            layout = QVBoxLayout(card); layout.setContentsMargins(16, 14, 16, 14); layout.setSpacing(5)
            value.setStyleSheet(f"font-size:27px;font-weight:700;color:{C[accent]};")
            caption_label = QLabel(caption); caption_label.setObjectName("PageSub")
            layout.addWidget(value); layout.addWidget(caption_label)
            cards.addWidget(card, 1)
        root.addLayout(cards)

        section = QFrame(); section.setObjectName("Card")
        sl = QVBoxLayout(section); sl.setContentsMargins(16, 14, 16, 14); sl.setSpacing(10)
        heading = QLabel("Последние оценки"); heading.setObjectName("SectionTitle")
        sl.addWidget(heading)
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Предмет", "Задание", "Дата", "Оценка"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        sl.addWidget(self.table)
        root.addWidget(section, 1)
        self.refresh_data()

    def refresh_data(self):
        items = load_json(HW_CACHE, [])
        if not isinstance(items, list): items = []
        rows = []
        marks = []
        todo = 0
        for item in items:
            hs = item.get("homework_stud") or {}
            mark = hw_mark(item)
            if mark is not None:
                marks.append(float(mark))
                dt = hw_parse_date(item.get("completion_time") or item.get("date_end"))
                rows.append((dt or datetime.date.min, item.get("name_spec") or "—", hw_clean(item.get("theme"), 100), hw_fmt_date(dt), mark))
            elif not hs.get("id"):
                todo += 1
        self.avg_value.setText(f"{sum(marks)/len(marks):.2f}" if marks else "—")
        self.count_value.setText(str(len(marks)))
        self.good_value.setText(str(sum(1 for m in marks if m >= 5)))
        self.todo_value.setText(str(todo))
        rows.sort(key=lambda row: row[0], reverse=True)
        self.table.setRowCount(min(12, len(rows)))
        for r, row in enumerate(rows[:12]):
            values = row[1:]
            for c, value in enumerate(values):
                cell = QTableWidgetItem("—" if value in (None, "") else str(value))
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                if c == 3:
                    cell.setTextAlignment(Qt.AlignCenter)
                    try:
                        n = float(value)
                        cell.setForeground(QColor(C["GREEN"] if n >= 5 else C["BLUE"] if n >= 4 else C["ORANGE"]))
                        font = cell.font(); font.setBold(True); cell.setFont(font)
                    except (TypeError, ValueError): pass
                self.table.setItem(r, c, cell)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def on_show(self):
        self.refresh_data()


# ### --- ОЦЕНКИ И ПРОФИЛЬ (оформление по макету) --- ###
def grades_unwrap(v):
    if isinstance(v, dict):
        for k in ("data", "items", "results", "list"):
            if isinstance(v.get(k), list): return v[k]
        return []
    return v if isinstance(v, list) else []

def grades_last_points(v):
    for x in reversed(grades_unwrap(v)):
        if isinstance(x, dict) and x.get("points") is not None: return x["points"]
    return None

def mark_key(v):
    """Цвет оценки: 5 — зелёный, 4 — синий, 3 — оранжевый, ниже — красный."""
    if v is None: return "BLUE"
    return "GREEN" if v >= 4.5 else "BLUE" if v >= 3.5 else "ORANGE" if v >= 2.5 else "DANGER"

def fmt_ru_date(d):
    return f"{d.day} {RU_MONTHS[d.month - 1]} {d.year}" if d else "—"

def fmt_percent(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 100: return f"{v:g}%"
    return "—" if v in (None, "") else str(v)

def gear_button(app):
    b = QToolButton(); b.setObjectName("GearBtn"); b.setCursor(Qt.PointingHandCursor)
    b.setIcon(make_icon("settings", C["META"], 20)); b.setIconSize(QSize(20, 20))
    b.clicked.connect(lambda _=False: app.show_page("settings"))
    return b

def set_on(btn, on):
    btn.setProperty("on", "true" if on else "false")
    btn.style().unpolish(btn); btn.style().polish(btn)

class RingGauge(QWidget):
    """Кольцо среднего балла (как на макете)."""
    def __init__(self, maximum=5.0):
        super().__init__()
        self.value = None; self.maximum = maximum
        self.setMinimumSize(170, 170)

    def set_value(self, v):
        self.value = v; self.update()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        width = 12.0
        side = min(self.width(), self.height()) - width - 6
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        pen = QPen(QColor(C["LINE"])); pen.setWidthF(width); pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen); p.drawArc(rect, 0, 360 * 16)
        key = mark_key(self.value)
        if self.value:
            frac = max(0.0, min(1.0, self.value / self.maximum))
            pen.setColor(QColor(C[key])); p.setPen(pen)
            p.drawArc(rect, 90 * 16, -int(frac * 360 * 16))
        f = QFont(self.font()); f.setPixelSize(34); f.setBold(True); p.setFont(f)
        p.setPen(QColor(C["INK"]))
        txt = f"{self.value:.2f}" if self.value else "—"
        p.drawText(QRectF(rect.x(), rect.center().y() - 34, rect.width(), 44), Qt.AlignCenter, txt)
        f2 = QFont(self.font()); f2.setPixelSize(13); p.setFont(f2); p.setPen(QColor(C["MUTED"]))
        p.drawText(QRectF(rect.x(), rect.center().y() + 10, rect.width(), 20), Qt.AlignCenter, f"из {self.maximum:g}")
        p.end()

class GradesPage(QWidget):
    TABS = ("Оценки", "Рейтинг группы", "Посещения и оценки")
    VISIT_COLS = (("date_visit", "Дата"), ("lesson_number", "Пара"), ("spec_name", "Предмет"),
                  ("status_was", "Посещ."), ("class_work_mark", "Работа на паре"),
                  ("home_work_mark", "ДЗ"), ("lab_work_mark", "Лаб."),
                  ("control_work_mark", "Контр."), ("final_work_mark", "Итог"))
    LEGEND = ((5, "Отлично", "GREEN"), (4, "Хорошо", "BLUE"),
              (3, "Удовлетворительно", "ORANGE"), (2, "Неудовлетворительно", "DANGER"))
    LIST_LIMIT = 200

    def __init__(self, app):
        super().__init__()
        self.app = app; self.loaded = False; self.data = load_json(GRADES_CACHE, {})
        self.entries = []; self.period = "all"; self.tiles = {}
        root = QVBoxLayout(self); root.setContentsMargins(28, 22, 28, 18); root.setSpacing(12)
        header = QHBoxLayout(); tb = QVBoxLayout(); tb.setSpacing(2)
        title = QLabel("Оценки"); title.setObjectName("PageTitle")
        sub = QLabel("Твои оценки, рейтинг и посещаемость · только просмотр"); sub.setObjectName("PageSub")
        tb.addWidget(title); tb.addWidget(sub); header.addLayout(tb); header.addStretch()
        self.status = QLabel(""); self.status.setObjectName("HwMeta"); self.status.setWordWrap(True)
        self.status.setMaximumWidth(420); self.status.setAlignment(Qt.AlignRight | Qt.AlignVCenter); header.addWidget(self.status)
        self.refresh_btn = QPushButton(t("refresh")); self.refresh_btn.setObjectName("Primary")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.reload); header.addWidget(self.refresh_btn)
        header.addWidget(gear_button(app)); root.addLayout(header)

        tabs = QHBoxLayout(); tabs.setSpacing(8); self.tab_btns = []
        for i, name in enumerate(self.TABS):
            b = QPushButton(name); b.setObjectName("SegBtn"); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, n=i: self.set_tab(n)); tabs.addWidget(b); self.tab_btns.append(b)
        tabs.addStretch(); root.addLayout(tabs)

        self.stack = QStackedWidget(); root.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_overview())
        self.stack.addWidget(self._build_rating())
        self.stack.addWidget(self._build_visits())
        self.set_tab(0); self.set_period("all", refresh=False); self.render()

    # ---------- построение страниц ----------
    def _build_overview(self):
        page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(12)
        bar = QHBoxLayout(); bar.setSpacing(8); self.period_btns = {}
        for key, name in (("all", "Все оценки"), ("sem", "Текущий семестр")):
            b = QPushButton(name); b.setObjectName("SegBtn"); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.set_period(k)); bar.addWidget(b); self.period_btns[key] = b
        bar.addStretch()
        self.subject_cb = QComboBox(); self.subject_cb.setMinimumWidth(240)
        self.subject_cb.currentIndexChanged.connect(self.render_overview); bar.addWidget(self.subject_cb)
        self.range_lbl = QLabel("—"); self.range_lbl.setObjectName("DatePill"); bar.addWidget(self.range_lbl)
        lay.addLayout(bar)

        row = QHBoxLayout(); row.setSpacing(12)
        avg_card = QFrame(); avg_card.setObjectName("Card")
        al = QVBoxLayout(avg_card); al.setContentsMargins(20, 16, 20, 16); al.setSpacing(8)
        t1 = QLabel("Средний балл"); t1.setObjectName("SectionTitle"); al.addWidget(t1)
        self.ring = RingGauge(); al.addWidget(self.ring, 1)
        self.legend = {}
        for level, name, key in self.LEGEND:
            r = QHBoxLayout(); r.setSpacing(8)
            dot = QLabel("●"); dot.setStyleSheet(f"color:{C[key]};font-size:12px;")
            nm = QLabel(name); nm.setObjectName("RowTitle")
            cnt = QLabel("0"); cnt.setObjectName("RowTime")
            r.addWidget(dot); r.addWidget(nm); r.addStretch(); r.addWidget(cnt)
            al.addLayout(r); self.legend[level] = cnt
        row.addWidget(avg_card, 4)

        list_card = QFrame(); list_card.setObjectName("Card")
        ll = QVBoxLayout(list_card); ll.setContentsMargins(20, 16, 20, 12); ll.setSpacing(6)
        t2 = QLabel("Последние оценки"); t2.setObjectName("SectionTitle"); ll.addWidget(t2)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QFrame(); holder.setObjectName("Flat")
        self.list_lay = QVBoxLayout(holder); self.list_lay.setContentsMargins(0, 0, 6, 0); self.list_lay.setSpacing(0)
        scroll.setWidget(holder); ll.addWidget(scroll, 1)
        row.addWidget(list_card, 6)
        lay.addLayout(row, 1)

        banner = QFrame(); banner.setObjectName("Banner")
        bl = QHBoxLayout(banner); bl.setContentsMargins(20, 14, 20, 14); bl.setSpacing(14)
        bl.addWidget(icon_tile("trophy", "YELLOW", 46, 26))
        bc = QVBoxLayout(); bc.setSpacing(0)
        self.banner_title = QLabel(""); self.banner_title.setObjectName("BannerTitle")
        self.banner_sub = QLabel(""); self.banner_sub.setObjectName("BannerSub")
        bc.addWidget(self.banner_title); bc.addWidget(self.banner_sub); bl.addLayout(bc, 1)
        lay.addWidget(banner)
        return page

    def _tile(self, key, caption):
        card = QFrame(); card.setObjectName("Card"); cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 14, 18, 14); cl.setSpacing(2)
        v = QLabel("—"); v.setStyleSheet(f"font-size:26px;font-weight:700;color:{C['TEAL']};")
        c = QLabel(caption); c.setObjectName("PageSub"); cl.addWidget(v); cl.addWidget(c)
        self.tiles[key] = (v, c, caption)
        return card

    @staticmethod
    def _make_table():
        tbl = QTableWidget(); tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows); tbl.verticalHeader().setVisible(False)
        tbl.verticalHeader().setDefaultSectionSize(38); tbl.setShowGrid(False)
        hh = tbl.horizontalHeader(); hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setHighlightSections(False); hh.setStretchLastSection(True)
        return tbl

    def _build_rating(self):
        page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(12)
        tiles = QHBoxLayout(); tiles.setSpacing(12)
        for key, cap in (("pos", "Место в группе"), ("prog", "Средний прогресс"), ("att", "Посещаемость")):
            tiles.addWidget(self._tile(key, cap), 1)
        lay.addLayout(tiles)
        self.rating_tbl = self._make_table(); lay.addWidget(self.rating_tbl, 1)
        return page

    def _build_visits(self):
        page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(12)
        self.visits_tbl = self._make_table(); lay.addWidget(self.visits_tbl, 1)
        return page

    # ---------- переключатели ----------
    def set_tab(self, i):
        self.stack.setCurrentIndex(i)
        for n, b in enumerate(self.tab_btns): set_on(b, n == i)

    def set_period(self, key, refresh=True):
        self.period = key
        for k, b in self.period_btns.items(): set_on(b, k == key)
        if refresh: self.render_overview()

    @staticmethod
    def semester_range(today=None):
        """1-й семестр: 1 сентября – 31 января, 2-й: 1 февраля – 31 августа."""
        today = today or datetime.date.today()
        if today.month >= 9: return datetime.date(today.year, 9, 1), datetime.date(today.year + 1, 1, 31)
        if today.month == 1: return datetime.date(today.year - 1, 9, 1), datetime.date(today.year, 1, 31)
        return datetime.date(today.year, 2, 1), datetime.date(today.year, 8, 31)

    # ---------- данные ----------
    def on_show(self):
        self.render()
        if not self.loaded: self.reload()

    def reload(self):
        self.refresh_btn.setEnabled(False); self.status.setStyleSheet(""); self.status.setText(t("loading"))
        asyncio.ensure_future(self.app.api.load_grades())

    def on_loaded(self, data):
        self.loaded = True; self.data = data if isinstance(data, dict) else {}
        self.refresh_btn.setEnabled(True); self.render()
        errs = self.data.get("errors") or []
        if errs: self.status.setStyleSheet(f"color:{C['DANGER']};"); self.status.setText("Ошибка: " + errs[0][:160])
        else: self.status.setStyleSheet(""); self.status.setText("Обновлено " + datetime.datetime.now().strftime("%H:%M"))

    def _set_tile(self, key, value, extra=""):
        v, c, cap = self.tiles[key]; v.setText("—" if value in (None, "") else str(value)); c.setText(cap + extra)

    def _fill(self, table, headers, rows, hl_row=None, stretch=None):
        table.clear(); table.setColumnCount(len(headers)); table.setHorizontalHeaderLabels(headers); table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                it = QTableWidgetItem("—" if val in (None, "") else str(val))
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if r == hl_row:
                    f = it.font(); f.setBold(True); it.setFont(f)
                    it.setForeground(QColor(C["TEAL"])); it.setBackground(QColor(C["TEAL_SOFT"]))
                table.setItem(r, c, it)
        hh = table.horizontalHeader()
        if stretch is None:
            table.resizeColumnsToContents(); hh.setStretchLastSection(True)
        else:
            hh.setStretchLastSection(False)
            for c in range(len(headers)):
                hh.setSectionResizeMode(c, QHeaderView.Stretch if c == stretch else QHeaderView.ResizeToContents)

    def render(self):
        d = self.data if isinstance(self.data, dict) else {}
        me = (load_json(PROFILE_CACHE, {}).get("full_name") or "").strip()
        group = [x for x in grades_unwrap(d.get("group")) if isinstance(x, dict)]
        group.sort(key=lambda x: x.get("position") or 9999)
        hl = next((i for i, x in enumerate(group) if me and (x.get("full_name") or "").strip() == me), None)
        self._fill(self.rating_tbl, ["#", "Студент", "Баллы"],
                   [(x.get("position"), x.get("full_name"), x.get("amount")) for x in group], hl, stretch=1)
        pts = d.get("group_pts") if isinstance(d.get("group_pts"), dict) else {}
        pos, tot = pts.get("studentPosition"), pts.get("totalCount")
        self._set_tile("pos", f"{pos} / {tot}" if pos and tot else pos)
        self._set_tile("prog", grades_last_points(d.get("avg")))
        self._set_tile("att", fmt_percent(grades_last_points(d.get("attendance"))))

        # оценки за ДЗ: только проверенные работы (оценка > 0)
        items = load_json(HW_CACHE, [])
        self.entries = []
        for it in items if isinstance(items, list) else []:
            m = hw_mark(it)
            if m is None: continue
            self.entries.append({"subject": hw_clean(it.get("name_spec")) or "—", "theme": hw_clean(it.get("theme"), 70),
                                 "date": hw_parse_date(it.get("completion_time")), "mark": m})
        self.entries.sort(key=lambda e: e["date"] or datetime.date.min, reverse=True)
        self._fill_subjects(); self.render_overview()

        vis = [x for x in grades_unwrap(d.get("visits")) if isinstance(x, dict)]
        cols = [(k, h) for k, h in self.VISIT_COLS if any(k in x for x in vis)]
        vrows = []
        for x in vis:
            row = []
            for k, _ in cols:
                v = x.get(k); row.append(str(v)[:10] if k.startswith("date") and v else v)
            vrows.append(row)
        self._fill(self.visits_tbl, [h for _, h in cols] or ["Нет данных"], vrows)

    def _fill_subjects(self):
        prev = self.subject_cb.currentData() or ""
        names = sorted({e["subject"] for e in self.entries} - {"—"})
        self.subject_cb.blockSignals(True); self.subject_cb.clear()
        self.subject_cb.addItem(t("hw_all_subjects"), "")
        for n in names: self.subject_cb.addItem(n, n)
        i = self.subject_cb.findData(prev); self.subject_cb.setCurrentIndex(i if i >= 0 else 0)
        self.subject_cb.blockSignals(False)

    def render_overview(self, *_):
        subj = self.subject_cb.currentData() or ""
        lo = hi = None
        if self.period == "sem": lo, hi = self.semester_range()
        sel = []
        for e in self.entries:
            if subj and e["subject"] != subj: continue
            if lo and not (e["date"] and lo <= e["date"] <= hi): continue
            sel.append(e)
        dates = [e["date"] for e in sel if e["date"]]
        if self.period == "sem": a, b = lo, hi
        elif dates: a, b = min(dates), max(dates)
        else: a = b = None
        self.range_lbl.setText(f"{hw_fmt_date(a)} – {hw_fmt_date(b)}" if a else "—")

        marks = [e["mark"] for e in sel]
        avg = sum(marks) / len(marks) if marks else None
        self.ring.set_value(avg)
        counts = {5: 0, 4: 0, 3: 0, 2: 0}
        for m in marks: counts[min(5, max(2, int(round(m))))] += 1
        for level, lbl in self.legend.items(): lbl.setText(str(counts[level]))

        clear_layout(self.list_lay)
        if not sel:
            lbl = QLabel("Нет оценок за выбранный период" if self.entries else "Проверенных оценок пока нет")
            lbl.setObjectName("HwEmpty"); lbl.setAlignment(Qt.AlignCenter); self.list_lay.addWidget(lbl)
        for e in sel[: self.LIST_LIMIT]: self.list_lay.addWidget(self._grade_row(e))
        self.list_lay.addStretch()

        if avg is None: ttl, sb = "Оценок пока нет", "Сдай домашнее задание — оценки появятся здесь"
        elif avg >= 4.5: ttl, sb = "Отличный результат!", "Ты на правильном пути!"
        elif avg >= 3.5: ttl, sb = "Хороший результат!", "Ещё немного — и будет отлично"
        else: ttl, sb = "Есть куда расти", "Сдавай ДЗ вовремя — средний балл подтянется"
        self.banner_title.setText(ttl); self.banner_sub.setText(sb)

    def _grade_row(self, e):
        f = QFrame(); f.setObjectName("HomeRow")
        h = QHBoxLayout(f); h.setContentsMargins(2, 8, 2, 8); h.setSpacing(12)
        h.addWidget(letter_tile(e["subject"], 38, 16), 0, Qt.AlignVCenter)
        c = QVBoxLayout(); c.setSpacing(0)
        a = QLabel(e["subject"]); a.setObjectName("RowTitle"); a.setWordWrap(True); a.setTextFormat(Qt.PlainText)
        sub = fmt_ru_date(e["date"])
        if e["theme"]: sub = f"{e['theme']} · {sub}"
        b = QLabel(sub); b.setObjectName("RowSub"); b.setWordWrap(True); b.setTextFormat(Qt.PlainText)
        c.addWidget(a); c.addWidget(b); h.addLayout(c, 1)
        key = mark_key(e["mark"])
        badge = QLabel(str(e["mark"])); badge.setFixedSize(36, 36); badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"background-color:{C[key + '_SOFT']};color:{C[key]};border:1px solid {C[key]};"
                            f"border-radius:18px;font-size:15px;font-weight:700;")
        h.addWidget(badge, 0, Qt.AlignVCenter)
        return f

class ProfilePage(QWidget):
    LINKS = (("palette", "VIOLET", "Внешний вид и язык", "settings"),
             ("profile", "BLUE", "Аккаунт и выход", "settings"),
             ("support", "GREEN", "Обратная связь", "support")) + (
        (("donate", "PINK", "Поддержать автора", "donate"),) if DONATE_URL else ())

    def __init__(self, app):
        super().__init__(); self.app = app; self.prof = {}
        root = QVBoxLayout(self); root.setContentsMargins(28, 22, 28, 18); root.setSpacing(14)
        header = QHBoxLayout(); tb = QVBoxLayout(); tb.setSpacing(2)
        title = QLabel(t("page_prof")); title.setObjectName("PageTitle")
        sub = QLabel(t("page_prof_sub")); sub.setObjectName("PageSub")
        tb.addWidget(title); tb.addWidget(sub); header.addLayout(tb); header.addStretch()
        header.addWidget(gear_button(app)); root.addLayout(header)

        cols = QHBoxLayout(); cols.setSpacing(14)
        self.card = QFrame(); self.card.setObjectName("Card")
        self.card.setMinimumWidth(320); self.card.setMaximumWidth(420)
        self.info = QVBoxLayout(self.card); self.info.setContentsMargins(24, 22, 24, 20); self.info.setSpacing(10)
        cols.addWidget(self.card, 4, Qt.AlignTop)

        right = QVBoxLayout(); right.setSpacing(14)
        sc = QFrame(); sc.setObjectName("Card"); sl = QVBoxLayout(sc)
        sl.setContentsMargins(20, 16, 20, 10); sl.setSpacing(0)
        st = QLabel("Настройки"); st.setObjectName("SectionTitle"); sl.addWidget(st); sl.addSpacing(6)
        for kind, key, text, page in self.LINKS: sl.addWidget(self._link_row(kind, key, text, page))
        right.addWidget(sc)
        self.stats_card = QFrame(); self.stats_card.setObjectName("Card")
        self.stats = QVBoxLayout(self.stats_card); self.stats.setContentsMargins(20, 16, 20, 10); self.stats.setSpacing(0)
        right.addWidget(self.stats_card); right.addStretch()
        cols.addLayout(right, 5); root.addLayout(cols)

        banner = QFrame(); banner.setObjectName("Banner")
        bl = QHBoxLayout(banner); bl.setContentsMargins(20, 14, 20, 14); bl.setSpacing(14)
        bl.addWidget(icon_tile("cap", "BLUE", 46, 26))
        bt = QLabel("Лучшие результаты ещё впереди!"); bt.setObjectName("BannerTitle"); bl.addWidget(bt, 1)
        root.addWidget(banner); root.addStretch()
        self.render(load_json(PROFILE_CACHE, {}))

    def _link_row(self, kind, key, text, page):
        f = QFrame(); f.setObjectName("SettingRow"); f.setCursor(Qt.PointingHandCursor)
        f.mousePressEvent = lambda e, k=page: self.app.show_page(k)
        h = QHBoxLayout(f); h.setContentsMargins(4, 10, 4, 10); h.setSpacing(12)
        h.addWidget(icon_tile(kind, key, 34, 18), 0, Qt.AlignVCenter)
        lb = QLabel(text); lb.setObjectName("RowTitle"); h.addWidget(lb, 1)
        ch = QLabel(); ch.setPixmap(make_pixmap("chevron", C["MUTED"], 16)); h.addWidget(ch)
        for w in (lb, ch): w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        return f

    def _info_row(self, kind, caption, value):
        h = QHBoxLayout(); h.setSpacing(10)
        ic = QLabel(); ic.setPixmap(make_pixmap(kind, C["MUTED"], 18)); ic.setFixedWidth(22)
        lk = QLabel(caption); lk.setObjectName("RowSub"); lk.setMinimumWidth(100)
        lv = QLabel(str(value) if value not in (None, "") else "—"); lv.setObjectName("RowTitle")
        lv.setWordWrap(True); lv.setTextFormat(Qt.PlainText); lv.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h.addWidget(ic); h.addWidget(lk); h.addWidget(lv, 1); self.info.addLayout(h)

    def _stat_row(self, kind, key, caption, value, color=None):
        f = QFrame(); f.setObjectName("HomeRow")
        h = QHBoxLayout(f); h.setContentsMargins(2, 9, 2, 9); h.setSpacing(12)
        h.addWidget(icon_tile(kind, key, 34, 18), 0, Qt.AlignVCenter)
        lb = QLabel(caption); lb.setObjectName("RowTitle"); h.addWidget(lb, 1)
        vl = QLabel(str(value) if value not in (None, "") else "—")
        vl.setStyleSheet(f"font-size:15px;font-weight:700;color:{color or C['INK']};"); h.addWidget(vl)
        return f

    @staticmethod
    def _hline():
        f = QFrame(); f.setFixedHeight(1); f.setStyleSheet(f"background-color:{C['LINE']};border:none;")
        return f

    def on_show(self): self.render(load_json(PROFILE_CACHE, {}))
    def on_loaded(self, prof): self.render(prof)

    def reload(self):
        self.refresh_btn.setEnabled(False)
        asyncio.ensure_future(self.app.api.load_profile())

    def render(self, prof):
        prof = prof if isinstance(prof, dict) else {}; self.prof = prof
        clear_layout(self.info)
        name = (prof.get("full_name") or "").strip()
        letters = "".join(w[0] for w in name.split()[:2]).upper() or "IT"
        av = QLabel(letters); av.setObjectName("ProfAvatar"); av.setFixedSize(84, 84); av.setAlignment(Qt.AlignCenter)
        self.info.addWidget(av, 0, Qt.AlignLeft)
        nm = QLabel(name or "—"); nm.setObjectName("ProfName"); nm.setWordWrap(True); nm.setTextFormat(Qt.PlainText)
        role = QLabel("Студент"); role.setObjectName("RowSub")
        self.info.addWidget(nm); self.info.addWidget(role)
        grp = (prof.get("group_name") or "").strip()
        if grp:
            g = QLabel(grp); g.setObjectName("UserGroup"); g.setTextFormat(Qt.PlainText); self.info.addWidget(g)
        self.refresh_btn = QPushButton("Обновить данные"); self.refresh_btn.setObjectName("Primary")
        self.refresh_btn.setCursor(Qt.PointingHandCursor); self.refresh_btn.clicked.connect(self.reload)
        self.info.addSpacing(4); self.info.addWidget(self.refresh_btn); self.info.addWidget(self._hline())
        bd = prof.get("birthday")
        bd_txt = hw_fmt_date(hw_parse_date(bd)) if hw_parse_date(bd) else bd
        self._info_row("users", t("group"), grp)
        self._info_row("layers", t("stream"), prof.get("stream_name"))
        self._info_row("calendar", "День рождения", bd_txt)
        self._info_row("profile", "Возраст", prof.get("age"))
        groups = [g.get("name", "") for g in (prof.get("groups") or []) if isinstance(g, dict) and g.get("name")]
        if len(groups) > 1: self._info_row("users", "Все группы", ", ".join(groups))
        self.info.addStretch()
        self._render_stats()

    def _render_stats(self):
        clear_layout(self.stats)
        st = QLabel("Статистика"); st.setObjectName("SectionTitle"); self.stats.addWidget(st); self.stats.addSpacing(6)
        items = load_json(HW_CACHE, [])
        marks = [m for m in (hw_mark(it) for it in (items if isinstance(items, list) else [])) if m is not None]
        avg = sum(marks) / len(marks) if marks else None
        d = load_json(GRADES_CACHE, {}); d = d if isinstance(d, dict) else {}
        gp = d.get("group_pts") if isinstance(d.get("group_pts"), dict) else {}
        pos, tot = gp.get("studentPosition"), gp.get("totalCount")
        pts = [p for p in (self.prof.get("gaming_points") or []) if isinstance(p, dict)]
        total = sum(p.get("points", 0) or 0 for p in pts) if pts else None
        self.stats.addWidget(self._stat_row("grades", "GREEN", "Средний балл за ДЗ",
                                            f"{avg:.2f}" if avg is not None else None, C[mark_key(avg)] if avg is not None else None))
        self.stats.addWidget(self._stat_row("calendar", "BLUE", "Посещаемость",
                                            fmt_percent(grades_last_points(d.get("attendance")))))
        self.stats.addWidget(self._stat_row("trophy", "YELLOW", "Место в группе", f"{pos} / {tot}" if pos and tot else pos))
        self.stats.addWidget(self._stat_row("star", "VIOLET", t("points"), total))

# ### --- СЕКЦИЯ ПОДДЕРЖКИ (БЕЗ ИЗМЕНЕНИЙ) --- ###
class SupportPage(QWidget):
    def __init__(self, app):
        super().__init__(); self.app = app
        root = QVBoxLayout(self); root.setContentsMargins(24, 20, 24, 20); root.setSpacing(10)
        title = QLabel(t("page_sup")); title.setObjectName("PageTitle"); root.addWidget(title)
        sub = QLabel(t("page_sup_sub")); sub.setObjectName("PageSub"); root.addWidget(sub)
        card = QFrame(); card.setObjectName("Card"); form = QFormLayout(card)
        self.subject = QLineEdit(); self.subject.setPlaceholderText(t("sup_subject"))
        form.addRow(t("sup_subject"), self.subject)
        self.text = QTextEdit(); self.text.setFixedHeight(160)
        self.text.setPlaceholderText(t("sup_text")); form.addRow(t("sup_text"), self.text)
        root.addWidget(card); self.status = QLabel(""); self.status.setStyleSheet(f"color:{C['MUTED']};font-size:12px;")
        root.addWidget(self.status); send = QPushButton(t("sup_send")); send.setObjectName("Primary")
        send.clicked.connect(self.send); root.addWidget(send, alignment=Qt.AlignLeft); root.addStretch()
    def send(self):
        s = self.subject.text().strip(); b = self.text.toPlainText().strip()
        if not s or not b: self.status.setText("Заполни тему и текст"); return
        asyncio.ensure_future(self.app.api.send_support(s, b))
    def on_sent(self, ok, msg):
        self.status.setText(msg)
        if ok: self.subject.clear(); self.text.clear()

# ### --- СЕКЦИЯ ДОНАТОВ (БЕЗ ИЗМЕНЕНИЙ) --- ###
class DonatePage(QWidget):
    def __init__(self, app):
        super().__init__(); self.app = app
        root = QVBoxLayout(self); root.setContentsMargins(28, 22, 28, 18); root.setSpacing(16)
        head = QVBoxLayout(); head.setSpacing(2)
        title = QLabel(t("page_don")); title.setObjectName("PageTitle")
        sub = QLabel(t("page_don_sub")); sub.setObjectName("PageSub")
        head.addWidget(title); head.addWidget(sub); root.addLayout(head)
        hero = QFrame(); hero.setObjectName("SupportHero"); hero.setMaximumWidth(840)
        hl = QHBoxLayout(hero); hl.setContentsMargins(30, 28, 30, 28); hl.setSpacing(24)
        col = QVBoxLayout(); col.setSpacing(10)
        headline = QLabel(t("don_head")); headline.setObjectName("SupportHead")
        text = QLabel(t("don_text")); text.setObjectName("SupportText"); text.setWordWrap(True)
        note = QLabel(t("don_note")); note.setObjectName("HwMeta"); note.setWordWrap(True)
        col.addWidget(headline); col.addWidget(text); col.addWidget(note); col.addSpacing(8)
        btn = QPushButton(t("don_btn")); btn.setObjectName("SupportBtn")
        btn.setCursor(Qt.PointingHandCursor); btn.clicked.connect(self.open_link)
        col.addWidget(btn, 0, Qt.AlignLeft); hint = QLabel(t("don_hint")); hint.setObjectName("HwMeta")
        col.addWidget(hint); hl.addLayout(col, 1); root.addWidget(hero)
        tiles_box = QFrame(); tiles_box.setObjectName("Flat"); tiles_box.setMaximumWidth(840)
        tiles = QHBoxLayout(tiles_box); tiles.setContentsMargins(0, 0, 0, 0); tiles.setSpacing(12)
        for key in ("bugs", "features", "growth"):
            tile = QFrame(); tile.setObjectName("SupportTile")
            tl = QVBoxLayout(tile); tl.setContentsMargins(16, 14, 16, 14); tl.setSpacing(3)
            ttl = QLabel(t(f"don_{key}")); ttl.setObjectName("SupportTileTitle")
            txt = QLabel(t(f"don_{key}_t")); txt.setObjectName("SupportTileText"); txt.setWordWrap(True)
            tl.addWidget(ttl); tl.addWidget(txt); tiles.addWidget(tile, 1)
        root.addWidget(tiles_box); root.addStretch()
    def open_link(self): QDesktopServices.openUrl(QUrl(DONATE_URL))

# ### --- СЕКЦИЯ НАСТРОЕК (БЕЗ ИЗМЕНЕНИЙ) --- ###
class SettingsPage(QWidget):
    def __init__(self, app):
        super().__init__(); self.app = app
        root = QVBoxLayout(self); root.setContentsMargins(24, 20, 24, 20); root.setSpacing(10)
        title = QLabel(t("page_set")); title.setObjectName("PageTitle"); root.addWidget(title)
        sub = QLabel(t("page_set_sub")); sub.setObjectName("PageSub"); root.addWidget(sub)
        card = QFrame(); card.setObjectName("Card"); form = QFormLayout(card)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([t("theme_dark"), t("theme_light")])
        self.theme_combo.setCurrentIndex(0 if settings.get("theme") == "dark" else 1)
        self.theme_combo.currentIndexChanged.connect(self.change_theme); form.addRow(t("theme"), self.theme_combo)
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["Русский", "English"])
        self.lang_combo.setCurrentIndex(0 if settings.get("lang") == "ru" else 1)
        self.lang_combo.currentIndexChanged.connect(self.change_lang); form.addRow(t("lang"), self.lang_combo)
        root.addWidget(card); acc = QFrame(); acc.setObjectName("Card")
        acc_lay = QVBoxLayout(acc); acc_lay.setContentsMargins(20, 18, 20, 18)
        self.acc_info = QLabel(""); self.acc_info.setStyleSheet(f"color:{C['MUTED']};font-size:12px;")
        self.acc_info.setWordWrap(True); acc_lay.addWidget(self.acc_info)
        logout_btn = QPushButton(t("logout")); logout_btn.setObjectName("Danger")
        logout_btn.clicked.connect(self.do_logout); acc_lay.addWidget(logout_btn, alignment=Qt.AlignLeft); root.addWidget(acc); root.addStretch()
        self.refresh_account()
    def refresh_account(self):
        prof = load_json(PROFILE_CACHE, {})
        if prof.get("full_name"): self.acc_info.setText(f"Вошёл: {prof.get('full_name')} · {prof.get('group_name', '')}")
        else: self.acc_info.setText("Не авторизован")
    def change_theme(self, idx):
        settings["theme"] = "dark" if idx == 0 else "light"; save_json(SETTINGS_FILE, settings)
        QMessageBox.information(self, "StudentHub", "Тема сохранена. Перезапусти приложение.")
    def change_lang(self, idx):
        settings["lang"] = "ru" if idx == 0 else "en"; save_json(SETTINGS_FILE, settings)
        QMessageBox.information(self, "StudentHub", "Язык сохранён. Перезапусти приложение.")
    def do_logout(self):
        if QMessageBox.question(self, "StudentHub", "Выйти из аккаунта?") == QMessageBox.Yes:
            asyncio.ensure_future(self.app.api.logout()); save_json(PROFILE_CACHE, {}); self.refresh_account(); self.app.refresh_user_chip({}); self.app.show_login()

# ### --- СЕКЦИЯ СТАРОСТЫ (БЕЗ ИЗМЕНЕНИЙ) --- ###
# ### --- СЕКЦИЯ ГЛАВНОЙ СТРАНИЦЫ --- ###
RU_MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]

def _pairs_word(n):
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11: return "пара"
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14: return "пары"
    return "пар"

class HomePage(QWidget):
    def __init__(self, app):
        super().__init__(); self.app = app
        root = QVBoxLayout(self); root.setContentsMargins(32, 28, 32, 24); root.setSpacing(18)
        top = QHBoxLayout()
        tb = QVBoxLayout(); tb.setSpacing(2)
        self.hello = QLabel("Привет!"); self.hello.setObjectName("PageTitle")
        self.hello_sub = QLabel("Хорошего дня и продуктивной учёбы!"); self.hello_sub.setObjectName("PageSub")
        tb.addWidget(self.hello); tb.addWidget(self.hello_sub)
        top.addLayout(tb); top.addStretch()
        self.date_pill = QLabel(""); self.date_pill.setObjectName("DatePill")
        top.addWidget(self.date_pill, 0, Qt.AlignTop)
        root.addLayout(top)

        tiles = QHBoxLayout(); tiles.setSpacing(14)
        f1, self.n_pairs, self.h_pairs = self._tile("calendar", "BLUE", "Сегодня", "sched")
        f2, self.n_hw, self.h_hw = self._tile("hw", "VIOLET", "Домашние задания", "homework")
        f3, self.n_avg, self.h_avg = self._tile("grades", "GREEN", "Средний балл за ДЗ", "grades")
        for f in (f1, f2, f3): tiles.addWidget(f, 1)
        root.addLayout(tiles)

        cols = QHBoxLayout(); cols.setSpacing(14)
        self.pairs_card, self.pairs_rows = self._section("Ближайшие пары", "Все пары", "sched")
        self.events_card, self.events_rows = self._section("Последние события", None, None)
        cols.addWidget(self.pairs_card, 1); cols.addWidget(self.events_card, 1)
        root.addLayout(cols)

        banner = QFrame(); banner.setObjectName("Banner")
        bl = QVBoxLayout(banner); bl.setContentsMargins(24, 18, 24, 18); bl.setSpacing(2)
        bt = QLabel("Учись. Развивайся. Достигай."); bt.setObjectName("BannerTitle")
        bs = QLabel("StudentHub — твой помощник в учёбе"); bs.setObjectName("BannerSub")
        bl.addWidget(bt); bl.addWidget(bs)
        root.addWidget(banner); root.addStretch()
        self.refresh()

    def _tile(self, kind, key, caption, target):
        f = QFrame(); f.setObjectName("HomeTile"); f.setCursor(Qt.PointingHandCursor)
        f.mousePressEvent = lambda e, k=target: self.app.show_page(k)
        row = QHBoxLayout(f); row.setContentsMargins(16, 14, 16, 14); row.setSpacing(14)
        row.addWidget(icon_tile(kind, key, 46, 24), 0, Qt.AlignVCenter)
        col = QVBoxLayout(); col.setSpacing(1)
        cap = QLabel(caption); cap.setObjectName("HomeTileCap")
        num = QLabel("—"); num.setObjectName("HomeTileNum")
        hint = QLabel(""); hint.setObjectName("HomeTileHint")
        for w in (cap, num, hint):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True); col.addWidget(w)
        row.addLayout(col, 1)
        return f, num, hint

    def _section(self, title, link_text, target):
        card = QFrame(); card.setObjectName("Card")
        lay = QVBoxLayout(card); lay.setContentsMargins(18, 14, 18, 12); lay.setSpacing(4)
        head = QHBoxLayout()
        ttl = QLabel(title); ttl.setObjectName("SectionTitle"); head.addWidget(ttl); head.addStretch()
        if link_text:
            b = QPushButton(link_text); b.setObjectName("Link"); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=target: self.app.show_page(k)); head.addWidget(b)
        lay.addLayout(head)
        rows = QVBoxLayout(); rows.setSpacing(0); lay.addLayout(rows); lay.addStretch()
        return card, rows

    def _row(self, tile, title, sub="", right=""):
        f = QFrame(); f.setObjectName("HomeRow")
        h = QHBoxLayout(f); h.setContentsMargins(2, 8, 2, 8); h.setSpacing(12)
        h.addWidget(tile, 0, Qt.AlignVCenter)
        c = QVBoxLayout(); c.setSpacing(0)
        a = QLabel(title); a.setObjectName("RowTitle"); a.setWordWrap(True); c.addWidget(a)
        if sub:
            b = QLabel(sub); b.setObjectName("RowSub"); b.setWordWrap(True); c.addWidget(b)
        h.addLayout(c, 1)
        if right:
            r = QLabel(right); r.setObjectName("RowTime"); h.addWidget(r)
        return f

    def _empty(self, text):
        lb = QLabel(text); lb.setObjectName("RowSub"); lb.setContentsMargins(0, 14, 0, 14)
        return lb

    def _today_lessons(self):
        hub = self.app.pages.get("sched")
        today = datetime.date.today()
        out = []
        if hub is None: return out
        page = hub.mine
        if page._api_mode():
            key = today.strftime("%Y-%m-%d")
            for x in page.api_items:
                if (x.get("date") or "")[:10] == key:
                    n = x.get("lesson")
                    out.append((_fmt_time(x.get("started_at")), _fmt_time(x.get("finished_at")),
                                x.get("subject_name") or "", x.get("room_name") or "",
                                n if isinstance(n, int) else 0))
            out.sort(key=lambda r: (r[4], r[0]))
        else:
            sched = hub.schedules.get(DEFAULT_MINE_ID) or []
            wd = today.weekday()
            if wd < len(sched):
                for r, pair in enumerate(sched[wd]):
                    if pair and r < len(SLOTS):
                        out.append((SLOTS[r][0], SLOTS[r][1], pair[0], pair[1] if len(pair) > 1 else "", r + 1))
        return out

    def refresh(self):
        prof = load_json(PROFILE_CACHE, {})
        parts = (prof.get("full_name") or "").split()
        name = parts[1] if len(parts) >= 2 else (parts[0] if parts else "")
        self.hello.setText(f"Привет, {name}!" if name else "Привет!")
        today = datetime.date.today()
        self.date_pill.setText(f"Сегодня, {today.day} {RU_MONTHS[today.month - 1]} {today.year}")

        lessons = self._today_lessons()
        self.n_pairs.setText(f"{len(lessons)} {_pairs_word(len(lessons))}")

        items = load_json(HW_CACHE, [])
        states = [hw_state(it, today) for it in items]
        overdue = states.count("overdue"); todo = states.count("todo")
        self.n_hw.setText(str(todo + overdue))
        self.h_hw.setText(f"{overdue} просрочено" if overdue else "")
        marks = [((it.get("homework_stud") or {}).get("mark") or 0) for it in items]
        marks = [m for m in marks if m > 0]
        self.n_avg.setText(f"{sum(marks) / len(marks):.1f}" if marks else "—")

        clear_layout(self.pairs_rows)
        now = datetime.datetime.now().hour * 60 + datetime.datetime.now().minute
        upcoming = [r for r in lessons if (_hhmm(r[1]) or 0) > now][:4]
        if not lessons:
            self.pairs_rows.addWidget(self._empty("Сегодня пар нет"))
        elif not upcoming:
            self.pairs_rows.addWidget(self._empty("На сегодня пары закончились"))
        for st, en, subj, room, _n in upcoming:
            self.pairs_rows.addWidget(self._row(letter_tile(subj, 34, 14), subj, "", f"{st} – {en}"
                                                if not room else f"{st} – {en}  ·  {room}"))

        clear_layout(self.events_rows)
        recent = sorted(items, key=lambda x: x.get("creation_time") or "", reverse=True)[:4]
        if not recent:
            self.events_rows.addWidget(self._empty("Пока нет событий"))
        for it in recent:
            d = hw_parse_date(it.get("creation_time"))
            self.events_rows.addWidget(self._row(
                icon_tile("hw", "VIOLET", 34, 18), "Новое задание: " + hw_clean(it.get("theme"), 60),
                f"{it.get('name_spec') or ''} · {hw_fmt_date(d)}"))

    def on_show(self):
        self.refresh()


# ### --- СЕКЦИЯ ГЛАВНОГО ОКНА --- ###
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("StudentHub 6.1")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 720)

        icon = BASE / "StudentHub.ico"
        if icon.exists(): self.setWindowIcon(QIcon(str(icon)))

        self.api = ApiBridge()
        self.api.logged_in.connect(self.on_logged_in)
        self.api.login_failed.connect(self.on_login_failed)
        self.api.schedule_loaded.connect(self.on_schedule_loaded)
        self.api.homework_loaded.connect(self.on_homework_loaded)
        self.api.upload_done.connect(self.on_upload_done)
        self.api.delete_done.connect(self.on_delete_done)
        self.api.support_sent.connect(self.on_support_sent)
        self.api.grades_loaded.connect(self.on_grades_loaded)
        self.api.profile_loaded.connect(self.on_profile_loaded)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        sidebar = QFrame(); sidebar.setObjectName("Sidebar"); sidebar.setFixedWidth(232)
        sb = QVBoxLayout(sidebar); sb.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout(); head.setContentsMargins(20, 24, 20, 18); head.setSpacing(10)
        mark = QLabel("IT"); mark.setObjectName("LogoMark"); mark.setFixedSize(36, 36); mark.setAlignment(Qt.AlignCenter)
        logo = QLabel("StudentHub"); logo.setObjectName("Logo")
        head.addWidget(mark); head.addWidget(logo); head.addStretch(); sb.addLayout(head)

        self.stack = QStackedWidget()
        self.pages = {}
        self.nav = {}

        self.nav_kinds = {}
        def add_nav(key, label, widget, kind):
            btn = QPushButton("  " + label); btn.setObjectName("NavBtn"); btn.setCursor(Qt.PointingHandCursor)
            btn.setIconSize(QSize(20, 20))
            btn.clicked.connect(lambda _, k=key: self.show_page(k))
            sb.addWidget(btn); self.nav[key] = btn; self.nav_kinds[key] = kind
            self.pages[key] = widget; self.stack.addWidget(widget)

        self.login_page = LoginPage(self)
        self.pages["login"] = self.login_page
        self.stack.addWidget(self.login_page)

        add_nav("home", "Главная", HomePage(self), "home")
        add_nav("sched", t("sched"), ScheduleHub(self), "calendar")
        add_nav("journal", "Журнал", JournalPage(self), "grades")
        add_nav("homework", "ДЗ", HomeworkPage(self), "hw")
        add_nav("grades", "Оценки", GradesPage(self), "grades")
        add_nav("profile", t("profile"), ProfilePage(self), "profile")
        add_nav("settings", t("settings"), SettingsPage(self), "settings")
        # Поддержка автора доступна в навигации, как отдельный раздел.
        if DONATE_URL:
            add_nav("donate", t("donate"), DonatePage(self), "donate")
        # Обратная связь с автором сохранена отдельной страницей и не удалена.
        self.pages["support"] = SupportPage(self)
        self.stack.addWidget(self.pages["support"])  # без этого страница не открывалась из профиля

        sb.addStretch()
        self.user_chip = QFrame(); self.user_chip.setObjectName("UserChip")
        uc = QHBoxLayout(self.user_chip); uc.setContentsMargins(10, 10, 12, 10); uc.setSpacing(10)
        self.user_avatar = QLabel(""); self.user_avatar.setObjectName("Avatar")
        self.user_avatar.setFixedSize(36, 36); self.user_avatar.setAlignment(Qt.AlignCenter)
        ucol = QVBoxLayout(); ucol.setSpacing(0)
        self.user_name = QLabel(""); self.user_name.setObjectName("UserName"); self.user_name.setWordWrap(True)
        self.user_group = QLabel(""); self.user_group.setObjectName("UserGroup")
        ucol.addWidget(self.user_name); ucol.addWidget(self.user_group)
        uc.addWidget(self.user_avatar); uc.addLayout(ucol, 1)
        uc_wrap = QHBoxLayout(); uc_wrap.setContentsMargins(14, 0, 14, 8); uc_wrap.addWidget(self.user_chip)
        sb.addLayout(uc_wrap)
        self.refresh_user_chip(load_json(PROFILE_CACHE, {}))
        ver = QLabel("v6.1"); ver.setObjectName("LogoSub"); sb.addWidget(ver)
        self.style_nav(None)

        # Верхняя панель приложения: поиск, уведомления и пользователь.
        content = QWidget()
        content_col = QVBoxLayout(content)
        content_col.setContentsMargins(0, 0, 0, 0)
        content_col.setSpacing(0)
        topbar = QFrame(); topbar.setObjectName("TopBar"); topbar.setFixedHeight(58)
        top_layout = QHBoxLayout(topbar); top_layout.setContentsMargins(26, 8, 22, 8); top_layout.setSpacing(12)
        top_layout.addStretch(1)
        self.global_search = QLineEdit(); self.global_search.setObjectName("GlobalSearch")
        self.global_search.setPlaceholderText("⌕   Поиск по разделам...")
        self.global_search.setMaximumWidth(500); self.global_search.setMinimumWidth(220)
        top_layout.addWidget(self.global_search, 1)
        bell = QLabel("♧"); bell.setObjectName("TopIcon"); bell.setAlignment(Qt.AlignCenter); bell.setFixedSize(34, 34)
        top_layout.addWidget(bell)
        top_avatar = QLabel("ИТ"); top_avatar.setObjectName("TopAvatar"); top_avatar.setAlignment(Qt.AlignCenter); top_avatar.setFixedSize(34, 34)
        top_layout.addWidget(top_avatar)
        self.top_user_label = QLabel("Студент"); self.top_user_label.setObjectName("TopUser")
        top_layout.addWidget(self.top_user_label)
        content_col.addWidget(topbar)
        content_col.addWidget(self.stack, 1)
        root.addWidget(sidebar); root.addWidget(content, 1)

        self.status = QLabel("")
        self.status.setStyleSheet(f"color:{C['TEAL']};font-weight:600;padding:8px 20px;font-size:14px;")
        self.statusBar().addWidget(self.status); self.statusBar().setStyleSheet(f"background:{C['CARD']};border-top:1px solid {C['LINE']};")

        if self.api.is_logged_in():
            QTimer.singleShot(100, lambda: asyncio.ensure_future(self.startup_async()))
        else:
            self.show_login()

    async def startup_async(self):
        ok = await self.api.try_refresh()
        if not ok: self.show_login(); return
        try:
            client = await self.api._get_client()
            info = await client.user.get_info()
            prof = info.model_dump() if hasattr(info, "model_dump") else dict(info)
            save_json(PROFILE_CACHE, prof); self.on_logged_in(prof)
        except Exception: self.show_login()

    def style_nav(self, active):
        for k, b in self.nav.items():
            on = k == active
            b.setIcon(make_icon(self.nav_kinds.get(k, "home"), C["ON_TEAL"] if on else C["MUTED"]))

    def show_login(self):
        self.stack.setCurrentWidget(self.login_page)
        for b in self.nav.values(): b.setProperty("active", "false"); b.style().unpolish(b); b.style().polish(b)
        self.style_nav(None)

    def show_page(self, key):
        if key not in self.pages: return
        self.stack.setCurrentWidget(self.pages[key])
        if hasattr(self.pages[key], "on_show"): self.pages[key].on_show()
        for k, b in self.nav.items(): b.setProperty("active", "true" if k == key else "false"); b.style().unpolish(b); b.style().polish(b)
        self.style_nav(key)

    def refresh_user_chip(self, prof):
        name = (prof or {}).get("full_name") or ""
        group = (prof or {}).get("group_name") or ""
        self.user_chip.setVisible(bool(name))
        self.user_name.setText(name); self.user_group.setText(group or "Студент")
        if hasattr(self, "top_user_label"):
            self.top_user_label.setText(name.split()[0] if name else "Студент")
        letters = "".join(w[0] for w in name.split()[:2]).upper()
        self.user_avatar.setText(letters or "IT")

    def on_logged_in(self, prof):
        self.refresh_user_chip(prof)
        self.login_page.on_success(); self.pages["profile"].render(prof); self.pages["settings"].refresh_account()
        if "journal" in self.pages: self.pages["journal"].refresh_data()
        self.show_page("home"); self.pages["sched"].reload()

    def on_login_failed(self, msg): self.login_page.on_failed(msg)

    def on_schedule_loaded(self, items):
        if "sched" in self.pages: self.pages["sched"].on_loaded(items)
        if "home" in self.pages: self.pages["home"].refresh()

    def on_homework_loaded(self, items, err):
        self.pages["homework"].on_loaded(items, err)
        if "grades" in self.pages: self.pages["grades"].render()
        if "journal" in self.pages: self.pages["journal"].refresh_data()
        if "home" in self.pages: self.pages["home"].refresh()

    def on_upload_done(self, ok, msg):
        self.pages["homework"].action_finished()
        QMessageBox.information(self, "StudentHub", msg)
        if ok: asyncio.ensure_future(self.api.load_homework())

    def on_delete_done(self, ok, msg):
        self.pages["homework"].action_finished()
        QMessageBox.information(self, "StudentHub", msg)
        if ok: asyncio.ensure_future(self.api.load_homework())

    def on_support_sent(self, ok, msg): self.pages["support"].on_sent(ok, msg)

    def on_grades_loaded(self, data): self.pages["grades"].on_loaded(data)

    def on_profile_loaded(self, prof):
        self.refresh_user_chip(prof)
        self.pages["profile"].render(prof)
        if "home" in self.pages: self.pages["home"].refresh()

def main():
    app = QApplication(sys.argv); app.setStyle("Fusion")
    font = QFont("Segoe UI", 10)
    try: font.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Noto Sans", "Helvetica Neue", "Arial"])
    except Exception: pass
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias); app.setFont(font)
    app.setStyleSheet(build_style())
    if HAS_QASYNC:
        loop = QEventLoop(app); asyncio.set_event_loop(loop)
    else: loop = None
    win = MainWindow(); win.show()
    if loop is not None:
        with loop: loop.run_forever()
    else: sys.exit(app.exec())

if __name__ == "__main__":
    main()
