#!/usr/bin/python
# filename: celery.py


###########################################################################
#
# Copyright (c) 2014 Bryan Briney.  All rights reserved.
#
# @version: 1.0.0
# @author: Bryan Briney
# @license: MIT (http://opensource.org/licenses/MIT) 
#
###########################################################################



from __future__ import absolute_import

from celery import Celery


# instantiate Celery object
celery = Celery(include=['utils.celery.tasks'])


# import celery config file
celery.config_from_object('celeryconfig')


if __name__ == '__main__':
    celery.start()