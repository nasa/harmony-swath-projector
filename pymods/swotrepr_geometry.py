""" The module contains functions designed to calculate and retrieve the
    extents and resolution of data in the projected Coordinate Reference System
    (CRS).

"""
from typing import List, Tuple
import functools

from netCDF4 import Variable
from pyproj import Proj
import numpy as np


def get_projected_resolution(projection: Proj, longitudes: Variable,
                             latitudes: Variable) -> Tuple[float]:
    """ Find the resolution of the target grid in the projected coordinates, x
        and y. First the perimeter points are found. These are then projected
        to the target CRS. Gauss' Area formula is then applied to find the area
        of the swath in the target CRS. This is assumed to be equally shared
        between input pixels. The pixels are also assumed to be square.

    """
    coordinates_mask = get_valid_coordinates_mask(longitudes, latitudes)
    perimeter_coordinates = get_perimeter_coordinates(longitudes[:],
                                                      latitudes[:],
                                                      coordinates_mask)

    x_values, y_values = reproject_perimeter_points(perimeter_coordinates,
                                                    projection)

    ordered_x, ordered_y = sort_perimeter_points(x_values, y_values)
    projected_area = get_polygon_area(ordered_x, ordered_y)
    absolute_resolution = get_absolute_resolution(
        projected_area,
        coordinates_mask.count() # pylint: disable=E1101
    )
    return absolute_resolution


def get_extents_from_perimeter(projection: Proj, longitudes: Variable,
                               latitudes: Variable) -> Tuple[float]:
    """ Find the swath extents in the target CRS. First the perimeter points of
        unfilled valid pixels are found. These are then projected to the target
        CRS. Finally the minimum and maximum values in the projected x and y
        coordinates are returned.

    """
    coordinates_mask = get_valid_coordinates_mask(longitudes, latitudes)
    perimeter_coordinates = get_perimeter_coordinates(longitudes[:],
                                                      latitudes[:],
                                                      coordinates_mask)
    x_values, y_values = reproject_perimeter_points(perimeter_coordinates,
                                                    projection)

    return (np.min(x_values), np.max(x_values), np.min(y_values),
            np.max(y_values))


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


def get_polygon_area(x_values: np.ndarray, y_values: np.ndarray) -> float:
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


def get_valid_coordinates_mask(longitudes: Variable,
                               latitudes: Variable) -> np.ma.core.MaskedArray:
    """ Get a numpy N-d array containing boolean values (0 or 1) indicating
        whether the elements of both longitude and latitude are valid at that
        location. Validity of these elements means that an element must not be
        a fill value, or contain a NaN. Note, a value of 1 means that the pixel
        contains valid data.

        When a `netCDF4.Variable` is loaded, the data will automatically be
        read as a `numpy.ma.core.MaskedArray`. Values matching the `_FillValue`
        as stored in the variable metadata will be masked.

    """
    valid_longitudes = np.logical_and(np.isfinite(longitudes),
                                      np.logical_not(longitudes[:].mask))
    valid_latitudes = np.logical_and(np.isfinite(latitudes),
                                     np.logical_not(latitudes[:].mask))

    condition = np.logical_and(valid_longitudes, valid_latitudes)

    return np.ma.masked_where(np.logical_not(condition),
                              np.ones(longitudes.shape))


def get_perimeter_coordinates(longitudes: np.ndarray, latitudes: np.ndarray,
                              mask: np.ma.core.MaskedArray) -> List[Tuple[float]]:
    """ Get the coordinates for all pixels in the input grid with non-fill,
        non-NaN values for both longitude and latitude. Note, these points will
        be in a random order, due to the use of the Python Set class.

    """
    row_points = {point
                  for row_index, row in enumerate(mask)
                  if row.any()
                  for point in get_slice_edges(row.nonzero()[0], row_index)}

    column_points = {point
                     for column_index, column in enumerate(mask.T)
                     if column.any()
                     for point in get_slice_edges(column.nonzero()[0],
                                                  column_index, is_row=False)}

    unordered_points = row_points.union(column_points)

    if swath_crosses_international_date_line(longitudes):
        # The International Date Line is between two pixel columns.
        if np.median(longitudes) < 0:
            # Most pixels are in the Western Hemisphere.
            longitudes[longitudes > 0] -= 360.0
        else:
            # Most pixels are in the Eastern Hemisphere.
            longitudes[longitudes < 0] += 360.0

    return [(longitudes[point[0], point[1]], latitudes[point[0], point[1]])
            for point in unordered_points]


def get_slice_edges(slice_valid_indices: np.ndarray, slice_index: int,
                    is_row: bool = True) -> List[Tuple[int]]:
    """ Given a list of indices for all valid data in a single row or column of
        an array, return the 2-dimensional indices of the first and last pixels
        with valid data. This function relies of the `nonzero` method of a
        numpy masked array returning array indices in ascending order.

    """
    if is_row:
        slice_edges = [(slice_index, slice_valid_indices[0]),
                       (slice_index, slice_valid_indices[-1])]
    else:
        slice_edges = [(slice_valid_indices[0], slice_index),
                       (slice_valid_indices[-1], slice_index)]

    return slice_edges


def sort_perimeter_points(unordered_x: np.ndarray,
                          unordered_y: np.ndarray) -> Tuple[np.ndarray]:
    """ Take arrays of x and y projected coordinates, combine into coordinate
        pairs, then order them clockwise starting from the point nearest to a
        reference vector originating at the polygon centroid. Finally, return
        ordered arrays of the x and y coordinates separated once more.

    """
    unordered_points = np.array(list(zip(unordered_x, unordered_y)))
    polygon_centroid = np.mean(unordered_points, axis=0)
    sort_key = functools.partial(clockwise_point_sort, polygon_centroid)
    ordered_points = sorted(unordered_points, key=sort_key)
    return zip(*ordered_points)


def clockwise_point_sort(origin: List[float],
                         point: List[float]) -> Tuple[float]:
    """ A key function to be used with the internal Python sorted function.
        This function should return a tuple of the clockwise angle and length
        between the point and a reference vector, which is a vetical unit
        vector. The origin argument should be the within the polygon for which
        perimeter points are being sorted, to ensure correct ordering. For
        simplicity, it is assumed this origin is the centroid of the polygon.

        See:

            - https://stackoverflow.com/a/41856340
            - https://stackoverflow.com/a/35134034

    """
    reference_vector = np.array([0, 1])

    vector = np.subtract(np.array(point), np.array(origin))
    vector_length = np.linalg.norm(vector)

    if vector_length == 0:
        # The closest point is identical
        vector_angle = -np.pi
    else:
        normalised_vector = np.divide(vector, vector_length)
        dot_product = np.dot(normalised_vector, reference_vector)
        determinant = np.linalg.det([normalised_vector, reference_vector])
        vector_angle = np.math.atan2(determinant, dot_product)

    return vector_angle, vector_length


def swath_crosses_international_date_line(longitudes: np.ndarray) -> bool:
    """ Check if swath begins west of the International Date Line and ends to
        the east of it. In this case there should be a discontinuity between
        either two adjacent longitude columns or rows.

    """
    # TODO: Mask fill_value pixels
    longitudes_difference_row = np.diff(longitudes, n=1, axis=0)
    longitudes_difference_column = np.diff(longitudes, n=1, axis=1)
    max_column_difference = np.max(np.abs(longitudes_difference_column))
    max_row_difference = np.max(np.abs(longitudes_difference_row))
    return np.max([max_column_difference, max_row_difference]) > 90.0
