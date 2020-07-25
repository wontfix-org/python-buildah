# coding: utf-8

import os as _os

import faker as _faker
import pytest as _pytest

import buildah as _buildah
#_buildah.unshare()

faker = _faker.Faker()
#_buildah.global_options.update({
#    "root": "own_root/lib/",
#    "runroot": "own_root/run/",
#})


def fake_name():
    return "buildah-test-" + "".join(faker.random_letters()).lower()


@_pytest.fixture
def container():
    c = _buildah.from_(base="alpine:3.12", name=fake_name())
    yield c
    c.rm()


@_pytest.fixture
def image(container):
    image = container.commit(fake_name())
    yield image
    image.rm()


def test_images():
    for actual in _buildah.images():
        assert actual.id


def test_containers():
    for actual in _buildah.containers():
        assert actual.id
        assert actual.name


def test_inspect_container(container):
    actual = _buildah.inspect(container.id, type="container")
    assert "Type" in actual


def test_inspect_image():
    c = _buildah.images()[0]
    actual = _buildah.inspect(c.id, type="image")
    assert "Type" in actual


def test_container_inspect(container):
    #actual = container.inspect()
    assert "Type" in container.info


def test_image_inspect():
    c = _buildah.images()[0]
    actual = c.inspect()
    assert "Type" in actual


def test_from_():
    name = "".join(faker.random_letters()).lower()
    c = _buildah.from_("alpine:3.12", name=name)
    actual = c.inspect()
    assert isinstance(actual, dict)
    c.rm()


def test_rm():
    container = _buildah.from_("alpine:3.12", name=fake_name())
    _buildah.inspect(container.id)
    _buildah.rm(container.id)
    with _pytest.raises(_buildah.BuildahNotFound):
        _buildah.inspect(container.id)


def test_commit(container):
    name = "".join(faker.random_letters()).lower()
    image = _buildah.commit(container.id, name)
    actual = _buildah.inspect(image.id)
    assert actual["FromImage"] == "localhost/{}:latest".format(name)
    image.rm()


def test_container_commit(container):
    name = "".join(faker.random_letters()).lower()
    image = container.commit(name)
    actual = _buildah.inspect(image.id)
    assert actual["FromImage"] == "localhost/{}:latest".format(name)
    image.rm()


def test_container_base_arg():
    c = _buildah.Container(fake_name(), base="alpine:3.12")
    assert isinstance(c.inspect(), dict)
    c.rm()


def test_config(container):
    wanted = "nobody"
    _buildah.config(container.id, user=wanted)
    info = container.inspect()
    assert info["OCIv1"]["config"]["User"] == wanted

@_pytest.mark.parametrize(
    "cmd",
    [
        ["echo", "-n", "foo"],
        "echo -n foo",
    ],
)
def test_run(container, cmd):
    wanted = "foo"
    actual = _buildah.run(container.id, cmd, _capture_output=True)
    assert actual == wanted


def test_copy(container, tmpdir):
    wanted = "foo"
    f = tmpdir.join("test")
    f.write(wanted)
    _digest = _buildah.copy(container.id, str(f), "/tmp/test")

    contents = _buildah.run(container.id, ["cat", "/tmp/test"], _capture_output=True)
    assert wanted == contents


def test_add(container, tmpdir):
    wanted = "foo"
    f = tmpdir.join("test")
    f.write(wanted)
    _digest = _buildah.add(container.id, str(f), "/tmp/test")
    contents = _buildah.run(container.id, ["cat", "/tmp/test"], _capture_output=True)
    assert wanted == contents


def test_mount_container(container, tmpdir):
    wanted = b"foo"
    f = tmpdir.join("test")
    f.write(wanted)
    _buildah.add(container.id, str(f), "/tmp/test")

    mounts = _buildah.mount(container.id)
    mount = list(mounts.items())[0][1]
    actual = open(_os.path.join(mount, "tmp", "test"), "rb").read()
    assert wanted == actual


def test_umount_container(container):
    _buildah.umount(all=True)
    _buildah.mount(container.id)
    assert _buildah.mount()
    _buildah.umount(container.id)
    assert not _buildah.mount()


def test_mount_show(container):
    mounts = _buildah.mount()
    assert not mounts

    _buildah.mount(container.id)
    mounts = _buildah.mount()

    assert mounts

def test_info():
    actual = _buildah.info()
    assert isinstance(actual, dict)


def test_pull():
    actual = _buildah.pull("alpine:3.11")
    assert isinstance(actual, _buildah.Image)
    assert actual.id


def test_push(image, tmpdir):
    dest = tmpdir.mkdir("pushed")
    _buildah.push(image.id, "dir:{}".format(dest))
    assert dest.join("version").check(file=1)


def test_tag(image):
    name = fake_name()
    wanted = f"localhost/{name}:latest"
    _buildah.tag(image.id, name)
    actual = _buildah.inspect(name)
    assert actual["FromImage"] == image.name
    _buildah.rmi(wanted)

@_pytest.mark.parametrize(
    "cmd",
    [
        ["echo", "-n", "foo"],
        "echo -n foo",
    ],
)
def test_container_run(container, cmd):
    wanted = "foo"
    actual = container.run(cmd, _capture_output=True)
    assert actual == wanted


def test_container_copy(container, tmpdir):
    wanted = "foo"
    f = tmpdir.join("test")
    f.write(wanted)
    _digest = container.copy(str(f), "/tmp/test")

    contents = container.run("cat /tmp/test", _capture_output=True)
    assert wanted == contents


def test_container_add(container, tmpdir):
    wanted = "foo"
    f = tmpdir.join("test")
    f.write(wanted)
    _digest = container.add(str(f), "/tmp/test")
    contents = container.run("cat /tmp/test", _capture_output=True)
    assert wanted == contents


def test_container_mount(container, tmpdir):
    wanted = b"foo"
    f = tmpdir.join("test")
    f.write(wanted)
    container.add(str(f), "/tmp/test")

    with container.mount() as mount:
        actual = open(_os.path.join(mount, "tmp", "test"), "rb").read()
        assert wanted == actual


def test_image_pull():
    actual = _buildah.Image("alpine:3.11").pull()
    assert isinstance(actual, _buildah.Image)
    assert actual.id


def test_mage_push(image, tmpdir):
    dest = tmpdir.mkdir("pushed")
    image.push("dir:{}".format(dest))
    assert dest.join("version").check(file=1)


def test_image_tag(image):
    name = fake_name()
    wanted = "localhost/" + name + ":latest"
    image.tag(name)
    actual = _buildah.inspect(name)
    assert actual["FromImage"] == image.name
    _buildah.rmi(wanted)


def test_container_config(container):
    wanted = [fake_name()]
    assert container.entrypoint == []
    container.entrypoint = wanted
    assert wanted == container.entrypoint
    container.refresh()
    assert wanted == container.entrypoint

    wanted = ["/bin/bash", "-c", "echo $USER"]
    assert container.cmd == ["/bin/sh"]
    container.cmd = wanted
    assert wanted == container.cmd
    container.refresh()
    assert wanted == container.cmd


    wanted = {"foo": "bar", "one": "two", "PATH": "some"}
    assert list(container.env.keys()) == ["PATH"]
    container.env = wanted
    assert wanted == container.env
    container.refresh()
    assert wanted == container.env

    container.env["PATH"] = "some other"
    assert container.env["PATH"] == "some other"
    container.refresh()
    assert container.env["PATH"] == "some other"

    del container.env["PATH"]
    assert "PATH" not in container.env
    container.refresh()
    assert "PATH" not in container.env


    assert not container.volumes
    container.volumes.add("/tmp/foo")
    assert set(container.volumes) == {"/tmp/foo"}
    container.refresh()
    assert set(container.volumes) == {"/tmp/foo"}

    container.volumes.add("/tmp/bar")
    container.volumes.discard("/tmp/foo")
    assert set(container.volumes) == {"/tmp/bar"}
    container.refresh()
    assert set(container.volumes) == {"/tmp/bar"}


    wanted = {"foo": "bar", "one": "two"}
    assert container.labels == {}
    container.labels = wanted
    container.refresh()
    assert wanted == container.labels
