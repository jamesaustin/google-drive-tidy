#!/usr/bin/env python
import os

from json import load as json_load, dump as json_dump
from httplib2 import Http
from logging import debug, info, warning, error, basicConfig as logging_config
from argparse import ArgumentParser
from re import compile as re_compile

from oauth2client.tools import run
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage

from apiclient.discovery import build
from apiclient import errors

OUTPUT = 'output.json'
CLIENT_SECRETS = 'client-secrets.json'
CREDENTIALS = 'credentials.dat'

class Node(list):
    def __init__(self, iterable=(), **attributes):
        self.attributes = attributes
        list.__init__(self, iterable)
    def __repr__(self):
        return '%s(%s, %r)' % (type(self).__name__, list.__repr__(self), self.attributes)
    def total_len(self):
        return len(self) + sum(x.total_len() for x in self)

def retrieve_all_files(service):
    result = [ ]
    page_token = None
    while True:
        param = { }
        if page_token:
            param['pageToken'] = page_token
        info('getting %s' % param)
        files = service.files().list(**param).execute()

        result.extend(files['items'])
        page_token = files.get('nextPageToken')
        if not page_token:
            break
    return result

def generate_all_files(output=OUTPUT, client_secrets=CLIENT_SECRETS, credentials=CREDENTIALS):
    response = None
    if os.path.exists(output):
        try:
            with open(OUTPUT, 'r') as f:
                response = json_load(f)
        except ValueError:
            response = None
            os.remove(output)

    if not response:
        storage = Storage(credentials)
        credentials = storage.get()
        if not credentials:
            flow = flow_from_clientsecrets(client_secrets, scope='https://www.googleapis.com/auth/drive')
            credentials = run(flow, storage)

        http = Http()
        http = credentials.authorize(http)
        service = build('drive', 'v2', http=http)

        try:
            response = {
                'all_files': retrieve_all_files(service),
                'about': service.about().get().execute()
            }
        except errors.HttpError, error:
            error('An error occurred: %s' % error)
            response = None
        else:
            with open(output, 'w') as f:
                json_dump(response, f, indent=2)

    return response

def process():
    response = generate_all_files()
    if response:

        root_id = response['about']['rootFolderId']
        orphan_id = '@'

        ids_to_titles = {
            root_id: 'ROOT'
        }
        ids_to_folders = {
            root_id: Node(name='<ROOT>'),
            orphan_id: Node(name='<ORPHAN>')
        }

        all_files = response['all_files']

        owners = { }
        mime_types = { }
        for r in all_files:
            id = r.get('id')
            title = r.get('title')
            ids_to_titles[id] = title

            mime_type = r.get('mimeType')
            if mime_type == 'application/vnd.google-apps.folder':
                ids_to_folders[id] = Node(name=title, asset=r)

            mime_types[mime_type] = mime_types.get(mime_type, 0) + 1

            owner_names = r.get('ownerNames')
            if len(owner_names) > 1:
                warning('Document with multiple owners: "%s" %s' % (title, owner_names))
            else:
                owner = owner_names[0]
                owners[owner] = owners.get(owner, 0) + 1

        else:
            def _log(label, data):
                return '%s:\n%s' % (label, '\n'.join(['%4i: %s' % (v, k) for k, v in data.iteritems()]))

            info('titles: %i, folders: %i' % (len(ids_to_titles), len(ids_to_folders)))
            info(_log('mime_types', mime_types))
            info(_log('owners', owners))

        orphans = [ ]
        parent_1 = [ ]
        parent_n = [ ]
        for r in all_files:
            num_parents = len(r.get('parents'))
            if num_parents == 0:
                orphans.append(r)
            elif num_parents == 1:
                parent_1.append(r)
            else:
                parent_n.append(r)
        else:
            info('orphans: %i, 1 parent: %i, n parent: %i' % (len(orphans), len(parent_1), len(parent_n)))

        for r in orphans:
            title = r.get('title')
            node = ids_to_folders.get(r.get('id'), Node(name=title, asset=r))
            ids_to_folders[orphan_id].append(node)
        else:
            info('orphan tree: %i' % ids_to_folders[orphan_id].total_len())

        for r in parent_n:
            parents = r.get('parents')
            parents_string = ', '.join([ids_to_titles[p['id']] for p in parents])
            warning('document "%s" with %i parents: %s' % (r.get('title'), len(parents), parents_string))

        for i, r in enumerate(parent_1):
            title = r.get('title')
            node = ids_to_folders.get(r.get('id'), Node(name=title, asset=r))

            parents = r.get('parents')
            assert len(parents) == 1
            p = parents[0]

            parent_id = p.get('id')
            parent = ids_to_folders[parent_id]
            parent.append(node)
        else:
            info('root tree: %i' % ids_to_folders[root_id].total_len())
            info('orphan tree: %i' % ids_to_folders[orphan_id].total_len())

        return (ids_to_folders[root_id], ids_to_folders[orphan_id])

def main():
    parser = ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose logging')
    parser.add_argument('-d', '--dump-tree', action='store_true', help='Dump tree')
    parser.add_argument('-o', '--dump-orphans', action='store_true', help='Dump orphans tree')
    parser.add_argument('-f', '--filter', help='Filter output')
    options = parser.parse_args()

    if options.verbose:
        logging_config(level='INFO', format='[%(levelname)s %(module)s@%(lineno)d] %(message)s')
    else:
        logging_config(format='[%(levelname)s] %(message)s')

    if options.filter:
        filter_re = re_compile(options.filter)
    else:
        filter_re = None

    root, orphans = process()

    def _log(node, indent=''):
        if len(node) == 0:
            asset = node.attributes['asset']
            owners = ', '.join(asset['ownerNames'])
            if (filter_re and filter_re.search(owners)) or not filter_re:

                if asset.get('explicitlyTrashed', False):
                    trashed = ' - TRASHED'
                else:
                    trashed = ''

                print '%s- "%s" (%s)%s' % (indent, node.attributes['name'], owners, trashed)
        else:
            print '%s-+ %s' % (indent, node.attributes['name'])
            if len(indent) > 0 and indent[-1] == '\\':
                indent = indent[:-1] + ' '
            for r in node[:-1]:
                _log(r, indent + ' |')
            else:
                _log(node[-1], indent + ' \\')

    if options.dump_tree:
        _log(root)
    if options.dump_orphans:
        _log(orphans)

    return 0

if __name__ == '__main__':
    exit(main())