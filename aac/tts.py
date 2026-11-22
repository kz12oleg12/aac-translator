"""Озвучка перевода субтитров.

Два движка:
  * neural  — нейроголоса Microsoft (как «Читать вслух» в Edge): живые, приятные, нужен интернет,
              пакет edge-tts; звук играется через встроенный в Windows MCI (без лишних библиотек);
  * silero  — офлайн-нейроголоса Silero (tts_silero.py): быстро, без интернета, нужен PyTorch;
  * windows — встроенный синтезатор Windows (System.Speech), работает без интернета.
Если нейроголос недоступен, реплика читается голосом Windows.
"""
import asyncio
import base64
import ctypes
import os
import queue
import tempfile
import re
import subprocess
import sys
import threading
import time

from . import config, core, tts_silero, voices

# PowerShell-процесс, который держит синтезатор речи и читает команды построчно: «команда<TAB>текст».
_PS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::InputEncoding = [Text.Encoding]::UTF8
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SetOutputToDefaultAudioDevice()
[Console]::Out.WriteLine('ready')
while (($line = [Console]::In.ReadLine()) -ne $null) {
    $p = $line.Split("`t", 2)
    $cmd = $p[0]; $arg = if ($p.Length -gt 1) { $p[1] } else { '' }
    switch ($cmd) {
        'say'   { $s.SpeakAsyncCancelAll(); [void]$s.SpeakAsync($arg) }
        'add'   { [void]$s.SpeakAsync($arg) }
        'stop'  { $s.SpeakAsyncCancelAll() }
        'rate'  { $s.Rate = [int]$arg }
        'vol'   { $s.Volume = [int]$arg }
        'voice' { try { $s.SelectVoice($arg) } catch {} }
        'list'  {
            foreach ($v in $s.GetInstalledVoices()) {
                if ($v.Enabled) { [Console]::Out.WriteLine('voice' + "`t" + $v.VoiceInfo.Name + "`t" + $v.VoiceInfo.Culture.Name) }
            }
            [Console]::Out.WriteLine('end')
        }
    }
}
"""

_proc = None
_lock = threading.Lock()
_voices = []
_voices_ready = threading.Event()
_ready = threading.Event()
_failed = False


def available():
    return sys.platform == "win32" and not _failed


def _reader(proc):
    """Читает ответы PowerShell (список голосов)."""
    buf = []
    for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").strip()
        if line == "ready":
            _ready.set()
        elif line.startswith("voice\t"):
            _, name, lang = (line.split("\t") + ["", ""])[:3]
            buf.append((name, lang))
        elif line == "end":
            _voices[:] = buf
            buf = []
            _voices_ready.set()


def _start():
    """Запускает синтезатор (один раз)."""
    global _proc, _failed
    if _proc is not None and _proc.poll() is None:
        return True
    if not available():
        return False
    try:
        encoded = base64.b64encode(_PS_SCRIPT.encode("utf-16-le")).decode()  # без проблем с кавычками
        _proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        _failed = True
        core.log(f"Озвучка недоступна: {e}", "error")
        return False
    threading.Thread(target=_reader, args=(_proc,), daemon=True).start()
    _ready.clear()

    def watchdog(proc=_proc):
        # если синтезатор Windows не ответил — сообщаем в журнал
        if not _ready.wait(10):
            code = proc.poll()
            core.log("Озвучка не запустилась: синтезатор речи Windows не ответил"
                     + (f" (код {code})" if code is not None else "") +
                     ". Проверьте, что PowerShell не заблокирован антивирусом.", "error")
        else:
            core.log("Озвучка готова", "ok")
    threading.Thread(target=watchdog, daemon=True).start()
    _send("rate", config.TTS_RATE)
    _send("vol", config.TTS_VOLUME)
    if config.TTS_VOICE:
        _send("voice", config.TTS_VOICE)
    return True


_out_q = queue.Queue()
_writer = {"t": None}


def _writer_loop():
    """Пишем команды озвучке Windows в отдельном потоке: если она подвиснет, окна программы не зависнут."""
    while True:
        line = _out_q.get()
        p = _proc
        if p is None or p.poll() is not None:
            continue
        try:
            p.stdin.write(line)
            p.stdin.flush()
        except Exception:
            pass


def _send(cmd, arg=""):
    if _proc is None or _proc.poll() is not None:
        return
    text = str(arg).replace("\t", " ").replace("\r", " ").replace("\n", ". ")
    if _writer["t"] is None:
        _writer["t"] = threading.Thread(target=_writer_loop, daemon=True)
        _writer["t"].start()
    _out_q.put(f"{cmd}\t{text}\n".encode("utf-8"))


_NAME_PREFIX = re.compile(r"^[A-ZА-ЯЁ][^\s:.!?…,]{0,24}(?:\s+[A-ZА-ЯЁ][^\s:.!?…,]{0,24}){0,2}\s*[:：]\s*(\S.*)$")


def _sounds_like(ru, en):
    """«Итан» похоже на «Ethan»? Сравниваем с грубой русской записью английского имени."""
    import difflib
    def norm(t):
        return re.sub(r"[^а-яё]", "", t.lower()).replace("ё", "е")
    a = norm(ru)
    b = norm(tts_silero.translit(en))
    if not a or not b:
        return False
    if difflib.SequenceMatcher(None, a, b).ratio() >= 0.6 or (len(a) >= 3 and a[:3] == b[:3]):
        return True
    # имя с должностью: «Архивариус Ротильд» ↔ «Archivist Rotild» — хватит совпадения самого имени
    ru_words = [norm(w) for w in ru.split() if len(norm(w)) >= 4]
    en_words = [norm(tts_silero.translit(w)) for w in en.split() if len(w) >= 4]
    return any(difflib.SequenceMatcher(None, x, y).ratio() >= 0.7 for x in ru_words for y in en_words)


def _strip_speaker(text, orig):
    """Имя говорящего осталось в начале перевода («Итан Аренда…», «Итан — Аренда…», «Ethan: …»)?
    Берём имя из оригинала (первая строка «Ethan»), смотрим, как его уже переводили, и отрезаем."""
    try:
        sp = voices.speaker("", orig)
    except Exception:
        sp = None
    if not sp:
        return text
    key, en, _ = sp
    names = [en]
    c = dict(voices.all_chars()).get(key)
    if c and c.get("ru"):
        names.append(c["ru"])
    for name in sorted({n for n in names if n}, key=len, reverse=True):
        m = re.match(r"\s*" + re.escape(name) + r"\s*(?:[:：—–\-/,.]\s*|\s+(?=[A-ZА-ЯЁ«\"„]))", text, re.I)
        if m and len(text) - m.end() >= 4:
            return text[m.end():]
    # имя ещё не знаем по-русски: в оригинале имя из N слов, а перевод начинается с N слов с заглавной
    # и дальше снова заглавная буква — значит, это «Имя Реплика…»
    k = len(en.split())
    m = re.match(r"\s*((?:[A-ZА-ЯЁ][\w'’-]*\s+){%d})?" % 0 + r"\s*([A-ZА-ЯЁ][\w'’-]*(?:\s+[A-ZА-ЯЁ][\w'’-]*){%d})\s*[:：—–]\s*(\S.*)$" % (k - 1),
                 text)
    if m and len(m.group(2)) <= 25 and _sounds_like(m.group(2), en):
        return m.group(3)                      # «Итан — Аренда…», «Итан: …»
    words = text.split()
    if len(words) > k and all(w[:1].isupper() for w in words[:k + 1]) and not re.search(r"[.!?,:]", " ".join(words[:k])):
        guess = " ".join(words[:k])
        if len(guess) <= 25 and _sounds_like(guess, en):
            return " ".join(words[k:])
    return text


def speech_text(translation, orig=None):
    """Что читать вслух: без имени говорящего (если не включено), без служебных значков."""
    lines = [ln.strip() for ln in translation.splitlines() if ln.strip()]
    if not config.TTS_READ_NAME and len(lines) > 1:
        first = lines[0]
        # первая строка — имя говорящего: короткая и без знаков конца предложения
        if len(first.split()) <= 3 and not re.search(r"[.!?…:,]", first):
            lines = lines[1:]
    if not config.TTS_READ_NAME and lines:
        # «Полдат: За твоё здоровье!» — имя через двоеточие в той же строке
        m = _NAME_PREFIX.match(lines[0])
        if m:
            lines[0] = m.group(1)
    text = " ".join(lines)
    if not config.TTS_READ_NAME and orig and len(lines) >= 1:
        text = _strip_speaker(text, orig)
    text = re.sub(r"\s*\([^)]*\)", "", text)          # «Клинок (Dawn Blade)» → «Клинок»
    return re.sub(r"[⏳❌✅📜💬]", "", text).strip()


def speak_subtitle(translation, seen=None, orig=None):
    """Озвучить перевод субтитров (голосом персонажа, если включено «разные голоса»)."""
    if not config.TTS_ENABLED or not translation:
        return
    if config.SKIP_SYSTEM and orig and voices.is_system(orig):
        return  # системное сообщение игры — не озвучиваем
    text = speech_text(translation, orig)
    if sum(ch.isalpha() for ch in text) < 4:
        return  # обрывки и одиночные слова интерфейса не читаем
    vp = None
    try:
        key = voices.note_line(translation, orig)
        if config.TTS_PER_CHARACTER:
            vp = voices.voice_for(key)
    except Exception as e:
        core.log(f"Голоса персонажей: {e}", "error")
    _say(text, seen, vp)


def _say(text, seen=None, voice_pitch=None):
    """Прочитать текст выбранным движком. voice_pitch — (голос, сдвиг высоты) персонажа или None."""
    if not text:
        return
    if engine_ready():
        _neural.say(text, seen, voice_pitch)
    else:
        _windows_queue(text)


def _windows_say(text):
    if _start():
        _send("say", text)


def _windows_queue(text):
    if _start():
        _send("add" if config.TTS_FINISH_LINE else "say", text)


def stop():
    _neural.stop()
    _send("stop")


def apply_settings():
    """Голос, скорость и громкость из настроек — сразу в синтезатор."""
    if _proc is None:
        return
    _send("rate", config.TTS_RATE)
    _send("vol", config.TTS_VOLUME)
    if config.TTS_VOICE:
        _send("voice", config.TTS_VOICE)


def list_voices(timeout=5):
    """[(имя, язык)] установленных голосов Windows."""
    if not _start():
        return []
    _voices_ready.clear()
    _send("list")
    _voices_ready.wait(timeout)
    return list(_voices)


def toggle():
    """Горячая клавиша: озвучка вкл/выкл."""
    config.TTS_ENABLED = not config.TTS_ENABLED
    core.save_settings(tts_enabled=config.TTS_ENABLED)
    if config.TTS_ENABLED:
        core.log("Озвучка субтитров включена", "ok")
        if not engine_ready():
            _start()
        else:
            warm()
    else:
        stop()
        core.log("Озвучка субтитров выключена")
    core.events.put(("tts_changed", None))


def say_test(voice_pitch=None, text=None):
    """Кнопка «Проверить голос» в настройках (и ▶ у персонажа)."""
    _say(text or "Проверка голоса. Так будет звучать перевод субтитров.", None, voice_pitch)


def shutdown():
    global _proc
    _neural.quit()
    if _proc is not None:
        try:
            _send("stop")
            _proc.stdin.close()
            _proc.wait(timeout=2)
        except Exception:
            try:
                _proc.kill()
            except Exception:
                pass
        _proc = None


# небольшой запас: если игра шлёт одну и ту же реплику подряд, не читаем её повторно
_last = {"text": None, "t": 0.0}


def speak_text(translation):
    """Прочитать вслух переведённый текст (обведённая область): голосом «без имени», целиком."""
    text = re.sub(r"\s*\([^)]*\)", "", translation or "")          # «Клинок (Dawn Blade)» → «Клинок»
    text = re.sub(r"[⏳❌✅📜💬🔎]", "", text)
    text = " ".join(ln.strip() for ln in text.splitlines() if ln.strip())
    if sum(ch.isalpha() for ch in text) < 2:
        return
    stop()
    _say(text)


def speak_subtitle_once(translation, seen=None, orig=None):
    if translation == _last["text"] and time.time() - _last["t"] < 30:
        return
    _last.update(text=translation, t=time.time())
    speak_subtitle(translation, seen, orig)


# ============================ нейроголоса ============================

# (id голоса, подпись в настройках). Русские — родные; «многоязычные» говорят по-русски с лёгким акцентом.
NEURAL_VOICES = [
    ("ru-RU-SvetlanaNeural", "Светлана — женский, русский"),
    ("ru-RU-DmitryNeural", "Дмитрий — мужской, русский"),
    ("en-US-AvaMultilingualNeural", "Ava — женский, многоязычный"),
    ("en-US-EmmaMultilingualNeural", "Emma — женский, многоязычный"),
    ("fr-FR-VivienneMultilingualNeural", "Vivienne — женский, многоязычный"),
    ("de-DE-SeraphinaMultilingualNeural", "Seraphina — женский, многоязычный"),
    ("en-US-AndrewMultilingualNeural", "Andrew — мужской, многоязычный"),
    ("en-US-BrianMultilingualNeural", "Brian — мужской, многоязычный"),
    ("fr-FR-RemyMultilingualNeural", "Remy — мужской, многоязычный"),
    ("de-DE-FlorianMultilingualNeural", "Florian — мужской, многоязычный"),
]


def neural_label(voice_id):
    for vid, label in NEURAL_VOICES:
        if vid == voice_id:
            return label
    return voice_id


def neural_id(label):
    for vid, lab in NEURAL_VOICES:
        if lab == label:
            return vid
    return label


_edge = {"mod": None, "checked": False}


def neural_available():
    """Есть ли пакет edge-tts (нейроголоса)."""
    if not _edge["checked"]:
        _edge["checked"] = True
        try:
            import edge_tts
            _edge["mod"] = edge_tts
        except Exception:
            core.log("Нейроголоса не установлены (нет пакета edge-tts) — читаю голосом Windows. "
                     "Запустите install.bat ещё раз.", "error")
    return _edge["mod"] is not None


_silero_warned = {"v": False}


def engine_ready():
    """Готов ли выбранный нейродвижок (иначе читаем голосом Windows)."""
    if config.TTS_ENGINE == "neural":
        return neural_available()
    if config.TTS_ENGINE == "silero":
        if tts_silero.installed():
            return True
        if not _silero_warned["v"]:
            _silero_warned["v"] = True
            core.log("Офлайн-голоса Silero не установлены — запустите install_silero.bat из папки программы. "
                     "Пока читаю голосом Windows.", "error")
    return False


def _rate_str(extra=0, pct=0):
    return f"{(int(config.TTS_RATE) + extra) * 10 + pct:+d}%"   # ползунок −5…6 → −50%…+60%


# ---------- интонация: восклицание звучит живее, «…» — медленнее, вопрос — чуть выше ----------
# нейроголос: (скорость %, высота Гц, громкость %); Silero: (шаг скорости, шаг высоты)
MOOD_EDGE = {"excl": (8, 10, 15), "ask": (0, 5, 0), "pause": (-12, -4, -5)}
MOOD_SILERO = {"excl": (1, 1), "ask": (0, 0), "pause": (-2, 0)}


def mood_of(phrase):
    """Настроение фразы по знакам: excl — «!» или КРИК, ask — «?», pause — «…», "" — обычная."""
    if not config.TTS_EXPRESSIVE:
        return ""
    s = phrase.strip().rstrip("»\"')» ")
    if s.endswith("!") or s.endswith("?!") or s.endswith("!?"):
        return "excl"
    letters = [c for c in s if c.isalpha()]
    if len(letters) >= 6 and sum(c.isupper() for c in letters) > 0.8 * len(letters):
        return "excl"
    if s.endswith("?"):
        return "ask"
    if s.endswith(("…", "...")):
        return "pause"
    return ""

CATCHUP_RATE = 2   # реплика ждала в очереди — читаем её на 20% быстрее, чтобы догнать диалог


def split_chunks(text, first_max=90, max_len=220):
    """Режем реплику на фразы: первая — короткая (быстрее синтезируется и раньше зазвучит)."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", text) if p.strip()]
    if not parts:
        return []
    first = parts[0]
    if len(first) > first_max:          # длинная первая фраза — режем по запятой
        m = re.search(r"^(.{25,%d}?[,;:—])\s+(.*)$" % first_max, first)
        if m:
            parts[0:1] = [m.group(1), m.group(2)]
    chunks = [parts[0]]
    for p in parts[1:]:                 # остальное склеиваем в куски покрупнее (но с одной интонацией)
        if len(chunks) > 1 and len(chunks[-1]) + len(p) < max_len and mood_of(chunks[-1]) == mood_of(p):
            chunks[-1] += " " + p
        else:
            chunks.append(p)
    return chunks


async def _synth_async(text, path, voice, rate, pitch="+0Hz", volume="+0%"):
    edge_tts = _edge["mod"]
    com = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume, connect_timeout=6,
                               receive_timeout=20)
    await com.save(path)
    if not os.path.exists(path) or os.path.getsize(path) < 200:
        raise RuntimeError("сервис вернул пустой звук")
    return path


def synthesize(text, path, voice=None):
    """Нейроголос → mp3-файл (синхронно; для проверки и тестов)."""
    return asyncio.run(_synth_async(text, path, voice or config.TTS_NEURAL_VOICE, _rate_str()))


class _Mci:
    """Проигрывание mp3 встроенным в Windows MCI. Вызывается только из потока _Neural.
    Два «слота»: пока звучит одна фраза, следующая уже открыта и стартует без паузы."""

    def __init__(self):
        self.slots = {}                 # alias -> открыт ли

    def cmd(self, text):
        buf = ctypes.create_unicode_buffer(256)
        err = ctypes.windll.winmm.mciSendStringW(text, buf, 255, 0)
        return err, buf.value

    def load(self, path):
        alias = "aac_tts_a" if not self.slots.get("aac_tts_a") else "aac_tts_b"
        self.close(alias)
        err, _ = self.cmd(f'open "{path}" type mpegvideo alias {alias}')
        if err:
            raise RuntimeError(f"не удалось открыть звук (MCI {err})")
        self.slots[alias] = True
        return alias

    def play(self, alias, volume):
        self.cmd(f"setaudio {alias} volume to {max(0, min(1000, int(volume) * 10))}")
        err, _ = self.cmd(f"play {alias}")
        if err:
            raise RuntimeError(f"не удалось проиграть звук (MCI {err})")

    def busy(self, alias):
        err, mode = self.cmd(f"status {alias} mode")
        return not err and mode.lower() in ("playing", "seeking")

    def close(self, alias):
        if self.slots.get(alias):
            self.cmd(f"stop {alias}")
            self.cmd(f"close {alias}")
        self.slots[alias] = False

    def close_all(self):
        for a in list(self.slots):
            self.close(a)


def _make_player():
    return _Mci() if sys.platform == "win32" else None


class _Neural:
    """Очередь озвучки.
    Реплика режется на фразы, все фразы синтезируются параллельно; первая — самая короткая,
    поэтому голос начинает звучать почти сразу, а следующие фразы готовы к своему моменту.
    Новая реплика прерывает старую."""

    def __init__(self):
        self.q = queue.Queue()
        self.gen = 0
        self.thread = None
        self.loop = None
        self.ok_logged = False
        self.last_err = 0.0
        self.warm_req = False
        self.warmed = False
        self.warm_fut = None
        self.dir = os.path.join(tempfile.gettempdir(), "aac_translator_tts")

    def _ensure(self):
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def say(self, text, seen=None, voice_pitch=None):
        self.gen += 1
        self._ensure()
        self.q.put(("say", (text, seen or time.time(), voice_pitch), self.gen))

    def stop(self):
        if self.thread is None:
            return
        self.gen += 1
        self.q.put(("stop", None, self.gen))

    def quit(self):
        if self.thread is not None:
            self.q.put(("quit", None, -1))

    def warm(self):
        """Прогрев в фоне: соединение с сервисом голосов и звуковой декодер Windows —
        чтобы первая реплика не ждала их запуска."""
        if self.warmed:
            return
        self.warm_req = True
        self._ensure()
        self.q.put(("noop", None, -1))

    def _warm_step(self, player):
        if self.warm_req and self.loop:
            self.warm_req = False
            self.warmed = True
            self.warm_fut = asyncio.run_coroutine_threadsafe(
                self._synth_coro("Готово.", os.path.join(self.dir, "warm")), self.loop)
        f = self.warm_fut
        if f is not None and f.done():
            self.warm_fut = None
            try:
                path = f.result()
                if player:
                    player.close(player.load(path))   # открыть-закрыть: Windows загрузит mp3-декодер
            except Exception:
                self.warmed = False   # не вышло (нет сети?) — попробуем при следующем случае

    # --- поток озвучки ---
    def _start_loop(self):
        """Отдельный постоянный цикл asyncio для синтеза (не создаём его заново на каждую фразу)."""
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

    def _synth_coro(self, text, path_base, faster=False, voice_pitch=None):
        """Корутина синтеза фразы выбранным движком → путь к звуковому файлу."""
        extra = CATCHUP_RATE if faster else 0
        pv, pitch = voice_pitch if voice_pitch else (None, 0)
        mood = mood_of(text)
        if config.TTS_ENGINE == "silero":
            d_rate, d_pitch = MOOD_SILERO.get(mood, (0, 0))
            voice, level = pv or config.TTS_SILERO_VOICE, int(config.TTS_RATE) + extra + d_rate
            pitch_s = pitch + d_pitch

            async def run():
                return await asyncio.get_running_loop().run_in_executor(
                    tts_silero.executor, tts_silero.synth_to_wav, text, path_base + ".wav", voice, level, pitch_s)
            return run()
        d_rate, d_hz, d_vol = MOOD_EDGE.get(mood, (0, 0, 0))
        voice, rate = pv or config.TTS_NEURAL_VOICE, _rate_str(extra, d_rate)
        kw = {"volume": f"{d_vol:+d}%"} if d_vol else {}

        async def run():
            await _synth_async(text, path_base + ".mp3", voice, rate, f"{int(pitch) + d_hz:+d}Hz", **kw)
            return path_base + ".mp3"
        return run()

    def _new_job(self, text, seen, gen, faster=False, voice_pitch=None):
        chunks = split_chunks(text)

        async def timed(coro):
            path = await coro
            return path, time.time()
        futs = [asyncio.run_coroutine_threadsafe(
                    timed(self._synth_coro(c, os.path.join(self.dir, f"g{gen % 4}_{i}"), faster, voice_pitch)),
                    self.loop)
                for i, c in enumerate(chunks)]
        return {"gen": gen, "chunks": chunks, "futs": futs, "idx": 0, "cur": None, "next": None,
                "seen": seen, "t0": time.time(), "dead": False, "faster": faster}

    def _cancel(self, job):
        job["dead"] = True
        for f in job["futs"]:
            f.cancel()

    def _fail(self, job, e):
        if time.time() - self.last_err > 60:
            self.last_err = time.time()
            why = str(e)[:160] or type(e).__name__
            if config.TTS_ENGINE == "silero":
                core.log(f"Silero: ошибка ({why}) — читаю голосом Windows.", "error")
            else:
                core.log(f"Нейроголос не ответил ({why}) — читаю голосом Windows. Нужен интернет.", "error")
        alive = not job["dead"]
        self._cancel(job)
        if alive:
            _windows_say(" ".join(job["chunks"][job["idx"]:]))

    def _step(self, job, player):
        """Продвинуть реплику: True — ещё звучит, False — закончилась."""
        i, futs = job["idx"], job["futs"]
        if job["cur"] is not None and player and player.busy(job["cur"]):
            # пока звучит фраза — заранее открываем следующую
            if job["next"] is None and i < len(futs) and futs[i].done() and not futs[i].exception():
                try:
                    job["next"] = player.load(futs[i].result()[0])
                except Exception:
                    pass
            return True
        if job["cur"] is not None and player:
            player.close(job["cur"])
            job["cur"] = None
        if i >= len(futs):
            return False
        if not futs[i].done():
            return True
        try:
            path, t_synth = futs[i].result()
            alias = job["next"] or (player.load(path) if player else None)
            job["next"] = None
            if player:
                player.play(alias, config.TTS_VOLUME)
            job["cur"] = alias
        except Exception as e:
            self._fail(job, e)
            return False
        if i == 0:
            now = time.time()
            msg = (f"🔊 голос через {now - job['t0']:.1f} с после перевода: синтез {t_synth - job['t0']:.1f} с, "
                   f"запуск звука {now - t_synth:.1f} с")
            if job["faster"]:
                msg += " (ждала конца прошлой реплики, читаю чуть быстрее)"
            elif job["seen"] < job["t0"] - 0.05:
                msg += f"; от появления текста {now - job['seen']:.1f} с"
            if not self.ok_logged:
                self.ok_logged = True
                core.log(f"Озвучка: «{voice_title()}». {msg}", "ok")
            elif config.SHOW_OCR_IN_LOG:
                core.log(msg)
        job["idx"] = i + 1
        return True

    def _run(self):
        os.makedirs(self.dir, exist_ok=True)
        self._start_loop()
        player = _make_player()
        job = None        # реплика, которая звучит (или готовится первой)
        waiting = None    # следующая реплика: уже синтезируется, ждёт конца текущей
        while True:
            self._warm_step(player)
            try:
                item = self.q.get(timeout=0.04) if (job or waiting or self.warm_fut) else self.q.get()
            except queue.Empty:
                item = None
            if item is not None:
                while True:                   # берём только самое свежее (пустые «noop» не в счёт)
                    try:
                        nxt = self.q.get_nowait()
                    except queue.Empty:
                        break
                    if nxt[0] != "noop" or item[0] == "noop":
                        item = nxt
                cmd, data, gen = item
                if cmd == "say" and gen == self.gen and job is not None and config.TTS_FINISH_LINE:
                    # дочитываем текущую; новая синтезируется уже сейчас и зазвучит сразу после неё
                    if waiting:
                        self._cancel(waiting)     # в очереди держим только самую свежую реплику
                    waiting = self._new_job(data[0], data[1], gen, faster=True, voice_pitch=data[2])
                elif cmd != "noop":
                    for jb in (job, waiting):
                        if jb:
                            self._cancel(jb)
                    job = waiting = None
                    if player:
                        player.close_all()
                    if cmd == "quit":
                        self.loop.call_soon_threadsafe(self.loop.stop)
                        return
                    if cmd == "say" and gen == self.gen:
                        job = self._new_job(data[0], data[1], gen, voice_pitch=data[2])
            if job and not self._step(job, player):
                job, waiting = waiting, None
                if job:
                    job["t0"] = min(job["t0"], time.time())


_neural = _Neural()


def warm():
    """Подготовить озвучку заранее (вызывается при запуске и при включении)."""
    if config.TTS_ENABLED and engine_ready():
        _neural.warm()
        if config.TTS_ENGINE == "silero" and tts_silero.cis_available():
            def preload():
                try:
                    tts_silero._load_cis()       # доп. голоса: скачать/загрузить заранее, а не на первой реплике
                except Exception:
                    pass
            tts_silero.executor.submit(preload)


def voice_title():
    """Короткая подпись голоса для панели."""
    if config.TTS_ENGINE == "neural":
        return neural_label(config.TTS_NEURAL_VOICE).split(" — ")[0] + " (нейроголос онлайн)"
    if config.TTS_ENGINE == "silero":
        return tts_silero.label(config.TTS_SILERO_VOICE).split(" — ")[0] + " (Silero, офлайн)"
    return config.TTS_VOICE or "голос Windows по умолчанию"
