# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""CVG GeoServ Processor -- setup.py (legacy editable install support)."""

from setuptools import setup, find_packages

setup(
    name="geoserv-processor",
    version="1.0.0",
    description=(
        "CVG GeoServ Processor -- shared geospatial processing engine "
        "for the CVG Wizard Suite (Rainfall, SLR, Storm Surge Wizards)"
    ),
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Alex Zelenski, GISP",
    author_email="azelenski@clearviewgeographic.com",
    url="https://www.clearviewgeographic.com",
    license="Proprietary",
    packages=find_packages(exclude=["tests*", "docs*"]),
    python_requires=">=3.11",
    install_requires=[
        "rasterio>=1.3",
        "numpy>=1.26",
        "click>=8.1",
        "fastapi>=0.110",
        "uvicorn[standard]>=0.29",
        "pydantic>=2.0",
        "geopandas>=0.14",
        "shapely>=2.0",
        "fiona>=1.9",
        "scikit-image>=0.22",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0",
            "pytest-cov>=5.0",
            "flake8>=7.0",
            "black>=24.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "geoserv-processor=geoserv_processor.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: GIS",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "License :: Other/Proprietary License",
        "Operating System :: OS Independent",
    ],
    keywords=[
        "gis", "geospatial", "flood", "dem", "raster",
        "storm surge", "sea level rise", "rainfall", "geoprocessing",
    ],
)
