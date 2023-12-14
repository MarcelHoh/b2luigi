import json

from DIRAC.Core.Security.X509Chain import X509Chain
import datetime


class Gbasf2ResultJsonEncoder(json.JSONEncoder):
    """
    JSON encoder for data structures possibly including certificate objects.
    """
    def default(self, obj):
        if isinstance(obj, X509Chain):
            return obj.dumpAllToString()
        elif isinstance(obj, datetime.date, datetime.datetime):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)