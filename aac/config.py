"""Настройки по умолчанию, ключи, модели, клавиши, подсказки для нейросетей."""


import os


VERSION = "15.11"
import sys as _sys
FROZEN = bool(getattr(_sys, "frozen", False))      # собранная программа (AAC Translator.exe), без Python
# папка программы (настройки, словарь, история, иконки): рядом с .exe или с aac_translator.py
APP_DIR = (os.path.dirname(_sys.executable) if FROZEN
           else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ===================== НАСТРОЙКИ =====================
# Кто переводит:
#   "groq_ocr" / "gemini_ocr" / "claude_ocr" — «OCR + ИИ»: текст распознаётся на ПК, нейросеть переводит
#               уже готовый текст с учётом предыдущих реплик. В разы меньше токенов, чем с картинкой.
#   "google"  — текст распознаётся на вашем ПК (встроенный OCR Windows) и переводится Google Переводчиком.
#               Бесплатно, без ключа, без жёстких лимитов. Перевод «машинный», без понимания сцены.
#   "microsoft" — то же самое, но переводит Microsoft Переводчик (как в браузере Edge). Бесплатно, без ключа.
#   "deepl"   — то же самое, но переводит DeepL (бесплатный ключ: 500 000 символов в месяц)
#   "gemini"  — облако Google (бесплатно, но лимит запросов в минуту/день)
#   "mistral" — облако Mistral (бесплатно, 1 запрос в секунду, очень щедрый месячный лимит)
#   "groq"    — облако Groq (бесплатно, очень быстро, ~30 запросов в минуту)
#   "claude"  — Claude от Anthropic (платно, но копейки; стабильно и хорошо переводит на русский)
#   "ollama"  — нейросеть на вашем компьютере (бесплатно, без лимитов и интернета,
#               но нужна видеокарта и она будет делить её с игрой)
# Это значения по умолчанию. Переводчик удобнее выбирать в системной панели —
# выбор запоминается и не сбрасывается при обновлении скрипта.
PROVIDER = "groq_ocr"

# Запасные переводчики: если основной упёрся в лимит или сломался, скрипт сам попробует эти по порядку.
# Переводчики без ключа пропускаются. Пример: ["mistral", "groq"]
FALLBACK_PROVIDERS = ["google"]

# --- распознавание текста и машинный перевод (режимы "google" и "deepl") ---
OCR_LANGUAGE = "en-US"        # язык текста в игре для распознавания
SOURCE_LANG = "en"            # с какого языка переводить
TARGET_LANG_CODE = "ru"       # на какой
DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "ВСТАВЬТЕ_СЮДА_КЛЮЧ_DEEPL")
SHOW_OCR_IN_LOG = True        # показывать в журнале, что распознал OCR (удобно для проверки; потом можно False)

# --- настройки Mistral (бесплатно: console.mistral.ai -> API Keys, тариф Free/Experiment) ---
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "ВСТАВЬТЕ_СЮДА_КЛЮЧ_MISTRAL")
MISTRAL_MODEL = "mistral-small-2603"     # видит картинки; точное название — из списка Admin -> API -> Rate limits

# --- настройки Groq (бесплатно: console.groq.com -> API Keys) ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "ВСТАВЬТЕ_СЮДА_КЛЮЧ_GROQ")
# Модели Groq, которые понимают картинки, по очереди. У каждой свой бесплатный лимит;
# если одна упёрлась в лимит или пропала — берётся следующая. Проверить список: py groq_test.py
GROQ_MODELS = [
    "qwen/qwen3.8-27b",   # проверено groq_test.py: видит картинки, 1000 запросов/день, 8000 токенов/мин
]
# Для режима «OCR + ИИ» картинки не нужны — подойдут и текстовые модели (у каждой свой лимит)
GROQ_TEXT_MODELS = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]

# --- настройки Claude (используются, если PROVIDER = "claude") ---
# Ключ: https://platform.claude.com -> API Keys (нужно пополнить баланс, хватит $5)
CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "ВСТАВЬТЕ_СЮДА_КЛЮЧ_CLAUDE")
CLAUDE_MODEL = "claude-haiku-5-5"       # самая быстрая и дешёвая модель Claude
# цены Haiku 5.5, $ за миллион токенов (запросы до 100k токенов) — для счётчика расходов в панели
CLAUDE_PRICE_IN = 0.10
CLAUDE_PRICE_OUT = 0.50

API_KEY = os.environ.get("GEMINI_API_KEY", "ВСТАВЬТЕ_СЮДА_КЛЮЧ")

# --- настройки Ollama (используются, если PROVIDER = "ollama") ---
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3-vl:4b-instruct"   # нужна модель, которая видит картинки. Альтернатива: "gemma3:4b"
OLLAMA_TIMEOUT = 90                     # первый запрос дольше: модель загружается в видеопамять
OLLAMA_CTX = 8192          # «память» модели в токенах (картинка + инструкция + ответ); 4096 по умолчанию мало
OLLAMA_MAX_TOKENS = 400    # максимум длины ответа — не даёт модели «зациклиться» и писать бесконечно
OLLAMA_IMAGE_SIDE = 1024   # картинку для локальной модели уменьшаем сильнее — быстрее и меньше токенов

# Модели по очереди: если первая перегружена (ошибка 503), берётся следующая
# У каждой модели свой бесплатный лимит, поэтому несколько моделей = больше переводов в минуту.
# Отключённые Google модели скрипт сам пропускает (видно в журнале и в панели).
MODELS = [
    "gemini-flash-lite-latest",   # самая быстрая, для перевода её хватает
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
]
TARGET_LANG = "русский"

HOTKEY_AUTO = "f8"
HOTKEY_ONCE = "f7"
HOTKEY_SUBS_ONCE = "shift+f8"       # перевести субтитры один раз (по сохранённой области, без автоперевода)
HOTKEY_ANSWERS_ONCE = "shift+f7"   # перевести варианты ответа один раз (по сохранённой области)
HOTKEY_SELECT = "f9"
HOTKEY_SELECT_ANSWERS = "shift+f9"
HOTKEY_SELECT_SUBS2 = "ctrl+f9"    # вторая область реплик (НПС говорят мимоходом в другом месте)
HOTKEY_TOGGLE = "f10"
HOTKEY_RESET = "f11"
HOTKEY_LAYOUT = "ctrl+shift+l"   # режим расстановки окон (L — layout); можно поменять на любое сочетание
HOTKEY_PANEL = "f6"
HOTKEY_QUIT = "ctrl+shift+q"
HOTKEY_TTS = "ctrl+shift+v"       # озвучка субтитров вкл/выкл
HOTKEY_ONCE_TTS = "ctrl+f7"          # обвести текст → перевести и прочитать вслух (книги, письма, задания)
HOTKEY_FLIP_GENDER = "ctrl+shift+g"
HOTKEY_SELECT_CHAT = "ctrl+shift+f9"   # обвести окно игрового чата
HOTKEY_CHAT_COMPOSE = "ctrl+shift+c"
HOTKEY_CHAT_ONCE = "ctrl+shift+f8"
HOTKEY_MENU_LEARN = "ctrl+shift+m"     # запомнить меню игры (пока оно открыто — пауза)     # перевести чат сейчас (даже если автоперевод выключен)   # написать в чат по-русски → английский перевод в буфер обмена   # «не тот голос»: сменить пол последнего говорящего
HOTKEY_REPEAT = "ctrl+f8"         # повторить последнюю реплику: показать и прочитать заново
HOTKEY_SUPPRESS = False           # клавиши программы не доходят до игры (перехватываются) — раздел «Клавиши»
HOTKEY_TOOLTIP = "mouse_x2"       # перевод под мышкой: подсказка предмета — большим окном, имя/табличка — плашкой

OVERLAY_WIDTH = 560          # ширина окна субтитров, px (если оно не привязано к области)
SUBS_ABOVE_REGION = True     # перевод субтитров всегда показывать прямо над их областью
ANCHOR_GAP = 6               # отступ между переводом и областью субтитров, px
QUEST_WIDTH = 620            # ширина окна перевода заданий (F7), px
PANEL_WIDTH = 740            # ширина системной панели, px
OVERLAY_ALPHA = 0.88         # прозрачность окна (0..1)
FONT = ("Segoe UI", 13)
TEXT_COLOR = "#eeeeee"       # цвет перевода (свой у каждой игры — раздел «Окна перевода»)
TEXT_MODE = "box"            # "box" — тёмная плашка, "outline" — без плашки, обводка букв
GRIP_COLOR = "#2a2a2a"         # правый край окна перевода, за который меняется ширина
GRIP_ACTIVE_COLOR = "#3c9a5f"  # он же в режиме расстановки
HISTORY_FONT = ("Segoe UI", 11)
SUBS_HISTORY = 1             # сколько предыдущих реплик показывать над текущей (0 — не показывать)
MAX_IMAGE_SIDE = 1600        # уменьшаем большие скриншоты — быстрее
REQUEST_TIMEOUT = 30         # сколько секунд ждать ответа от Gemini

# --- автоперевод ---
POLL_INTERVAL = 0.25                 # как часто проверять область, сек
OCR_CONFIRM_INTERVAL = 0.15          # как часто перечитывать новый текст (пока он «дописывается»), сек
MIN_REQUEST_GAP = 1.5        # не чаще одного запроса в N сек (бесплатный лимит)
TEXT_BRIGHTNESS = 190        # пиксели ярче этого считаются «текстом» (субтитры обычно светлые)
CHANGE_THRESHOLD = 0.006     # насколько должен измениться текст, чтобы считать реплику новой (меньше = чувствительнее)
STABLE_THRESHOLD = 0.003     # текст «успокоился» (дописался) — можно переводить
HIDE_DELAY = 0.8             # через сколько секунд после исчезновения субтитров прятать перевод
GONE_RATIO = 0.3             # «текста» стало меньше 30% от переведённого — считаем, что реплика исчезла
MAX_SHOW_TIME = 60           # перевод в любом случае прячется через N сек без новых реплик
KEEP_UNTIL_NEXT = False      # не прятать перевод, пока не появится новая реплика (настройки)
ANSWERS_TEXT_BRIGHTNESS = 150   # варианты ответа часто серые/жёлтые — порог пониже
ANSWERS_SIDE = "left"        # где показывать перевод ответов: "left" (слева от области), "right" или "above"
ANSWERS_WIDTH = 420          # ширина окна перевода ответов, px (для left/right)
FORCE_EVERY = 3.0            # если фон за текстом светлый и всё время мигает — всё равно переводить раз в N сек

SETTINGS_FILE = os.path.join(APP_DIR, "aac_translator_settings.json")

# Инструкции для нейросети написаны по-английски: так они занимают в 2–3 раза меньше токенов
# (важно для лимитов Groq/Mistral), а перевод всё равно выдаётся на TARGET_LANG_EN.
TARGET_LANG_EN = "Russian"

PROMPT = f"""Screenshot from the MMORPG ArcheAge Chronicles (quest, dialogue or cutscene subtitles).
Translate all game text into {TARGET_LANG_EN}.
- Keep structure: speaker name, line, quest title, description, objectives — each on its own line.
- Items, skills, places, NPC names: translate, original in brackets, e.g. «Клинок рассвета (Dawn Blade)».
- Keep numbers and stats unchanged. Skip UI fragments, player nicknames, timers.
- Ignore the Windows watermark ("Activate Windows" / «Активация Windows»).
- Translate each line once, no repeats. Output only the translation.
If there is no text, output exactly: НЕТ_ТЕКСТА"""

ANSWERS_PROMPT = f"""Screenshot of the player's dialogue reply options in the MMORPG ArcheAge Chronicles.
{{context}}
Translate each option into {TARGET_LANG_EN}, so it fits what the NPC said.
- Keep the order, one option per line, numbered 1. 2. 3. Exactly as many options as in the image.
- Tags like [Quest], [Leave]: translate inside square brackets.
- Items, places, NPC names: translate, original in brackets.
- Ignore the Windows watermark. No repeats. Output only the translation.
If there are no options, output exactly: НЕТ_ТЕКСТА"""


TOOLTIP_PROMPT = f"""Screenshot of a tooltip (item, skill, buff or UI hint) from the MMORPG ArcheAge Chronicles.
Translate it into {TARGET_LANG_EN}.
- Keep the layout: title first, then every stat / line on its own line.
- Keep numbers, percentages, +/- signs and time values unchanged.
- The title (item/skill name): translation, original in brackets. Short, clear wording, as in a localized game.
- Ignore the Windows watermark. Output only the translation.
If there is no text, output exactly: НЕТ_ТЕКСТА"""

# ---------- подсказки под мышкой (предметы, навыки) ----------
TOOLTIP_BOX = (1100, 900)    # сколько экрана вокруг курсора искать подсказку (ширина, высота), px
TOOLTIP_WIDTH = 420          # ширина окна перевода подсказки
TOOLTIP_MOVE_HIDE = 260      # увели мышку дальше стольких px от места нажатия — перевод подсказки прячется
WORD_MOVE_HIDE = 150         # надпись: увели мышку дальше — плашка прячется
WORD_SHOW_TIME = 10          # и в любом случае через столько секунд
TOOLTIP_SHOW_TIME = 40       # и в любом случае через столько секунд

# ---------- игровой чат ----------
CHAT_POLL = 1.0          # как часто читать область чата, сек
CHAT_LINES = 8           # сколько сообщений видно в окошке без ограничения высоты
CHAT_HISTORY = 200       # сколько сообщений хранится для прокрутки колесом мыши
CHAT_WIDTH = 460
CHAT_COVER = False       # перевод поверх самого окна чата (на месте оригинала), той же ширины и высоты
CHAT_HEIGHT = 0          # предельная высота окошка чата, px (0 — по числу сообщений)
CHAT_ALPHA = 0.85        # непрозрачность окошка чата (отдельно от остальных окон перевода)
CHAT_FG = "#eeeeee"      # цвет текста перевода чата
CHAT_BLINK_EVERY = 3     # если Windows не прячет окно от снимков: как часто «моргать», чтобы прочитать чат под ним

MENU_MATCH = 45            # меню: насколько может отличаться яркость (0..255)
MENU_CORR = 0.6            # меню: насколько должны совпасть очертания (надписи, рамки), 0..1

# ---------- обновления ----------
UPDATE_REPO = "kz12oleg12/aac-translator"   # откуда брать новые версии (GitHub)
UPDATE_BRANCH = "main"
UPDATE_CHECK = True                         # проверять при запуске и потом регулярно
UPDATE_EVERY_SECONDS = 0                    # 0 — проверять только при запуске и по кнопке «Проверить обновления»
UPDATE_AUTO = False                         # новая версия есть при запуске программы — поставить сразу (выкл. — только кнопка)

# ---------- пауза, когда игра не на переднем плане ----------
GAMES_ONLY = True          # переводить только игры из списка пресетов (в других программах — пауза)
PAUSE_OUTSIDE_GAME = True      # значение по умолчанию; переключается галочкой в панели


# ---------- настройки внешнего вида и история переводов ----------
SHOW_ORIGINAL = False      # показывать оригинал мелким шрифтом под переводом
SAVE_HISTORY = True        # сохранять все переводы в папку history (по файлу на день)

# --- озвучка перевода субтитров (голос Windows) — меняется в окне «Настройки» ---
WEB_PANEL = True           # новая панель на HTML (WebView2); False — прежняя на tkinter
SHOW_ON_STREAM = False     # окна перевода видны на трансляции/записи экрана (Discord, OBS)
CACHE_ENABLED = True       # кэш переводов: одинаковая фраза переводится один раз, дальше мгновенно и без запросов
CACHE_MAX = 20000          # сколько фраз помнить (старые забываются)
GLOSSARY_AUTO = True       # словарь пополняется сам: имена говорящих и названия «Перевод (Original)» из переводов
SKIP_SYSTEM = False        # системные сообщения игры в областях субтитров не переводить и не озвучивать
SHOW_INDICATOR = True      # маленький значок «● AAC: перевод вкл» поверх игры, пока включён автоперевод
ANSWERS_DOCKED = False     # ответы одним окном с субтитрами (вплотную под ними)
TTS_ENABLED = False        # озвучивать перевод субтитров
TTS_ENGINE = "neural"     # "neural" — нейроголоса Microsoft (онлайн), "silero" — Silero (офлайн), "windows"
TTS_NEURAL_VOICE = "ru-RU-SvetlanaNeural"
TTS_SILERO_VOICE = "xenia"   # офлайн-голос Silero: xenia, baya, kseniya, aidar, eugene
TTS_VOICE = ""             # имя голоса Windows ("" — голос по умолчанию)
TTS_RATE = 0               # скорость: от -10 (медленно) до 10 (быстро)
TTS_VOLUME = 100           # громкость 0..100
TTS_FINISH_LINE = True     # дочитывать реплику до конца (следующая — сразу после, чуть быстрее)
TTS_PER_CHARACTER = True   # свой голос для каждого персонажа (по имени в субтитрах)
TTS_RUSSIAN_ONLY = False
TTS_EXPRESSIVE = True      # интонация: «!» — живее и громче, «?» — выше, «…» — медленнее
TTS_VARY_IN_GENDER = True  # у каждого мужчины/женщины свой голос; выкл — всем мужчинам один, всем женщинам один
# голос для всех мужчин и для всех женщин (по движкам) — когда TTS_VARY_IN_GENDER выключено
TTS_DEFAULT_VOICES = {"neural": {"m": "", "f": ""}, "silero": {"m": "", "f": ""}}   # персонажам — только русские голоса (без многоязычных с акцентом)
TTS_READ_NAME = False      # читать имя говорящего перед репликой

# Слова интерфейса игры, которые попадают в область, но переводить их не нужно (кнопки и т.п.).
# Свои можно добавить в словарь (glossary.txt) строкой вида:  - Слово
IGNORE_UI_WORDS = ["skip", "next", "continue", "back", "auto", "log", "close", "ok", "cancel",
                   "accept", "decline", "menu", "hide", "esc", "f", "space", "enter", "press"]
UNSTABLE_READS = 15        # подсказка «сузьте область»: столько разных прочтений подряд…
UNSTABLE_SECONDS = 8       # …и дольше стольких секунд (дописывающийся текст не в счёт)
TEXT_SAME_RATIO = 0.9      # насколько распознанный текст должен совпасть с прошлым кадром, чтобы считаться «устоявшимся»
COOLDOWN_429 = 60     # лимит запросов: модель отдыхает минуту
COOLDOWN_503 = 20     # перегрузка: 20 секунд
# Минимальный промежуток между запросами к одному сервису (бесплатный Mistral — 1 запрос в секунду).
# Запросы субтитров и ответов к одному сервису идут по очереди, а не одновременно.
PROVIDER_MIN_GAP = {"mistral": 1.2, "groq": 1.0}
# Сколько «отдыхает» сервис после отказа по лимиту
PROVIDER_COOLDOWN = {"mistral": 10, "groq": 20, "google": 30, "microsoft": 30,
                     "groq_ocr": 15, "mistral_ocr": 10}


COMPAT_IMAGE_SIDE = 800    # для Mistral/Groq картинку уменьшаем: лимит у них считается в токенах в минуту
COMPAT_MAX_TOKENS = 350    # резерв на ответ; Groq засчитывает его в лимит токенов, поэтому не завышаем
# --- ИИ-редактор: правит перевод основного переводчика с учётом контекста (раздел «Переводчики») ---
EDITOR_ON = False          # ИИ-редактор включён
EDITOR = "groq"            # какая нейросеть правит: "groq", "gemini", "mistral", "claude"
EDITOR_WAIT = 1.2          # сколько ждать редактора, с; не успел — показываем перевод основного, потом подменяем
EDITOR_SCENE_EVERY = 6     # раз в столько реплик обновлять «память сцены»
EDITOR_LOG = True          # писать в журнал, что редактор поправил
HISTORY_LINES = 4                         # сколько предыдущих реплик давать нейросети для контекста

TEXT_PROMPT = f"""You translate dialogue and quest text from the MMORPG ArcheAge Chronicles into {TARGET_LANG_EN}.
The text below was read from the screen by OCR and may contain recognition errors — silently fix obvious ones
(e.g. "aut the moment" -> "But the moment"). Ignore UI garbage and the Windows watermark.
- Keep the structure: a speaker name stays on its own line.
- Character, place and item names: render naturally in {TARGET_LANG_EN}, keep them consistent with the context.
- Natural, lively game dialogue, not word-for-word.
{{context}}
Text to translate:
<<<
{{text}}
>>>
Output only the translation. If there is no meaningful text, output exactly: НЕТ_ТЕКСТА"""

TEXT_TOOLTIP_PROMPT = f"""You translate a tooltip (item, skill, buff or UI hint) from the MMORPG ArcheAge Chronicles into {TARGET_LANG_EN}.
The text was read by OCR and may contain small errors — fix obvious ones. Ignore UI garbage and the Windows watermark.
- Keep the layout: the title first, then every stat / line on its own line, in the same order.
- Keep numbers, percentages, +/- signs and time values unchanged.
- Title (item/skill name): translation, original in brackets. Short, clear wording, as in a localized game.
{{context}}
Tooltip:
<<<
{{text}}
>>>
Output only the translation. If there is no meaningful text, output exactly: НЕТ_ТЕКСТА"""

TEXT_ANSWERS_PROMPT = f"""You translate the player's dialogue reply options from the MMORPG ArcheAge Chronicles into {TARGET_LANG_EN}.
The text was read by OCR and may contain small errors — fix obvious ones. Ignore UI garbage.
Each option is on its own line. Translate each one so it fits the conversation; output them numbered 1. 2. 3.,
exactly as many options as given. Tags like [Quest], [Leave] — translate inside square brackets.
{{context}}
Options:
<<<
{{text}}
>>>
Output only the numbered translation. If there are no options, output exactly: НЕТ_ТЕКСТА"""


WATERMARK_WORDS = ("активация windows", "activate windows", "чтобы активировать windows",
                   "to activate windows", "перейдите в раздел", "go to settings to activate")


SINGLE_PORT = 47911   # «замок» от второй копии программы
