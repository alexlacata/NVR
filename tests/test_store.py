import pytest

from app.models import CameraCreate, CameraUpdate, SourceType
from app.store import CameraNotFound, CameraStore


@pytest.fixture()
def store(tmp_path):
    return CameraStore(tmp_path / "cameras.yaml")


def test_create_and_get(store):
    cam = store.create(CameraCreate(name="Porte d'entree", source_type=SourceType.rtsp, url="rtsp://cam1/stream"))
    assert cam.id == "porte-d-entree"
    fetched = store.get(cam.id)
    assert fetched.name == "Porte d'entree"
    assert fetched.enabled is True


def test_duplicate_names_get_unique_ids(store):
    a = store.create(CameraCreate(name="Garage", source_type=SourceType.rtsp, url="rtsp://a/x"))
    b = store.create(CameraCreate(name="Garage", source_type=SourceType.rtsp, url="rtsp://b/x"))
    assert a.id != b.id
    assert {c.id for c in store.list()} == {a.id, b.id}


def test_update(store):
    cam = store.create(CameraCreate(name="Jardin", source_type=SourceType.rtsp, url="rtsp://x/1"))
    updated = store.update(cam.id, CameraUpdate(enabled=False, name="Jardin arriere"))
    assert updated.enabled is False
    assert updated.name == "Jardin arriere"
    assert updated.url == "rtsp://x/1"


def test_delete(store):
    cam = store.create(CameraCreate(name="Cave", source_type=SourceType.rtsp, url="rtsp://x/2"))
    store.delete(cam.id)
    with pytest.raises(CameraNotFound):
        store.get(cam.id)


def test_get_missing_raises(store):
    with pytest.raises(CameraNotFound):
        store.get("nope")


def test_invalid_rtsp_url_rejected(store):
    with pytest.raises(Exception):
        store.create(CameraCreate(name="Bad", source_type=SourceType.rtsp, url="http://not-rtsp"))


def test_persists_across_instances(tmp_path):
    path = tmp_path / "cameras.yaml"
    s1 = CameraStore(path)
    cam = s1.create(CameraCreate(name="Toit", source_type=SourceType.test, url="test:pattern"))
    s2 = CameraStore(path)
    assert s2.get(cam.id).name == "Toit"
