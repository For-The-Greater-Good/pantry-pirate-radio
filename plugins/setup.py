from setuptools import setup

setup(
    name="datasette-custom-nav",
    version="0.1",
    py_modules=["datasette_custom_nav"],
    entry_points={
        "datasette": ["custom_nav = datasette_custom_nav"]
    },
)