#!/usr/bin/env python # -- coding: utf-8 --

from setuptools import setup, find_packages

import sys

version = '1.0-dev'

install_requires = [
    'setuptools',
    'twisted',
    'txzookeeper >= 0.9.6',
    ]

if sys.version_info[:3] < (2,6,0):
    raise ValueError("Must have Python 2.6+.")


setup(name="pop",
      version=version,
      description="Automated build, deployment and service management tool.",
      long_description=open("README.rst").read() + open("CHANGES.rst").read(),
      classifiers=[
        "Programming Language :: Python",
        "Topic :: Software Development :: Libraries :: Python Modules",
        ],
      keywords="coordination deployment services zookeeper",
      author="Malthe Borch",
      author_email="mborch@gmail.com",
      url="http://www.github.com/malthe/pop",
      license="GPL",
      namespace_packages=[],
      packages = find_packages('src'),
      package_dir = {'':'src'},
      include_package_data=True,
      zip_safe=False,
      entry_points = """
      [console_scripts]
      pop = pop.control:main
      """,
      install_requires=install_requires,
      tests_require=install_requires + [
          'nose',
          ],
      )
