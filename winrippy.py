#!/usr/bin/python

import pytsk3
import os
import hashlib
import argparse


def ReadFileSystem(url=absImageFile):
	'''Takes the command-line argument for the forensic image file and returns a file system object and the root inode'''

	#Create image file object, then pass it to FS constructor
	fs = pytsk3.FS_Info(pytsk3.Img_Info(url))

	# Opens the root of the image's file system
	root = fs.open('/')

	# Find the inode of root
	root_inode = root.info.meta.addr
	
	return fs, root_inode

def ExtractFiles(**kwargs):
	'''
	Unpacks the file_metadata dictionary and performs an icat-esque operation to copy out the target file
	to the output directory
	'''
				
	#Creates a string of the output directory, the target filename, and its corresponding inode
	output_file = str(os.path.join(absOutputDir, ''.join(filename, inode)))

	'''
	Read from file, copy out data to output file. Primary logic comes from
	pytsk tutorials. Delicious spaghetti code.
	'''
	
	offset = 0
	size = f.info.meta.size
	BUFF_SIZE = 4096
	data = ''			
	
	print '[!] COPYING: %s' % full_path_to_file
	
	try:		
		while offset < size:
			available_to_read = min(BUFF_SIZE, size - offset)
			data = f.read_random(offset, available_to_read)
			if not data:
				break
			offset += len(data)
			
	except OSError as exception:
		print '[!] ERROR COPYING: %s, %s' % (full_path_to_file, exception.errno)

	with open(output_file, 'wb') as icat:
			icat.write(data)	

def HashFiles(**kwargs):
	'''
	Unpacks the file_metadata dictionary and performs a sha256 hash computation on the target file
	'''
	
	'''
	Read from file, copy out data to output file. Primary logic comes from
	pytsk tutorials. Delicious spaghetti code.
	'''		
	
	offset = 0
	size = f.info.meta.size
	BUFF_SIZE = 4096
	sha = hashlib.sha256()
	
	try:
		while offset < size:
			available_to_read = min(BUFF_SIZE, size - offset)
			data = f.read_random(offset, available_to_read)
			if not data:
				break
			offset += len(data)

			sha.update(data)

		digest = sha.hexdigest()
		
		#Write a test to see if this exists
		output = os.path.join(absOutputDir, 'hashlist.csv')
		
	except:
		print '[!] ERROR HASHING: %s' % full_path_to_file
		
	# Creates .csv file in append/binary mode containing the path, inode, and hash digest
	with open(output, 'ab+') as output_file:
		output_file.write('"%s","%s","%s"\n' % (full_path_to_file, inode, digest))
			
def ParseImageDir(cur_inode, dir_path):
	''' Recursively parse directories in the image file and sort the entries into two categories:
		Files - Files are hashed
		Directories - Directories are added to a list, which is later passed recursively to walk the tree
	'''
	directories = []
	cwd = fs.open_dir(inode=cur_inode)
			
	for f in cwd:
		try:
			tsk_name = f.info.name

			if not tsk_name:
				continue
			# Unallocated entries cause odd errors, idea came from Plaso
			if tsk_name.flags == pytsk3.TSK_FS_NAME_FLAG_UNALLOC:
				continue
			if not f.info.meta:
				continue
			else:		
				file_metadata = {'file_obj' : f,
								'filename' : tsk_name.name,
								'file_type' : f.info.meta.type,
								'full_path_to_file' : str(os.path.join(cwd, filename)), 
								'inode' : f.info.meta.addr,
								'parent_dir' : str(os.path.split(cwd))}
		except:
			print 'Error finding name'

			# Skip orphan files and symlinks, again error prone
		if file_metadata['filename'] in ['$OrphanFiles', '.', '..']:
			continue
		elif file_metadata['file_type'] == pytsk3.TSK_FS_META_TYPE_DIR:
			# If it's a directory, create a tuple of the inode and the full 
			# path from root. This tuple gets passed for later traversal.		
			directories.append(file_metadata)
		elif file_metadata['file_type'] == pytsk3.TSK_FS_META_TYPE_REG:
			# If the file is a keyfile or within a keypath, extract it via pseudo-iCat	
			if cwd in keypaths or filename in keyfiles:
				try:				
					ExtractFiles(file_metadata)
				except:
					print 'Error extracting target files.'			
			else:
				pass
		else:
			pass
				
			try: 
				HashFiles(file_metadata)
			except:
				print 'Error during hashing.'

	for entry in directories:
		ParseImageDir(entry['inode'], entry['full_path_to_file'])
	
if __name__ == '__main__':
	# Argument parsing
	parser = argparse.ArgumentParser(description='Mount a forensic image and extract selected files for examination.')
	parser.add_argument("ImageFile", help="Image File")
	parser.add_argument("OutputDir", help="Output Directory")
	args = parser.parse_args()
	
	# Ensure that path to image file is absolute
	absImageFile = os.path.abspath(args.ImageFile)

	# Ensure that path to the output directory is absolute
	absOutputDir = os.path.abspath(args.OutputDir)
	
	# 	Note:
	#	These two lists contain the 'target' data for extraction. Modify these lists to find/extract 
	#	other files. Entries are likely case-sensitive, so enter the same file with multiple casing
	#	to ensure that the file will be gathered correctly.
	keypaths = ['/Boot', '/Windows/Tasks', '/Windows/System32/config', '/Windows/System32/winevt']
	keyfiles = ['NTUSER.DAT', 'usrclass.dat', 'Thumbs.db']
	
	global fs, root_inode = ReadFileSystem(absImageFile)
	
	Parse_Image_Dir(root_inode, os.path.sep)
