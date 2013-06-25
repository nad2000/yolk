"""pypi

Desc: Library for getting information about Python packages by querying
      The CheeseShop (PYPI a.k.a. Python Package Index).


Author: Rob Cakebread <cakebread at gmail>

License  : BSD (See COPYING)

"""

from __future__ import print_function

import ast
import re
import platform
if platform.python_version().startswith('2'):
    import xmlrpclib
    import urllib2
else:
    import xmlrpc.client as xmlrpclib
    import urllib.request as urllib2
import os
import time
import logging

from yolk.utils import get_yolk_dir


XML_RPC_SERVER = 'https://pypi.python.org/pypi'


class ProxyTransport(xmlrpclib.Transport):

    """Provides an XMl-RPC transport routing via a http proxy.

    This is done by using urllib2, which in turn uses the environment
    varable http_proxy and whatever else it is built to use (e.g. the
    windows    registry).

    NOTE: the environment variable http_proxy should be set correctly.
    See check_proxy_setting() below.

    Written from scratch but inspired by xmlrpc_urllib_transport.py
    file from http://starship.python.net/crew/jjkunce/ by jjk.

    A. Ellerton 2006-07-06

    """

    def request(self, host, handler, request_body, verbose):
        """Send xml-rpc request using proxy."""
        # We get a traceback if we don't have this attribute:
        self.verbose = verbose
        url = 'http://' + host + handler
        request = urllib2.Request(url)
        request.add_data(request_body)
        # Note: 'Host' and 'Content-Length' are added automatically
        request.add_header('User-Agent', self.user_agent)
        request.add_header('Content-Type', 'text/xml')
        proxy_handler = urllib2.ProxyHandler()
        opener = urllib2.build_opener(proxy_handler)
        fhandle = opener.open(request)
        return(self.parse_response(fhandle))


def check_proxy_setting():
    """If the environmental variable 'HTTP_PROXY' is set, it will most likely
    be in one of these forms:

    proxyhost:8080 http://proxyhost:8080 urlllib2
    requires the proxy URL to start with 'http://' This routine does that, and
    returns the transport for xmlrpc.

    """
    try:
        http_proxy = os.environ['HTTP_PROXY']
    except KeyError:
        return

    if not http_proxy.startswith('http://'):
        match = re.match('(http://)?([-_\.A-Za-z]+):(\d+)', http_proxy)
        os.environ['HTTP_PROXY'] = 'http://%s:%s' % (match.group(2),
                                                     match.group(3))
    return


class CheeseShop(object):

    """Interface to Python Package Index."""

    def __init__(self, debug=False, no_cache=False, yolk_dir=None):
        self.debug = debug
        self.no_cache = no_cache
        if yolk_dir:
            self.yolk_dir = yolk_dir
        else:
            self.yolk_dir = get_yolk_dir()
        self.xmlrpc = self.get_xmlrpc_server()
        self.pkg_cache_file = self.get_pkg_cache_file()
        self.last_sync_file = self.get_last_sync_file()
        self.pkg_list = None
        self.logger = logging.getLogger('yolk')
        self.get_cache()

    def get_cache(self):
        """Get a package name list from disk cache or PyPI."""
        # This is used by external programs that import `CheeseShop` and don't
        # want a cache file written to ~/.pypi and query PyPI every time.
        if self.no_cache:
            self.pkg_list = self.list_packages()
            return

        if not os.path.exists(self.yolk_dir):
            os.mkdir(self.yolk_dir)
        try:
            self.pkg_list = self.query_cached_package_list()
        except (IOError, ValueError):
            self.logger.debug(
                'DEBUG: Fetching package list cache from PyPi...')
            self.fetch_pkg_list()

    def get_last_sync_file(self):
        """Get the last time in seconds since The Epoc since the last pkg list
        sync."""
        return os.path.abspath(self.yolk_dir + '/last_sync')

    def get_xmlrpc_server(self):
        """Returns PyPI's XML-RPC server instance."""
        check_proxy_setting()
        if 'XMLRPC_DEBUG' in os.environ:
            debug = 1
        else:
            debug = 0
        try:
            return xmlrpclib.Server(XML_RPC_SERVER, transport=ProxyTransport(),
                                    verbose=debug)
        except IOError:
            self.logger("ERROR: Can't connect to XML-RPC server: %s"
                        % XML_RPC_SERVER)

    def get_pkg_cache_file(self):
        """Returns filename of pkg cache."""
        return os.path.abspath('%s/pkg_list.pkl' % self.yolk_dir)

    def query_versions_pypi(self, package_name):
        """Fetch list of available versions for a package from PyPI."""
        if not package_name in self.pkg_list:
            self.logger.debug('Package %s not in cache, querying PyPI...'
                              % package_name)
            self.fetch_pkg_list()
        # I have to set version=[] for edge cases like "Magic file extensions"
        # but I'm not sure why this happens. It's included with Python or
        # because it has a space in it's name?
        versions = []
        for pypi_pkg in self.pkg_list:
            if pypi_pkg.lower() == package_name.lower():
                if self.debug:
                    self.logger.debug('DEBUG: %s' % package_name)
                versions = self.package_releases(pypi_pkg)
                package_name = pypi_pkg
                break
        return (package_name, versions)

    def query_cached_package_list(self):
        """Return list of cached package names from PYPI."""
        if self.debug:
            self.logger.debug('DEBUG: reading cache file')
        with open(self.pkg_cache_file, 'r') as input_file:
            return ast.literal_eval(input_file.read())

    def fetch_pkg_list(self):
        """Fetch and cache master list of package names from PYPI."""
        self.logger.debug('DEBUG: Fetching package name list from PyPI')
        package_list = self.list_packages()
        print('write cache')
        with open(self.pkg_cache_file, 'w') as output_file:
            print(package_list, file=output_file)
        self.pkg_list = package_list

    def search(self, spec, operator):
        """Query PYPI via XMLRPC interface using search spec."""
        return self.xmlrpc.search(spec, operator.lower())

    def changelog(self, hours):
        """Query PYPI via XMLRPC interface using search spec."""
        return self.xmlrpc.changelog(get_seconds(hours))

    def updated_releases(self, hours):
        """Query PYPI via XMLRPC interface using search spec."""
        return self.xmlrpc.updated_releases(get_seconds(hours))

    def list_packages(self):
        """Query PYPI via XMLRPC interface for a a list of all package
        names."""
        return self.xmlrpc.list_packages()

    def release_urls(self, package_name, version):
        """Query PYPI via XMLRPC interface for a pkg's available versions."""

        return self.xmlrpc.release_urls(package_name, version)

    def release_data(self, package_name, version):
        """Query PYPI via XMLRPC interface for a pkg's metadata."""
        try:
            return self.xmlrpc.release_data(package_name, version)
        except xmlrpclib.Fault:
            # XXX Raises xmlrpclib.Fault if you give non-existent version
            # Could this be server bug?
            return

    def package_releases(self, package_name):
        """Query PYPI via XMLRPC interface for a pkg's available versions."""
        if self.debug:
            self.logger.debug('DEBUG: querying PyPI for versions of '
                              + package_name)
        return self.xmlrpc.package_releases(package_name)

    def get_download_urls(self, package_name, version='', pkg_type='all'):
        """Query PyPI for pkg download URI for a packge."""

        if version:
            versions = [version]
        else:

            # If they don't specify version, show em all.

            (package_name, versions) = self.query_versions_pypi(package_name)

        all_urls = []
        for ver in versions:
            metadata = self.release_data(package_name, ver)
            for urls in self.release_urls(package_name, ver):
                if pkg_type == 'source' and urls['packagetype'] == 'sdist':
                    all_urls.append(urls['url'])
                elif pkg_type == 'egg' and \
                        urls['packagetype'].startswith('bdist'):
                    all_urls.append(urls['url'])
                elif pkg_type == 'all':
                    # All
                    all_urls.append(urls['url'])

            # Try the package's metadata directly in case there's nothing
            # returned by XML-RPC's release_urls()
            if metadata and 'download_url' in metadata and \
                metadata['download_url'] != 'UNKNOWN' and \
                    metadata['download_url'] is not None:
                if metadata['download_url'] not in all_urls:
                    if pkg_type != 'all':
                        url = filter_url(pkg_type, metadata['download_url'])
                        if url:
                            all_urls.append(url)
        return all_urls


def filter_url(pkg_type, url):
    """Returns URL of specified file type.

    'source', 'egg', or 'all'

    """
    bad_stuff = ['?modtime', '#md5=']
    for junk in bad_stuff:
        if junk in url:
            url = url.split(junk)[0]
            break

    # pkg_spec==dev (svn)
    if url.endswith('-dev'):
        url = url.split('#egg=')[0]

    if pkg_type == 'all':
        return url

    elif pkg_type == 'source':
        valid_source_types = ['.tgz', '.tar.gz', '.zip', '.tbz2', '.tar.bz2']
        for extension in valid_source_types:
            if url.lower().endswith(extension):
                return url

    elif pkg_type == 'egg':
        if url.lower().endswith('.egg'):
            return url


def get_seconds(hours):
    """Get number of seconds since epoch from now minus `hours`

    @param hours: Number of `hours` back in time we are checking
    @type hours: int

    Return integer for number of seconds for now minus hours

    """
    return int(time.time() - (60 * 60) * hours)
