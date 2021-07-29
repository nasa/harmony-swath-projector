""" A utility function to run the Swath Projector source code on a locally
    hosted granule, without requiring a full Docker image. This function will
    also mock the `shutil.rmtree` function used in file clean-up by the
    `HarmonyAdapter`, so that the NetCDF-4 output can be inspected. The path of
    this temporary directory should be printed to the terminal in green.

    2021-07-29

    Prerequisites:

    * The `harmony-service-lib-py` package must be installed, via Pip, in the
      current Python environment (e.g., conda environment or virtualenv).
    * Python v3.7 or higher.

    Usage:

    * Navigate to the root directory of this repository, `swotrepr`.
    * Begin a local Python session.
    * Run: the following:

    ```
    from bin.project_local_granule import project_granule

    project_granule(<path to local file>)
    ```

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

"""
from os import environ
from unittest.mock import patch

from harmony.util import config
from harmony.message import Message

from swotrepr import HarmonyAdapter


def set_environment_variables():
    """ If the following environment variables are absent, the `HarmonyAdapter`
        class will not allow the projector to run. Make sure to run this script
        in a different environment (e.g. conda environment) than any local
        instance of Harmony.

    """
    environ['ENV'] = 'dev'
    environ['OAUTH_CLIENT_ID'] = ''
    environ['OAUTH_PASSWORD'] = ''
    environ['OAUTH_REDIRECT_URI'] = ''
    environ['OAUTH_UID'] = ''
    environ['STAGING_BUCKET'] = ''
    environ['STAGING_PATH'] = ''


def rmtree_side_effect(workdir: str, ignore_errors=True) -> None:
    """ A side effect for the `shutil.rmtree` mock that will print the
        temporary working directory containing all output NetCDF-4 files.

    """
    print(f'\n\n\n\033[92mOutput files saved to: {workdir}\033[0m\n\n\n')


def project_granule(local_file_path: str, target_crs: str = 'EPSG:4326',
                    interpolation_method: str = 'near') -> None:
    """ The `local_file_path` will need to be absolute, and prepended with
        `file:///` to ensure that the `harmony-service-lib-py` package can
        recognise it as a local file.

        The optional keyword arguments `target_crs` and `interpolation_method`
        allow for a test that overrides the default message parameters of a
        geographically projected output using nearest neighbour interpolation.

    """
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
        'format': {'crs': target_crs, 'interpolation': interpolation_method},
    })

    set_environment_variables()

    reprojector = HarmonyAdapter(message, config=config(False))

    with patch('swotrepr.shutil.rmtree', side_effect=rmtree_side_effect):
        reprojector.invoke()
