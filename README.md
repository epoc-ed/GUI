# JFGui — Control Interface for the JUNGFRAU Detector on JEOL TEM

**JFGui** is a graphical user interface for operating the **JUNGFRAU hybrid pixel detector** integrated with **JEOL transmission electron microscopes (TEM)**.
It streamlines detector configuration, acquisition, and live visualization for electron diffraction workflows.

Full documentation: https://epoc-ed.github.io/manual/

---

## Table of Contents
- [Features](#features)
- [Installation (Conda + local recipe)](#installation-conda--local-recipe)
- [Startup](#startup)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [License](#license)
- [Authors & Acknowledgments](#authors--acknowledgments)
- [References / Cite Us](#references--cite-us)

---

## Features

- Control of **JUNGFRAU** detector parameters, trigger modes, and frame acquisition.
- Integration with **JEOL TEM** workflows.
- Live preview and basic visualization of frames.
- Written in **Python** with a **Qt (PySide6)** frontend.
- Reproducible builds using a **Conda recipe**.

For detailed user and operator guides, see the manual: https://epoc-ed.github.io/manual/

---

## Installation (Conda + local recipe)

Below is a condensed “How-To” for building and installing **JFGui** as a Conda package from a local recipe.
For the canonical version, refer to the manual page.

**A) Create the environment**

```bash
git clone git@github.com:epoc-ed/GUI.git
cd GUI
conda create --name jf_gui python=3.10
conda activate jf_gui
cd jungfrau_gui
pip install -r requirements.txt
```

**B) Build and install as a Conda package**

```text
my_project/
├─ jungfrau_gui/
├─ setup.py
├─ MANIFEST.in
└─ conda-recepie/
   └─ meta.yaml
```

```bash
conda install conda-build     # if not already installed
conda build conda-recepie     # produces a .conda/.tar.bz2 in conda-bld/<platform>
conda install --use-local jungfrau_gui \
  || conda install /path/to/conda-bld/noarch/jungfrau_gui-YYYY.MM.DD-py_0.conda
```

---

## Startup

> This is a brief field guide. For the complete startup flow and screenshots, see the **Start up** section of the manual.

### 1) TEM‑PC — Relay server (Windows, PyJEM)

- **Goal:** Allow microscope control from other machines via a ZMQ socket.
- **Usual case:** It may already be running.

**Check & start**

1. On the TEM-PC, verify if `server_tem.py` is running (Miniconda PowerShell Prompt).
   - If running, continue to **CameraPC** below.
2. If not running, double‑click: `C:\Users\JEM User\Documents\DataExchange\bat\run_tem_server.bat`

**Manual fallback (if the .bat fails)**

```powershell
# Open: Miniconda PowerShell Prompt (Anaconda submenu)
# Disable Quick Edit Mode in the console properties if scripts get interrupted.

cd C:\ProgramData\EPOC
conda activate vjem38  # conda environment on TEM-PC with PyJem 3.8 installed
python server_tem.py
```

### 2) CameraPC — Backend & GUI

- As of **2025‑01‑24**, Jungfraujoch **broker** and **writer** are **auto‑started** at boot on `noether`.
- Future releases will use `systemd` services; keep an eye on the manual for updates.

**Sanity checks on DAQ server (optional)**

```bash
ssh noether
ps -elf | grep writer     # expect jfjoch_writer ... tcp://localhost:5500
ps -elf | grep broker     # expect jfjoch_broker /opt/config/broker_jf1M.json

# Metadata updater
ps -elf | grep metadata_update_server
# If missing or stuck:
python -i /data/epoc/storage/jem2100plus/metadata_update_server.py
# If looping in error: ctrl+z; kill %1; fg; re-run the command above.
```

**Initialize detector & launch GUI**

1. Open the web UI: `http://noether:5232/`
2. Click **INITIALIZE** in the webpage.
3. Launch the desktop GUI:
```bash
conda activate jf_gui
# Run the JFGui
# Option 1:
jungfrau_gui            # command after local build
# Option 2:
python launch_gui.py    # without local build from the /GUI folder
```

---

## Configuration

- **Detector host/port**: Set the control server/IP and ports matching your JUNGFRAU readout system.
- **Acquisition settings**: Number of frames, integration time, trigger mode, gain mode.
- **Data paths**: Output directories for saved data and logs.
- **JEOL integration**: Ensure microscope-side services/permissions match your site deployment.

For setting up the Jungfraujoch backend, consult the **Jungfraujoch** section in the manual: [https://epoc-ed.github.io/manual/](https://epoc-ed.github.io/manual/Jungfraujoch.html)

---

## Troubleshooting

- **Package not found after build**  
  Use direct installation from the built `.conda`/`.tar.bz2` path (see above).

- **Missing Qt plugins / blank window**  
  Verify that `PySide6` (or Qt) is installed cleanly in the `jf_gui` environment.

- **Cannot connect to detector**  
  Check network routes, firewall rules, and that the readout/DAQ service is running and reachable.

- **Unknown module errors**  
  Re-run:
  ```bash
  pip install -r jungfrau_gui/requirements.txt
  ```

For more, see the manual: [https://epoc-ed.github.io/manual/](https://epoc-ed.github.io/manual/Troubleshooting.html).

---

## Development

**Install in editable mode**
```bash
conda activate jf_gui
pip install -e .
```

**Contributing**
- Fork the repository, create a feature branch, and submit a PR.
- For larger changes, open an issue first to discuss design and scope.
- Please include concise descriptions, reproducible steps, and screenshots when relevant.

---

## License

This project is distributed under the **To be completed**.
See the [LICENSE](LICENSE) file for the full text.

---

## Authors & Acknowledgments

**Core contributors**
- **Khalil Ferjaoui** — PSI
- **Kiyofumi Takaba** — University of Vienna
- **Erik Fröjd** — PSI
- **Tim Gruene** — University of Vienna

**Acknowledgments**  
We thank the **Paul Scherrer Institute (PSI)**, the **University of Vienna**, and the broader EPOC Electron Diffraction community for support, feedback, and testing during integration on JEOL instruments.

---

## References / Cite Us

Please cite the following when using **JF_GUI** and related JUNGFRAU-based measurements in your work.
(Replace with the final bibliographic details as papers are still in review.)

- Ferjaoui, K., *et al.* **A 1 Megapixel charge integrating hybrid pixel detector for electron diffraction**. *JINST*, 2025.
- Takaba, K., *et al.* **An electron diffractometer with the JUNGFRAU detector with large scale capacity**. *IUCrJ*, 2026.

**BibTeX (template)**
```bibtex
@article{Ferjaoui2025JINST,
  author  = {Ferjaoui, K. and others},
  title   = {A 1 Megapixel charge integrating hybrid pixel detector for electron diffraction},
  journal = {Journal of Instrumentation},
  year    = {2025},
  note    = {In press}
}

@article{Takaba2026IUCrJ,
  author  = {Takaba, K. and others},
  title   = {An electron diffractometer with the JUNGFRAU detector with large scale capacity},
  journal = {IUCrJ},
  year    = {2026}
}
```
