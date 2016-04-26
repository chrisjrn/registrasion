#!/usr/bin/env python
import os
from setuptools import setup, find_packages

import registrasion


def read_file(filename):
    """Read a file into a string."""
    path = os.path.abspath(os.path.dirname(__file__))
    filepath = os.path.join(path, filename)
    try:
        return open(filepath).read()
    except IOError:
        return ''

setup(
    name="registrasion",
    author="Christopher Neugebauer",
    author_email="_@chrisjrn.com",
    version=registrasion.__version__,
    description="A registration app for the Symposion conference management "
                "system.",
    url="http://github.com/chrisjrn/registrasion/",
    packages=find_packages(),
    include_package_data=True,
    classifiers=(
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python",
        "Framework :: Django",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "License :: OSI Approved :: Apache Software License",
    ),
    install_requires=read_file("requirements/base.txt").splitlines(),
    dependency_links=read_file("requirements/dependencies.txt").splitlines(),
)
