"""Deal with thor grid objects"""

import yaml
import inspect
import numpy as np
from pyproj import Geod
from thor.utils import almost_equal, pad
from thor.config import get_outputs_directory
from thor.log import setup_logger
from thor.option import save_options


logger = setup_logger(__name__)


def create_options(
    name="geographic",
    altitude=None,
    latitude=None,
    longitude=None,
    x=None,
    y=None,
    projection=None,
    altitude_spacing=500,
    cartesian_spacing=[2500, 2500],
    geographic_spacing=[0.025, 0.025],
    shape=None,
    regrid=True,
    save=False,
    **kwargs,
):
    """
    Generate grid options dictionary.

    Parameters
    ----------
    timestep : int, optional
        Time step for the dataset; default is None.
    start_latitude : float, optional
        Starting latitude for the dataset; default is None.
    end_latitude : float, optional
        Ending latitude for the dataset; default is None.
    start_longitude : float, optional
        Starting longitude for the dataset; default is None.
    end_longitude : float, optional
        Ending longitude for the dataset; default is None.
    central_latitude : float, optional
        Central latitude for the dataset; default is None.
    central_longitude : float, optional
        Central longitude for the dataset; default is None.
    projection : str, optional
        Projection for the dataset; default is None.
    start_x : float, optional
        Starting x-coordinate for the dataset; default is None.
    end_x : float, optional
        Ending x-coordinate for the dataset; default is None.
    start_y : float, optional
        Starting y-coordinate for the dataset; default is None.
    end_y : float, optional
        Ending y-coordinate for the dataset; default is None.
    start_alt : float, optional
        Starting z-coordinate for the dataset; default is 0.
    end_alt : float, optional
        Ending z-coordinate for the dataset; default is 25e3.
    cartesian_spacing : list, optional
        Spacing for the cartesian grid [z, y, x] in metres; default is
        [500, 2500, 2500].
    geographic_spacing : list, optional
        Spacing for the geographic grid [z, lat, lon] in metres and
        degrees; default is [500, 0.025, 0.025].
    regrid : bool, optional
        Whether to regrid the dataset; default is True.
    save : bool, optional
        Whether to save the dataset; default is False.
    **kwargs

    Returns
    -------
    options : dict
        Dictionary containing the grid options.
    """

    if regrid and altitude is None:
        altitude = list(np.arange(0, 25e3 + altitude_spacing, altitude_spacing))
    if shape is None and (latitude is not None and longitude is not None):
        shape = (len(latitude), len(longitude))

    options = {
        "name": name,
        "latitude": latitude,
        "longitude": longitude,
        "altitude": altitude,
        "x": x,
        "y": y,
        "projection": projection,
        "altitude_spacing": altitude_spacing,
        "cartesian_spacing": cartesian_spacing,
        "geographic_spacing": geographic_spacing,
        "shape": shape,
        "regrid": regrid,
        "save": save,
    }

    for key, value in kwargs.items():
        options[key] = value

    if save:
        filepath = get_outputs_directory() / "option/default/grid.yaml"
        dump_options = {"default_flow_style": False, "allow_unicode": True}
        dump_options.update({"sort_keys": False})
        with open(filepath, "w") as outfile:
            yaml.dump(options, outfile, **dump_options)

    return options


def save_grid_options(
    grid_options, filename=None, options_directory=None, append_time=False
):
    if options_directory is None:
        options_directory = get_outputs_directory() / "options/grid_options"
    if filename is None:
        filename = grid_options["name"]
        append_time = True
    save_options(grid_options, filename, options_directory, append_time=append_time)


def check_spacing(array, dx):
    """Check if array equally spaced."""
    if not almost_equal(np.diff(array)):
        raise ValueError("Grid not equally spaced.")
    elif not almost_equal(list(np.diff(array)) + [dx]):
        raise ValueError("Grid spacing does not match prescribed gridlengths.")


def check_options(options):
    """
    Check the input options.

    Parameters
    ----------
    options : dict
        Dictionary containing the input options.


    Returns
    -------
    options : dict
        Dictionary containing the input options.
    """

    if not options["regrid"]:
        # If not regridding, don't check options
        return options

    if options["name"] == "cartesian":
        [x, y, z] = [options[var] for var in ["x", "y", "altitude"]]
        spacing = options["cartesian_spacing"]
    elif options["name"] == "geographic":
        [x, y, z] = [options[var] for var in ["longitude", "latitude", "altitude"]]
        spacing = options["geographic_spacing"]
    [dx, dy, dz] = [spacing[1], spacing[0], options["altitude_spacing"]]

    if x is None or y is None or z is None:
        logger.warning("Coordinates not specified. Will attempt to infer from input.")
    else:
        [check_spacing(v, dv) for v, dv in zip([x, y, z], [dx, dy, dz])]

    for key in inspect.getfullargspec(create_options).args:
        if key not in options.keys():
            raise ValueError(f"Missing required key {key}")

    return options


def new_geographic_grid(lats, lons, dlat, dlon):
    """
    Get the geographic grid.

    Parameters
    ----------
    lons : numpy.ndarray
        Array of longitudes, ascending.
    lats : numpy.ndarray
        Array of latitudes, ascending.
    grid_options : dict
        Dictionary containing the grid options.

    Returns
    -------
    tuple
        The geographic grid as a tuple of (lons, lats).
    """

    min_lat = np.floor(lats.min() / dlat) * dlat
    max_lat = np.ceil(lats.max() / dlat) * dlat
    min_lon = np.floor(lons.min() / dlon) * dlon
    max_lon = np.ceil(lons.max() / dlon) * dlon
    new_lats = np.arange(min_lat, max_lat + dlat, dlat)
    new_lons = np.arange(min_lon, max_lon + dlon, dlon)

    return list(new_lats), list(new_lons)


def get_cell_areas(options):
    """
    Get the cell areas.

    Parameters
    ----------
    options : dict
        Dictionary containing the grid options.

    Returns
    -------
    numpy.ndarray
        The cell areas in km^2.
    """

    if options["name"] == "cartesian":
        area = np.prod(options["cartesian_spacing"]) / 1e6  # Convert to km^2
        return np.ones((len(options["y"]), len(options["x"]))) * area
    elif options["name"] == "geographic":
        return get_geographic_cell_areas(options["latitude"], options["longitude"])
    else:
        raise ValueError("Grid name must be 'cartesian' or 'geographic'.")


def get_coordinate_names(options):
    """Get the names of the horizontal coordinates."""
    if options["name"] == "cartesian":
        return ["y", "x"]
    elif options["name"] == "geographic":
        return ["latitude", "longitude"]
    else:
        raise ValueError("Grid name must be 'cartesian' or 'geographic'.")


def get_distance(row_1, col_1, row_2, col_2, options):
    """Get the distance in meters between two grid cells."""
    row_coords, col_coords = get_horizontal_coordinates(options)
    row_coord_1, col_coord_1 = [row_coords[row_1], col_coords[col_1]]
    row_coord_2, col_coord_2 = [row_coords[row_2], col_coords[col_2]]

    if options["name"] == "cartesian":
        return np.sqrt(
            (row_coord_2 - row_coord_1) ** 2 + (col_coord_2 - col_coord_1) ** 2
        )
    elif options["name"] == "geographic":
        return geodesic_distance(col_coord_1, row_coord_1, col_coord_2, row_coord_2)


def get_geographic_cell_areas(lats, lons):
    """Get cell areas in km^2."""

    lats, lons = np.array(lats), np.array(lons)
    d_lon = lons[1:] - lons[:-1]
    d_lat = lats[1:] - lats[:-1]

    if almost_equal(d_lon, 5) and almost_equal(d_lat, 5):

        dx = geodesic_distance(lons[2], lats, lons[0], lats) / 2
        dy = geodesic_distance(lons[0], lats[2:], lons[0], lats[:-2]) / 2
        dy = pad(dy)

        areas = dx * dy
        areas = np.tile(areas, (len(lons), 1)).T
    else:
        logger.warning("Irregular lat/lon grid. May be slow to calculate areas.")
        LONS, LATS = np.meshgrid(lons, lats)
        dx = geodesic_distance(
            LONS[1:-1, 2:], LATS[1:-1, 1:-1], LONS[1:-1, :-2], LATS[1:-1, 1:-1]
        )
        dx = dx / 2
        dy = geodesic_distance(
            LONS[1:-1, 1:-1], LATS[2:, 1:-1], LONS[1:-1, 1:-1], LATS[:-2, 1:-1]
        )
        dy = dy / 2
        areas = dx * dy
        areas = np.apply_along_axis(pad, axis=0, arr=areas)
        areas = np.apply_along_axis(pad, axis=1, arr=areas)

    return areas / 1e6  # Convert to km^2


def get_horizontal_coordinates(options):
    """
    Get the coordinates for the grid.

    Parameters
    ----------
    options : dict
        Dictionary containing the grid options.

    Returns
    -------
    tuple
        The coordinates as a tuple of (lats, lons, alts).
    """

    if options["name"] == "cartesian":
        [col_coords, row_coords] = [options[var] for var in ["x", "y"]]
    elif options["name"] == "geographic":
        [col_coords, row_coords] = [options[var] for var in ["longitude", "latitude"]]

    return np.array(row_coords), np.array(col_coords)


def get_horizontal_spacing(options):
    """
    Get the grid spacing.

    Parameters
    ----------
    options : dict
        Dictionary containing the grid options.

    Returns
    -------
    tuple
        The grid spacing as a tuple of (dlat, dlon, dz).
    """

    if options["name"] == "cartesian":
        return options["cartesian_spacing"]
    elif options["name"] == "geographic":
        return options["geographic_spacing"]
    else:
        raise ValueError("Grid name must be 'cartesian' or 'geographic'.")


def pixel_to_cartesian_vector(row, col, vector, options):
    """
    Convert a vector from gridcell, i.e. "pixel", coordinates to cartesian coordinates.
    Note that while mathematically a vector does not have a "start" position, if the
    grid is in geographic coordinates, the "location" of the vector in pixel coordinates
    determines what distances it corresponds to in cartesian coordinates.

    Parameters
    ----------
    row : int
        The start row of the vector.
    col : int
        The start column of the vector
    vector : tuple
        The vector to be converted, represented as a tuple of (delta_row, delta_col)
        in pixel coordinates.
    options : dict
        The grid options dictionary.

    Returns
    -------
    tuple
        The converted vector in cartesian coordinates, represented as a tuple
        (delta_y, delta_x), both in units of metres.
    """

    if options["name"] == "cartesian":
        return vector * options["cartesian_spacing"]
    elif options["name"] == "geographic":
        options["geographic_spacing"]
        lats = options["latitude"]
        lons = options["longitude"]
        start_lat = lats[row]
        start_lon = lons[col]
        end_lat = start_lat + vector[0] * options["geographic_spacing"][0]
        end_lon = start_lon + vector[1] * options["geographic_spacing"][1]
        return geographic_to_cartesian_displacement(
            start_lat, start_lon, end_lat, end_lon
        )
    else:
        raise ValueError("Grid name must be 'cartesian' or 'geographic'.")


geod = Geod(ellps="WGS84")
geodesic_inverse = np.vectorize(
    lambda lon1, lat1, lon2, lat2: geod.inv(lon1, lat1, lon2, lat2)
)
geodesic_forward = np.vectorize(
    lambda lon, lat, direction, distance: geod.fwd(lon, lat, direction, distance)
)
geodesic_distance = lambda lon1, lat1, lon2, lat2: geodesic_inverse(
    lon1, lat1, lon2, lat2
)[2]


def geographic_to_cartesian_displacement(start_lat, start_lon, end_lat, end_lon):
    """
    Calculate the y and x displacements in metres in cartesian coordinates between two
    points on the Earth's surface given in geographic coordinates.
    """
    direction, backward_direction, distance = geodesic_inverse(
        start_lon, start_lat, end_lon, end_lat
    )
    y_displacement = distance * np.cos(np.radians(direction))
    x_displacement = distance * np.sin(np.radians(direction))
    return y_displacement, x_displacement


def get_pixels_geographic(rows, cols, grid_options):
    """Get the geographic coordinates of the gridcells, i.e. "pixels" at rows, cols."""
    if np.array(rows).shape != np.array(cols).shape:
        raise ValueError("row and col must have the same shape.")
    scalar_input = np.isscalar(rows) and np.isscalar(cols)
    rows = np.array([rows]).flatten()
    cols = np.array([cols]).flatten()
    latitudes = grid_options["latitude"]
    longitudes = grid_options["longitude"]
    if grid_options["name"] == "cartesian":
        # lats, lons are 2D arrays
        lats = [latitudes[row, col] for row, col in zip(rows, cols)]
        lons = [longitudes[row, col] for row, col in zip(rows, cols)]
    elif grid_options["name"] == "geographic":
        # lats, lons are 1D arrays
        lats, lons = [latitudes[row] for row in rows], [longitudes[col] for col in cols]
    else:
        raise ValueError("Grid name must be 'cartesian' or 'geographic'.")
    if scalar_input:
        lats = lats[0]
        lons = lons[0]
    return lats, lons
