#!/usr/bin/env python

import pytsk3
import os
import argparse
import hashlib
import csv
import multiprocessing
import logging

class Image(object):
    def __init__(self, url):
        self.url                = os.path.abspath(url)
        self.basename           = os.path.basename(url)
        self.image_obj          = pytsk3.Img_Info(url)
        self.partition_table    = self.IterateVolumes(self.image_obj)
        self.filesystems        = self.IterateFileSystems(self.image_obj, 
                                                        self.partition_table)
        
    def IterateVolumes(self, image_obj):
        '''This function takes an image object and lists all of the partitions
        in the image. It creates a tuple of the partition table and returns 
        it in a list.'''
        partition_table = []
    
        volumes = pytsk3.Volume_Info(image_obj)
    
        for part in volumes:
            partition_table.append((part.addr, part.desc.decode('utf-8'), 
                                    part.start, part.len))
        return partition_table

    def IdentifyOffsets(self, partition_table):
        '''This function takes the partition table and identifies the offsets
        to each of its partitions.'''
        offsets = []
    
        for partition in partition_table:
            offsets.append(partition[2])
        return offsets

    def IterateFileSystems(self, image_obj, partition_table):
        block_size = 512
        filesystems = []
        for partition in partition_table:
            vol_offset = partition[2] * block_size
            try:
               fs = pytsk3.FS_Info(image_obj, offset=vol_offset)
               filesystems.append({'fs' : fs, 'partition' : partition})
            except:
                continue  
        return filesystems  
                

class Filesystem(Image):
    def __init__(self, basename, fs_entry):
        self.basename = basename
        self.partition_number = fs_entry['partition'][0]
        self.partition_name = fs_entry['partition'][1]
        self.partition_block_offset = fs_entry['partition'][2]
        self.fs = fs_entry['fs']
        
        if self.AccessFileByPath is not None:
            self.root_inode = self.AccessFileByPath('/')['inode']
        else:
            self.root_inode = None  
        
    def ExtractFileByInode(self, file_entry, full_path=''):
        '''This function will icat a file based on its inode. Data is 
        printed to the console.'''
        
        try:
            file_entry['file_obj'] = self.fs.open_meta(inode=file_entry['inode'])
        except:
            print '[{0}] [Error] Cannot open file {1}'.format(self.basename, 
                                                        file_entry['inode'])
            return
            
        offset = 0
        size = file_entry['file_obj'].info.meta.size
        BUFF_SIZE = 4096
        data = ''
        
        while offset < size:
            available_to_read = min(BUFF_SIZE, size - offset)
            data = file_entry['file_obj'].read_random(offset, available_to_read)
            if not data:
                break
            offset += len(data)
            
        if full_path.startswith('/'):
            rel_path = full_path.lstrip('/')
        else:
            rel_path = full_path
            
        output_path = os.path.join(output_directory, self.basename, 
                                        str(self.partition_number), rel_path)
        output_file = os.path.join(output_path, file_entry['filename'])
        
        self.CheckOutput(output_path)
        
        try:
            print '[{0}] Copying {1} >> {2}'.format(self.basename, full_path, 
                                                    output_file)
            with open(output_file, 'wb') as output:
                output.write(data)
        except:
            print '[{0}] [Error] Error writing {1} in Partition {1} : {2}'.format(self.basename, 
                file_entry['filename'], self.partition_number, self.partition_name)
    
    def ProcessFile(self, file_obj):
        tsk_name = file_obj.info.name
        if not tsk_name:
            return
        if tsk_name.flags == pytsk3.TSK_FS_NAME_FLAG_UNALLOC:
            return
        if not file_obj.info.meta:
            return
            
        file_entry = {'file_obj' : file_obj,
                        'filename' : tsk_name.name,
                        'inode' : file_obj.info.meta.addr,
                        'file_type' : file_obj.info.meta.type,
                        'file_size' : file_obj.info.meta.size}
        return file_entry
            
    def ExtractDirectoryByName(self, directory):
        '''This function extracts all files within a given directory via icat.'''
        try:
            d = self.fs.open_dir(path=directory)
        except:
            print '[{0}] [Error] Cannot find directory {1} in Partition {2} : {3}'.format(self.basename, 
                directory, self.partition_number, self.partition_name)
            return

        for f in d:
            file_entry = self.ProcessFile(f)
            if not file_entry:
                continue
            if file_entry['filename'] in ['$OrphanFiles', '.', '..']:
                continue
            if file_entry['file_type'] == pytsk3.TSK_FS_META_TYPE_DIR:
                continue
                
            self.ExtractFileByInode(file_entry, full_path=directory)
    
    def AccessFileByPath(self, full_path):
        '''This function takes an absolute path and attempts to find an inode.'''
        try:
            f = self.fs.open(full_path)
        except:
            print '[{0}] Cannot find file {1} in Partition {2} : {3}'.format(self.basename, 
                full_path, self.partition_number, self.partition_name)
            return
            
        file_entry = self.ProcessFile(f)
            
        if not file_entry:
            return
        if file_entry['filename'] in ['$OrphanFiles', '.', '..']:
            return
        return file_entry
    
    def ExtractTargetFiles(self, target_files):
        for file  in target_files:
            file_entry = self.AccessFileByPath(file)
            if file_entry is None:
                continue
            else:
                print '[{0}] Extracting {1} : {2}'.format(self.basename, file, 
                                                        file_entry['inode'])
                
                target_directory = os.path.dirname(file)
                self.ExtractFileByInode(file_entry, full_path=target_directory)
    
    def ExtractTargetDirectories(self, target_dirs):
        for dir in target_dirs:
            print '[{0}] Extracting {1}'.format(self.basename, dir)
            self.ExtractDirectoryByName(dir)

    def CheckOutput(self, output_path):
        try:
            if not os.path.exists(output_path):
                os.makedirs(output_path)
        except:
            print '[{0}] [Error] Error Creating Output Directory: {1}'.format(self.basename, 
                                                            output_directory)
        
    def WalkFilesystem(self):
        
        self.QuickMode()
        
        if self.root_inode is None:
            print '[{0}] [Error] Cannot identify root inode in Parition {1} : {2}'.format(self.basename, 
                self.partition_number, self.partition_name)
            return            
        else:
            cur_inode = self.root_inode
            self.RecurseDirectories(cur_inode, os.path.sep)
            
    def RecurseDirectories(self, cur_inode, dir_path):
        
        if not cur_inode:
            print '[{0}] Parsing {1} complete!'.format(self.basename, 
                                                        self.partition_name)
                
        directories = []
        
        cwd = self.fs.open_dir(inode=cur_inode)
        
        self.DetectKeyDirectories(dir_path)
        
        for f in cwd:
            file_entry = self.ProcessFile(f)
            
            if file_entry is None:
                continue
            if file_entry['filename'] in ['$OrphanFiles', '.', '..']:
                continue
                
            full_path = os.path.join(dir_path, file_entry['filename'])
            
            if file_entry['file_type'] == pytsk3.TSK_FS_META_TYPE_DIR:
                directories.append((file_entry['inode'], full_path))
            elif file_entry['file_type'] == pytsk3.TSK_FS_META_TYPE_REG:
                digest = self.HashFile(file_entry)
                self.CreateDirectoryListing(file_entry['inode'], full_path, digest)
                #print '{0} {1} {2} {3} {4}'.format(self.basename, 
                #    self.partition_number, file_entry['inode'], full_path, digest)
                if file_entry['filename'] in key_files:
                    self.ExtractFileByInode(file_entry, full_path=dir_path)
        
        for inode, full_path in directories:
            self.RecurseDirectories(inode, full_path)
            
    def DetectKeyDirectories(self, dir_path):
        if dir_path in target_dirs:
            self.ExtractDirectoryByName(dir_path)
            
    def HashFile(self, file_entry):    
        offset = 0
        size = file_entry['file_size']
        BUFF_SIZE = 4096
        md5 = hashlib.md5()
    
        while offset < size:
            available_to_read = min(BUFF_SIZE, size - offset)
            data = file_entry['file_obj'].read_random(offset, available_to_read)
            if not data:
                break
            offset += len(data)
            
            md5.update(data)
            
        digest = md5.hexdigest()
        return digest
        
    def CreateDirectoryListing(self, inode, dir_path, digest):
        directory_listing = os.path.join(output_directory, self.basename, 
                            'DirectoryListing-{0}.csv'.format(self.basename))
        
        row = [self.basename, str(self.partition_number), inode, dir_path, digest]
        try:
            with open(directory_listing, 'ab+') as csvfile:
                writer = csv.writer(csvfile, delimiter=',')
                writer.writerow(row)
        except:
            return
            
    def QuickMode(self):
        self.ExtractTargetFiles(target_files)
        self.ExtractTargetDirectories(target_dirs)
           
def Automate(image_file):
    for fs_entry in i.filesystems:
        filesystem = Filesystem(i.basename, fs_entry)
        print '[{0}] Opening Partition {1} : {2} at offset {3}'.format(i.basename, 
        filesystem.partition_number, filesystem.partition_name, filesystem.partition_block_offset)

        if quick_flag:
            filesystem.QuickMode()
        else:
            filesystem.WalkFilesystem()
            
if __name__ == '__main__':
    '''This is the primary logic for the script. This function iterates over 
    all available partitions and attempts to extract target files and directories.'''
    
    parser = argparse.ArgumentParser(description='Description',
        epilog='Epilogue')
    parser.add_argument('--quick', help='''extract specific files and locations, 
        do not walk file system.''', action='store_true')
    parser.add_argument('outputdirectory', help='path to output directory')
    parser.add_argument('imagefiles', help='path to image files', nargs='+')
    args = parser.parse_args()

    global output_directory    
    output_directory    = os.path.abspath(args.outputdirectory)
    quick_flag          = args.quick
    image_files         = args.imagefiles
    
    global target_dirs
    global target_files
    global key_files
    
    target_dirs         = ['/Windows/System32/config', '/Windows/Tasks', 
        '/Windows/System32/winevt', '/Windows/System32/Drivers/etc', 
        '/Windows/Prefetch']
    target_files        = ['/$MFT', '/pagefile.sys', '/hiberfil.sys', '/$Logfile']
    key_files           = ['NTUSER.DAT', 'usrclass.dat', 'Thumbs.db']
    
    worker_processes = []
        
    #multiprocessing.log_to_stderr(logging.DEBUG)
    for url in image_files:
        i = Image(url)
        process = multiprocessing.Process(target=Automate, args=(i,))
        worker_processes.append(process)
        process.start()
