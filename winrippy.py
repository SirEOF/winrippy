#!/usr/bin/env python

import pytsk3
import os
import argparse
import hashlib
import csv
import multiprocessing
import logging
import pyewf
import fnmatch

from collections import namedtuple

#1 - Parse arguments
#2 - Get image info
#3 - Get volume info
#4 - Use image info and volume info offset to get fs_info
#5 - Recurse directories
#6 - Copy files

#################################################################### Structs

partition = namedtuple('partition', 
	['image_info',
	'volume_info', 
	'partition_number',
	'description',
	'starting_offset_bytes',
	'starting_offset_sector',
	'partition_length'])
#partition.__new__.__defaults__ = ('', '', '', '', '', '')

file_info = namedtuple('file_info', 
	['fs_info',
	'path',
	'file_handle', 
	'filename',
	'inode',
	'file_type',
	'file_size'])
#file_info.__new__.__defaults__ = ('', '', '', '', '')

#################################################################### Funcs

def get_image_info(list_of_file_paths):
	return [pytsk3.Img_Info(file_path) 
			for file_path in list_of_file_paths]


def get_volume_info(image_info):
	return [partition(
		image_info=image_info,
		volume_info=part,
		partition_number=part.addr,
		description=part.desc.decode('utf-8'),
		starting_offset_bytes=part.start,
		starting_offset_sector=int(part.start*512),
		partition_length=part.len)
		for part in pytsk3.Volume_Info(image_info)]


def get_fs_info(partition):
	return pytsk3.FS_Info(partition.image_info, 
			offset=partition.starting_offset_sector)


def get_file(fs_info, path):
	print 'debug-get_file {0}'.format(path)
	file_handle = fs_info.open(path)
	return file_info(
		fs_info=fs_info,
		path=path,
		file_handle=file_handle,
		filename=file_handle.info.name.name,
		inode=file_handle.info.meta.addr,
		file_type=str(file_handle.info.meta.type),
		file_size=file_handle.info.meta.size)


def list_dir_contents(fs_info, path):
	print 'debug-list_dir_contents {0}'.format(path)
	cwd = fs_info.open_dir(path=path)

	files = [get_file(fs_info, 
		os.path.join(path, _file.info.name.name))
		for _file in cwd
		if validate_file(_file)
		if is_file(_file)]

	directories = [get_file(fs_info, 
		os.path.join(path, directory.info.name.name))
		for directory in cwd
		if validate_file(directory)
		if is_directory(directory)]

	return files, directories


def walk_filesystem(fs_info):
	return recurse_directory(fs_info, '/')


def recurse_directory(fs_info, path):
	print 'debug-recurse_directory {0}'.format(path)
	files, directories = list_dir_contents(fs_info, path)

	for directory in directories:
		recurse_directory(fs_info, os.path.join(path, directory.filename))


def read_file_contents(file_info):
	offset = 0
	size = file_info.file_size
	BUFF_SIZE = 4096
	data = ''

	while offset < size:
		available_to_read = min(BUFF_SIZE, size - offset)
		data = file_info.file_handle.read_random(offset, available_to_read)
		if not data:
			break
		offset += len(data)
	return data


def read_dir_contents(file_info):
	files, directories = list_dir_contents(file_info.fs_info, file_info.path)
	return (read_file_contents(_file) 
			for _file in files)

#################################################################### Filters

def validate_file(file_handle):
	if not file_handle:
		return False
	elif file_handle == None:
		return False
	elif not file_handle.info.meta:
		return False
	elif not file_handle.info.name:
		return False
	#elif fileObject.info.name.flags == pytsk3.TSK_FS_NAME_FLAG_UNALLOC:
	#	return False
	elif file_handle.info.name.name in ['$OrphanFiles', '.', '..']:
		return False
	else:
		return True

def is_directory(file_handle):
		if file_handle.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
			return True
		else:
			return False

def is_file(file_handle):
	if file_handle.info.meta.type == pytsk3.TSK_FS_META_TYPE_REG:
		return True
	else:
		return False

####################################################################

if __name__ == '__main__':
	list_of_file_paths = ['../path/to/image.raw']
	print [os.path.abspath(path) for path in list_of_file_paths]

	images = get_image_info([os.path.abspath(path) 
		for path in list_of_file_paths])

	volumes = (get_volume_info(image) for image in images)


	for partition_table in volumes:
		for partition in partition_table:
			if 'NTFS' in partition.description:
				fs = get_fs_info(partition)
				walk_filesystem(fs)
			else:
				continue
