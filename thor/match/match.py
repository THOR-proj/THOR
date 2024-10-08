from collections import deque
import numpy as np
import pandas as pd
import xarray as xr
from thor.log import setup_logger
import thor.object.object as thor_object
import thor.match.tint as tint
from thor.match.utils import get_masks

logger = setup_logger(__name__)


def initialise_match_records(object_tracks, object_options):
    object_tracks["current_matched_mask"] = None
    deque_length = object_options["deque_length"]
    object_tracks["previous_matched_masks"] = deque(
        [None] * deque_length, maxlen=deque_length
    )
    object_tracks["object_record"] = thor_object.empty_object_record()
    object_tracks["previous_object_records"] = deque(
        [None] * deque_length, maxlen=deque_length
    )


def match(object_tracks, object_options, grid_options):
    """Match objects between previous and current masks."""
    if object_options["tracking"]["method"] is None:
        return
    current_mask, previous_mask = get_masks(object_tracks, object_options)
    logger.info(f"Matching {object_options['name']} objects.")
    current_ids = np.unique(current_mask)
    current_ids = current_ids[current_ids != 0]
    if previous_mask is None or np.max(previous_mask) == 0:
        logger.info("No previous mask, or no objects in previous mask.")
        object_tracks["object_record"] = thor_object.empty_object_record()
        object_tracks["global_flow"] = None
        # Create matched mask by relabelling current mask with universal ids.
        get_matched_mask(
            object_tracks, object_options, grid_options, current_ids=current_ids
        )
        return

    match_data = tint.get_matches(object_tracks, object_options, grid_options)
    # Get the previous ids from the previous, previous mask, i.e. the previous mask of
    # the last matching iteration, to see whether objects in detected in the previous
    # mask of the current matching iteration are new.
    previous_ids = np.array(object_tracks["object_record"]["previous_ids"])
    previous_ids[previous_ids > 0]

    if len(previous_ids) == 0:
        logger.info("New matchable objects. Initializing object record.")
        thor_object.initialize_object_record(match_data, object_tracks, object_options)
    else:
        logger.info("Updating object record.")
        thor_object.update_object_record(match_data, object_tracks, object_options)

    get_matched_mask(object_tracks, object_options, grid_options)


def get_matched_mask(object_tracks, object_options, grid_options, current_ids=None):
    """Get the matched mask for the current time."""
    current_mask = get_masks(object_tracks, object_options)[0]

    object_record = object_tracks["object_record"]
    if current_ids is None:
        current_ids = np.unique(current_mask.values)
        current_ids = current_ids[current_ids != 0]
    universal_id_dict = dict(
        zip(object_record["matched_current_ids"], object_record["universal_ids"])
    )

    # Not all the objects in the current mask are in the current objects list of the
    # object record. These are new objects in the current mask, unmatched with those in
    # the previous mask. These new object ids will be created in the object record in
    # the next iteration of the tracking loop. However, to update the current
    # matched mask, we need to premptively assign new universal ids to these new objects.
    unmatched_ids = [
        id for id in current_ids if id not in object_record["matched_current_ids"]
    ]
    new_universal_ids = np.arange(
        object_tracks["object_count"] + 1,
        object_tracks["object_count"] + len(unmatched_ids) + 1,
    )
    new_universal_id_dict = dict(zip(unmatched_ids, new_universal_ids))
    universal_id_dict.update(new_universal_id_dict)
    universal_id_dict[0] = 0

    def replace_values(data_array, value_dict):
        series = pd.Series(data_array.ravel())
        replaced = series.map(value_dict).values.reshape(data_array.shape)
        return replaced

    if grid_options["name"] == "cartesian":
        core_dims = [["y", "x"]]
    elif grid_options["name"] == "geographic":
        core_dims = [["latitude", "longitude"]]
    else:
        raise ValueError(f"Grid name must be 'cartesian' or 'geographic'.")

    matched_mask = xr.apply_ufunc(
        replace_values,
        object_tracks["current_mask"],
        kwargs={"value_dict": universal_id_dict},
        input_core_dims=core_dims,
        output_core_dims=core_dims,
        vectorize=True,
    )
    previous_matched_mask = object_tracks["current_matched_mask"]
    object_tracks["previous_matched_masks"].append(previous_matched_mask)
    object_tracks["current_matched_mask"] = matched_mask
