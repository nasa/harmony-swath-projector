"""Utility classes used to extend the unittest capabilities."""

from collections import namedtuple
from datetime import datetime
from os import sep
from os.path import basename
from shutil import copy

from harmony_service_lib.util import bbox_to_geometry
from pystac import Asset, Catalog, Item


class StringContains:
    """A custom matcher that can be used in `unittest` assertions, ensuring
    a substring is contained in one of the expected arguments.

    """

    def __init__(self, expected_substring):
        self.expected_substring = expected_substring

    def __eq__(self, string_to_check):
        return self.expected_substring in string_to_check


def download_side_effect(file_path, working_dir, **kwargs):
    """A side effect to be used when mocking the `harmony.util.download`
    function. This should copy the input file (assuming it is a local
    file path) to the working directory, and then return the new file
    path.

    """
    file_base_name = basename(file_path)
    output_file_path = sep.join([working_dir, file_base_name])

    copy(file_path, output_file_path)
    return output_file_path


Granule = namedtuple('Granule', ['url', 'media_type', 'roles'])


def create_stac(granule: Granule) -> Catalog:
    """Create a SpatioTemporal Asset Catalog (STAC). These are used as inputs
    for Harmony requests, containing the URL and other information for
    input granules.

    For simplicity the geometric and temporal properties of each item are
    set to default values.

    """
    catalog = Catalog(id='input catalog', description='test input')

    item = Item(
        id='input granule',
        bbox=[-180, -90, 180, 90],
        geometry=bbox_to_geometry([-180, -90, 180, 90]),
        datetime=datetime(2020, 1, 1),
        properties=None,
    )

    item.add_asset(
        'input data',
        Asset(granule.url, media_type=granule.media_type, roles=granule.roles),
    )
    catalog.add_item(item)

    return catalog
