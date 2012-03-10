#!/usr/bin/env python
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

        self.dirs = {
                '/modx_site_content': {
                    'list':'select pagetitle from modx_site_content',
                    'get': 'select content, editedon from modx_site_content where pagetitle = %s',
                    'put': 'update modx_site_content set content = %s where pagetitle =%s',
                    },
                '/modx_site_templates': {
                    'list':'select templatename from modx_site_templates',
                    'get': 'select content from modx_site_templates where templatename = %s',
                    'put': 'update modx_site_templates set content = %s where templatename=%s',
                    },
                '/modx_site_htmlsnippets': {
                    'list': 'select id from modx_site_htmlsnippets',
                    'get': 'select snippet from modx_site_htmlsnippets where id = %s',
                    'put': 'update modx_site_htmlsnippets set snippet = %s where id=%s',
                    },
                '/modx_site_tmplvar_contentvalues': {
                    'list': 'select id from modx_site_tmplvar_contentvalues',
                    'get': 'select value from modx_site_tmplvar_contentvalues where id = %s',
                    'put': 'update modx_site_tmplvar_contentvalues set value = %s where id=%s',
                    }
                }

    def files_in_dir(self, path):

        filenames = []

        rows = execute_query(self.dirs[path]['list'])
        for row in rows:
            filenames.append(str(row[0]) + ext)

        return filenames

    def is_file(self, path):

        logger.info(path)
        try:
            dirpath, index = self.dirpath_index(path)
        except:
            return False

        rows = execute_query( self.dirs[dirpath]['get'], ( index ) )

        for row in rows:
            logger.info(row)
            files[path] = row[0]
            if len(row) > 1:
                editedon[path] = row[1]
            return True

        return False

    def dirpath_index(self, path):
        match = re.search('^(/\w+?)/([0-9\w\-\s"\'\(\)\[\]]+)'+ext+'$', path)
        return (match.group(1), str(match.group(2)))

    def getattr(self, path):
        st = MyStat()

        if path == '/':
            st.st_mode = stat.S_IFDIR | 0777
            st.st_nlink = 2

        elif self.dirs.has_key(path):
            st.st_mode = stat.S_IFDIR | 0777
            st.st_nlink = 2

        elif self.is_file(path):
            logger.info(path)
            if editedon.has_key(path):
                st.st_mtime = editedon[path]
            st.st_mode = stat.S_IFREG | 0666
            st.st_nlink = 1
            st.st_size = len(files[path])
        else:
            return -errno.ENOENT

        return st


    def readdir(self, path, offset):

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

        if self.is_file(path):
            return 0

        return -errno.ENOENT

    def read(self,path,size,offset):

        if files.has_key(path):
            body = files[path]
            slen = len(body)
            if offset < slen:
                if (offset+size)>slen:
                    size = slen-offset
                buf = body[offset:offset+size]
            else:
                buf = ''
            return buf
        else:
            return -errno.ENOENT

    def write(self, path, txt, offset):
        if files.has_key(path):
            dirpath, index = self.dirpath_index(path)
            execute_query(self.dirs[dirpath]['put'], (txt, index))
            logger.info(txt)
            logger.info('offset: %s' % offset)
            return len(txt)
        return -errno.ENOSYS
        

    def release(self, path, flags):
        logger.info(path)
        logger.info('release flag: %s' % flags)
        return 0

    def mknod(self, path, mode, dev):
        logger.info('mknod: %s' % path)
        return 0

    def create(self, path, mode, dev):
        return -errno.EACCES

    def unlink(self, path):
        return 0

    def truncate(self, path, size):
        if files.has_key(path):
            files[path] = ''
            txt = ''
            dirpath, index = self.dirpath_index(path)
            execute_query(self.dirs[dirpath]['put'], (txt, index))

        logger.info('truncate: %s' % path)
        return 0

    def utime(self, path, times):
        return 0

    def mkdir(self, path, mode):
        return 0

    def rmdir(self, path):
        return 0

    def rename(self, pathfrom, pathto):
        return 0

    def fsync(self, path, isfsyncnofile):
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
