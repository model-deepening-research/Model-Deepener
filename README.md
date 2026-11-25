# Model Deepener

<img width="1870" height="499" alt="Model Deepener Logo" src="https://github.com/user-attachments/assets/e0e0cef2-23e4-42a7-b089-43953145c81a" />

## Overview
Model Deepener is the core application of a research project aimed to support automated model deepening. Model deepening transforms flat representations into multi-level models, increasing the level of semantics of the original representation and thus facilitating comprehensibility, integration, and reusability of representation. The current version of the tool supports uploading CSV files or flat FMMLx models and can produce multi-level models in FMMLx. The FMMLx (Flexible Multi-Level Modeling and Execution Language)[^1] is an object-oriented multi-level modeling language. Multi-level modeling (MLM) is a novel conceptual-modeling paradigm for information-systems development that enables the specification of an unbounded number of classification levels, among others. The FMMLx offers a two-level modeling mode that resembles common UML syntax called UML++.[^2] FMMLx and UML++ models can be created, executed, and instantiated with the [XModelerML](https://github.com/xmf-xmodeler/MosaicFX).[^3]
[^1]: Frank U (2014) Multilevel Modeling: Toward a New Paradigm of Conceptual Modeling and Information Systems Design. Business and Information Systems Engineering 6(6):319–337
[^2]: Maier P, Schwarz T (2024) UML++: Enhancing Student Learning of Object-Oriented Modeling through Executable Objects. MODELS Companion '24: Proceedings of the ACM/IEEE 27th International Conference on Model Driven Engineering Languages and Systems, pp 107–114
[^3]: Maier P, Töpel D (2025) XModelerML v3: Integrating Executable UML with a Multi-Level Language Engineering, Modeling, and Execution Environment. ACM/IEEE 28th International Conference on Model Driven Engineering Languages and Systems Companion (MODELS-C)

Maier and Kadziolka (2026)[^4] investigate the potential for using LLMs to support model deepening. Maier (2026)[^5] motivates and describes one analysis approach of model deepening called _Property-Precedence Analysis_ that analyzes populations of instance data to infer possible higher-level conceptual distinctions.
[^4]: Maier P, Kadziolka V (2026) Model Deepening with Large Language Models: Insights from Exploratory Studies with ChatGPT. Advances in Conceptual Modeling: - ER 2025 Workshops, CMLS, FCM, LLM4Modeling, OntoCom, and QUAMES, Poitiers, France, October 20–23, 2025, Proceedings, pp 119–136<br>
[^5]:  Maier P (2026) Property-Precedence Analysis for Model Deepening. Proceedings of the ACM/IEEE 29th International Conference on Model Driven Engineering Languages and Systems, pp. 1024-1033

> [!IMPORTANT]
> The tool is targeted for a research audience and only supports experimentation with sample models at the current stage.

## Installation Guide

### Preconditions

| Requirement | Details |
|---|---|
| **Python 3.12** | Implemented and tested only with Python 3.12 |
| **Tkinter** | The GUI is built on Tkinter/CustomTkinter. It's included with the python.org installers for Windows and macOS. On Linux, install it separately (e.g. `sudo apt install python3.12-tk`). |
| **Git** | Needed to clone the repository. You can also download the ZIP from GitHub instead. |
| **Operating system** | Windows is the main development and test platform. Some window-handling features use Windows APIs and are skipped on other systems. |
| *Optional:* **Graphviz** | Only needed to export precedence graphs as PNG/SVG images. Install it from [graphviz.org](https://graphviz.org/download/) and make sure `dot` is on your `PATH`. |
| *Optional:* **XModelerML** | Needed to open, execute and instantiate the FMMLx/UML++ models the tool produces. Download here: [XModelerML](https://www.wi-inf.uni-due.de/LE4MM/xmodelerml/#download). |

You can check your Python version with:

```bash
python --version      # should print Python 3.12.x
```

### 1. Clone the repository

```bash
git clone https://github.com/model-deepening-research/Model-Deepener.git
cd Model-Deepener
```

### 2. Create and activate a virtual environment

**Windows (PowerShell)**
```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux**
```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 3. Install the dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Start Model Deepener

Run this from the repository root (the folder that contains `src/`):

```bash
python -m src
```

The Model Deepener GUI should open. Sample input models (CSV, FMMLx, Ecore, PlantUML, XMI) are in the `models/` folder.

### Troubleshooting

- **`ModuleNotFoundError: No module named 'src'`**: Start the tool from the repository root with `python -m src`. Don't run `python src/__main__.py` or start it from inside `src/`.
- **`ModuleNotFoundError: No module named 'tkinter'`**: Tkinter is missing from your Python installation. See the preconditions above.
- **pip fails to build `numpy` or `pandas`**: You're probably on Python 3.13 or newer. Recreate the virtual environment with Python 3.12.
- **Graph image export fails (`"dot" not found in path`)**: Install Graphviz and restart your terminal.

## Authors

Created and maintained by Pierre Maier ([@map-research](https://github.com/map-research)), University of Duisburg-Essen

Installation guide created with Claude.ai
