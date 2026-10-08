"""Setup script for Manus Python SDK"""
from setuptools import setup

setup(
    name="manus-sdk",
    version="1.0.0",
    description="Python bindings for Manus SDK using CFFI",
    author="Manus Meta",
    packages=["manus_sdk", "manus_sdk.generated"],
    py_modules=["_manus_sdk"],
    package_data={
        "manus_sdk": [
            "ManusSDK/include/*.h",
            "ManusSDK/lib/*",
            "generated/*.py",
        ],
    },
    include_package_data=True,
    python_requires=">=3.9,<3.15",
)
