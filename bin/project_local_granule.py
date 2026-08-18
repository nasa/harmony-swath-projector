"""A utility function to run the Swath Projector source code on a locally
hosted granule, without requiring a full Docker image. The reprojected
output is written to the current working directory, and its path is printed
to the terminal in green.

2021-07-29

Prerequisites:

* The `harmony-service-lib-py` package must be installed, via Pip, in the
  current Python environment (e.g., conda environment or virtualenv).
* Python v3.11 or higher.

Usage:

* Navigate to the root directory of this repository,
  `harmony-swath-projector`.
* Begin a local Python session.
* Run: the following:

```
from bin.project_local_granule import project_granule

project_granule(<path to local file>)
```

The path may be given either as a plain local path or as a `file:///` URL;
plain paths are resolved to absolute paths and converted for you.

More complicated messages:

The Swath Projector can read a number of parameters from the `format`
attribute of a Harmony message. A more complicated example would be:

```
message = Message({
    'callback': 'https://example.com/callback',
    'stagingLocation': 's3://example-bucket/example-path',
    'sources': [{
        'granules': [{
            'url': local_file_path,
            'temporal': {
                'start': '2021-01-03T23:45:00.000Z',
                'end': '2020-01-04T00:00:00.000Z',
            },
            'bbox': [-180, -90, 180, 90],
        }],
    }],
    'format': {'crs': 'EPSG:4326',
               'interpolation': 'near',
               'height': 100,
               'width': 100,
               'scaleExtent': {'x': {'min': -180, 'max': -150},
                               'y': {'min': 20, 'max': 30}}}
})
```

Note, `scaleSize` can also be specified in the `format` attribute:

```
`format`: {'scaleSize': {'x': 0.1, 'y': 0.1}}
```

However, this property cannot be specified in conjunction with both the
output grid dimensions and the output grid extents, as all three sets of
properties must be consistent with one another.

For local testing of a more complicated example, the message content in the
function below can be edited.

Note on the STAC catalog:

`BaseHarmonyAdapter.invoke` requires a `pystac.Catalog` describing the input
granules. The catalog is built in memory by `create_stac_catalog` below,
so that `SwathProjectorAdapter.process_item` selects the input granule by
looking for the `data` role.

"""

from datetime import datetime
from os import environ
from os.path import abspath
from pathlib import Path
from shutil import move
from unittest.mock import patch

from harmony_service_lib.message import Message
from harmony_service_lib.util import bbox_to_geometry, config
from pystac import Asset, Catalog, Item

from swath_projector.adapter import SwathProjectorAdapter

GLOBAL_BOUNDING_BOX = [-180, -90, 180, 90]


def set_environment_variables():
    """If the following environment variables are absent, the
    `SwathProjectorAdapter` class will not allow the projector to run. Make
    sure to run this script in a different environment (e.g. conda
    environment) than any local instance of Harmony.

    """
    environ['ENV'] = 'dev'
    environ['OAUTH_CLIENT_ID'] = ''
    environ['OAUTH_PASSWORD'] = ''
    environ['OAUTH_REDIRECT_URI'] = ''
    environ['OAUTH_UID'] = ''
    environ['STAGING_BUCKET'] = ''
    environ['STAGING_PATH'] = ''


def as_file_url(local_file_path: str) -> str:
    """Ensure the granule location is a `file:///` URL, as required by the
    `harmony-service-lib-py` download utility to recognise it as a local
    file. Paths that already specify a scheme are returned unaltered.

    """
    if '://' in local_file_path:
        return local_file_path

    return f'file://{abspath(local_file_path)}'


def create_stac_catalog(granule_url: str) -> Catalog:
    """Create a SpatioTemporal Asset Catalog (STAC) for a single local
    granule. Harmony supplies a catalog such as this alongside the input
    message, and `BaseHarmonyAdapter.invoke` iterates its items, calling
    `SwathProjectorAdapter.process_item` for each.

    For simplicity, the geometric and temporal properties of the item are
    set to whole-Earth, fixed values. They are only used to populate the
    output STAC record, not the reprojection itself.

    """
    catalog = Catalog(id='input catalog', description='Local granule input')

    item = Item(
        id='input granule',
        bbox=GLOBAL_BOUNDING_BOX,
        geometry=bbox_to_geometry(GLOBAL_BOUNDING_BOX),
        datetime=datetime(2020, 1, 1),
        properties=None,
    )

    # The 'data' role is how `SwathProjectorAdapter.process_item` locates the
    # granule to reproject.
    item.add_asset(
        'input data',
        Asset(granule_url, media_type='application/x-netcdf', roles=['data']),
    )
    catalog.add_item(item)

    return catalog


def stage_side_effect(
    local_filename: str, remote_filename: str, *args, **kwargs
) -> str:
    """A side effect that moves the reprojected output out of the temporary
    directory created by `reproject` and into the current working directory

    Returns the path of the moved file.
    """
    output_path = Path.cwd() / remote_filename
    move(local_filename, output_path)

    print(f'\n\n\n\033[92mOutput file saved to: {output_path}\033[0m\n\n\n')

    return str(output_path)


def project_granule(
    local_file_path: str,
    target_crs: str = 'EPSG:4326',
    interpolation_method: str = 'near',
    collection_short_name: str = None,
) -> tuple:
    """The `local_file_path` will be converted to an absolute `file:///` URL,
    if it is not one already, to ensure that the `harmony-service-lib-py`
    package can recognise it as a local file.

    The optional keyword arguments `target_crs` and `interpolation_method`
    allow for a test that overrides the default message parameters of a
    geographically projected output using nearest neighbour interpolation.

    Returns the `(message, output_catalog)` tuple produced by
    `BaseHarmonyAdapter.invoke`.

    """
    granule_url = as_file_url(local_file_path)

    message = Message(
        {
            'callback': 'https://example.com/callback',
            'stagingLocation': 's3://example-bucket/example-path',
            'sources': [
                {
                    'shortName': collection_short_name,
                    'granules': [
                        {
                            'url': granule_url,
                            'temporal': {
                                'start': '1979-01-03T23:45:00.000Z',
                                'end': '2037-01-04T00:00:00.000Z',
                            },
                            'bbox': GLOBAL_BOUNDING_BOX,
                        }
                    ],
                }
            ],
            'format': {'crs': target_crs, 'interpolation': interpolation_method},
        }
    )

    set_environment_variables()

    reprojector = SwathProjectorAdapter(
        message,
        config=config(False),
        catalog=create_stac_catalog(granule_url),
    )

    with patch('swath_projector.adapter.stage', side_effect=stage_side_effect):
        return reprojector.invoke()
