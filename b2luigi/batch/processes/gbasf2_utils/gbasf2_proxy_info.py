#!/usr/bin/env python3

"""
Script to run as subprocess in a gbasf2 environment (with ``run_with_gbasf``) to
query the proxy status. If successful, prints proxy info in JSON format.
"""

from __future__ import print_function

import json
import sys

from DIRAC import gLogger
from DIRAC.Core.Base import Script
from DIRAC.Core.Security.X509Chain import X509Chain
from DIRAC.Core.Security.ProxyInfo import getProxyInfo

# from b2luigi.batch.processes.gbasf2_utils.json_encoder import Gbasf2ResultJsonEncoder

import json

from DIRAC.Core.Security.X509Chain import X509Chain
import datetime


class Gbasf2ResultJsonEncoder(json.JSONEncoder):
    """
    JSON encoder for data structures possibly including certificate objects.
    """
    def default(self, obj):
        if isinstance(obj, X509Chain):
            x509dict =  obj.dumpAllToString()
            x509dict['Value'] = x509dict['Value'].decode()
            return x509dict
        elif isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)

if __name__ == "__main__":
    # Suppress error messages, since stdout of this script is expected to be in JSON format
    gLogger.setLevel("FATAL")

    Script.enableCS()  # Required so dict includes username
    ProxyInfo = getProxyInfo()
    if not ProxyInfo["OK"]:
        sys.exit(1)
    print(json.dumps(ProxyInfo["Value"], cls=Gbasf2ResultJsonEncoder))
