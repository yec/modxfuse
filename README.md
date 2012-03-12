MODxFUSE
========

FUSE system for MODx.

Edit templates and database contents using a standard text editor instead of
the slow web interface.

WARNING: This software is still in development and may delete your file instead
of saving it.

![screenshot](http://i.imgur.com/9efjL.png)

Instructions
------------

* Edit config.ini to point to the database.
* Run the following code:

        easy_install MySQL-python
        easy_install fuse-python
        easy_install configobj
        mkdir tmp
        python modxfuse.py tmp
