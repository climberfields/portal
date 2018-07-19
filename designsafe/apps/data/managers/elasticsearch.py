import logging
# import datetime
import os
# import urllib2
# import json
from elasticsearch_dsl.query import Q
from designsafe.apps.data.models.elasticsearch import IndexedFile
from django.conf import settings
import magic
import json
import re

# pylint: disable=invalid-name
logger = logging.getLogger(__name__)
# pylint: enable=invalid-name


class FileManager(object):
    """Elasticsearch File Manager Class"""
    def __init__(self, username):
        self.username = username

    def _pems_filter(self):
        term_username_query = Q(
            'term',
            **{'permissions.username': self.username}
        )
        term_world_query = Q(
            'term',
            **{'permissions.username': 'WORLD'}
        )
        bool_query = Q('bool')
        bool_query.should = [term_username_query, term_world_query]
        nested_query = Q('nested')
        nested_query.path = 'permissions'
        nested_query.query = bool_query
        return nested_query

    def listing(self, system='designsafe.storage.default', path='/'):
        """Lists a file

        :param str system: System Id. Default: designsafe.storage.default
        :param str path: Path
        """
        logger.debug('listing %s', os.path.join(system, path))
        search = IndexedFile.search()
        term_system_query = Q(
            'term',
            **{'system._exact': system}
        )
        term_path_query = Q('term', **{'path._exact': path})
        bool_query = Q('bool')
        bool_query.must = [term_system_query, term_path_query]
        bool_query.filter = self._pems_filter()
        search = search.query(bool_query)
        search = search.sort({'name._exact': 'asc'})
        res = search.execute()
        logger.debug('res %s', str(res.hits.total))
        return res, search

    def listing_recursive(
            self,
            system='designsafe.storage.default',
            path='/'):
        """Lists every folder's children"""
        search = IndexedFile.search()
        term_system_query = Q(
            'term',
            **{'system._exact': system}
        )
        term_path_query = Q('term', **{'path._path': path})
        bool_query = Q('bool')
        bool_query.must = [term_system_query, term_path_query]
        bool_query.filter = self._pems_filter()
        search = search.query(bool_query)
        search = search.sort({'name._exact': 'asc'})
        res = search.execute()
        return res, search

    def get(self, system='designsafe.storage.default', path='/', name=''):
        """Gets a file"""
        search = IndexedFile.search()
        term_system_query = Q(
            'term',
            **{'system._exact': system}
        )
        term_path_query = Q('term', **{'path._exact': path})
        term_username_query = Q('term', **{'name._exact': name})
        bool_query = Q('bool')
        bool_query.must = [
            term_system_query,
            term_path_query,
            term_username_query
        ]
        bool_query.filter = self._pems_filter()
        search = search.query(bool_query)
        search = search.sort({'name._exact': 'asc'})
        res = search.execute()
        # logger.debug('search :%s', json.dumps(search.to_dict(), indent=2))
        return res, search

    @staticmethod
    def mimetype_lookup(file_object, debug_mode):
        if debug_mode == True:
            # In local dev, corral isn't mounted so we have to download the file to get its mimetype.
            import requests
            href = file_object['_links']['self']['href']
            header = {"Authorization": "Bearer " + settings.AGAVE_SUPER_TOKEN}
            u = requests.get(href, headers=header)
            if u.status_code == 200:
                mimeType = magic.from_buffer(u.content, mime=True)
            elif json.loads(u.content)['message'] == 'Directory downloads not supported':
                mimeType =  'text/directory'
            else:
                raise requests.HTTPError
            return mimeType

        else:
            # In dev/prod, Corral is mounted and we can use the absolute path to get the mimetype.
            SYSTEM_ID_PATHS = [
                {'regex': r'^designsafe.storage.default$',
                'path': '/corral-repl/projects/NHERI/shared'},
                {'regex': r'^designsafe.storage.community$',
                'path': '/corral-repl/projects/NHERI/community'},
                {'regex': r'^designsafe.storage.published$',
                'path': '/corral-repl/projects/NHERI/published'},
                {'regex': r'^project\-',
                'path': '/corral-repl/projects/NHERI/projects'}
            ]
            for mapping in SYSTEM_ID_PATHS:
                if re.search(mapping['regex'], file_object['system']):
                    base_path = mapping['path']
                    if mapping['regex'] == r'^project\-':
                        base_path += '/' + file_object['system'][8:] 
                    break

            filePath = base_path + file_object['path']
            if os.path.isdir(filePath):
                mimeType = 'text/directory'
            else:
                mimeType = magic.from_file(filePath, mime=True)

            return mimeType
   
    def index(self, file_object, pems):
        """Indexes an Agave response file object (json) to an IndexedFile"""
        res, search = self.get(file_object.system,
                               os.path.dirname(file_object.path.strip('/')),
                               os.path.basename(file_object.path.strip('/')))
        if res.hits.total > 1:
            for doc in res[1:]:
                doc.delete(ignore=404)
        if res.hits.total >= 1:
            document = res[0]
            file_object.pop('_links')
            file_object.pop('permissions')
            document.update(**file_object)
        else:
            document = IndexedFile(
                name=os.path.basename(file_object.path.strip('/')),
                path=os.path.dirname(file_object.path.strip('/')) or '/',
                lastModified=file_object.lastModified.isoformat(),
                length=file_object.length,
                format=file_object.format,
                mimeType=FileManager.mimetype_lookup(file_object, settings.DEBUG),
                type=file_object.type,
                system=file_object.system,
            )
            if pems is None or not pems:
                document.permissions = [{
                    'username': self.username,
                    'permission': {
                        'read': True,
                        'write': True,
                        'execute': True
                    }
                }]
            document.save()

        if pems:
            for pem in pems:
                pem.pop('_links', None)
                pem.pop('internalUsername', None)
            document.update(permissions=pems)
        return document
