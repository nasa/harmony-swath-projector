"""
 Data Services Reprojection service for Harmony
"""

import argparse
import mimetypes
import os

import harmony

from pymods.reproject import reproject

class HarmonyAdapter(harmony.BaseHarmonyAdapter):
    """
        Data Services Reprojection service for Harmony

        This class uses the Harmony utility library for processing the
        service input options.
    """

    def invoke(self):
        """
            Callback used by BaseHarmonyAdapter to invoke the service
        """
        logger = self.logger
        logger.info("Starting Data Services Reprojection Service")
        os.environ['HDF5_DISABLE_VERSION_CHECK'] = '1'

        try:
            if not hasattr(self, 'message'):
                raise Exception("No message request")

            # Verify a granule URL has been provided and make a local copy of the granule file

            # message schema
            # {'granules': [{'local_filename': '/home/test/data/VNL2_oneBand.nc'}],
            # 'format': {'crs': 'CRS:84',  'interpolation': 'bilinear',
            #            # 'width': 1000, 'height': 500,
            #            'scaleExtent': {
            #                'x': {'min': -160, 'max': -30},
            #                'y': {'min': 10, 'max': 25}
            #            },
            #            'scaleSize': {'x': 1, 'y': 1}
            #            }}
            msg = self.message
            if not hasattr(msg, 'granules') or not msg.granules:
                raise Exception("No granules specified for reprojection")
            if not isinstance(msg.granules, list):
                raise Exception("Invalid granule list")
            if len(msg.granules) > 1:
                raise Exception("Too many granules")

            self.download_granules()
            logger.info("Granule data copied")
            logger.info(f'Received message: {msg}')

            # Call Reprojection utility
            granule, output_file = reproject(msg, logger)

            # Return the output file back to Harmony
            logger.info("Reprojection complete")
            # TODO: mimetype should be based on output file(s)?
            mimetype = mimetypes.guess_type(granule.local_filename, False) or ('application/x-netcdf4', None)
            self.completed_with_local_file(
                output_file,
                source_granule=granule,
                is_regridded=True,
                mime=mimetype[0]
            )

        except Exception as err:
            # TODO log the stacktrace here to make debugging much easier
            logger.error("Reprojection failed: " + str(err))
            self.completed_with_error("Reprojection failed with error: " + str(err))

        finally:
            self.cleanup()


# Main program start
#
if __name__ == "__main__":
    PARSER = argparse.ArgumentParser(
        prog='Reproject',
        description='Run the Data Services Reprojection Tool'
    )
    harmony.setup_cli(PARSER)
    ARGS, _ = PARSER.parse_known_args()
    harmony.run_cli(PARSER, ARGS, HarmonyAdapter)
