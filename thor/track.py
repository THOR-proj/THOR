"""Track storm objects in a dataset."""

from collections import deque
import copy
import numpy as np
from thor.log import setup_logger
import thor.option as option
import thor.data.dispatch as dispatch
import thor.detect.detect as detect
import thor.group.group as group
import thor.visualize as visualize
import thor.match.match as match
from thor.config import get_outputs_directory
from thor.utils import now_str, hash_dictionary, format_time
import thor.write as write
import thor.attribute as attribute

logger = setup_logger(__name__)


def initialise_input_records(data_options):
    """
    Initialise the input datasets dictionary.
    """
    input_records = {"track": {}, "tag": {}}
    for name in data_options.keys():
        use = data_options[name]["use"]
        init_input_record = initialise_input_record_dispatcher.get(use)
        if init_input_record is None:
            raise KeyError(f"Initialisation function for {use} not found.")
        input_record = init_input_record(data_options[name])
        input_records[use][name] = input_record

    return input_records


def initialise_boilerplate_input_record(dataset_options):
    """
    Initialise the tag input record dictionary.
    """

    input_record = {}
    input_record["current_file_index"] = -1
    input_record["dataset"] = None

    return input_record


def initialise_track_input_record(dataset_options):
    """
    Initialise the track input record dictionary.
    """

    input_record = initialise_boilerplate_input_record(dataset_options)
    input_record["current_grid"] = None
    deque_length = dataset_options["deque_length"]
    input_record["previous_grids"] = deque([None] * deque_length, deque_length)

    # Initialize deques of domain masks and boundary coordinates. For datasets like
    # gridrad the domain mask is different for objects identified at different levels.
    input_record["current_domain_mask"] = None
    input_record["previous_domain_masks"] = deque([None] * deque_length, deque_length)
    input_record["current_boundary_coordinates"] = None
    input_record["previous_boundary_coordinates"] = deque(
        [None] * deque_length, deque_length
    )

    return input_record


initialise_input_record_dispatcher = {
    "track": initialise_track_input_record,
    "tag": initialise_boilerplate_input_record,
}


def initialise_object_tracks(object_options):
    """
    Initialise the object tracks dictionary.

    parent_ds holds the xarray metadata associated with the current file.
    current_ds holds the loaded xarray dataset from which grids are extracted.
    current_grid holds the current grid on which objects at a given time are detected.

    """
    object_tracks = {}
    object_tracks["name"] = object_options["name"]
    object_tracks["object_count"] = 0
    object_tracks["tracks"] = []
    object_tracks["current_grid"] = None
    object_tracks["current_time_interval"] = None
    deque_length = object_options["deque_length"]
    object_tracks["previous_time_interval"] = deque([None] * deque_length, deque_length)
    object_tracks["current_time"] = None
    object_tracks["previous_times"] = deque([None] * deque_length, deque_length)
    object_tracks["previous_grids"] = deque([None] * deque_length, deque_length)
    object_tracks["current_mask"] = None
    object_tracks["previous_masks"] = deque([None] * deque_length, deque_length)

    if object_options["tracking"]["method"] is not None:
        match.initialise_match_records(object_tracks, object_options)
    if object_options["mask_options"]["save"]:
        object_tracks["mask_list"] = []

    # Initialize attributes dictionaries
    if object_options["attributes"] is not None:
        # The current_attributes dict holds the attributes associated with matching the
        # "previous" grid to the "current" grid. It is reset at the start of each time
        # step.
        current_attributes = attribute.utils.initialize_attributes(object_options)
        object_tracks["current_attributes"] = current_attributes
        attributes = attribute.utils.initialize_attributes(object_options)
        object_tracks["attributes"] = attributes

    object_tracks["last_write_time"] = None

    return object_tracks


def initialise_tracks(track_options, data_options):
    """
    Initialise the tracks dictionary.

    Parameters
    ----------
    track_options : dict
        Dictionary containing the track options.

    Returns
    -------
    dict
        Dictionary that will contain the tracks of each object.

    """

    tracks = []
    for level_options in track_options:
        level_tracks = {obj: {} for obj in level_options.keys()}
        for obj in level_options.keys():
            dataset = level_options[obj]["dataset"]
            if dataset is not None and dataset not in data_options.keys():
                raise ValueError(f"{dataset} dataset not in data_options.")
            obj_tracks = initialise_object_tracks(level_options[obj])
            level_tracks[obj] = obj_tracks
        tracks.append(level_tracks)
    return tracks


def consolidate_options(data_options, grid_options, track_options, visualize_options):
    """Consolidate the options for a given run."""

    consolidated_options = {
        "data_options": data_options,
        "grid_options": grid_options,
        "track_options": track_options,
        "visualize_options": visualize_options,
    }

    return consolidated_options


def simultaneous_track(
    times,
    data_options,
    grid_options,
    track_options,
    visualize_options=None,
    output_directory=None,
):
    """
    Track objects across the hierachy simultaneously.

    Parameters
    ----------
    filenames : list of str
        List of filepaths to the netCDF files that need to be consolidated.
    data_options : dict
        Dictionary containing the data options.
    grid_options : dict
        Dictionary containing the grid options.
    track_options : dict
        Dictionary containing the track options.

    Returns
    -------
    pandas.DataFrame
        The pandas dataframe containing the object tracks.
    xarray.Dataset
        The xarray dataset containing the object masks.

    """

    logger.info("Beginning simultaneous tracking.")
    option.check_options(track_options)
    dispatch.check_data_options(data_options)
    tracks = initialise_tracks(track_options, data_options)
    input_records = initialise_input_records(data_options)

    consolidated_options = consolidate_options(
        track_options, data_options, grid_options, visualize_options
    )

    for time in times:

        if output_directory is None:
            consolidated_options["start_time"] = str(time)
            hash_str = hash_dictionary(consolidated_options)
            output_directory = (
                get_outputs_directory() / f"runs/{now_str()}_{hash_str[:8]}"
            )

        logger.info(f"Processing {format_time(time, filename_safe=False)}.")
        dispatch.update_track_input_records(
            time, input_records["track"], track_options, data_options, grid_options
        )
        # loop over levels
        for level_index in range(len(track_options)):
            logger.info("Processing hierarchy level %s.", level_index)
            track_level_args = [time, level_index, tracks, input_records["track"]]
            track_level_args += [data_options, grid_options, track_options]
            track_level_args += [visualize_options, output_directory]
            track_level(*track_level_args)
        dispatch.update_tag_input_records(
            time, input_records["tag"], track_options, data_options, grid_options
        )

    write.mask.write_final(tracks, track_options, output_directory)
    write.attribute.write_final(tracks, track_options, output_directory)
    write.mask.aggregate(track_options, output_directory)
    write.attribute.aggregate(track_options, output_directory)
    visualize.visualize.animate_all(visualize_options, output_directory)

    return tracks


def track_level(
    time,
    level_index,
    tracks,
    track_input_records,
    data_options,
    grid_options,
    track_options,
    visualize_options,
    output_directory,
):
    """Track a hierarchy level."""
    level_tracks = tracks[level_index]
    level_options = track_options[level_index]
    for obj in level_tracks.keys():
        logger.info("Tracking %s.", obj)
        dataset = level_options[obj]["dataset"]
        if dataset is None:
            dataset_options = None
        else:
            dataset_options = data_options[dataset]
        track_object_args = [time, level_index, obj, tracks, track_input_records]
        track_object_args += [dataset_options, grid_options, track_options]
        track_object_args += [visualize_options, output_directory]
        track_object(*track_object_args)

    return level_tracks


def track_object(
    time,
    level_index,
    obj,
    tracks,
    track_input_records,
    dataset_options,
    grid_options,
    track_options,
    visualize_options,
    output_directory,
):
    """Track the given object."""
    # Get the object options
    object_options = track_options[level_index][obj]
    object_tracks = tracks[level_index][obj]

    # Update current and previous time
    if object_tracks["current_time"] is not None:
        current_time = copy.deepcopy(object_tracks["current_time"])
        object_tracks["previous_times"].append(current_time)
    object_tracks["current_time"] = time

    # Write existing data to file if necessary
    if write.utils.write_interval_reached(time, object_tracks, object_options):
        write.mask.write(object_tracks, object_options, output_directory)
        write.attribute.write(object_tracks, object_options, output_directory)

    # Detect objects at time
    get_objects = get_objects_dispatcher.get(object_options["method"])
    get_objects_args = [track_input_records, tracks, level_index, obj, dataset_options]
    get_objects_args += [object_options, grid_options]
    get_objects(*get_objects_args)

    match.match(object_tracks, object_options, grid_options)

    # Visualize the operation of the algorithm
    visualize_args = [track_input_records, tracks, level_index, obj, track_options]
    visualize_args += [grid_options, visualize_options, output_directory]
    visualize.runtime.visualize(*visualize_args)
    # Update the lists used to periodically write data to file
    attribute.attribute.record(time, object_tracks, object_options, grid_options)
    write.mask.update(object_tracks, object_options)


get_objects_dispatcher = {
    "detect": detect.detect,
    "group": group.group,
}
