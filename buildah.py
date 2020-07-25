# coding: utf-8

import os as _os
import time as _time
import json as _json
import shlex as _shlex
import operator as _op
import subprocess as _sp
import logging as _logging
import tempfile as _tempfile
import contextlib as _contextlib


_log = _logging.getLogger()

global_options = {}
#timings = open("/tmp/timings", "wt")


class BuildahError(Exception):
    pass


class BuildahNotFound(BuildahError):
    pass


def _optify_key(k):
    if len(k) == 1:
        return "-{}".format(k)
    return "--{}".format(k.replace("_", "-"))


def _split_special(d):
    special = {}
    normal = {}
    for key, value in d.items():
        if key.startswith("_"):
            special[key[1:]] = value
        else:
            normal[key] = value
    return (special, normal)


def _optify(d):
    opts = []
    for key, value in d.items():
        if value is None:
            continue
        key = _optify_key(key)
        if isinstance(value, bool):
            opts.append(key)
        elif isinstance(value, (list, tuple, set)):
            for v in value:
                opts += [key, v]
        else:
            opts += [key, str(value)]
    return opts


def _buildah(subcommand, *args, **kwargs):
    special, options = _split_special(kwargs)
    json_ = special.get("json", False)
    json_flag = special.get("json_flag", True)
    list_ = special.get("list", False)
    wrapper = special.get("wrapper")
    capture_output = special.get("capture_output", json_ or list_ or wrapper)

    if not wrapper:
        wrapper = lambda x: x

    if json_ and json_flag:
        options["json"] = True

    cmd = (
        ["buildah"]
        + _optify(global_options)
        + [subcommand]
        + _optify(options)
        + list(args)
    )

    print("Running {}".format(" ".join([str(_).strip() for _ in cmd])))
    t_start = _time.time()
    result = _sp.run(cmd, stdout=_sp.PIPE if capture_output else None, stderr=_sp.PIPE, text=True)
    if result.returncode != 0:
        raise BuildahError(result.stderr)
    #timings.write(_json.dumps({"subcommand": str(subcommand), "options": options, "args": [str(_) for _ in args], "duration": _time.time() - t_start}) + "\n")
    if json_:
        result = _json.loads(result.stdout)
    elif capture_output:
        result = result.stdout

    if list_:
        # Handle "null" return string, the "containers" subcommand
        # returns "null" instead of "[]" when there are no containers
        return [wrapper(_) for _ in result or []]

    if capture_output:
        return wrapper(result)

    return result


class ConfigurableSet(set):

    def __init__(self, name_or_id, option, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._option = option
        self._name_or_id = name_or_id

    def add(self, value):
        config(self._name_or_id, **{self._option: value})
        return super().add(value)

    def discard(self, value):
        config(self._name_or_id, **{self._option: f"{value}-"})
        return super().discard(value)


class ConfigurableMapping(dict):

    def __init__(self, name_or_id, option, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._name_or_id = name_or_id
        self._option = option

    def __setitem__(self, name, value):
        config(self._name_or_id, **{self._option: {name: value}})
        return super().__setitem__(name, value)

    def __delitem__(self, name):
        config(self._name_or_id, **{self._option: {name: None}})
        return super().__delitem__(name)


class Info:

    def __init__(self, name, reader):
        self.name = name
        self._reader = reader

    def __get__(self, obj, objtype):
        if self.name not in obj._cache:
            obj._cache[self.name] = self._reader(obj.info)
        return obj._cache[self.name]


class Configurable(Info):

    def __set__(self, obj, val):
        obj._cache[self.name] = val
        config(obj.id, **{self.name: val})


class Inspectable:

    _TYPE = None

    def __init__(self, name_or_id):
        self._name_or_id = name_or_id
        self.info = None
        self._cache = dict()
        self.refresh()

    def inspect(self):
        return inspect(self._name_or_id, type=self._TYPE)

    def refresh(self):
        self.info = self.inspect()


class Image(Inspectable):

    _TYPE = "image"
    id = Info("id", _op.itemgetter("FromImageID"))
    name = Info("name", _op.itemgetter("FromImage"))
    digest = Info("digest", _op.itemgetter("FromImageDigest"))

    def rm(self):
        return rmi(self.id)

    def push(self, destination):
        return push(self.id, destination)

    def pull(self):
        return pull(self.id)

    def tag(self, *aliases):
        return tag(self.id, *aliases)


class Container(Inspectable):

    _TYPE = "container"
    _config = None

    id = Info("id", lambda x: x["ContainerID"])
    name = Info("name", lambda x: x["Container"])
    annotations = Configurable("annotation", _op.itemgetter("ImageAnnotations"))
    cmd = Configurable("cmd", lambda x: x["OCIv1"]["config"].get("Cmd", []) or [])
    entrypoint = Configurable(
        "entrypoint",
        lambda x: x["OCIv1"]["config"].get("Entrypoint", []) or [],
    )
    port = Configurable("port", lambda x: list(x["OCIv1"]["config"].get("ExposedPorts", {}).keys()))
    imageid = Info("imageid", _op.itemgetter("FromImageID"))
    env = Configurable(
        "env",
        lambda x: ConfigurableMapping(
            x["ContainerID"],
            "env",
            dict(_.split("=", 1) for _ in x["OCIv1"]["config"].get("Env", [])),
        ),
    )
    labels = Configurable(
        "label",
        lambda x: ConfigurableMapping(
            x["ContainerID"],
            "label",
            x["OCIv1"]["config"].get("Labels", {}) or {},
        ),
    )
    workingdir = Configurable("workingdir", lambda x: x["Config"]["config"]["WorkingDir"])
    user = Configurable("user", lambda x: x["Config"]["config"]["User"])
    arch = Configurable("arch", lambda x: x["Config"]["architecture"])
    os = Configurable("os", lambda x: x["Config"]["os"])
    author = Configurable("author", lambda x: x["OCIv1"].get("author"))
    volumes = Configurable(
        "volume",
        lambda x: ConfigurableSet(
            x["ContainerID"],
            "volume", 
            (x["OCIv1"]["config"].get("Volumes") or {}).keys(),
        ),
    )
    onbuild = Configurable("onbuild", lambda x: x["Config"].get("OnBuild"))
    stop_signal = Configurable("stop_signal", lambda x: x["OCIv1"]["config"].get("StopSignal"))

    def __init__(self, name_or_id=None, base=None):
        if name_or_id is None and base is None:
            raise RuntimeError("You need to either pass an existing image name or a base image to create a new container from")

        if base is not None:
            name_or_id = from_(base, _wrapper=str, name=name_or_id)

        super().__init__(name_or_id)

    def rmi(self, **options):
        return rmi(self.imageid, **options)

    def rm(self, **options):
        return rm(self.id, **options)

    def add(self, source, *args, **options):
        return add(self.id, source, *args, **options)

    def add_contents(self, contents, *args, mode=None, **options):
        with _tempfile.NamedTemporaryFile() as f:
            if mode is not None:
                _os.fchmod(f.fileno(), mode)
            f.write(contents)
            f.flush()
            return add(self.id, f.name, *args, **options)

    def copy(self, source, *args, **options):
        return copy(self.id, source, *args, **options)

    @_contextlib.contextmanager
    def mount(self, **options):
        yield list(mount(self.id, **options).values())[0]
        umount(self.id)

    def commit(self, image_name, **options):
        return commit(self.id, image_name, **options)

    def run(self, *args, **options):
        return run(self.id, *args, **options)


def rmi(name_or_id, **kwargs):
    return _buildah("rmi", name_or_id, _capture_output=True, **kwargs)


def rm(name_or_id, **kwargs):
    return _buildah("rm", name_or_id, _capture_output=True, **kwargs)


def images(*args, **options):
    return _buildah(
        "images",
        *args,
        _list=True,
        _json=True,
        _wrapper=lambda x: Image(x["id"]),
        **options
    )


def containers(*args, **options):
    return _buildah(
        "containers",
        *args,
        _list=True,
        _json=True,
        _wrapper=lambda x: Container(x["id"]),
        **options
    )


def inspect(image_or_container, **options):
    try:
        info = _json.loads(
            _buildah(
                "inspect",
                image_or_container,
                _capture_output=True,
                **options
            ),
        )
        if info.get("Config"):
            info["Config"] = _json.loads(info["Config"])
        return info
    except BuildahError as e:
        raise BuildahNotFound(
            "Could not find container or image {!r}".format(image_or_container),
        ) from e


def from_(base, _wrapper=Container, **options):
    f = _tempfile.NamedTemporaryFile(mode="w+t")
    _result = _buildah(
        "from",
        base,
        _capture_output=True,
        cidfile=f.name,
        _wrapper=None,
        **options,
    )
    return _wrapper(str(f.read()))


def commit(name_or_id, image_name, **options):
    return _buildah(
        "commit",
        name_or_id,
        image_name,
        _wrapper=lambda _: Image(_.strip()),
        **options,
    )


def unshare():
    if "BUILDAH_ISOLATION" in _os.environ:
        return
    cmdline = open("/proc/self/cmdline", "rt").read().split("\0")
    cmdline = ["buildah"] + _optify(global_options) + ["unshare"] + cmdline
    _os.execvp("buildah", cmdline)


def run(name_or_id, cmd, **options):
    if isinstance(cmd, str):
        cmd = ["sh", "-c", cmd]

    return _buildah("run", name_or_id, *cmd, **options)


def copy(name_or_id, *args, **options):
    return _buildah("copy", name_or_id, *args, _capture_output=True, **options)


def info():
    return _buildah("info", _json=True, _json_flag=False)


def mount(*names_or_ids, **options):
    output = _buildah("mount", *names_or_ids, _capture_output=True, **options)
    output = output.strip()

    if not output:
        return {}

    if len(names_or_ids) > 1 or not names_or_ids:
        return dict(_.split(" ") for _ in output.split("\n"))
    return {names_or_ids[0]: output}


def umount(*names_or_ids, **options):
    output = _buildah("umount", *names_or_ids, _capture_output=True, **options)
    output = output.strip()
    return output.split("\n")


def add(name_or_id, *args, **options):
    return _buildah("add", name_or_id, *args, _capture_output=True, **options)


def _shlex_join(l):
    return " ".join(_shlex.quote(_) for _ in l)


def config(name_or_id, **options):
    def list_writer(x):
        return [f"{k}={v}" if v is not None else f"{k}-" for k, v in x.items()]

    def mapping_writer(x):
        return [f"{k}={v}" if v is not None else f"{k}-" for k, v in x.items()]

    writer = {
        # Even though entrypoint and cmd are output in `inspect` as lists
        # One supports accepting a json array, the other only strings that
        # are then kinda `shlex.split` into an array again.
        # In order to prevent confusion, we justr decide that the only valid
        # representation for is is arrays, we convert the input accordingly
        # and as of now, do not need to do anything about the output since
        # that is arrays already in both cases.
        "entrypoint": _json.dumps,
        "cmd": _shlex_join,
        # I know a "key=value" string is even the official interface via `putenv`,
        # but in my head these are mappings and so my head always hurts when I
        # have to force it into this weird mode, so just handle them all as dicts
        "env": mapping_writer,
        "label": mapping_writer,
        "annotation": mapping_writer,
    }
    for key, value in options.items():
        if key not in writer:
            continue
        options[key] = writer[key](value)
    return _buildah("config", name_or_id, **options)


def pull(name, **options):
    return _buildah("pull", name, quiet=True, _wrapper=lambda x: Image(x.strip()), **options)


def push(name_or_id, destination, **options):
    return _buildah(
        "push",
        name_or_id,
        destination,
        quiet=True,
        **options,
    )


def tag(name_or_id, *aliases, **options):
    return _buildah("tag", name_or_id, *aliases, **options)
