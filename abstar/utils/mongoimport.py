#!/usr/bin/python
# filename: mongoimport.py


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


import os
import subprocess
import sys


def parse_arguments():
	import argparse
	parser = argparse.ArgumentParser("Performs the mongoimport operation on all files in the input directory.  Determines the appropriate collection using the filename.")
	parser.add_argument('-i', '--ip', dest='ip', default='localhost',
						help="The IP address of the MongoDB server. Defaults to 'localhost'.")
	parser.add_argument('-u', '--user', dest='user', default=None,
						help="Username for the MongoDB server. Not used if not provided.")
	parser.add_argument('-p', '--password', dest='password', default=None,
						help="Password for the MongoDB server. Not used if not provided.")
	parser.add_argument('-f', '--in', dest='mongo_input_dir', required=True,
						help="A directory containing multiple JSON files for import to MongoDB.")
	parser.add_argument('-d', '--db', dest='db', required=True,
						help="The MongoDB database for import.")
	parser.add_argument('-l', '--log', dest='mongo_log', required=True,
						help="Log file for the mongoimport stdout.")
	parser.add_argument('-e', '--delim1', dest='delim1', default=None,
						help="The first character delimiter used to split the filename to get the collection name. \
						If splitting with a single delimiter, use this option to provide the delimiter. Required.")
	parser.add_argument('--delim2', dest='delim2', default=None,
						help="If splitting with two different delimiters, use this option to provide the second delimiter. \
						Required if splitting with two delimiters.")
	parser.add_argument('-s', '--split1', dest='split1_pos', default=1, type=int,
						help="Builds the collection name by truncating at the <split> occurance of the <delim> character. \
						If splitting with multiple delimiters, this option is used to specifiy the occurance of the first delimiter. \
						Default is 1.")
	parser.add_argument('--split2', dest='split2_pos', default=1, type=int,
						help="If splitting with multiple delimiters, this option is used to specify the occurance of the \
						second delimiter at which to split. \
						Required if splitting with two different delimiters.")
	parser.add_argument('-x', '--split-only', dest='split_only', default=False, action='store_true',
						help="Instead of truncating the filename to get the collection name, takes only the split for the collection. \
						Default is False.")
	return parser.parse_args()


class Args(object):
	"""Holds arguments, mimics argparse's Namespace when running mongoimport as an imported module"""
	def __init__(self, ip='localhost', user=None, password=None, db=None,
				 mongo_input_dir=None, mongo_log=None,
				 delim1=None, delim2=None,
				 split1_pos=1, split2_pos=1, split_only=False):
		super(Args, self).__init__()
		self.ip = ip
		self.user = user
		self.password = password
		self.mongo_input_dir = mongo_input_dir
		self.db = db
		self.mongo_log = mongo_log if mongo_log else sys.stdout
		self.delim1 = delim1
		self.delim2 = delim2
		self.split1_pos = int(split1_pos)
		self.split2_pos = int(split2_pos)
		self.split_only = split_only


def mongo_import(json, db, coll, log, args):
	username = " -u {}".format(args.user) if args.user else ""
	password = " -p {}".format(args.password) if args.password else ""
	# user_password = "{}{} --authenticationDatabase admin".format(username, password)
	mongo_cmd = "mongoimport --host {}:27017{}{} --db {} --collection {} --file {}".format(
		args.ip, username, password, db, coll, json)
	mongo = subprocess.Popen(mongo_cmd, shell=True, stdout=log)
	mongo.communicate()


def listdir_fullpath(d):
	if os.path.isdir(d):
		files = [os.path.join(d, f) for f in os.listdir(d) if f.split('.')[-1].lower() == 'json']
    	if files:
    		return sorted(files)
	else:
		if d.split('.')[-1].lower() == 'json':
			return [d, ]
	print("ERROR: no importable JSON files were found. Double-check your input file/directory")
	sys.exit(1)


def get_collection(i, args):
	# split with two different delimiters
	if args.delim1 and args.delim2:
		bname = os.path.basename(i)
		split1 = args.delim1.join(bname.split(args.delim1)[args.split1_pos:])
		return args.delim2.join(split1.split(args.delim2)[:args.split2_pos])
	# split with a single delimiter
	elif args.delim1:
		delim = str(args.delim1)
		split = args.split1_pos
		if args.split_only:
			return os.path.basename(i).split(delim)[split - 1]
		if split <= 1:
			return os.path.basename(i).split(delim)[0]
		else:
			pre_collection = os.path.basename(i).split(delim)
			return delim.join(pre_collection[:split])
	else:
		return os.path.basename(i)


def preflight_checks(args):
	if not args.db:
		print("ERROR: a MongoDB database name must be provided.")
	if not args.mongo_input_dir:
		print("ERROR: a directory of JSON files must be provided.")
	if args.delim2 and not args.delim1:
		print("ERROR: --delim1 must be provided with --delim2")
		sys.exit(1)


def run(**kwargs):
	args = Args(kwargs)
	main(args)


def main(args):
	preflight_checks(args)
	in_files = listdir_fullpath(args.mongo_input_dir)
	log_handle = open(args.mongo_log, 'a')
	open(args.mongo_log, 'w').write('')
	for i, f in enumerate(in_files):
		coll = get_collection(f, args)
		print "\n[ {} ] Importing {} into collection {}.".format(i + 1, os.path.basename(f), coll)
		log_handle.write('\n\n----------------------------------------')
		log_handle.write('File: {0}\nCollection: {1}'.format(f, coll))
		log_handle.write('----------------------------------------\n')
		mongo_import(f, args.db, coll, log_handle, args)
	print "\nDone. {0} files were imported into MongoDB.\n\n".format(len(in_files))


if __name__ == '__main__':
	args = parse_arguments()
	main(args)
