"""Data Services Swath Projector service for Harmony."""

import mimetypes
import os
import shutil
from tempfile import mkdtemp

from harmony import BaseHarmonyAdapter
from harmony.message import Source as HarmonySource
from harmony.util import HarmonyException, download, generate_output_filename, stage
from pystac import Asset, Item

from swath_projector.reproject import reproject


class SwathProjectorAdapter(BaseHarmonyAdapter):
    """Data Services Swath Projector service for Harmony

    This class uses the Harmony utility library for processing the
    service input options.
    """

    def invoke(self):
        """Adds validation to default process_item-based invocation

        Returns
        -------
        pystac.Catalog
            the output catalog
        """
        logger = self.logger
        logger.info('Starting Data Services Swath Projector Service')
        os.environ['HDF5_DISABLE_VERSION_CHECK'] = '1'
        self.validate_message()
        return super().invoke()

    def process_item(self, item: Item, source: HarmonySource):
        """
        Processes a single input item.  Services that are not aggregating multiple input files
        should prefer to implement this method rather than #invoke

        This example copies its input to the output, marking "dpi" and "variables" message
        attributes as having been processed

        Parameters
        ----------
        item : pystac.Item
            the item that should be processed
        source : harmony.message.Source
            the input source defining the variables, if any, to subset from the item

        Returns
        -------
        pystac.Item
            a STAC catalog whose metadata and assets describe the service output
        """
        logger = self.logger
        result = item.clone()
        result.assets = {}

        # Create a temporary dir for processing we may do
        workdir = mkdtemp()
        try:
            # Get the data file
            asset = next(v for v in item.assets.values() if 'data' in (v.roles or []))
            granule_url = asset.href

            input_filename = download(
                granule_url,
                workdir,
                logger=logger,
                access_token=self.message.accessToken,
                cfg=self.config,
            )

            logger.info('Granule data copied')

            # Call Reprojection utility
            working_filename = reproject(
                self.message,
                source.shortName,
                granule_url,
                input_filename,
                workdir,
                logger,
            )

            # Stage the output file with a conventional filename
            output_filename = generate_output_filename(asset.href, is_regridded=True)
            mimetype, _ = mimetypes.guess_type(output_filename, False) or (
                'application/x-netcdf4',
                None,
            )

            url = stage(
                working_filename,
                output_filename,
                mimetype,
                location=self.message.stagingLocation,
                logger=self.logger,
            )

            # Update the STAC record
            asset = Asset(
                url, title=output_filename, media_type=mimetype, roles=['data']
            )
            result.assets['data'] = asset

            # Return the output file back to Harmony
            logger.info('Reprojection complete')

            return result

        except Exception as err:
            logger.error('Reprojection failed: ' + str(err), exc_info=1)
            raise HarmonyException(
                'Reprojection failed with error: ' + str(err)
            ) from err

        finally:
            # Clean up any intermediate resources
            shutil.rmtree(workdir, ignore_errors=True)

    def validate_message(self):
        """Check the service was triggered by a valid message containing
        the expected number of granules.

        """
        if not hasattr(self, 'message'):
            raise HarmonyException('No message request')

        has_granules = hasattr(self.message, 'granules') and self.message.granules
        try:
            has_items = bool(self.catalog and next(self.catalog.get_all_items()))
        except StopIteration:
            has_items = False

        if not has_granules and not has_items:
            raise HarmonyException('No granules specified for reprojection')

        if not isinstance(self.message.granules, list):
            raise Exception('Invalid granule list')
