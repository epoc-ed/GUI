import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()


setuptools.setup(
    name="jungfrau_gui",
    version= '2024.10.12',
    author="Khalil Ferjaoui",
    author_email="khalil.ferjaoui@psi.ch",
    description="Pyqtgraph based GUI for Jungfrau",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/epoc-ed/GUI",
    packages=setuptools.find_packages(),
    include_package_data = True,
    package_data={'jungfrau_gui': ['ui_config/.reussrc',
    'ui_components/tem_controls/toolbox/jfgui2_config.json',
    'version.txt']},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GPL License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
    entry_points={
        'console_scripts': [
            'jungfrau_gui=jungfrau_gui.main_ui:main',
        ],
    },
)
