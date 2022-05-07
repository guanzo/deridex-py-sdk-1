import setuptools


with open("README.md", "r") as f:
    long_description = f.read()

setuptools.setup(
    name="deridex-py-sdk",
    description="Deridex Derivative Protocol Python SDK",
    author="Deridex",
    author_email="info@deridex.org",
    version="0.0.1",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="MIT",
    project_urls={
        "Source": "https://github.com/DeridexHQ/deridex-py-sdk",
    },
    install_requires=["py-algorand-sdk >= 1.6.0"],
    packages=setuptools.find_packages(),
    python_requires=">=3.8",
    package_data={'deridex.options.v1': ['contracts.json']},
    include_package_data=True,
)