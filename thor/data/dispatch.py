"""General input data processing."""

import copy
import thor.data.aura as aura
import thor.data.era5 as era5
import thor.data.synthetic as synthetic
import thor.data.gridrad as gridrad
import thor.data.utils as utils
import thor.write as write
from thor.log import setup_logger
from thor.utils import time_in_dataset_range


logger = setup_logger(__name__)


update_dataset_dispatcher = {
    "cpol": aura.update_dataset,
    "operational": aura.update_dataset,
    "gridrad": gridrad.update_dataset,
    "era5_pl": era5.update_dataset,
    "era5_sl": era5.update_dataset,
    "synthetic": synthetic.update_dataset,
}

convert_dataset_dispatcher = {
    "cpol": aura.convert_cpol,
    "operational": aura.convert_operational,
    "gridrad": gridrad.convert_gridrad,
    "era5_pl": era5.convert_era5,
    "era5_sl": era5.convert_era5,
    "synthetic": synthetic.convert_synthetic,
}

grid_from_dataset_basic = lambda dataset, variable, time: dataset[variable].sel(
    time=time
)

grid_from_dataset_dispatcher = {
    "cpol": aura.cpol_grid_from_dataset,
    "gridrad": gridrad.gridrad_grid_from_dataset,
    "operational": grid_from_dataset_basic,
    "synthetic": grid_from_dataset_basic,
}


generate_filepaths_dispatcher = {
    "cpol": aura.get_cpol_filepaths,
    "operational": aura.generate_operational_filepaths,
    "gridrad": gridrad.get_gridrad_filepaths,
    "era5_pl": era5.get_era5_filepaths,
    "era5_sl": era5.get_era5_filepaths,
    "synthetic": None,
}


check_data_options_dispatcher = {
    "cpol": aura.check_data_options,
    "operational": aura.check_data_options,
    "gridrad": gridrad.check_data_options,
    "era5_pl": era5.check_data_options,
    "era5_sl": era5.check_data_options,
    "synthetic": synthetic.check_data_options,
}


get_domain_mask_dispatcher = {
    "gridrad": gridrad.get_domain_mask,
    "cpol": utils.mask_from_input_record,
}


def check_data_options(data_options):
    """TBA."""
    for name in data_options.keys():
        check_data_options = check_data_options_dispatcher.get(name)
        dataset_options = data_options[name]
        if check_data_options is None:
            message = "check_data_options function for dataset "
            message += f"{name} not found."
            raise KeyError(message)
        else:
            check_data_options(dataset_options)
        if "filepaths" in dataset_options and dataset_options["filepaths"] is None:
            filepaths = generate_filepaths(dataset_options)
            dataset_options["filepaths"] = filepaths


def generate_filepaths(dataset_options):
    """
    Get the filepaths for the dataset.

    Parameters
    ----------
    dataset_options : dict
        Dictionary containing the dataset options. Note this is the
        dictionary for an individual dataset, not the entire data_options
        dictionary.

    Returns
    -------
    list
        List of filepaths to files ready to be converted.

    """

    get_filepaths = generate_filepaths_dispatcher.get(dataset_options["name"])
    if get_filepaths is None:
        raise KeyError(f"Filepath generator for {dataset_options['name']} not found.")
    filepaths = get_filepaths(dataset_options)

    return filepaths


def boilerplate_update(
    time, input_record, track_options, dataset_options, grid_options
):
    """Update the dataset."""
    if not time_in_dataset_range(time, input_record["dataset"]):
        update_dataset(time, input_record, track_options, dataset_options, grid_options)


def update_track_input_records(
    time,
    track_input_records,
    track_options,
    data_options,
    grid_options,
    output_directory,
):
    """Update the input record, i.e. grids and datasets."""
    for name in track_input_records.keys():
        input_record = track_input_records[name]
        boilerplate_update(
            time, input_record, track_options, data_options[name], grid_options
        )
        if input_record["current_grid"] is not None:
            input_record["previous_grids"].append(input_record["current_grid"])
        grid_from_dataset = grid_from_dataset_dispatcher.get(name)
        if len(data_options[name]["fields"]) > 1:
            raise ValueError("Only one field allowed for track datasets.")
        else:
            field = data_options[name]["fields"][0]
        input_record["current_grid"] = grid_from_dataset(
            input_record["dataset"], field, time
        )
        if "filepaths" not in data_options[name].keys():
            return
        input_record["time_list"].append(time)
        filepath = data_options[name]["filepaths"][input_record["current_file_index"]]
        input_record["filepath_list"].append(filepath)

        args = [time, input_record, input_record]
        if write.utils.write_interval_reached(*args):
            write.filepath.write(input_record, output_directory)


def update_tag_input_records(
    time, tag_input_records, track_options, data_options, grid_options
):
    """Update the tag input records."""
    if time is None:
        return
    for name in tag_input_records.keys():
        input_record = tag_input_records[name]
        boilerplate_update(
            time, input_record, track_options, data_options[name], grid_options
        )


def update_dataset(time, input_record, track_options, dataset_options, grid_options):
    """Update the dataset."""

    updt_dataset = update_dataset_dispatcher.get(dataset_options["name"])
    if updt_dataset is None:
        raise KeyError(f"Dataset updater for {dataset_options['name']} not found.")
    updt_dataset(time, input_record, track_options, dataset_options, grid_options)
