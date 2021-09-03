from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name='pakler',
    use_scm_version={
        'write_to': '_version.py',
    },
    setup_requires=['setuptools_scm'],
    author='Vincent Mallet',
    author_email='vmallet@gmail.com',
    license='MIT License',
    description='Manipulate .PAK firmware files from Swann and Reolink',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/vmallet/pakler',
    py_modules = ['swanntool', '_version'],
    packages=find_packages(),
    install_requires=[],
    python_requires='>=3.6',
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.6",
        "Operating System :: OS Independent",
    ],
    entry_points = '''
        [console_scripts]
        pakler=swanntool:main
        '''
)
