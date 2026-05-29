"""Tests del helper compartido de resolución de nombres de template."""
from src.core.templates import (
    nombre_base_template, PREFIJOS_PLATAFORMA, sanitizar_id,
)


def test_quita_prefijo_meta():
    assert nombre_base_template("Meta_default_4x5") == "default_4x5"


def test_quita_prefijo_tiktok():
    assert nombre_base_template("TikTok_juanita_9x16") == "juanita_9x16"


def test_sin_prefijo_queda_igual():
    assert nombre_base_template("default_4x5") == "default_4x5"


def test_solo_quita_prefijo_del_inicio_no_toca_el_resto():
    # Nombres reales de todos los clientes: solo se saca el prefijo de
    # plataforma, el resto del nombre queda intacto.
    casos = {
        "Meta_default_4x5": "default_4x5",
        "TikTok_default_9x16": "default_9x16",
        "Meta_cuotas_4x5": "cuotas_4x5",        # antonia
        "Meta_electro_9x16": "electro_9x16",    # morashop
        "TikTok_innova_4x5": "innova_4x5",      # morashop
        "Meta_juanita_4x5": "juanita_4x5",      # juanita
        "TikTok_juanita_9x16": "juanita_9x16",  # juanita
    }
    for entrada, esperado in casos.items():
        assert nombre_base_template(entrada) == esperado


def test_no_quita_prefijo_parcial():
    # 'Meta' sin '_' no es prefijo de plataforma: no se toca.
    assert nombre_base_template("Metalico_4x5") == "Metalico_4x5"


def test_prefijos_definidos():
    assert PREFIJOS_PLATAFORMA == ("Meta_", "TikTok_")


# ===================== sanitizar_id =====================

def test_sanitizar_id_deja_validos_intactos():
    assert sanitizar_id("bota-soraya-negro__Meta_juanita_4x5") == "bota-soraya-negro__Meta_juanita_4x5"


def test_sanitizar_id_reemplaza_invalidos_por_guion_bajo():
    assert sanitizar_id("mora cuero/chocolate") == "mora_cuero_chocolate"
    assert sanitizar_id("SKU.con#raros") == "SKU_con_raros"


def test_sanitizar_id_trim():
    assert sanitizar_id("  abc  ") == "abc"


def test_sanitizar_id_png_y_public_id_coinciden():
    # El nombre del PNG (motor) y el tail del public_id (cloudinary) deben
    # salir idénticos del mismo helper.
    sku, tpl = "mora cuero/chocolate", "Meta_default_4x5"
    s = f"{sanitizar_id(sku)}__{sanitizar_id(tpl)}"
    png = f"{s}.png"
    assert png[:-4] == s
