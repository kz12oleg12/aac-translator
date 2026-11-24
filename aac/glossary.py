"""Словарь имён и терминов (glossary.txt)."""


import os

import re


from . import config, core


# ---------- словарь имён и терминов (glossary.txt рядом с программой) ----------
GLOSSARY_FILE = os.path.join(config.APP_DIR, "glossary.txt")
GLOSSARY_TEMPLATE = """# Словарь имён и терминов для AAC Translator.
# Каждая строка:  Оригинал = Перевод
# Переводчик всегда будет использовать эти варианты (имена, места, предметы).
# Строки, начинающиеся с #, — комментарии. Сохраните файл — изменения подхватятся сами.
# Строка вида  - Слово  — не переводить это слово/фразу вообще (кнопки интерфейса и т.п.), например:
# - Skip

Renald = Ренальд
Kevin = Кевин
Jennifer = Дженнифер
Herlei = Херлей
Edward = Эдвард
"""
_glossary = {"mtime": None, "items": [], "ignore": set()}


def glossary():
    """[(оригинал, перевод)], перечитывается, если файл изменился."""
    try:
        if not os.path.exists(GLOSSARY_FILE):
            with open(GLOSSARY_FILE, "w", encoding="utf-8") as f:
                f.write(GLOSSARY_TEMPLATE)
        st = os.stat(GLOSSARY_FILE)
        mt = (st.st_mtime_ns, st.st_size)    # и размер: Windows обновляет время грубо — дописали в тот же миг
        if mt != _glossary["mtime"]:
            items, ignore = [], set()
            with open(GLOSSARY_FILE, encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("-") and len(line) > 1:
                        ignore.add(normalize(line[1:]))
                        continue
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    src, dst = (x.strip() for x in line.split("=", 1))
                    if src and dst:
                        items.append((src, dst))
            items.sort(key=lambda x: -len(x[0]))  # длинные фразы раньше коротких
            _glossary.update(mtime=mt, items=items, ignore=ignore)
            if _glossary.get("loaded"):
                core.log(f"Словарь обновлён: {len(items)} записей", "ok")
            _glossary["loaded"] = True
    except Exception as e:
        print("glossary:", e)
    return _glossary["items"]


def normalize(text):
    """Для сравнения слов интерфейса: без регистра, пробелов по краям и знаков препинания."""
    return re.sub(r"[^\w\s-]", "", text).strip().lower()


def ignored_words():
    """Слова интерфейса, которые не переводим: из aac/config.py + строки «- слово» в словаре."""
    glossary()
    return {normalize(w) for w in config.IGNORE_UI_WORDS} | _glossary.get("ignore", set())


def glossary_for(text=None, limit=60):
    """Записи словаря, которые встречаются в тексте (или все, если текста нет)."""
    items = glossary()
    if text is not None:
        low = text.lower()
        items = [(a, b) for a, b in items if a.lower() in low]
    return items[:limit]


def glossary_prompt(text=None):
    items = glossary_for(text)
    if not items:
        return ""
    return ("\nAlways use these fixed translations of names/terms:\n"
            + "\n".join(f"{a} -> {b}" for a, b in items))


def glossary_apply_source(text):
    """Для Google/Microsoft: заменяем имена в оригинале на готовый перевод до отправки."""
    for a, b in glossary_for(text):
        text = re.sub(rf"(?i)\b{re.escape(a)}\b", b, text)
    return text


def open_glossary():
    glossary()  # создаст файл с примерами, если его ещё нет
    try:
        os.startfile(GLOSSARY_FILE)
    except Exception as e:
        core.log(f"Не удалось открыть словарь: {e}", "error")


# ---------- словарь пополняется сам ----------
AUTO_HEADER = "# ---- добавлено программой автоматически (можно исправить или удалить строку) ----"
_RU = re.compile(r"^[А-ЯЁа-яё][А-ЯЁа-яё'’\-]*$")
_TERM = re.compile(r"([^\s()«»\"„“:;,.!?]+(?:[ \t]+[^\s()«»\"„“:;,.!?]+){0,4})[ \t]*\(([A-Za-z][A-Za-z'’\- ]{1,40})\)")


def _known(en):
    low = en.strip().lower()
    return any(a.lower() == low for a, _ in glossary()) or normalize(en) in _glossary.get("ignore", set())


def learn(en, ru, what="название"):
    """Добавить в словарь «en = ru», если такого ещё нет. True — добавили."""
    if not config.GLOSSARY_AUTO:
        return False
    en, ru = (en or "").strip(" .,:;!?«»\"'"), (ru or "").strip(" .,:;!?«»\"'")
    if not en or not ru or len(en) > 40 or len(ru) > 50 or en.lower() == ru.lower():
        return False
    if not re.fullmatch(r"[A-Za-z][A-Za-z'’\- ]*", en) or not all(_RU.match(w) for w in ru.split()):
        return False
    if _known(en):
        return False
    try:
        with open(GLOSSARY_FILE, encoding="utf-8-sig") as f:
            content = f.read()
        add = ("" if content.endswith("\n") else "\n")
        if AUTO_HEADER not in content:
            add += "\n" + AUTO_HEADER + "\n"
        add += f"{en} = {ru}\n"
        with open(GLOSSARY_FILE, "a", encoding="utf-8") as f:
            f.write(add)
    except Exception as e:
        print("glossary learn:", e)
        return False
    glossary()   # перечитать (запись подхватится сразу)
    core.log(f"📖 В словарь ({what}): {en} = {ru}", "ok")
    return True


def terms_in(translation):
    """Пары «Клинок рассвета (Dawn Blade)» из перевода → [("Dawn Blade", "Клинок рассвета")]."""
    out = []
    for m in _TERM.finditer(translation or ""):
        ru_words, en = m.group(1).split(), m.group(2).strip()
        if any(ch.isdigit() for ch in m.group(1)):
            continue
        k = len(en.split())
        tail = ru_words[-(k + 1):]
        caps = [i for i, w in enumerate(tail) if w[:1].isupper()]
        if not caps:
            continue                     # название должно начинаться с заглавной
        # «Возьми Клинок рассвета (Dawn Blade)» → «Клинок рассвета»; «Огненный шар (Fireball)» → целиком
        start = len(tail) - k if (len(tail) - k) in caps else caps[0]
        ru = tail[start:]
        if not (max(1, k - 1) <= len(ru) <= k + 1):
            continue
        if all(_RU.match(w) for w in ru):
            out.append((en, " ".join(ru)))
    return out


def learn_from_translation(translation, kind=""):
    """Названия берём только из заголовков подсказок и заданий (первая строка): там они в обычной форме
    («Огненный шар»), а в репликах имена склоняются («к Кевину») — такое в словарь не годится."""
    if kind not in ("Подсказка", "Задание"):
        return
    first = next((ln for ln in (translation or "").splitlines() if ln.strip()), "")
    for en, ru in terms_in(first):
        learn(en, ru, "подсказка" if kind == "Подсказка" else "задание")


# ---------- правка словаря из программы (раздел «Словарь») ----------
def _read_lines():
    glossary()            # создаст файл из шаблона, если его нет
    with open(GLOSSARY_FILE, encoding="utf-8-sig") as f:
        return f.read().splitlines()


def _write_lines(lines):
    tmp = GLOSSARY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")
    os.replace(tmp, GLOSSARY_FILE)
    _glossary["mtime"] = None     # перечитать (без записи «словарь обновлён» в журнал — правку сделали вы)
    _glossary["loaded"] = False
    glossary()


def _entry_of(line):
    s = line.strip()
    if not s or s.startswith("#") or s.startswith("-") or "=" not in s:
        return None
    a, b = (x.strip() for x in s.split("=", 1))
    return (a, b) if a and b else None


def entries():
    """[(оригинал, перевод, добавлено_программой)] в порядке файла."""
    out, auto = [], False
    for line in _read_lines():
        if line.strip() == AUTO_HEADER:
            auto = True
            continue
        e = _entry_of(line)
        if e:
            out.append((e[0], e[1], auto))
    return out


def set_entry(en, ru):
    """Добавить или исправить запись. Новая — в «ручную» часть (до записей, добавленных программой)."""
    en, ru = en.strip(), ru.strip()
    if not en or not ru or "=" in en:
        return False
    lines = _read_lines()
    for i, line in enumerate(lines):
        e = _entry_of(line)
        if e and e[0].lower() == en.lower():
            lines[i] = f"{en} = {ru}"
            _write_lines(lines)
            return True
    pos = next((i for i, line in enumerate(lines) if line.strip() == AUTO_HEADER), None)
    if pos is None:
        lines.append(f"{en} = {ru}")
    else:
        while pos > 0 and not lines[pos - 1].strip():
            pos -= 1
        lines.insert(pos, f"{en} = {ru}")
    _write_lines(lines)
    return True


def remove_entry(en):
    lines = [line for line in _read_lines() if not ((e := _entry_of(line)) and e[0].lower() == en.lower())]
    _write_lines(lines)


def ignore_entries():
    """[(слово, встроенное)] — что не переводится: свои строки «- слово» и встроенные слова интерфейса."""
    own = [line.strip()[1:].strip() for line in _read_lines()
           if line.strip().startswith("-") and len(line.strip()) > 1]
    builtin = [w for w in config.IGNORE_UI_WORDS if normalize(w) not in {normalize(o) for o in own}]
    return [(w, False) for w in own] + [(w, True) for w in builtin]


def add_ignore(word):
    word = word.strip()
    if not word or normalize(word) in {normalize(w) for w, _ in ignore_entries()}:
        return False
    lines = _read_lines()
    lines.append(f"- {word}")
    _write_lines(lines)
    return True


def remove_ignore(word):
    lines = [line for line in _read_lines()
             if not (line.strip().startswith("-") and normalize(line.strip()[1:]) == normalize(word))]
    _write_lines(lines)
