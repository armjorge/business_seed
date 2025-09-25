# business_seed

business_seed is an interactive command line assistant for spinning up Oracle XE containers, installing Oracle APEX, and cataloging multiple client initiatives so you can move from strategic design to operational delivery in days instead of weeks.

## Overview
- Capture per-business metadata (name, container reference, APEX URL, installation status) in a lightweight SQLite registry.
- Automate the busywork of cloning Oracle Docker containers and keeping their IDs handy.
- Walk through an opinionated Oracle APEX + ORDS installation checklist with clipboard-ready commands.
- Keep artefacts such as APEX, ORDS, and JDK installers organized for consistent redeployments.

## Repository Layout
- `main.py`: interactive menu that orchestrates project tracking, container prompts, and the installation wizard.
- `Scripts/handle_container_db.py`: SQLite wrapper that stores project/container data and exposes CRUD helpers.
- `Scripts/install_apex.py`: reusable guidance engine that discovers required installers and produces staged checklists for APEX and ORDS.
- `Local Data/`: runtime working area generated on first run (config file, SQLite database, APEX installer cache).

## Prerequisites
- Python 3.10+ with `pip install pyyaml`.
- Docker Desktop (or Docker Engine) with the `gvenzl/oracle-xe:21-slim` image available locally.
- Oracle download bundles stored under `Local Data/APEX_files/` (JDK for Linux x64, APEX, and ORDS archives).
- macOS clipboard utilities (`pbcopy`) are used by default; on Linux install `xclip` or `xsel` if you want clipboard support.

## Setup
1. Clone or download this repository.
2. (Optional) create and activate a virtual environment.
3. Install dependencies: `pip install -r requirements.txt` (or simply `pip install pyyaml`).
4. Run `python main.py` to launch the assistant. On the first launch it will create `Local Data/config.yaml`; edit it with your database defaults before continuing.

## Usage
### Launching the Assistant
Run `python main.py` and use the numeric shortcuts to navigate. Press `0` in any menu to back out.

### Manage Projects
- Register each business initiative with a friendly name, optional container alias, and default APEX URL.
- Review existing projects, update container metadata, or delete stale entries without touching running containers.
- Use "Fix projects without container info" to bulk-fill missing Docker IDs as containers come online.

### Install Oracle APEX
- Select a project that still needs APEX and review the local artefact report. Missing files are highlighted so you can drop them into `Local Data/APEX_files/`.
- Follow the staged installation wizard to copy installers, configure Java, set up ORDS, and finalize the APEX workspace. Commands can be copied straight to your clipboard.
- Mark the project as APEX-ready once you can reach the published URL; the assistant will persist the status and updated URL for future reference.

### Working Folder (`Local Data/`)
- `config.yaml`: template for environment defaults (host, ports, credentials) that feed the guided steps.
- `container_projects.db`: SQLite file with the project registry—back it up to carry the portfolio across machines.
- `APEX_files/`: drop installers here to enable auto-discovery by the wizard.

## Roadmap Ideas
- Add scripted Oracle datafile exports for fast environment snapshots.
- Enrich project records with operational KPIs to bridge strategy, execution, and analytics.
- Surface project health dashboards once multiple business designs are tracked.

## Contributing
Feel free to open issues or submit pull requests with improvements to the workflow, documentation, or automation scripts.
