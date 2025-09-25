"""Guidance helpers for preparing Oracle APEX inside Docker containers."""

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class InstallationStep:
    """Describe a single actionable instruction for the guided installer."""

    title: str
    description: str
    context: str
    commands: List[str] = field(default_factory=list)


@dataclass
class InstallationStage:
    """Group multiple steps under a themed stage."""

    key: str
    title: str
    description: str
    steps: List[InstallationStep]


class ApexInstallerHelper:
    """Utility class that keeps track of local APEX artifacts and installation guidance."""

    REQUIRED_ARTIFACTS: Dict[str, Dict[str, object]] = {
        "java": {
            "keywords": ["jdk", "linux"],
            "url": "https://www.oracle.com/java/technologies/downloads/",
            "friendly_name": "Java Development Kit for Linux x64",
        },
        "apex": {
            "keywords": ["apex"],
            "url": "https://www.oracle.com/tools/downloads/apex-downloads/",
            "friendly_name": "Oracle APEX bundle",
        },
        "ords": {
            "keywords": ["ords"],
            "url": "https://www.oracle.com/database/technologies/appdev/rest-data-services-downloads.html",
            "friendly_name": "Oracle REST Data Services (ORDS)",
        },
    }

    def __init__(self, working_folder: str) -> None:
        self.working_folder = working_folder
        self.apex_folder = os.path.join(self.working_folder, "APEX_files")
        os.makedirs(self.apex_folder, exist_ok=True)

    def scan_required_files(self) -> Dict[str, Optional[str]]:
        """Return a map with the best match for every required artifact."""
        matches: Dict[str, Optional[str]] = {}
        for key, metadata in self.REQUIRED_ARTIFACTS.items():
            matches[key] = self._find_artifact(metadata["keywords"])
        return matches

    def missing_artifacts_report(self, matches: Dict[str, Optional[str]]) -> List[str]:
        """Create user facing notes about missing downloads."""
        notes: List[str] = []
        for key, metadata in self.REQUIRED_ARTIFACTS.items():
            if matches.get(key):
                continue
            notes.append(
                f"Missing {metadata['friendly_name']}. Download it from {metadata['url']}"
            )
        return notes

    def artifact_summary(self, matches: Dict[str, Optional[str]]) -> List[str]:
        """Summarize the artifacts and their discovered paths."""
        lines: List[str] = []
        for key, metadata in self.REQUIRED_ARTIFACTS.items():
            path = matches.get(key)
            if path:
                lines.append(f"{metadata['friendly_name']}: {path}")
            else:
                lines.append(f"{metadata['friendly_name']}: not found")
        return lines

    def installation_checklist(self, project: Dict[str, object]) -> List[str]:
        """Prepare procedural steps for installing APEX inside a container."""
        container_id = project.get("container_id") or "<container_id>"
        apex_url = project.get("apex_url") or "http://localhost:8080/ords"

        checklist = [
            "Make sure Docker Desktop is running and the Oracle database image is installed.",
            f"Start the container: docker start {container_id}",
            f"Attach to the container shell: docker exec -it {container_id} bash",
            "Inside the container, create a tools directory: mkdir -p /opt/oracle/tools",
            "From the host: docker cp ./APEX_files/. {container_id}:/opt/oracle/tools",
            "Inside the container unzip APEX: cd /opt/oracle/tools && unzip apex*.zip",
            "Install APEX following the official guide (run apexins.sql as SYS).",
            "Install ORDS by running ords.war setup pointing to the pluggable database.",
            "Expose ORDS using the suggested port mapping or confirm it already listens on 8080.",
            f"Access APEX: {apex_url}",
        ]
        return checklist

    def run_installation_wizard(
        self, project: Dict[str, object], matches: Dict[str, Optional[str]]
    ) -> None:
        """Walk the user through an interactive, copy-friendly installation guide."""

        stages = self._build_guided_stages(project, matches)
        if not stages:
            print(
                "\nGuided wizard is unavailable: make sure the project has container information."
            )
            return

        print("\n--- Guided APEX Installation Wizard ---")
        print("Pick the stage you need. You can run them individually or execute all of them in sequence.")

        collected_notes: List[str] = []
        stage_map = {str(index): stage for index, stage in enumerate(stages)}
        stage_keys = {stage.key.lower(): stage for stage in stages}

        while True:
            print("\nAvailable stages:")
            for index, stage in enumerate(stages):
                print(f"  [{index}] {stage.title} — {stage.description}")

            choice = input(
                "Select a stage number, type its keyword, use 'a' for all, or press Enter to exit: "
            ).strip().lower()

            if not choice:
                break

            if choice in {"a", "all"}:
                sequence = stages
            elif choice in stage_map:
                sequence = [stage_map[choice]]
            elif choice in stage_keys:
                sequence = [stage_keys[choice]]
            else:
                print("Unknown option. Try again.")
                continue

            interrupted = False
            for stage in sequence:
                if not self._run_stage(stage, collected_notes):
                    interrupted = True
                    break

            if interrupted:
                break

        if collected_notes:
            print("\nSession notes:")
            for entry in collected_notes:
                print(f"  - {entry}")
        print("\nWizard closed. Re-run it if you need to revisit any stage.")

    def _run_stage(
        self, stage: InstallationStage, collected_notes: List[str]
    ) -> bool:
        """Execute all steps for a given stage and return False if interrupted."""

        print(f"\n=== {stage.title} ===")
        print(stage.description)

        for index, step in enumerate(stage.steps, start=1):
            if not self._process_step(step, index, stage, collected_notes):
                return False
        return True

    def _process_step(
        self,
        step: InstallationStep,
        index: int,
        stage: InstallationStage,
        collected_notes: List[str],
    ) -> bool:
        """Interact with the user for a single step; return False if the wizard should exit."""

        print(f"\n[{stage.key.upper()} {index:02d}] {step.title} — {step.context}")
        print(step.description)

        if step.commands:
            print("Suggested commands:")
            for cmd_index, command in enumerate(step.commands, start=1):
                print(f"  ({cmd_index}) {command}")

            while True:
                choice = input(
                    "Select a command number to copy, 'a' to copy all, or press Enter to continue: "
                ).strip().lower()
                if not choice:
                    break
                if choice == "a":
                    if copy_to_clipboard("\n".join(step.commands)):
                        print("All commands copied to clipboard.")
                    else:
                        print("Could not copy commands to the clipboard.")
                    continue
                if choice.isdigit():
                    selected = int(choice) - 1
                    if 0 <= selected < len(step.commands):
                        if copy_to_clipboard(step.commands[selected]):
                            print("Command copied to clipboard.")
                        else:
                            print("Clipboard copy failed on this system.")
                    else:
                        print("Command number out of range.")
                    continue
                print("Unknown option. Please try again.")

        while True:
            follow_up = input(
                "Press Enter when the step is done, 'n' to log a note, or 'q' to exit the wizard: "
            ).strip().lower()
            if not follow_up:
                break
            if follow_up == "n":
                note = input("Write your note for this step: ").strip()
                if note:
                    collected_notes.append(f"{stage.title} / {step.title}: {note}")
                continue
            if follow_up == "q":
                print("Wizard interrupted. Resume later from the remaining steps.")
                return False
            print("Unknown option. Please try again.")

        return True

    def _build_guided_stages(
        self, project: Dict[str, object], matches: Dict[str, Optional[str]]
    ) -> List[InstallationStage]:
        """Transform project metadata into themed stages for the guided wizard."""

        container_reference = self._resolve_container_reference(project)
        if not container_reference:
            return []

        container_label = project.get("container_name") or container_reference
        apex_url = project.get("apex_url") or "http://localhost:8080/ords"
        tools_folder = "/opt/oracle/tools"

        artifacts_folder = os.path.join(self.working_folder, "APEX_files")
        artifacts_dir = artifacts_folder.rstrip("/\\")
        copy_source = shlex.quote(f"{artifacts_dir}/.")

        java_path = matches.get("java")
        ords_path = matches.get("ords")
        apex_path = matches.get("apex")

        java_archive = os.path.basename(java_path) if java_path else None
        ords_archive = os.path.basename(ords_path) if ords_path else None
        apex_archive = os.path.basename(apex_path) if apex_path else None

        java_hint = self._guess_java_home(java_archive)
        ords_home = "ords"
        apex_home = "apex"
        ords_config_root = "/opt/oracle/ords_config"

        if sys.platform == "darwin":
            browser_command = f"open {apex_url}"
        elif sys.platform == "win32":
            browser_command = f"start {apex_url}"
        else:
            browser_command = f"xdg-open {apex_url}"

        available = [name for name in (java_archive, ords_archive, apex_archive) if name]
        missing = [
            metadata["friendly_name"]
            for key, metadata in self.REQUIRED_ARTIFACTS.items()
            if not matches.get(key)
        ]

        artifact_message = "Found archives: " + ", ".join(available) if available else "No archives detected."
        if missing:
            artifact_message += " Missing: " + ", ".join(missing) + "."

        # Stage 0 – prepare container and unpack files
        preparation_steps: List[InstallationStep] = [
            InstallationStep(
                title="Verify Docker runtime",
                context="Host shell",
                description=(
                    "Make sure Docker Desktop is running and can reach the local daemon. "
                    "Install the gvenzl/oracle-xe image beforehand."
                ),
                commands=["docker info"],
            ),
            InstallationStep(
                title="Start Oracle container",
                context="Host shell",
                description=(
                    f"Start the container assigned to this project ({container_label}) and wait for the database to open. "
                    "Follow the logs until you see Database ready messages, then exit with CTRL+C."
                ),
                commands=[
                    f"docker start {container_reference}",
                    f"docker logs -f {container_reference}",
                ],
            ),
            InstallationStep(
                title="Create tools directory",
                context="Host shell",
                description=(
                    "Ensure the shared tools directory exists inside the container before copying the installers."
                ),
                commands=[f"docker exec -it {container_reference} mkdir -p {tools_folder}"],
            ),
            InstallationStep(
                title="Copy installation artifacts",
                context="Host shell",
                description=(
                    f"Transfer the installer archives into the container. {artifact_message}"
                ),
                commands=[
                    f"docker cp {copy_source} {container_reference}:{tools_folder}",
                    f"docker exec -it {container_reference} ls -lh {tools_folder}",
                ],
            ),
            InstallationStep(
                title="Open oracle shell",
                context="Host shell",
                description=(
                    "Enter the container as the oracle user. Use the root shell as a fallback and export ORACLE_HOME manually."
                ),
                commands=[
                    f"docker exec -it --user oracle {container_reference} bash",
                    f"docker exec -it {container_reference} bash",
                ],
            ),
        ]

        extract_commands: List[str] = [
            f"cd {tools_folder}",
            "ls -1",
        ]
        if java_archive:
            extract_commands.append(f"tar -xzf {java_archive}")
        if apex_archive:
            extract_commands.append(f"unzip -o {apex_archive}")
        if ords_archive:
            extract_commands.append("mkdir -p ords")
            extract_commands.append(f"unzip -o {ords_archive} -d ords")
        extract_commands.append(f"ls -lh {tools_folder}")

        preparation_steps.append(
            InstallationStep(
                title="Extract installers",
                context="Container shell",
                description=(
                    "Unpack the archives inside the tools directory. If the files were already extracted, re-run the commands to refresh them."
                ),
                commands=extract_commands,
            )
        )

        # Stage 1 – Java runtime
        java_steps = [
            InstallationStep(
                title="Configure Java environment",
                context="Container shell",
                description=(
                    "Point JAVA_HOME to the JDK you just extracted so ORDS can use it. Adjust the folder name if it differs or if you are running as root instead of the oracle user."
                ),
                commands=[
                    f"cd {tools_folder}",
                    f"export JAVA_HOME={tools_folder}/{java_hint}",
                    "export PATH=\"$JAVA_HOME/bin:$PATH\"",
                    "$JAVA_HOME/bin/java -version",
                ],
            ),
            InstallationStep(
                title="Persist Java environment (optional)",
                context="Container shell",
                description=(
                    "Append the JAVA_HOME exports to the oracle user's shell profile so new sessions inherit the configuration. Skip if you prefer to set it manually per session."
                ),
                commands=[
                    f"echo 'export JAVA_HOME={tools_folder}/{java_hint}' >> ~/.bashrc",
                    "echo 'export PATH=\"$JAVA_HOME/bin:$PATH\"' >> ~/.bashrc",
                    "tail -n 5 ~/.bashrc",
                ],
            ),
        ]

        # Stage 2 – ORDS setup
        ords_steps = [
            InstallationStep(
                title="Make ORDS CLI available",
                context="Container shell",
                description=(
                    "Add the ords launcher to PATH for this session. Append the export to ~/.bashrc if you want every shell to include it automatically."
                ),
                commands=[
                    f"cd {tools_folder}/{ords_home}",
                    f"export PATH=\"$PATH:{tools_folder}/{ords_home}/bin\"",
                    f"echo 'export PATH=\"$PATH:{tools_folder}/{ords_home}/bin\"' >> ~/.bashrc  # optional",
                    "ords --version",
                ],
            ),
            InstallationStep(
                title="Review ORDS directory",
                context="Container shell",
                description=(
                    "Confirm the ORDS archive was extracted into its own folder."
                ),
                commands=[
                    f"cd {tools_folder}",
                    "ls -1",
                    f"cd {tools_folder}/{ords_home}",
                    "ls -1",
                ],
            ),
            InstallationStep(
                title="Prepare ORDS configuration directory",
                context="Container shell",
                description=(
                    "Create a configuration folder outside the ORDS product path to avoid warnings. If you are retrying the install, move the previous config out of the way first."
                ),
                commands=[
                    "mv /opt/oracle/ords_config /opt/oracle/ords_config.bak.$(date +%Y%m%d%H%M%S) 2>/dev/null || true",
                    f"mkdir -p {ords_config_root}",
                    f"ls -ld {ords_config_root}",
                ],
            ),
            InstallationStep(
                title="Install ORDS",
                context="Container shell",
                description=(
                    "Run the interactive installer. Select connection type 1 (Basic), enter host localhost, port 1521, and service XEPDB1. When prompted for administrator credentials use 'sys as sysdba' with the container password (JACJConsulting). On the summary screen edit option 3 to set a known password for ORDS_PUBLIC_USER, then accept the configuration."
                ),
                commands=[
                    f"cd {tools_folder}/{ords_home}",
                    f"ords --config {ords_config_root} install",
                ],
            ),
            InstallationStep(
                title="Sync ORDS runtime credentials",
                context="Container shell",
                description=(
                    "Reset the ORDS and APEX REST users to the password you chose in the installer, then store it securely in the ORDS config. Replace <ords_password> with that value when running these commands."
                ),
                commands=[
                    "sqlplus / as sysdba <<'EOF'",
                    "ALTER SESSION SET CONTAINER = CDB$ROOT;",
                    "ALTER USER ORDS_PUBLIC_USER IDENTIFIED BY \"<ords_password>\" ACCOUNT UNLOCK CONTAINER = ALL;",
                    "ALTER SESSION SET CONTAINER = XEPDB1;",
                    "ALTER USER APEX_PUBLIC_USER IDENTIFIED BY \"<ords_password>\" ACCOUNT UNLOCK;",
                    "ALTER USER APEX_REST_PUBLIC_USER IDENTIFIED BY \"<ords_password>\" ACCOUNT UNLOCK;",
                    "EXIT;",
                    "EOF",
                    f"ords --config {ords_config_root} config secret db.password",
                    "# enter <ords_password> when prompted",
                ],
            ),
            InstallationStep(
                title="Enable PL/SQL gateway",
                context="Container shell",
                description=(
                    "Turn on the PL/SQL gateway so /ords/apex and /ords/apex_admin respond."
                ),
                commands=[
                    f"ords --config {ords_config_root} config set feature.plsql.gateway.enabled true",
                ],
            ),
            InstallationStep(
                title="Start ORDS service",
                context="Container shell",
                description=(
                    "Launch ORDS so it listens on port 8080. Consider using screen, tmux, or nohup to keep it running in the background."
                ),
                commands=[
                    f"cd {tools_folder}/{ords_home}",
                    f"ords --config {ords_config_root} serve",
                    f"curl -I {apex_url.rstrip('/')}/_/",
                ],
            ),
            InstallationStep(
                title="Grant ORDS-enabled schema access",
                context="Container shell",
                description=(
                    "Run the optional grant/enable tasks if you plan to use SQL Developer Web or REST endpoints for additional schemas."
                ),
                commands=[
                    f"cd {tools_folder}/{ords_home}",
                    f"ords --config {ords_config_root} grant-schema",
                    f"ords --config {ords_config_root} enable-schema",
                ],
            ),
        ]

        # Stage 3 – APEX installation
        apex_steps = [
            InstallationStep(
                title="Inspect XDB component",
                context="Container shell",
                description=(
                    "Verify the XDB component status in both CDB$ROOT and XEPDB1. APEX requires XDB to be VALID in every container."
                ),
                commands=[
                    "sqlplus / as sysdba",
                    "SHOW con_name;",
                    "SELECT comp_name, status FROM dba_registry WHERE comp_id = 'XDB';",
                    "ALTER SESSION SET CONTAINER = XEPDB1;",
                    "SHOW con_name;",
                    "SELECT comp_name, status FROM dba_registry WHERE comp_id = 'XDB';",
                ],
            ),
            InstallationStep(
                title="Repair XDB when invalid (advanced)",
                context="Container shell",
                description=(
                    "If XDB reports INVALID in any container, follow Oracle's documented reload procedure. This restarts the instance in UPGRADE mode; plan for downtime. Skip this step if XDB is already VALID."
                ),
                commands=[
                    "ALTER SESSION SET CONTAINER = CDB$ROOT;",
                    "SHUTDOWN IMMEDIATE;",
                    "STARTUP UPGRADE;",
                    "@?/rdbms/admin/xdbrelod.sql",
                    "SHUTDOWN IMMEDIATE;",
                    "STARTUP;",
                    "ALTER PLUGGABLE DATABASE ALL OPEN;",
                    "@?/rdbms/admin/utlrp.sql",
                    "ALTER SESSION SET CONTAINER = XEPDB1;",
                    "@?/rdbms/admin/utlrp.sql",
                    "SELECT comp_name, status FROM dba_registry WHERE comp_id = 'XDB';",
                ],
            ),
            InstallationStep(
                title="Install APEX core",
                context="Container shell",
                description=(
                    "Run the core APEX installation inside the XEPDB1 pluggable database. If the prerequisite check reports XDB as INVALID, rerun the previous step before retrying this installation."
                ),
                commands=[
                    f"cd {tools_folder}/{apex_home}",
                    "sqlplus / as sysdba",
                    "ALTER SESSION SET CONTAINER = XEPDB1;",
                    "@apexins.sql SYSAUX SYSAUX TEMP /i/",
                ],
            ),
            InstallationStep(
                title="Set APEX administrator password",
                context="Container shell",
                description=(
                    "Define the ADMIN password so you can log in to the APEX workspace after the installation."
                ),
                commands=[
                    f"cd {tools_folder}/{apex_home}",
                    "sqlplus / as sysdba",
                    "ALTER SESSION SET CONTAINER = XEPDB1;",
                    "@apxchpwd.sql",
                ],
            ),
            InstallationStep(
                title="Configure REST support",
                context="Container shell",
                description=(
                    "Run the APEX REST configuration script to set passwords for APEX_PUBLIC_USER and ORDS_PUBLIC_USER. When prompted, provide the same passwords twice and type SYSAUX and TEMP when the script asks for tablespaces."
                ),
                commands=[
                    f"cd {tools_folder}/{apex_home}",
                    "sqlplus / as sysdba",
                    "ALTER SESSION SET CONTAINER = XEPDB1;",
                    "@apex_rest_config.sql",
                ],
            ),
            InstallationStep(
                title="Unlock REST accounts",
                context="Container shell",
                description=(
                    "If needed, unlock application users so ORDS can authenticate. Replace <password> with the values you selected during the REST configuration step. ORDS_PUBLIC_USER is only present on older installs; skip its ALTER if the account does not exist."
                ),
                commands=[
                    "sqlplus / as sysdba",
                    "ALTER SESSION SET CONTAINER = XEPDB1;",
                    "SELECT username, account_status FROM dba_users WHERE username IN ('APEX_PUBLIC_USER','APEX_REST_PUBLIC_USER','ORDS_PUBLIC_USER');",
                    "ALTER USER APEX_PUBLIC_USER IDENTIFIED BY \"<password>\" ACCOUNT UNLOCK;",
                    "ALTER USER APEX_REST_PUBLIC_USER IDENTIFIED BY \"<password>\" ACCOUNT UNLOCK;",
                    "ALTER USER ORDS_PUBLIC_USER IDENTIFIED BY \"<password>\" ACCOUNT UNLOCK; -- optional, only if it exists",
                ],
            ),
            InstallationStep(
                title="Validate APEX endpoint",
                context="Host browser",
                description=(
                    "Confirm that the APEX login page is reachable. Replace localhost with the mapped host if required."
                ),
                commands=[
                    f"curl -I {apex_url}",
                    browser_command,
                ],
            ),
        ]

        return [
            InstallationStage(
                key="prep",
                title="Stage 0 – Files and Extraction",
                description="Move the installer archives into the container and unpack them.",
                steps=preparation_steps,
            ),
            InstallationStage(
                key="java",
                title="Stage 1 – Java Runtime",
                description="Configure JAVA_HOME inside the container and verify the runtime.",
                steps=java_steps,
            ),
            InstallationStage(
                key="ords",
                title="Stage 2 – ORDS Setup",
                description="Install Oracle REST Data Services and bring the standalone server online.",
                steps=ords_steps,
            ),
            InstallationStage(
                key="apex",
                title="Stage 3 – APEX Installation",
                description="Install Oracle APEX, set the ADMIN password, and expose the endpoint.",
                steps=apex_steps,
            ),
        ]

    def _resolve_container_reference(self, project: Dict[str, object]) -> Optional[str]:
        """Return the best docker reference available for the project."""

        container_id = project.get("container_id")
        container_name = project.get("container_name")
        if container_id:
            return str(container_id)
        if container_name:
            return str(container_name)
        return None

    def _guess_java_home(self, archive_name: Optional[str]) -> str:
        """Infer the directory created by the JDK archive, fallback to a placeholder."""

        if not archive_name:
            return "<jdk_folder>"

        name = archive_name
        for suffix in (".tar.gz", ".tgz", ".tar"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        if "_linux" in name:
            name = name.split("_linux", 1)[0]
        return name or "<jdk_folder>"

    def _find_artifact(self, keywords: List[str]) -> Optional[str]:
        """Return the first file that matches the expected keywords."""
        normalized_keywords = [keyword.lower() for keyword in keywords]
        for root, _, files in os.walk(self.apex_folder):
            for file_name in files:
                normalized_file = file_name.lower().replace(" ", "")
                if all(keyword in normalized_file for keyword in normalized_keywords):
                    return os.path.join(root, file_name)
        return None


def copy_to_clipboard(text: str) -> bool:
    """Attempt to copy text to the system clipboard."""
    if not text:
        return False

    data = text.encode("utf-8")

    if sys.platform == "darwin":
        try:
            subprocess.run(["pbcopy"], input=data, check=True)
            return True
        except (OSError, subprocess.CalledProcessError):
            return False
    if sys.platform.startswith("linux"):
        for command in ("xclip", "xsel"):
            try:
                subprocess.run(
                    [command, "-selection", "clipboard"], input=data, check=True
                )
                return True
            except (OSError, subprocess.CalledProcessError):
                continue
        return False
    if sys.platform == "win32":
        try:
            subprocess.run(["clip"], input=data, check=True)
            return True
        except (OSError, subprocess.CalledProcessError):
            return False
    return False
