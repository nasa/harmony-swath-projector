import logging
from unittest import TestCase

from harmony_service_lib.message import Message
from harmony_service_lib.util import HarmonyException, config

from swath_projector.adapter import SwathProjectorAdapter
from swath_projector.reproject import reproject


class TestInputFileDownload(TestCase):
    """A test class to ensure that common failures arising from missing or
    incorrect file details in the input Harmony message are well handled.

    """

    def test_message_has_no_granules_attribute(self):
        """Handle a harmony message that does not list any granules"""
        reprojector = SwathProjectorAdapter(
            Message({'format': {}, 'sources': [{}]}), config=config(False)
        )

        with self.assertRaises(HarmonyException) as context:
            reprojector.invoke()

        self.assertEqual(
            str(context.exception), 'No granules specified for reprojection'
        )

    def test_local_file_does_not_exist(self):
        """Handle a harmony message that refers to a granule local file that
        does not exist

        """
        reprojector = SwathProjectorAdapter(
            Message({'format': {}, 'sources': [{'granules': [{}]}]}),
            config=config(False),
        )

        with self.assertRaises(Exception) as context:
            reproject(
                reprojector.message,
                'short name',
                'https://example.com/no_such_file.nc4',
                'test/data/no_such_file',
                '/no/such/dir',
                reprojector.logger,
            )

        self.assertEqual(str(context.exception), 'Input file does not exist')

    def test_local_tempo_03tot_l2_v2_das_2219(self):
        """Handle a harmony message that refers to a granule local file that
        does not exist

        """
        reprojector = SwathProjectorAdapter(
            Message(
                {
                    "sources": [
                        {
                            "collection": "C1270257471-EEDTEST",
                            "shortName": "TEMPO_O3TOT_L2",
                            "versionId": "V03",
                            "coordinateVariables": [],
                            "visualizations": [],
                        }
                    ],
                    "format": {
                        "crs": "+proj=longlat +datum=WGS84 +no_defs",
                        "srs": {
                            "proj4": "+proj=longlat +datum=WGS84 +no_defs",
                            "wkt": "GEOGCS[\"WGS 84\",DATUM[\"WGS_1984\",SPHEROID[\"WGS 84\",6378137,298.257223563,AUTHORITY[\"EPSG\",\"7030\"]],AUTHORITY[\"EPSG\",\"6326\"]],PRIMEM[\"Greenwich\",0,AUTHORITY[\"EPSG\",\"8901\"]],UNIT[\"degree\",0.0174532925199433,AUTHORITY[\"EPSG\",\"9122\"]],AXIS[\"Latitude\",NORTH],AXIS[\"Longitude\",EAST],AUTHORITY[\"EPSG\",\"4326\"]]",
                            "epsg": "EPSG:4326",
                        },
                        "interpolation": "near",
                        "mime": "application/netcdf",
                    },
                    "subset": {"dimensions": []},
                }
            ),
            config=config(False),
        )

        reprojector.logger.setLevel(logging.DEBUG)

        working_filename = reproject(
            reprojector.message,
            'TEMPO_O3TOT_L2',
            'https://harmony.uat.earthdata.nasa.gov/service-results/harmony-uat-eedtest-data/C1270257471-EEDTEST/TEMPO_O3TOT_L2_V03_20230802T151249Z_S001G01.nc',
            '/Users/vtran11/Documents/workspace/granules/TEMPO_O3TOT_L2_V03_20230802T151249Z_S001G01.nc',
            '/Users/vtran11/Documents/workspace/harmony-swath-projector/tests/output_files/TEMPO_O3TOT_L2',
            reprojector.logger,
        )
