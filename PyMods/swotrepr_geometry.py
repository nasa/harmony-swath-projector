""" The module contains functions designed to calculate and retrieve the
    extents and resolution of data in the projected Coordinate Reference System
    (CRS).

"""
from typing import List, Tuple

import numpy as np
from pyproj import Proj


def get_projected_resolution(projection: Proj, longitudes: np.ndarray,
                             latitudes: np.ndarray) -> Tuple[float]:
    """ Find the resolution of the target grid in the projected coordinates, x
        and y. First the perimeter points are found. These are then projected
        to the target CRS. Gauss' Area formula is then applied to find the area
        of the swath in the target CRS. This is assumed to be equally shared
        between input pixels. The pixels are also assumed to be square.

    """
    perimeter_points = get_perimeter_points(longitudes, latitudes)
    x_values, y_values = reproject_perimeter_points(perimeter_points,
                                                    projection)
    projected_area = get_polygon_area(x_values, y_values)
    absolute_resolution = get_absolute_resolution(projected_area,
                                                  latitudes.size)
    return absolute_resolution


def get_extents_from_perimeter(projection: Proj, longitudes: np.ndarray,
                               latitudes: np.ndarray) -> Tuple[float]:
    """ Find the swath extents in the target CRS. First the perimeter points
        are found. These are then projected to the target CRS. Finally the
        minimum and maximum values in the projected x and y coordinates are
        returned.

    """
    perimeter_points = get_perimeter_points(longitudes, latitudes)
    x_values, y_values = reproject_perimeter_points(perimeter_points,
                                                    projection)

    return (np.min(x_values), np.max(x_values), np.min(y_values),
            np.max(y_values))


def get_perimeter_points(longitudes: np.ndarray,
                         latitudes: np.ndarray) -> List[Tuple]:
    """ Given longitudes and latitudes, construct a list of two-element tuples,
        each containing the longitude and latitude for a single pixel on the
        outer edge of the input granule grid. Corners are present only once.

        As these points are to be used in determining either extents or
        resolutions, efforts are taken to keep data on one side of the
        International Date Line.

    """
    if swath_crosses_international_date_line(longitudes):
        # The International Date Line is between two pixel columns.
        if np.median(longitudes) < 0:
            # Most pixels are in the Western Hemisphere.
            longitudes[longitudes > 0] -= 360.0
        else:
            # Most pixels are in the Eastern Hemisphere.
            longitudes[longitudes < 0] += 360.0

    count_y, count_x = longitudes.shape

    left_points = [(longitudes[index, 0], latitudes[index, 0])
                   for index in range(count_y)]

    bottom_points = [(longitudes[-1, index], latitudes[-1, index])
                     for index in range(1, count_x)]

    right_points = [(longitudes[index, -1], latitudes[index, -1])
                    for index in range(count_y - 2, -1, -1)]

    top_points = [(longitudes[0, index], latitudes[0, index])
                  for index in range(count_x - 2, 0, -1)]

    return left_points + bottom_points + right_points + top_points


def reproject_perimeter_points(points: List[Tuple],
                               projection: Proj) -> Tuple[np.ndarray]:
    """ Reproject a list of input perimeter points, in longitude and latitude
        tuples, to the target CRS.

        Returns:
            x: numpy.ndarray of projected x coordinates.
            y: numpy.ndarray of projected y coordinates.

    """
    perimeter_longitudes, perimeter_latitudes = zip(*points)
    return projection(perimeter_longitudes, perimeter_latitudes)


def get_polygon_area(x_values: List[float], y_values: List[float]) -> float:
    """ Use the Gauss' Area Formula (a.k.a. Shoelace Formula) to calculate the
        area of the input swath from its perimeter points. These points must
        be sorted so consecutive points along the perimeter are consecutive in
        the input lists.

    """
    return 0.5 * np.abs(np.dot(x_values, np.roll(y_values, 1))
                        - np.dot(y_values, np.roll(x_values, 1)))


def get_absolute_resolution(polygon_area: float, n_pixels: int) -> float:
    """ Find the absolute value of the resolution of the target CRS. This
        assumes that all pixels are equal in area, and that they are square.

    """
    return np.sqrt(np.divide(polygon_area, n_pixels))


def swath_crosses_international_date_line(longitudes: np.ndarray) -> bool:
    """ Check if swath begins west of the International Date Line and ends to
        the east of it. In this case there should be a discontinuity between
        two adjacent longitude columns.

    """
    # TODO: Mask fill_value pixels
    longitudes_difference = np.diff(longitudes, n=1, axis=1)
    return np.max(np.abs(longitudes_difference)) > 90.0
