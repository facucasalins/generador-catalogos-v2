"""Tests del loop multi-aspect-ratio del CLI - Fase H activación."""


def test_cli_tiene_loop_aspect_ratios():
    """El cli loopea sobre aspect_ratios_cfg."""
    cli_source = open("src/cli.py").read()
    # Debe leer la sección del yaml
    assert "aspect_ratios" in cli_source
    assert "aspect_ratios_cfg" in cli_source
    # Debe loopear
    assert "for ar_cfg in aspect_ratios_cfg" in cli_source


def test_cli_aplica_template_suffix():
    """El cli usa template_suffix para construir nombre del template."""
    cli_source = open("src/cli.py").read()
    assert "template_suffix" in cli_source
    assert "decision.template + template_suffix" in cli_source


def test_cli_hash_incluye_aspect_ratio():
    """calcular_hash recibe aspect_ratio para que el diff sea por aspect."""
    cli_source = open("src/cli.py").read()
    assert "aspect_ratio=ar_label" in cli_source


def test_cli_historial_clave_compuesta_en_loop():
    """historial_actual.get usa (sku, ar_label) en el loop."""
    cli_source = open("src/cli.py").read()
    assert "historial_actual.get((decision.sku, ar_label))" in cli_source


def test_cli_default_retrocompat_4x5():
    """Si no hay aspect_ratios en yaml, default a una pasada 4:5."""
    cli_source = open("src/cli.py").read()
    # Default cuando no está la sección en yaml
    assert '"label": "4:5"' in cli_source
    assert '"template_suffix": ""' in cli_source


def test_cli_dedup_decisiones_por_sku():
    """Para feeds: dedup por SKU (mismo producto en 4:5 y 9:16 = 1 entrada)."""
    cli_source = open("src/cli.py").read()
    assert "productos_renderizados_set" in cli_source
    assert "decisiones_renderizadas_set" in cli_source


def test_cli_reverse_template_suffix_para_feed():
    """Las decisiones que van al feed usan template SIN sufijo (ej: default, no default_tiktok),
    para que el agrupamiento por template no duplique pestañas. Usa endswith() para
    no romper templates con el sufijo en el medio (edge case improbable)."""
    cli_source = open("src/cli.py").read()
    assert "_quitar_suffix" in cli_source
    assert "endswith(suffix)" in cli_source
