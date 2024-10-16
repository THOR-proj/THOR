"""Test GridRad tracking."""

from pathlib import Path
import shutil
import numpy as np
import thor.data as data
import thor.data.dispatch as dispatch
import thor.grid as grid
import thor.option as option
import thor.analyze as analyze
import thor.parallel as parallel
import thor.visualize as visualize
import thor.log as log
import thor.track as track

notebook_name = "gridrad_demo.ipynb"

logger = log.setup_logger(__name__)


def test_gridrad():
    # Parent directory for saving outputs
    logger.info("Setting up GridRad test.")
    base_local = Path.home() / "THOR_output"
    start = "2010-01-20T21:00:00"
    end = "2010-01-20T23:00:00"
    event_start = "2010-01-20"

    period = parallel.get_period(start, end)

    output_parent = base_local / "runs/gridrad_demo"
    if output_parent.exists():
        shutil.rmtree(output_parent)
    options_directory = output_parent / "options"

    # Create the data_options dictionary
    converted_options = {"save": True, "load": False, "parent_converted": None}
    gridrad_options = data.gridrad.gridrad_data_options(
        start=start,
        end=end,
        converted_options=converted_options,
        event_start=event_start,
    )

    lon_range = [-102, -89]
    lat_range = [27, 39]
    era5_pl_options = data.era5.data_options(
        start=start, end=end, longitude_range=lon_range, latitude_range=lat_range
    )
    args_dict = {"start": start, "end": end, "data_format": "single-levels"}
    args_dict.update({"longitude_range": lon_range, "latitude_range": lat_range})
    era5_sl_options = data.era5.data_options(**args_dict)

    data_options = option.consolidate_options(
        [gridrad_options, era5_pl_options, era5_sl_options]
    )

    dispatch.check_data_options(data_options)
    data.option.save_data_options(data_options, options_directory=options_directory)

    # Create the grid_options dictionary using the first file in the cpol dataset
    grid_options = grid.create_options(
        name="geographic", regrid=False, altitude_spacing=None, geographic_spacing=None
    )
    grid.check_options(grid_options)
    grid.save_grid_options(grid_options, options_directory=options_directory)

    # Create the track_options dictionary
    track_options = option.default_track_options(dataset="gridrad")
    # Modify the default options for gridrad. Because grids so large we now use a distinct
    # global flow box for each object.
    track_options.levels[1].objects[0].tracking.global_flow_margin = 70
    track_options.levels[1].objects[0].tracking.unique_global_flow = False
    track_options.to_yaml(options_directory / "track.yml")

    # Create the display_options dictionary
    visualize_options = {
        obj: visualize.option.runtime_options(obj, save=True, style="presentation")
        for obj in ["mcs"]
    }
    visualize_options = None

    times = data.utils.generate_times(data_options["gridrad"])
    track.simultaneous_track(
        times,
        data_options,
        grid_options,
        track_options,
        visualize_options,
        output_directory=output_parent,
    )

    analysis_options = analyze.mcs.analysis_options()
    analyze.mcs.process_velocities(output_parent)
    analyze.mcs.quality_control(output_parent, analysis_options)
    analyze.mcs.classify_all(output_parent)
    figure_options = visualize.option.horizontal_attribute_options(
        "mcs_velocity_analysis", style="presentation", attributes=["velocity", "offset"]
    )
    start_time = np.datetime64("2010-01-20T18:00")
    end_time = np.datetime64(np.datetime64("2010-01-21T03:30"))
    args = [output_parent, start_time, end_time, figure_options]
    args_dict = {"parallel_figure": True, "dt": 5400, "by_date": False}
    visualize.attribute.mcs_series(*args, **args_dict)


if __name__ == "__main__":
    test_gridrad()
