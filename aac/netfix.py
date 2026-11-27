"""Работа через корпоративный VPN/прокси.

На рабочих компьютерах VPN часто подменяет сертификаты сайтов своим (проверка трафика). Windows и браузер
этому сертификату доверяют (его ставит администратор), а Python — нет: у него свой список, и онлайн-
переводчики, ИИ и голоса падают с CERTIFICATE_VERIFY_FAILED. Здесь Python учится доверять тому же,
чему доверяет Windows (пакет truststore) — так же, как браузер. Проверка сертификатов остаётся включённой.
"""
import sys

active = False


def enable():
    """Включить один раз при запуске, до первого обращения в интернет. Без truststore — тихо ничего не делает."""
    global active
    if active or sys.version_info < (3, 10):
        return active
    try:
        import truststore
        truststore.inject_into_ssl()
        active = True
    except Exception:
        active = False
    return active
