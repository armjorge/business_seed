import os
import re
import subprocess
from datetime import date
from typing import Dict, List, Optional

import yaml

from Scripts.handle_container_db import ProjectDatabase
from Scripts.install_apex import ApexInstallerHelper, copy_to_clipboard


class ProjectManagement:
    """Interactive helper to manage Oracle Docker containers and APEX setup."""

    def __init__(self) -> None:
        self.folder_root = os.getcwd()
        self.working_folder = os.path.join(self.folder_root, "Local Data")
        os.makedirs(self.working_folder, exist_ok=True)
        self.yaml_path = os.path.join(self.working_folder, "config.yaml")
        self.data_access = self._load_variables(self.yaml_path)
        self.today = date.today()
        self.db = ProjectDatabase(self.working_folder)
        self.apex_helper = ApexInstallerHelper(self.working_folder)

    def _clone_image_instructions(self) -> Optional[Dict[str, Optional[str]]]:
        projects = self.db.list_projects()
        if not projects:
            print("No projects recorded yet. Create one first.")
            return None

        print("\n--- Clone Oracle XE Container ---")
        self._print_projects_table(projects)
        selection = input(
            "Select the project id to prepare the container (Enter to cancel): "
        ).strip()
        if not selection:
            return None
        if not selection.isdigit():
            print("Please enter a numeric id.")
            return None

        project_id = int(selection)
        project = self.db.get_project(project_id)
        if not project:
            print("Project not found.")
            return None

        project_name = project.get("project_name") or f"project_{project_id}"
        container_name = project.get("container_name") or self._suggest_container_name(
            project_name, projects
        )

        existing_container = project.get("container_name")
        if existing_container:
            print(
                f"This project currently uses container '{existing_container}'. "
                "You can reuse it or register a new one."
            )

        print("\nMake sure Docker Desktop is running.")
        print("If the Oracle XE image is missing, pull it with:")
        print("  docker pull gvenzl/oracle-xe:21-slim")

        

        docker_command = (
            "docker run -d "
            "--platform linux/amd64 "
            f"--name {container_name} "
            "-e ORACLE_PASSWORD=JACJConsulting "
            "-p 1522:1521 "
            "-p 5501:5500 "
            "-p 8080:8080 "
            "-v oracle_data:/opt/oracle/oradata "
            "gvenzl/oracle-xe:21-slim"
        )

        print("\nRun the container with:")
        print(f"  {docker_command}")
        if copy_to_clipboard(docker_command):
            print("The docker command is in your clipboard.")
        print("Password in use (SYS/SYSTEM): JACJConsulting")
        print("Listener port: 1522  |  ORDS Console port: 5501  |  APEX port: 8080")

        print("\nVerify the container with:")
        print(f"  docker ps --filter name={container_name}")
        print("You can retrieve the container id with:")
        print(f"  docker ps -aq --filter name={container_name}")
        print(
            "Once it is up, you can connect using the host ports you selected."
        )

        detected_id: Optional[str] = None
        fetch_choice = input(
            "Attempt to detect the container id automatically? (Y/n): "
        ).strip().lower()
        if fetch_choice in {"", "y", "yes"}:
            detected_id = self._lookup_container_id(container_name)
            if detected_id:
                print(f"Detected container id: {detected_id}")
            else:
                print("Could not detect the container id automatically.")

        if not detected_id:
            manual_id = input(
                "Paste the container id from docker (leave blank to skip): "
            ).strip()
            if manual_id:
                detected_id = manual_id

        store_choice = input(
            "Save this container information to the project now? (y/n): "
        ).strip().lower()
        if store_choice == "y":
            self.db.update_container(
                project_id,
                container_name=container_name,
                container_id=detected_id,
            )
            print("Container details stored in the project record.")

        return {"container_name": container_name, "container_id": detected_id}


    def _load_variables(self, yaml_path: str) -> Dict[str, str]:
        default_string = """User: 'your_user'
Password: 'your_password'
Host: 'your_host'
Port: 'your_port'
"""
        if not os.path.exists(yaml_path):
            with open(yaml_path, "w", encoding="utf-8") as pointer:
                pointer.write(default_string)
            print("Configuration file created at:")
            print(f"  {yaml_path}")
            print("Update it with your credentials before proceeding.")
            input("Press Enter after editing the file...")

        with open(yaml_path, "r", encoding="utf-8") as pointer:
            data_access = yaml.safe_load(pointer)

        default_keys = set(re.findall(r"^(\w+):", default_string, re.MULTILINE))
        yaml_keys = set(data_access.keys())
        extra_keys = yaml_keys - default_keys
        if extra_keys:
            print("Warning: new keys detected in config.yaml ->", ", ".join(extra_keys))
            print("Update the default template so future deployments remain consistent.")

        return data_access

    def run(self) -> None:
        while True:
            print("\n--- Project Assistant ---")
            print("1) Manage projects")
            print("2) Install APEX")
            print("3) Backup helpers (coming soon)")
            print("0) Exit")
            choice = input("Select an option: ").strip()

            if choice == "1":
                self._manage_projects_menu()
            elif choice == "2":
                self._install_apex_flow()
            elif choice == "3":
                self._show_backup_placeholder()
            elif choice == "0":
                print("Goodbye!")
                break
            else:
                print("Please pick a valid option.")

    def _manage_projects_menu(self) -> None:
        while True:
            print("\n--- Manage Projects ---")
            print("1) Create new project")
            print("2) Load existing project")
            print("3) Fix projects without container info")
            print("4) Update project details")
            print("5) Delete project")
            print("0) Back to main menu")
            choice = input("Select an option: ").strip()

            if choice == "1":
                self._create_new_project()
            elif choice == "2":
                self._load_project()
            elif choice == "3":
                defaults = self._clone_image_instructions()
                self._resolve_incomplete_projects(defaults)
            elif choice == "4":
                self._update_project_details()
            elif choice == "5":
                self._delete_project()
            elif choice == "0":
                break
            else:
                print("Please pick a valid option.")

    def _delete_project(self) -> None:
        projects = self.db.list_projects()
        if not projects:
            print("No projects recorded yet.")
            return

        self._print_projects_table(projects)
        print(
            "Type the project id to delete. For safety, confirm by typing DELETE when prompted."
        )
        selection = input("Project id (or Enter to cancel): ").strip()
        if not selection:
            return
        if not selection.isdigit():
            print("Please enter a numeric id.")
            return

        project_id = int(selection)
        project = self.db.get_project(project_id)
        if not project:
            print("Project not found.")
            return

        confirmation = input(
            "Type DELETE to remove this project record (this does not touch Docker containers): "
        ).strip()
        if confirmation != "DELETE":
            print("Deletion cancelled.")
            return

        self.db.delete_project(project_id)
        print(f"Project {project_id} removed from the registry.")

        container_name = project.get("container_name")
        if container_name:
            print("\nRemember to stop and remove the Docker container manually if needed:")
            print(f"  docker stop {container_name}")
            print(f"  docker rm {container_name}")

    def _create_new_project(self) -> None:
        print("\n--- Create New Project ---")
        name = input("Project name: ").strip()
        if not name:
            print("Project name cannot be empty.")
            return

        container_name = input("Docker container name (leave blank to fill later): ").strip()
        apex_url = input("APEX url (default http://localhost:8080/ords): ").strip()
        apex_url = apex_url or "http://localhost:8080/ords"

        project_id = self.db.add_project(
            name,
            container_name=container_name or None,
            apex_url=apex_url,
        )
        print(f"Project registered with id {project_id}.")
        print("Open Docker Desktop, pull or clone the Oracle image, and start the container.")
        print(
            "When running docker run include -p 8080:8080 so ORDS can expose APEX to your host."
        )
        print(
            "Once you finish preparing the Docker container, record the details via 'Fix projects without container id'."
        )

    def _load_project(self) -> None:
        projects = self.db.list_projects()
        if not projects:
            print("No projects recorded yet.")
            return

        self._print_projects_table(projects)
        selection = input("Type the project id to load (or press Enter to cancel): ").strip()
        if not selection:
            return
        if not selection.isdigit():
            print("Please enter a numeric id.")
            return

        project = self.db.get_project(int(selection))
        if not project:
            print("Project not found.")
            return

        container_name = project.get("container_name")
        container_id = project.get("container_id")
        if not container_name:
            print("This project does not have container details yet. Assign them first.")
            return

        print("\nContainer lifecycle:")
        print(f"  docker start {container_name}")
        if container_id:
            print(f"  # container id: {container_id}")

        print("\nOpen a shell as the oracle user (preferred) or root as fallback:")
        print(f"  docker exec -it --user oracle {container_name} bash")
        print(f"  docker exec -it {container_name} bash")

        print("\nInside the shell, prepare the environment and start ORDS:")
        print("  cd /opt/oracle/tools/ords")
        print("  source ~/.bashrc  # loads JAVA_HOME if you persisted it")
        print("  ords --config /opt/oracle/ords_config serve")
        print("Keep this process running (use tmux/screen/nohup if you need it detached).")

        print("If you expose APEX through a proxy container, start it as well (example):")
        print("  docker start ords-proxy")

        print("\nTo validate the database, you can still run:")
        print("  sqlplus / as sysdba")

        print("\nAPEX access reminders:")
        print("  - APEX builder: http://localhost:8080/ords/ (login with workspace credentials)")
        print("  - APEX administration: http://localhost:8080/ords/apex_admin (user ADMIN)")
        print("  - SQL Developer Web: choose PDB XEPDB1 on the landing page and sign in with a REST-enabled schema (for example APEX_PUBLIC_USER).")

        apex_url = project.get("apex_url") or "http://localhost:8080/ords"
        print(f"Access APEX at: {apex_url}")
        if copy_to_clipboard(apex_url):
            print("The APEX url is now in your clipboard.")
        else:
            print("Could not copy the url to the clipboard. Copy it manually if needed.")

    def _resolve_incomplete_projects(
        self, defaults: Optional[Dict[str, Optional[str]]] = None
    ) -> None:
        projects = self.db.list_projects(only_missing_container=True)
        if not projects:
            print("All projects have container details recorded. Great!")
            return

        while True:
            print("\nProjects needing container details:")
            self._print_projects_table(projects)
            choice = input(
                "Enter an id to assign a container, use d<ID> to delete, or Enter to exit: "
            ).strip()
            if not choice:
                break
            if choice.lower().startswith("d"):
                target = choice[1:]
                if not target.isdigit():
                    print("Use the format d<ID>, for example d3.")
                    continue
                project_id = int(target)
                self.db.delete_project(project_id)
                print(f"Project {project_id} removed.")
            elif choice.isdigit():
                project_id = int(choice)
                default_name = (defaults or {}).get("container_name")
                default_id = (defaults or {}).get("container_id")

                prompt_name = "Container name"
                if default_name:
                    prompt_name += f" (Enter to use {default_name})"
                prompt_name += ": "
                container_name = input(prompt_name).strip()
                if not container_name and default_name:
                    container_name = default_name

                prompt_id = "Container id"
                if default_id:
                    prompt_id += f" (Enter to use {default_id})"
                prompt_id += ": "
                container_id = input(prompt_id).strip()
                if not container_id and default_id:
                    container_id = default_id

                if not container_name:
                    print("Container name cannot be empty.")
                    continue

                if not container_id:
                    print(
                        "Warning: container id is missing. Run the docker ps command and try again."
                    )

                self.db.update_container(
                    project_id,
                    container_name=container_name,
                    container_id=container_id or None,
                )
                print("Container details updated.")
                defaults = None
            else:
                print("Unknown action. Try again.")

            projects = self.db.list_projects(only_missing_container=True)
            if not projects:
                print("All container details are up to date.")
                break

    def _update_project_details(self) -> None:
        projects = self.db.list_projects()
        if not projects:
            print("No projects to update yet.")
            return

        self._print_projects_table(projects)
        selection = input("Type the project id to update (or Enter to cancel): ").strip()
        if not selection:
            return
        if not selection.isdigit():
            print("Please enter a numeric id.")
            return

        project_id = int(selection)
        project = self.db.get_project(project_id)
        if not project:
            print("Project not found.")
            return

        new_name = input("New project name (leave blank to keep current): ").strip()
        if new_name:
            self.db.update_project_name(project_id, new_name)
        container_updates: Dict[str, Optional[str]] = {}
        new_container_name = input(
            "New container name (leave blank to keep current): "
        ).strip()
        if new_container_name:
            container_updates["container_name"] = new_container_name
        new_container_id = input(
            "New container id (leave blank to keep current): "
        ).strip()
        if new_container_id:
            container_updates["container_id"] = new_container_id
        if container_updates:
            self.db.update_container(project_id, **container_updates)
        new_url = input("New APEX url (leave blank to keep current): ").strip()
        if new_url:
            self.db.update_apex_url(project_id, new_url)
        mark_apex = input("Mark APEX as installed? (y/n, leave blank to skip): ").strip().lower()
        if mark_apex in {"y", "n"}:
            self.db.mark_apex_status(project_id, mark_apex == "y")
        print("Project updated.")

    def _install_apex_flow(self) -> None:
        pending = self.db.list_projects(only_without_apex=True)
        if not pending:
            print("All projects are marked as APEX ready. Nice!")
            force = input("Do you want to run the installer anyway? (Y/n): ").strip().lower()
            if force not in {"", "y", "yes"}:
                return
            pending = self.db.list_projects()
            if not pending:
                print("No projects recorded yet. Create one first.")
                return

        print("\nProjects without APEX installed:")
        self._print_projects_table(pending)
        selection = input("Type the project id to work on (or Enter to cancel): ").strip()
        if not selection:
            return
        if not selection.isdigit():
            print("Please enter a numeric id.")
            return

        project_id = int(selection)
        project = self.db.get_project(project_id)
        if not project:
            print("Project not found.")
            return

        container_name = project.get("container_name")
        if not container_name:
            print("This project still lacks container details. Assign them first.")
            return
        if not project.get("container_id"):
            print("Warning: container id has not been recorded yet.")

        matches = self.apex_helper.scan_required_files()
        summary = self.apex_helper.artifact_summary(matches)
        print("\nLocal artifacts status:")
        for line in summary:
            print(f"  {line}")

        missing_notes = self.apex_helper.missing_artifacts_report(matches)
        if missing_notes:
            print("\nDownloads needed:")
            for note in missing_notes:
                print(f"  {note}")
            print("Add the files to the APEX_files folder and rerun this option when ready.")
            proceed = input("Continue with the checklist anyway? (y/n): ").strip().lower()
            if proceed != "y":
                return

        print("\nSuggested installation steps:")
        for index, step in enumerate(self.apex_helper.installation_checklist(project), start=1):
            print(f"  {index:02d}. {step}")

        launch_wizard = input(
            "\nStart the interactive installation wizard now? (Y/n): "
        ).strip().lower()
        if launch_wizard in {"", "y", "yes"}:
            self.apex_helper.run_installation_wizard(project, matches)

        confirmation = input("Were you able to access APEX successfully? (y/n): ").strip().lower()
        if confirmation == "y":
            self.db.mark_apex_status(project_id, True)
            new_url = input("Paste the final APEX url if it changed (Enter to skip): ").strip()
            if new_url:
                self.db.update_apex_url(project_id, new_url)
            print("Project marked as APEX ready.")
        else:
            print("Keep iterating with the checklist and run this option again once ready.")

    def _show_backup_placeholder(self) -> None:
        print("\nBackup helpers are not implemented yet.")
        print("Plan: export Oracle datafiles and important directories for quick restore.")

    def _print_projects_table(self, projects: List[Dict[str, object]]) -> None:
        headers = [
            "ID",
            "Project",
            "Container Name",
            "Container ID",
            "APEX URL",
            "APEX?",
        ]
        rows = []
        for project in projects:
            rows.append(
                [
                    project.get("id"),
                    project.get("project_name"),
                    project.get("container_name") or "-",
                    project.get("container_id") or "-",
                    project.get("apex_url") or "-",
                    "Yes" if project.get("apex_installed") else "No",
                ]
            )

        column_widths = [len(header) for header in headers]
        for row in rows:
            for index, value in enumerate(row):
                column_widths[index] = max(column_widths[index], len(str(value)))

        def format_row(values: List[object]) -> str:
            fragments = []
            for index, value in enumerate(values):
                fragments.append(str(value).ljust(column_widths[index]))
            return " | ".join(fragments)

        print(format_row(headers))
        print("-" * (sum(column_widths) + 3 * (len(headers) - 1)))
        for row in rows:
            print(format_row(row))

    def _suggest_container_name(
        self, project_name: str, projects: List[Dict[str, object]]
    ) -> str:
        sanitized = re.sub(r"[^a-z0-9]+", "_", project_name.lower()).strip("_")
        if not sanitized:
            sanitized = "project"
        base_name = f"{sanitized}_xe"
        existing = {
            (entry.get("container_name") or "").strip()
            for entry in projects
            if entry.get("container_name")
        }
        candidate = base_name
        suffix = 1
        while candidate in existing:
            candidate = f"{base_name}_{suffix}"
            suffix += 1
        return candidate

    def _lookup_container_id(self, container_name: str) -> Optional[str]:
        """Attempt to obtain the Docker container id for the given name."""
        if not container_name:
            return None
        try:
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "-aq",
                    "--filter",
                    f"name={container_name}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            print("Docker command not found on this system.")
            return None
        except subprocess.CalledProcessError as error:
            print("Docker command failed:", error)
            return None

        container_id = result.stdout.strip().splitlines()
        if not container_id:
            return None
        if len(container_id) > 1:
            print(
                "Multiple containers matched that name. Using the most recent entry."
            )
        return container_id[0]


if __name__ == "__main__":
    app = ProjectManagement()
    app.run()
