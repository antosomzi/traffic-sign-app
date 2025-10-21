"""Cleanup utility functions for macOS system files"""

import os
import shutil


def clean_macos_files(root_path):
    """Removes macOS system files from extracted folder"""
    for root, dirs, files in os.walk(root_path, topdown=False):
        # Remove macOS system files
        for fname in files:
            if fname in [".DS_Store", "._.DS_Store"] or fname.startswith("._"):
                file_path = os.path.join(root, fname)
                try:
                    os.remove(file_path)
                except OSError:
                    pass
        
        # Remove __MACOSX directories
        for dirname in dirs:
            if dirname == "__MACOSX":
                dir_path = os.path.join(root, dirname)
                try:
                    shutil.rmtree(dir_path)
                except OSError:
                    pass
