#!/usr/bin/python
# filename: basespace.py

#
# Copyright (c) 2015 Bryan Briney
# License: The MIT license (http://opensource.org/licenses/MIT)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software
# and associated documentation files (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge, publish, distribute,
# sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or
# substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
# BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#


from __future__ import print_function, absolute_import

import json
import os
import platform
import time

from BaseSpacePy.api.BaseSpaceAPI import BaseSpaceAPI
from BaseSpacePy.model.QueryParameters import QueryParameters as qp


class BaseSpace(object):
	"""docstring for BaseSpace"""
	def __init__(self, log, project_id=None, undetermined=False):
		super(BaseSpace, self).__init__()
		self.log = log
		# BaseSpace credentials
		creds = self._get_credentials()
		self.client_key = creds['client_id']
		self.client_secret = creds['client_secret']
		self.access_token = creds['access_token']
		self.version = creds['version']
		self.api_server = creds['api_server']
		self.api = BaseSpaceAPI(self.client_key, self.client_secret, self.api_server, self.version, AccessToken=self.access_token)
		self.params = qp(pars={'Limit': 1024, 'SortDir': 'Desc'})
		if project_id:
			self.project_id = project_id
			self.project_name = None
		else:
			self.project_id, self.project_name = self._user_selected_project_id()


	def _get_credentials(self):
		# BaseSpace credentials file should be in JSON format
		cred_file = os.path.expanduser('~/.abstar/basespace_credentials')
		# if platform.system().lower() == 'darwin':
		# 	cred_file = os.path.expanduser('~/.abstar/basespace_credentials')
		# elif platform.system().lower() == 'linux':
		# 	cred_file = '/usr/share/abstar/basespace_credentials'
		cred_handle = open(cred_file, 'r')
		return json.load(cred_handle)



	def _user_selected_project_id(self):
		projects = self.api.getProjectByUser(queryPars=self.params)
		self.print_basespace_project()
		offset = 0
		while True:
			for i, project in enumerate(projects[offset * 25:(offset * 25) + 25]):
				project_name = project.Name.encode('ascii', 'ignore')
				print('[ {} ] {}'.format(i + (offset * 25), project_name))
			print('')
			project_index = raw_input("Select the project number (or 'next' to see more projects): ")
			try:
				project_index = int(project_index)
				return projects[project_index].Id, projects[project_index].Name.encode('ascii', 'ignore')
			except:
				offset += 1
		return projects[project_index].Id, projects[project_index].Name.encode('ascii', 'ignore')

	def _get_projects(self, start=0):
		projects = self.api.getProjectByUser(queryPars=self.params)
		self.print_basespace_project()
		for i, project in enumerate(projects[:25]):
			project_name = project.Name.encode('ascii', 'ignore')
			print('[ {} ] {}'.format(i, project_name))
		print('')
		return projects

	def _get_samples(self, project_id):
		samples = []
		offset = 0
		while True:
			query_params = qp(pars={'Limit': 1024, 'SortDir': 'Asc', 'Offset': offset * 1024})
			s = self.api.getSamplesByProject(self.project_id, queryPars=query_params)
			if not s:
				break
			samples.extend(s)
			offset += 1
		return samples

	def _get_files(self):
		files = []
		samples = self._get_samples(self.project_id)
		for sample in samples:
			files.extend(self.api.getFilesBySample(sample.Id, queryPars=self.params))
		return files

	def download(self, direc):
		files = self._get_files()
		self.print_download_info(files)
		start = time.time()
		for i, f in enumerate(files):
			self.log.write('[ {} ] {}\n'.format(i, str(f)))
			f.downloadFile(self.api, direc)
		end = time.time()
		self.print_completed_download_info(start, end)
		return len(files)


	def print_basespace_project(self):
		print('')
		print('')
		print('========================================')
		print('BaseSpace Project Selection')
		print('========================================')
		print('')


	def print_download_info(self, files):
		self.log.write('\n')
		self.log.write('\n')
		self.log.write('========================================\n')
		self.log.write('Downloading files from BaseSpace\n')
		self.log.write('========================================\n')
		self.log.write('\n')
		self.log.write('Identified {0} files for download.\n'.format(len(files)))
		self.log.write('\n')

	def print_completed_download_info(self, start, end):
		self.log.write('\n')
		self.log.write('Download completed in {0} seconds\n'.format(end - start))
