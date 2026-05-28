"""Tests de src/distribucion/storage/cloudinary.py (multi-template)."""
from unittest.mock import patch, MagicMock
import pytest

from src.core.modelo_datos import Placa
from src.distribucion.storage.base import ErrorStorage
from src.distribucion.storage.cloudinary import (
    ConfigCloudinary,
    CloudinaryStorage,
    _sanitizar,
)


@pytest.fixture
def config():
    return ConfigCloudinary(
        cloud_name="test-cloud", api_key="test-key",
        api_secret="test-secret", folder="morashop-v2",
    )


@pytest.fixture
def storage(config):
    return CloudinaryStorage(config)


@pytest.fixture
def placa_local(tmp_path):
    png_path = tmp_path / "test.png"
    png_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    return Placa(
        sku="TEST-001", template_usado="default_4x5",
        path_local=str(png_path), width=1080, height=1350, aspect_ratio="4:5",
    )


@pytest.mark.parametrize("campo", ["cloud_name", "api_key", "api_secret", "folder"])
def test_config_requiere_campos_obligatorios(campo):
    kwargs = {
        "cloud_name": "test", "api_key": "k", "api_secret": "s", "folder": "f",
        campo: "",
    }
    with pytest.raises(ErrorStorage, match=campo):
        CloudinaryStorage(ConfigCloudinary(**kwargs))


def test_sanitizar_con_espacios():
    assert _sanitizar("GOLDNU0 CREA 300G") == "GOLDNU0_CREA_300G"


def test_sanitizar_con_barras():
    assert _sanitizar("SKU/ABC-123") == "SKU_ABC-123"


def test_sanitizar_alfanumerico():
    assert _sanitizar("ABC123-XYZ") == "ABC123-XYZ"


def test_public_id_incluye_folder_y_template(storage):
    pid = storage._public_id("ABC-001", "default_4x5")
    assert pid == "morashop-v2/ABC-001__default_4x5"


def test_public_id_sanitiza_sku(storage):
    pid = storage._public_id("GOLDNU0 CREA 300G", "default_4x5")
    assert pid == "morashop-v2/GOLDNU0_CREA_300G__default_4x5"


def test_public_id_sanitiza_template(storage):
    pid = storage._public_id("ABC", "Meta_default_4x5")
    assert pid == "morashop-v2/ABC__Meta_default_4x5"


@patch("src.distribucion.storage.cloudinary.cloudinary.uploader.upload")
def test_subida_basica_devuelve_url(mock_upload, storage, placa_local):
    mock_upload.return_value = {
        "secure_url": "https://res.cloudinary.com/test-cloud/image/upload/morashop-v2/TEST-001__default_4x5.png",
        "public_id": "morashop-v2/TEST-001__default_4x5",
    }
    subida = storage.subir(placa_local)
    assert subida.sku == "TEST-001"
    assert subida.template_usado == "default_4x5"
    assert subida.url_publica.startswith("https://res.cloudinary.com/")
    assert subida.storage_backend == "cloudinary"


@patch("src.distribucion.storage.cloudinary.cloudinary.uploader.upload")
def test_subida_usa_overwrite_y_invalidate(mock_upload, storage, placa_local):
    mock_upload.return_value = {"secure_url": "https://x/y.png"}
    storage.subir(placa_local)
    kwargs = mock_upload.call_args.kwargs
    assert kwargs["overwrite"] is True
    assert kwargs["invalidate"] is True
    assert kwargs["public_id"] == "morashop-v2/TEST-001__default_4x5"


@patch("src.distribucion.storage.cloudinary.cloudinary.uploader.upload")
def test_subida_incluye_tags_utiles(mock_upload, storage, placa_local):
    mock_upload.return_value = {"secure_url": "https://x/y.png"}
    storage.subir(placa_local)
    tags = mock_upload.call_args.kwargs["tags"]
    assert "morashop-v2" in tags
    assert "sku:TEST-001" in tags
    assert "template:default_4x5" in tags


@patch("src.distribucion.storage.cloudinary.cloudinary.uploader.upload")
def test_subida_falla_si_no_existe_archivo_local(mock_upload, storage):
    placa = Placa(
        sku="X", template_usado="default_4x5",
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
    mock_upload.return_value = {"public_id": "x"}
    with pytest.raises(ErrorStorage, match="secure_url"):
        storage.subir(placa_local)


def test_nombre_storage(storage):
    assert storage.nombre() == "cloudinary"


def test_borrar_exitoso_con_public_id_relativo(monkeypatch):
    import src.distribucion.storage.cloudinary as cloud_module
    calls = []
    def fake_destroy(public_id, **kwargs):
        calls.append((public_id, kwargs))
        return {"result": "ok"}
    monkeypatch.setattr(cloud_module.cloudinary.uploader, "destroy", fake_destroy)
    storage = cloud_module.CloudinaryStorage(cloud_module.ConfigCloudinary(
        cloud_name="x", api_key="y", api_secret="z", folder="test-folder",
    ))
    resultado = storage.borrar("SKU-A__default_4x5")
    assert resultado is True
    assert len(calls) == 1
    assert calls[0][0] == "test-folder/SKU-A__default_4x5"
    assert calls[0][1].get("invalidate") is True


def test_borrar_acepta_public_id_completo(monkeypatch):
    import src.distribucion.storage.cloudinary as cloud_module
    calls = []
    def fake_destroy(public_id, **kwargs):
        calls.append(public_id)
        return {"result": "ok"}
    monkeypatch.setattr(cloud_module.cloudinary.uploader, "destroy", fake_destroy)
    storage = cloud_module.CloudinaryStorage(cloud_module.ConfigCloudinary(
        cloud_name="x", api_key="y", api_secret="z", folder="test-folder",
    ))
    storage.borrar("otra-carpeta/SKU__default")
    assert calls[0] == "otra-carpeta/SKU__default"


def test_borrar_not_found_devuelve_true(monkeypatch):
    import src.distribucion.storage.cloudinary as cloud_module
    def fake_destroy(public_id, **kwargs):
        return {"result": "not found"}
    monkeypatch.setattr(cloud_module.cloudinary.uploader, "destroy", fake_destroy)
    storage = cloud_module.CloudinaryStorage(cloud_module.ConfigCloudinary(
        cloud_name="x", api_key="y", api_secret="z", folder="f",
    ))
    assert storage.borrar("SKU-FANTASMA__default") is True


def test_borrar_falla_devuelve_false(monkeypatch):
    import src.distribucion.storage.cloudinary as cloud_module
    def fake_destroy(public_id, **kwargs):
        raise Exception("Cloudinary timeout")
    monkeypatch.setattr(cloud_module.cloudinary.uploader, "destroy", fake_destroy)
    storage = cloud_module.CloudinaryStorage(cloud_module.ConfigCloudinary(
        cloud_name="x", api_key="y", api_secret="z", folder="f",
    ))
    assert storage.borrar("SKU-X__default") is False


def test_borrar_resultado_inesperado_devuelve_false(monkeypatch):
    import src.distribucion.storage.cloudinary as cloud_module
    def fake_destroy(public_id, **kwargs):
        return {"result": "rate_limited"}
    monkeypatch.setattr(cloud_module.cloudinary.uploader, "destroy", fake_destroy)
    storage = cloud_module.CloudinaryStorage(cloud_module.ConfigCloudinary(
        cloud_name="x", api_key="y", api_secret="z", folder="f",
    ))
    assert storage.borrar("SKU-X__default") is False
