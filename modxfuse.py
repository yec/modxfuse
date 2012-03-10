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

attrs = {}

config = ConfigObj('config.ini')

conn = MySQLdb.connect(
        host = config['host'],
        user = config['username'],
        passwd = config['password'],
        db = config['db']
        )

cursor = conn.cursor()

files = {}

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

class MODxFS(Fuse):


    def getattr(self, path):
        st = MyStat()

        if path == '/':
            st.st_mode = stat.S_IFDIR | 0777
            st.st_nlink = 2
#            elif path == hello_path:
#                st.st_mode = stat.S_IFREG | 0666
#                st.st_nlink = 1
#                st.st_size = len(hello_str)
        elif path == '/modx_site_content':
            st.st_mode = stat.S_IFDIR | 0777
            st.st_nlink = 2
        elif re.search('/(.+?)/', path).group(1) == 'modx_site_content':
            index = re.search('/([0-9]+)', path).group(1)
            cursor.execute('select content, editedon from modx_site_content where id = %s' % str(index))
            rows = cursor.fetchall()
            for row in rows:
                logger.info(row)
                st.st_mode = stat.S_IFREG | 0666
                st.st_nlink = 1
                st.st_size = len(row[0])
                st.st_mtime = row[1]
                files[path] = row[0]
                return st

            return -errno.ENOENT

        else:
            return -errno.ENOENT

        return st

    def readdir(self, path, offset):

        ret = ['.',
        '..']

        if path == '/':
            ret.append('modx_site_content')

        elif path == '/modx_site_content':
            cursor.execute('select id from modx_site_content')
            rows = cursor.fetchall()
            for row in rows:
                ret.append(str(row[0]) + ext)

        for r in ret:
            yield fuse.Direntry(r)


    def open(self,path,flags):

        logger.info('open flag: %s' % flags)
        if re.search('/(.+?)/', path).group(1) == 'modx_site_content':
            index = re.search('/([0-9]+)', path).group(1)
            cursor.execute('select content from modx_site_content where id = %s' % str(index))
            rows = cursor.fetchall()
            for row in rows:
                files[path] = row[0]
                return 0

        return -errno.ENOENT
        #if (flags & 3) != os.O_RDONLY:
            #return -errno.EACCES


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
            logger.info(buf)
            return buf
        else:
            return -errno.ENOENT


    def write(self, path, txt, offset):
        if files.has_key(path):
            index = re.search('/([0-9]+)', path).group(1)
            cursor.execute("""update modx_site_content set content = %s,editedon = %s where id=%s""", (txt, time.time(), index))
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
            index = re.search('/([0-9]+)', path).group(1)
            cursor.execute("""update modx_site_content set content = %s,editedon = %s where id=%s""", (txt, time.time(), index))

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
