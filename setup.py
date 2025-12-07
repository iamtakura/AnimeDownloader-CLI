"""Setup script for AnimePahe CLI Downloader."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="animepahe-dl",
    version="1.0.0",
    author="iamtakura",
    description="CLI-based AnimePahe downloader using Brave, Selenium, and yt-dlp",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/iamtakura/AnimeDownloader-CLI",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "animepahe=animepahe.downloader:main",
            "anime-dl=animepahe.downloader:main",
            "apdl=animepahe.downloader:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Multimedia :: Video",
    ],
    keywords="anime, downloader, animepahe, cli, selenium, yt-dlp",
)
