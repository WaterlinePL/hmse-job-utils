import os

import flopy
import numpy as np
import phydrus as ph

from hmse_job_utils.hmse_projects.hmse_hydrological_models.modflow import modflow_utils
from hmse_job_utils.hmse_projects.project_dao import project_dao
from hmse_job_utils.hmse_projects.project_metadata import ProjectMetadata


def pass_data_from_hydrus_to_modflow(project_id: str):
    project_metadata = project_dao.read_metadata(project_id)
    modflow_id = project_metadata.modflow_metadata.modflow_id
    modflow_path = project_dao.get_modflow_model_path(project_id, modflow_id)
    nam_file = modflow_utils.scan_for_modflow_file(modflow_path)

    for model in get_used_shape_mappings(project_metadata):
        shapes_for_model = [project_dao.get_shape(project_id, shape_id)
                            for shape_id in project_metadata.shapes_to_hydrus.keys()
                            if project_metadata.shapes_to_hydrus[shape_id] == model]

        # load MODFLOW model - basic info and RCH package
        modflow_model = flopy.modflow.Modflow.load(nam_file, model_ws=modflow_path,
                                                   load_only=["rch"],
                                                   forgive=True)
        spin_up = project_metadata.spin_up

        if isinstance(model, str):
            hydrus_recharge_path = os.path.join(project_dao.get_project_path(project_id), 'hydrus', model, 'T_Level.out')
            sum_v_bot = ph.read.read_tlevel(path=hydrus_recharge_path)['sum(vBot)']

            # calc difference for each day (excluding spin_up period)
            sum_v_bot = (-np.diff(sum_v_bot))[spin_up:]
            if spin_up >= len(sum_v_bot):
                raise RuntimeError(f"Spin up is longer than hydrus model time for model: {model}")

        elif isinstance(model, float):
            sum_v_bot = model

        else:
            raise RuntimeError("Unknown mapping in simulation!")

        for shape in shapes_for_model:
            mask = (shape == 1)  # Frontend sets explicitly 1

            stress_period_begin = 0  # beginning of current stress period
            for idx, stress_period_duration in enumerate(modflow_model.modeltime.perlen):
                # float -> int indexing purposes
                stress_period_duration = int(stress_period_duration)

                # modflow rch array for given stress period
                recharge_modflow_array = modflow_model.rch.rech[idx].array

                if isinstance(sum_v_bot, float):
                    avg_v_bot_stress_period = sum_v_bot
                else:
                    # average from all hydrus sum(vBot) values during given stress period
                    stress_period_end = stress_period_begin + stress_period_duration
                    if stress_period_begin >= len(sum_v_bot) or stress_period_end >= len(sum_v_bot):
                        raise RuntimeError(f"Stress period {idx + 1} exceeds simulation time in hydrus model: {model}")
                    avg_v_bot_stress_period = np.average(sum_v_bot[stress_period_begin:stress_period_end])

                # add calculated hydrus average sum(vBot) to modflow recharge array
                recharge_modflow_array[mask] = avg_v_bot_stress_period

                # save calculated recharge to modflow model
                modflow_model.rch.rech[idx] = recharge_modflow_array

                # update beginning of current stress period
                stress_period_begin += stress_period_duration

        new_recharge = modflow_model.rch.rech
        rch_package = modflow_model.get_package("rch")  # get the RCH package

        # generate and save new RCH (same properties, different recharge)
        flopy.modflow.ModflowRch(modflow_model, nrchop=rch_package.nrchop, ipakcb=rch_package.ipakcb,
                                 rech=new_recharge,
                                 irch=rch_package.irch).write_file(check=False)


def get_used_shape_mappings(metadata: ProjectMetadata):
    return {mapping_value for mapping_value in metadata.shapes_to_hydrus.values()}
