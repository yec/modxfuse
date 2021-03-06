#!/usr/bin/env python

import StringIO
import MySQLdb
import logging
import os,stat,errno
import fuse
from fuse import Fuse
import logging
import re
import time
from configobj import ConfigObj

logger = logging.getLogger()
hdlr = logging.FileHandler('/tmp/modxfuse.log')
formatter = logging.Formatter('%(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr)
logger.setLevel(logging.INFO)

fuse.fuse_python_api = (0, 2)

config = ConfigObj('config.ini')

files = {}
editedon = {}
unlinked = []
writebuffer = StringIO.StringIO()

ext = '.html'

class MyStat(fuse.Stat):
    def __init__(self):
        self.st_mode=0
        self.st_ino=0
        self.st_dev=0
        self.st_nlink=0
        self.st_uid=0
        self.st_gid=0
        self.st_size=0
        self.st_atime=0
        self.st_mtime=0
        self.st_ctime=0

def execute_query(query, args = None):

    conn = MySQLdb.connect(
        host = config['host'],
        user = config['username'],
        passwd = config['password'],
        db = config['db']
        )
    cursor = conn.cursor()

    if args != None:
        cursor.execute(query, args)
    else:
        cursor.execute(query)

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    return rows

class MODxFS(Fuse):

    def __init__(self, *arr, **dic):
        Fuse.__init__(self, *arr, **dic)

        """ self.dirs stores the tables available to access and the properties
            related to accessing the tables sucha as the sql queries

            list: The query to list the contents of the table. The first column
                  returned is used as its index.

            get:  Get a specific record. The first column returned is the
                  relvant value of the record. Record is dentified by the
                  index nominated above.

            put:  Update the record with the first argument being the content
                  and the second argument being your nominated index.

            ext:  The extension for the file. Can be .html or .php. """

        self.dirs = {
                '/modx_site_content': {
                    'list':'select concat(lpad(id, 2, "0"), " ", pagetitle, " | ", id) from modx_site_content',
                    'get': 'select content, editedon from modx_site_content where id = %s',
                    'put': 'update modx_site_content set content = %s, editedon = unix_timestamp(now()) where id =%s',
                    'ext': '.html'
                    },
                '/modx_site_templates': {
                    'list':'select concat(templatename, " | ", id) from modx_site_templates',
                    'get': 'select content from modx_site_templates where id = %s',
                    'put': 'update modx_site_templates set content = %s where id=%s',
                    'ext': '.html'
                    },
                '/modx_site_htmlsnippets': {
                    'list': 'select concat(name, " | ", id) from modx_site_htmlsnippets',
                    'get': 'select snippet from modx_site_htmlsnippets where id = %s',
                    'put': 'update modx_site_htmlsnippets set snippet = %s where id = %s',
                    'ext': '.html'
                    },
                '/modx_site_snippets': {
                    'list': 'select concat(name, " | ", id) from modx_site_snippets',
                    'get': 'select snippet from modx_site_snippets where id = %s',
                    'put': 'update modx_site_snippets set snippet = %s where id=%s',
                    'ext': '.php'
                    },
                '/modx_site_tmplvar_contentvalues': {
                    'list': 'select concat(lpad(msc.id, 2, "0"), " ", msc.pagetitle, " - ", mst.name , " | ", mstc.id ) name from modx_site_tmplvar_contentvalues mstc join modx_site_content msc on mstc.contentid = msc.id join modx_site_tmplvars mst on mst.id = mstc.tmplvarid',
                    'get': 'select value from modx_site_tmplvar_contentvalues where id = %s',
                    'put': 'update modx_site_tmplvar_contentvalues set value = %s where id=%s',
                    'ext': '.html'
                    }
                }

    def files_in_dir(self, path):
        """ Returns a directory listing given the path. """
        filenames = []

        rows = execute_query(self.dirs[path]['list'])
        for row in rows:
            filenames.append(str(row[0]) + self.dirs[path]['ext'])

        return filenames

    def is_file(self, path):
        """ Check if specified path is a file
        this check is done at the database so is quite costly """

        # check if deleted
        if path in unlinked:
            return False

        # First see if can split path into its directory and file component
        try:
            dirpath, index = self.dirpath_index(path)
        except:
            return False

        # Attempt to return record of that path
        rows = execute_query( self.dirs[dirpath]['get'], ( index ) )

        for row in rows:
            files[path] = row[0]
            if len(row) > 1:
                editedon[path] = row[1]
            return True

        return False

    def dirpath_index(self, path):
        """ Seperate path into table and index components. """
        # TODO: Is ugly regex at the moment. Could be performed in a better way.
        match = re.search('^(/\w+?)/([\|\w\-\s"\'\(\)\[\]\{\}]+)(\.html|\.php)$', path)
        index = str(match.group(2)).split("|");
        logger.info('index: %s' % index)

        if len(index) > 1:
            index = index[1].strip()

        return (match.group(1), index)

    def getattr(self, path):
        """ FUSE method. Return file information. """
        st = MyStat()

        if path == '/':
            st.st_mode = stat.S_IFDIR | 0777
            st.st_nlink = 2

        elif self.dirs.has_key(path):
            st.st_mode = stat.S_IFDIR | 0777
            st.st_nlink = 2

        elif self.is_file(path):
            if editedon.has_key(path):
                st.st_mtime = editedon[path]
            st.st_mode = stat.S_IFREG | 0666
            st.st_nlink = 1
            st.st_size = len(files[path])
        else:
            return -errno.ENOENT

        return st

    def readdir(self, path, offset):
        """ FUSE method. return directory list. """

        ret = ['.',
        '..']

        if path == '/':
            for dirpath in self.dirs.keys():
                ret.append(dirpath[1:])

        elif self.dirs.has_key(path):
            for filename in self.files_in_dir(path):
                ret.append(filename)

        for r in ret:
            yield fuse.Direntry(r)

    def open(self,path,flags):
        """ FUSE method. Open file. """
        if self.is_file(path):
            return 0

        return -errno.ENOENT

    def read(self,path,size,offset):
        """ FUSE method. Read file. """
        if files.has_key(path):
            body = files[path]
            slen = len(body)
            if offset < slen:
                if (offset+size)>slen:
                    size = slen-offset
                buf = body[offset:offset+size]
            else:
                buf = ''

            logger.info('read: %s' % size)
            return buf
        else:
            return -errno.ENOENT

    def write(self, path, txt, offset):
        """ FUSE method. write file """
        if files.has_key(path):
            writebuffer.seek(offset)
            writebuffer.write(txt)
            dirpath, index = self.dirpath_index(path)
            execute_query(self.dirs[dirpath]['put'], (writebuffer.getvalue(), index))
            logger.info('offset: %s' % offset)
            return len(txt)
        return -errno.ENOSYS
        

    def release(self, path, flags):
        """ FUSE method. release file """
        if files.has_key(path) and flags == 1:
            dirpath, index = self.dirpath_index(path)
            execute_query(self.dirs[dirpath]['put'], (writebuffer.getvalue(), index))
        logger.info('release flag: %s %s' % flags, path)
        return 0

    def mknod(self, path, mode, dev):
        """ FUSE method. mknod """
        logger.info('mknod: %s' % path)
        return 0

    def create(self, path, mode, dev):
        """ FUSE method. create """
        if path in unlinked:
            unlinked.remove(path)
            return 0
        else:
            return -errno.EACCES

    def unlink(self, path):
        """ FUSE method. unlink """
        unlinked.append(path);
        logger.info('unlinked: %s' % path)
        return 0

    def truncate(self, path, size):
        """ FUSE method. truncate """
        if files.has_key(path):
            files[path] = ''
            txt = ''
            writebuffer.truncate(0)
            dirpath, index = self.dirpath_index(path)
            execute_query(self.dirs[dirpath]['put'], (txt, index))

        logger.info('truncate: %s' % path)
        return 0

    def utime(self, path, times):
        """ FUSE method. utime """
        return 0

    def mkdir(self, path, mode):
        """ FUSE method. mkdir """
        return 0

    def rmdir(self, path):
        """ FUSE method. rmdir """
        return 0

    def rename(self, pathfrom, pathto):
        """ FUSE method. rename """
        return 0

    def fsync(self, path, isfsyncnofile):
        """ FUSE method. fsync """
        path = config['cache']
        for each in os.listdir(path):
            if each.endswith(".php"):
                name = os.path.join(path, each)
                try: os.remove(name)
                except:
                    logger.info('cache delete failed')

        logger.info('fsync: %s' % path)
        return 0

def main():
    usage="""
    Userspace MODx

    """ + Fuse.fusage
    server = MODxFS(version="%prog " + fuse.__version__,
    usage=usage,
    dash_s_do='setsingle')

    server.parse(values=server, errex=1)
    server.main()

if __name__=='__main__':
    main()
