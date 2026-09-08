from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="trading-engine",
    version="2.2.0",
    author="Quantitative Research Department",
    description="Statistical Arbitrage and Market-Making Engine - Glass Box Open Source Architecture",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/YOUR_ORG/trading-engine",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Financial and Insurance Industry",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
    python_requires=">=3.10",
    install_requires=[
        "numpy>=1.24.0",
        "pandas>=2.0.0",
        "pyyaml>=6.0",
        "torch>=2.0.0",
    ],
    keywords=[
        "algorithmic trading",
        "statistical arbitrage",
        "market making",
        "high frequency trading",
        "quantitative finance",
        "risk management",
    ],
)
