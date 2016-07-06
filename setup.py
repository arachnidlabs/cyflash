import re
from setuptools import setup


version = re.search(
    '^__version__\s*=\s*"(.*)"',
    open('cyflash/bootload.py').read(),
    re.M
    ).group(1)


with open("README.md", "rb") as f:
    long_descr = f.read().decode("utf-8")


setup(
    name = "cyflash",
    packages = ["cyflash"],
    entry_points = {
        "console_scripts": ['cyflash = cyflash.bootload:main']
        },
    version = version,
    description = "Tool for flashing data to Cypress PSoC devices via bootloader.",
    long_description = long_descr,
    author = "Nick Johnson",
    author_email = "nick@arachnidlabs.com",
    url = "http://github.com/arachnidlabs/cyflash/",
    install_requires = ["pyserial", "six"],
    include_package_data = True,
    )
