"""Methods for analyzing objects."""

import copy
import numpy as np
import xarray as xr
from thor.log import setup_logger
from thor.match.utils import get_masks
from thor.match.correlate import get_global_flow

logger = setup_logger(__name__)


def get_object_area(obj, mask, gridcell_area):
    """Get object area. Note gridcell_area is in km^2 by default."""
    row_inds, col_inds = np.where(mask == obj)
    row_points = xr.Variable("mask_points", row_inds)
    col_points = xr.Variable("mask_points", col_inds)
    areas = gridcell_area.isel(latitude=row_points, longitude=col_points).values
    return areas.sum()


def get_object_center(obj, mask, gridcell_area=None, grid=None):
    """Get object centre."""
    row_inds, col_inds = np.where(mask == obj)
    if gridcell_area is not None or grid is not None:
        row_points = xr.Variable("mask_points", row_inds)
        col_points = xr.Variable("mask_points", col_inds)
        if gridcell_area is not None:
            areas = gridcell_area.isel(latitude=row_points, longitude=col_points).values
            row_inds = np.sum(row_inds * areas) / np.sum(areas)
            col_inds = np.sum(col_inds * areas) / np.sum(areas)
        if grid is not None:
            grid_values = grid.isel(latitude=row_points, longitude=col_points).values
            row_inds = np.sum(row_points * grid_values) / np.sum(grid_values)
            col_inds = np.sum(col_points * grid_values) / np.sum(grid_values)
    else:
        row_points = row_points / len(row_inds)
        col_points = col_points / len(col_inds)
    center_row = np.round(np.sum(row_inds)).astype(int)
    center_col = np.round(np.sum(col_inds)).astype(int)
    latitudes = mask.latitude.values
    longitudes = mask.longitude.values
    center_lat = latitudes[center_row]
    center_lon = longitudes[center_col]
    return center_lat, center_lon, areas.sum()


def find_objects(box, mask):
    """Identifies objects found in the search region."""
    search_area = mask.values[
        box["row_min"] : box["row_max"], box["col_min"] : box["col_max"]
    ]
    objects = np.unique(search_area)
    return objects[objects != 0]


def reset_object_record(object_tracks):
    """Reset record of object properties in previous and current masks."""
    object_record = {
        "previous_ids": [],
        "universal_ids": [],
        "matched_current_ids": [],
        "parents": [],
        "global_flow": None,
        "previous_displacements": [],
        "current_displacements": [],
    }
    object_tracks["object_record"] = object_record


def initialize_object_record(match_data, object_tracks, object_options):
    """Initialize record of object properties in previous and current masks."""

    previous_mask = get_masks(object_tracks, object_options)[1]
    total_previous_objects = np.max(previous_mask)
    global_flow = get_global_flow(object_tracks, object_options)
    previous_ids = np.arange(1, total_previous_objects + 1)

    universal_ids = np.arange(
        object_tracks["object_count"] + 1, total_previous_objects + 1
    )
    object_tracks["object_count"] += total_previous_objects
    object_record = match_data.copy()
    object_record["previous_ids"] = previous_ids
    object_record["global_flow"] = global_flow
    object_record["universal_ids"] = universal_ids
    object_tracks["object_record"] = object_record


def update_object_record(match_data, object_tracks, object_options):
    """Update record of object properties in previous and current masks."""

    previous_object_record = copy.deepcopy(object_tracks["object_record"])
    previous_mask = get_masks(object_tracks, object_options)[1]
    global_flow = get_global_flow(object_tracks, object_options)

    total_previous_objects = np.max(previous_mask.values)
    previous_ids = np.arange(1, total_previous_objects + 1)
    universal_ids = np.array([], dtype=int)

    for previous_id in np.arange(1, total_previous_objects + 1):
        # Check if object was matched in previous iteration
        if previous_id in previous_object_record["matched_current_ids"]:
            index = np.argwhere(
                previous_object_record["matched_current_ids"] == previous_id
            )
            index = index[0, 0]
            # Append the previously created universal id corresponding to previous_id
            universal_ids = np.append(
                universal_ids, previous_object_record["universal_ids"][index]
            )
        else:
            uid = object_tracks["object_count"] + 1
            object_tracks["object_count"] += 1
            universal_ids = np.append(universal_ids, uid)
            # Check if new object split from old?

    object_record = match_data.copy()
    object_record["global_flow"] = global_flow
    object_record["universal_ids"] = universal_ids
    object_record["previous_ids"] = previous_ids
    object_tracks["object_record"] = object_record