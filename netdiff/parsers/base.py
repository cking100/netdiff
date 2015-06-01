import six
import json
import os
import requests
import telnetlib
from collections import OrderedDict

try:
    import urlparse
except ImportError:
    import urllib.parse as urlparse

from ..exceptions import ParserError, ParserJsonError, NetJsonError, TopologyRetrievalError
from ..utils import diff


class BaseParser(object):
    """
    Base Class for Parsers
    To create a parser, extend this class
    and implement a parse method
    """
    protocol = None
    version = None
    revision = None
    metric = None

    def __init__(self, data, version=None, revision=None, metric=None,
                 timeout=None, verify=True):
        """
        Initializes a new Parser

        :param data: JSON, dict, path to file or HTTP URL of topology
        :param version: routing protocol version
        :param revision: routing protocol revision
        :param metric: routing protocol metric
        :param timeout: timeout in seconds for HTTP or telnet requests
        :param verify: boolean (valid for HTTPS requests only)
        """
        if version:
            self.version = version
        if revision:
            self.revision = revision
        if metric:
            self.metric = metric
        self.timeout = timeout
        self.verify = verify
        self.original_data = self.to_python(data)
        # avoid throwing NotImplementedError in tests
        if self.__class__ is not BaseParser:
            self.parse(self.original_data)

    def __sub__(self, other):
        return diff(other, self)

    def to_python(self, data):
        """
        Parses the input data and converts it into a Python data structure
        Input data might be:
            * a path which points to a JSON file
            * a URL which points to a JSON file
              (supported schemes: http, https, telnet)
            * a JSON formatted string
            * a dict representing a JSON structure
        """
        if isinstance(data, dict):
            return data
        elif isinstance(data, six.string_types):
            # if it looks like URL
            if '://' in data:
                url = urlparse.urlparse(data)
                if url.scheme in ['http', 'https']:
                    data = self._get_http(url)
                if url.scheme == 'telnet':
                    data = self._get_telnet(url)
            # if it looks like a path
            elif True in [data.startswith('./'),
                          data.startswith('../'),
                          data.startswith('/'),
                          data.startswith('.\\'),
                          data.startswith('..\\'),
                          data.startswith('\\'),
                          data[1:3].startswith(':\\')]:
                data = self._get_file(data)
            # assuming is JSON
            try:
                return json.loads(data)
            except ValueError:
                raise ParserJsonError('Could not decode JSON data')
        else:
            raise ParserError('Could not find valid data to parse')

    def _get_file(self, path):
        try:
            return open(path).read()
        except Exception as e:
            raise TopologyRetrievalError(e)

    def _get_http(self, url):
        try:
            response = requests.get(url.geturl(), verify=self.verify, timeout=self.timeout)
        except Exception as e:
            raise TopologyRetrievalError(e)
        if response.status_code != 200:
            raise TopologyRetrievalError('Expecting HTTP 200 ok, got {0}'.format(response.status_code))
        return response.content.decode()

    def _get_telnet(self, url):
        try:
            tn = telnetlib.Telnet(url.hostname, url.port, timeout=self.timeout)
        except Exception as e:
            raise TopologyRetrievalError(e)
        tn.write(("\r\n").encode('ascii'))
        data = tn.read_all().decode('ascii')
        tn.close()

    def parse(self, data):
        """
        Converts the original python data structure into a NetworkX Graph object
        Must be implemented by subclasses.
        """
        raise NotImplementedError()

    def json(self, dict=False, **args):
        """
        Outputs NetJSON format
        """
        try:
            graph = self.graph
        except AttributeError:
            raise NotImplementedError()
        # netjson formatting check
        if self.protocol is None:
            raise NetJsonError('protocol cannot be None')
        if self.version is None:
            raise NetJsonError('version cannot be None')
        if self.metric is None and self.protocol != 'static':
            raise NetJsonError('metric cannot be None')
        # prepare lists
        nodes = [{'id': node} for node in graph.nodes()]
        links = []
        for link in graph.edges(data=True):
            links.append(OrderedDict((
                ('source', link[0]),
                ('target', link[1]),
                ('weight', link[2]['weight'])
            )))
        data = OrderedDict((
            ('type', 'NetworkGraph'),
            ('protocol', self.protocol),
            ('version', self.version),
            ('revision', self.revision),
            ('metric', self.metric),
            ('nodes', nodes),
            ('links', links)
        ))
        if dict:
            return data
        return json.dumps(data, **args)
