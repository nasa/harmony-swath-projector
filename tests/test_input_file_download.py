from unittest import TestCase

from harmony.message import Message
from harmony.util import HarmonyException, config

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
