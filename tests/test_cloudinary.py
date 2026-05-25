"""Tests de src/distribucion/storage/cloudinary.py

Mockean cloudinary.uploader.upload para no llamar a la API real.
"""
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.core.modelo_datos import Placa
from src.distribucion.storage.base import ErrorStorage
from src.distribucion.storage.cloudinary import (
    ConfigCloudinary,
    CloudinaryStorage,
    _sanitizar_sku,
)


@pytest.fixture
def config():
    return ConfigCloudinary(
        cloud_name="test-cloud",
        api_key="test-key",
        api_secret="test-secret",
        folder="morashop-v2",
    )


@pytest.fixture
def storage(config):
    return CloudinaryStorage(config)


@pytest.fixture
def placa_local(tmp_path):
    """Crea un PNG fake en disco para los tests."""
    png_path = tmp_path / "test.png"
    png_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    return Placa(
        sku="TEST-001",
        template_usado="default",
        path_local=str(png_path),
        width=1080,
        height=1350,
    )


# ============ Validaciones de config ============

@pytest.mark.parametrize("campo", ["cloud_name", "api_key", "api_secret", "folder"])
def test_config_requiere_campos_obligatorios(campo):
    kwargs = {
        "cloud_name": "test", "api_key": "k", "api_secret": "s", "folder": "f",
        campo: "",
    }
    with pytest.raises(ErrorStorage, match=campo):
        CloudinaryStorage(ConfigCloudinary(**kwargs))


# ============ Sanitizado de SKU ============

def test_sanitizar_sku_con_espacios():
    assert _sanitizar_sku("GOLDNU0 CREA 300G") == "GOLDNU0_CREA_300G"


def test_sanitizar_sku_con_barras():
    assert _sanitizar_sku("SKU/ABC-123") == "SKU_ABC-123"


def test_sanitizar_sku_alfanumerico():
    assert _sanitizar_sku("ABC123-XYZ") == "ABC123-XYZ"


# ============ Generación del public_id ============

def test_public_id_incluye_folder(storage):
    pid = storage._public_id("ABC-001")
    assert pid == "morashop-v2/ABC-001"


def test_public_id_sanitiza_sku(storage):
    pid = storage._public_id("GOLDNU0 CREA 300G")
    assert pid == "morashop-v2/GOLDNU0_CREA_300G"


# ============ Subida ============

@patch("src.distribucion.storage.cloudinary.cloudinary.uploader.upload")
def test_subida_basica_devuelve_url(mock_upload, storage, placa_local):
    mock_upload.return_value = {
        "secure_url": "https://res.cloudinary.com/test-cloud/image/upload/morashop-v2/TEST-001.png",
        "public_id": "morashop-v2/TEST-001",
    }

    subida = storage.subir(placa_local)

    assert subida.sku == "TEST-001"
    assert subida.url_publica.startswith("https://res.cloudinary.com/")
    assert subida.storage_backend == "cloudinary"


@patch("src.distribucion.storage.cloudinary.cloudinary.uploader.upload")
def test_subida_usa_overwrite_y_invalidate(mock_upload, storage, placa_local):
    """Confirmar que mandamos overwrite=True para reemplazar placas
    y invalidate=True para purgar CDN."""
    mock_upload.return_value = {"secure_url": "https://x/y.png"}

    storage.subir(placa_local)

    kwargs = mock_upload.call_args.kwargs
    assert kwargs["overwrite"] is True
    assert kwargs["invalidate"] is True
    assert kwargs["public_id"] == "morashop-v2/TEST-001"


@patch("src.distribucion.storage.cloudinary.cloudinary.uploader.upload")
def test_subida_incluye_tags_utiles(mock_upload, storage, placa_local):
    """Tags para poder buscar/filtrar en Cloudinary después."""
    mock_upload.return_value = {"secure_url": "https://x/y.png"}

    storage.subir(placa_local)

    tags = mock_upload.call_args.kwargs["tags"]
    assert "morashop-v2" in tags
    assert "sku:TEST-001" in tags
    assert "template:default" in tags


@patch("src.distribucion.storage.cloudinary.cloudinary.uploader.upload")
def test_subida_falla_si_no_existe_archivo_local(mock_upload, storage):
    placa = Placa(
        sku="X", template_usado="default",
        path_local="/no/existe.png", width=1080, height=1350,
    )
    with pytest.raises(ErrorStorage, match="No existe"):
        storage.subir(placa)

    mock_upload.assert_not_called()


@patch("src.distribucion.storage.cloudinary.cloudinary.uploader.upload")
def test_subida_falla_si_api_da_error(mock_upload, storage, placa_local):
    mock_upload.side_effect = Exception("Connection timeout")

    with pytest.raises(ErrorStorage, match="Falló subida"):
        storage.subir(placa_local)


@patch("src.distribucion.storage.cloudinary.cloudinary.uploader.upload")
def test_subida_falla_si_respuesta_sin_secure_url(mock_upload, storage, placa_local):
    """Si Cloudinary devuelve respuesta rara, fallamos explícitamente."""
    mock_upload.return_value = {"public_id": "x"}  # sin secure_url

    with pytest.raises(ErrorStorage, match="secure_url"):
        storage.subir(placa_local)


# ============ Identidad del módulo ============

def test_nombre_storage(storage):
    assert storage.nombre() == "cloudinary"


# ============ borrar() (Fase H) ============

def test_borrar_exitoso(monkeypatch):
    """destroy() responde {'result': 'ok'} → True."""
    import src.distribucion.storage.cloudinary as cloud_module

    mock_destroy_calls = []
    def fake_destroy(public_id, **kwargs):
        mock_destroy_calls.append((public_id, kwargs))
        return {"result": "ok"}

    monkeypatch.setattr(cloud_module.cloudinary.uploader, "destroy", fake_destroy)

    storage = cloud_module.CloudinaryStorage(cloud_module.ConfigCloudinary(
        cloud_name="x", api_key="y", api_secret="z", folder="test-folder",
    ))

    resultado = storage.borrar("SKU-A")
    assert resultado is True
    # Borra ambos aspect ratios (4:5 sin sufijo, 9:16 con _9x16)
    assert len(mock_destroy_calls) == 2
    public_ids_usados = [c[0] for c in mock_destroy_calls]
    assert "test-folder/SKU-A" in public_ids_usados
    assert "test-folder/SKU-A_9x16" in public_ids_usados
    # Todos con invalidate=True
    for _, kwargs in mock_destroy_calls:
        assert kwargs.get("invalidate") is True


def test_borrar_not_found_devuelve_true(monkeypatch):
    """Si la imagen ya no existe en Cloudinary, también consideramos éxito."""
    import src.distribucion.storage.cloudinary as cloud_module

    def fake_destroy(public_id, **kwargs):
        return {"result": "not found"}

    monkeypatch.setattr(cloud_module.cloudinary.uploader, "destroy", fake_destroy)

    storage = cloud_module.CloudinaryStorage(cloud_module.ConfigCloudinary(
        cloud_name="x", api_key="y", api_secret="z", folder="f",
    ))
    assert storage.borrar("SKU-FANTASMA") is True


def test_borrar_falla_devuelve_false(monkeypatch):
    """Si destroy() levanta excepción, no rompe el pipeline: devuelve False."""
    import src.distribucion.storage.cloudinary as cloud_module

    def fake_destroy(public_id, **kwargs):
        raise Exception("Cloudinary timeout")

    monkeypatch.setattr(cloud_module.cloudinary.uploader, "destroy", fake_destroy)

    storage = cloud_module.CloudinaryStorage(cloud_module.ConfigCloudinary(
        cloud_name="x", api_key="y", api_secret="z", folder="f",
    ))
    # NO debe raisear
    assert storage.borrar("SKU-X") is False


def test_borrar_resultado_inesperado_devuelve_false(monkeypatch):
    """Si destroy() devuelve algo raro (rate-limited, etc.), False."""
    import src.distribucion.storage.cloudinary as cloud_module

    def fake_destroy(public_id, **kwargs):
        return {"result": "rate_limited"}

    monkeypatch.setattr(cloud_module.cloudinary.uploader, "destroy", fake_destroy)

    storage = cloud_module.CloudinaryStorage(cloud_module.ConfigCloudinary(
        cloud_name="x", api_key="y", api_secret="z", folder="f",
    ))
    assert storage.borrar("SKU-X") is False
