"""Track storm objects in a dataset."""

from collections import deque
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
    object_tracks["object_count"] = 0
    object_tracks["tracks"] = []
    object_tracks["current_grid"] = None
    object_tracks["current_time_interval"] = None
    deque_length = object_options["deque_length"]
    object_tracks["previous_time_interval"] = deque([None] * deque_length, deque_length)
    object_tracks["previous_grids"] = deque([None] * deque_length, deque_length)
    object_tracks["current_mask"] = None
    object_tracks["previous_masks"] = deque([None] * deque_length, deque_length)
    if object_options["tracking"]["method"] is not None:
        match.initialise_match_records(object_tracks, object_options)
    if object_options["mask_options"]["save"]:
        object_tracks["mask_list"] = []
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


def consolidate_options(
    data_options, grid_options, track_options, tag_options, visualize_options
):
    """Consolidate the options for a given run."""

    consolidated_options = {
        "data_options": data_options,
        "grid_options": grid_options,
        "track_options": track_options,
        "tag_options": tag_options,
        "visualize_options": visualize_options,
    }

    return consolidated_options


def simultaneous_track(
    times,
    data_options,
    grid_options,
    track_options,
    tag_options,
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

    option.check_options(track_options)
    dispatch.check_data_options(data_options)
    tracks = initialise_tracks(track_options, data_options)
    input_records = initialise_input_records(data_options)

    consolidated_options = consolidate_options(
        track_options, data_options, grid_options, tag_options, visualize_options
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
            time, input_records["track"], data_options, grid_options
        )
        # loop over levels
        for level_index in range(len(track_options)):
            logger.debug("Processing hierarchy level %s.", level_index)
            track_level(
                time,
                level_index,
                tracks,
                input_records["track"],
                data_options,
                grid_options,
                track_options,
                tag_options,
                visualize_options,
                output_directory,
            )
        dispatch.update_tag_input_records(
            time, input_records["tag"], data_options, grid_options
        )

    write.mask.write_final(tracks, track_options, output_directory, time)
    write.mask.aggregate(track_options, output_directory)
    visualize.visualize.animate(visualize_options, output_directory)

    return tracks


def track_level(
    time,
    level_index,
    tracks,
    track_input_records,
    data_options,
    grid_options,
    track_options,
    tag_options,
    visualize_options,
    output_directory,
):
    """Track a hierarchy level."""
    level_tracks = tracks[level_index]
    level_options = track_options[level_index]
    for obj in level_tracks.keys():
        logger.debug("Tracking %s.", obj)
        dataset = level_options[obj]["dataset"]
        if dataset is None:
            dataset_options = None
        else:
            dataset_options = data_options[dataset]
        track_object(
            time,
            level_index,
            obj,
            tracks,
            track_input_records,
            dataset_options,
            grid_options,
            track_options,
            tag_options,
            visualize_options,
            output_directory,
        )

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
    tag_options,
    visualize_options,
    output_directory,
):
    """Track the given object."""
    # detect
    object_options = track_options[level_index][obj]
    get_objects = get_objects_dispatcher.get(object_options["method"])
    get_objects(
        track_input_records, tracks, level_index, obj, object_options, grid_options
    )
    match.match(tracks[level_index][obj], object_options, grid_options)

    # visualize
    visualize.runtime.visualize(
        track_input_records,
        tracks,
        level_index,
        obj,
        track_options,
        grid_options,
        visualize_options,
        output_directory,
    )
    # write
    write.mask.update(tracks[level_index][obj], object_options, output_directory)

    # return tracks[level_index][obj]


get_objects_dispatcher = {
    "detect": detect.detect,
    "group": group.group,
}
