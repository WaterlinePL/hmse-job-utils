import json
import os
from typing import Dict


def read_local_project_metadata(project_name: str):
    with open(os.path.join(get_project_simulation_dir(project_name), "metadata.json")) as handle:
        return json.load(handle)


def get_project_simulation_dir(project_id: str) -> str:
    return os.path.join("workspace", project_id)


def get_used_hydrus_models(project_metadata: Dict):
    return {hydrus_id for hydrus_id in project_metadata["shapes_to_hydrus"].values()
            if isinstance(hydrus_id, str)}
