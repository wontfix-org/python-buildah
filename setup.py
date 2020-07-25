#!/usr/bin/env python

import setuptools as _setuptools

_setuptools.setup(
    name = "python-buildah",
    version = "0.0.0",
    description = "Control buildah with python",
    author = "Michael van Bracht",
    author_email = "michael@wontfix.org",
    url = "https://github.com/wontfix-org/pyhton-buildah",
    license="MIT",
    packages = _setuptools.find_packages(),
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Programming Language :: Python :: 3 :: Only",
    ],
)
