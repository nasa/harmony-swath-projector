
import logging


# Test class used to construct a Harmony type 'Message' object
# from a dictionary.
#
class Message(object):
    def __init__(self, data):
        for k,v in data.items():
            if isinstance(v, (list, tuple)):
               setattr(self, k, [Message(x) if isinstance(x, dict) else x for x in v])
            else:
               setattr(self, k, Message(v) if isinstance(v, dict) else v)



# Test class used to simulate the BaseHarmonyAdapter base class used by
# harmony services.
#
class BaseHarmonyAdapter:

    def __init__(self, data):
        self.logger = logging.getLogger()
        self.message = Message(data)


    def download_granules(self):
        pass

    def completed_with_local_file(self, local_file, output_name, mime_type):
        pass

    def completed_with_error(self, error):
        pass

    def cleanup(self):
        pass

