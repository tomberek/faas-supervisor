# Copyright (C) GRyCAP - I3M - UPV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
""" Module containing all the classes and methods
related with the Onedata storage provider. """

import requests
from faassupervisor.logger import get_logger
from faassupervisor.storage.providers.default import DefaultStorageProvider
from faassupervisor.utils import SysUtils, FileUtils


class Onedata(DefaultStorageProvider):
    """ Class that manages downloads and uploads from Onedata. """

    _CDMI_PATH = 'cdmi'

    def __init__(self, storage_auth, storage_path):
        super().__init__(storage_auth, storage_path)
        self._set_onedata_environment()

    def _set_onedata_environment(self):
        self.oneprovider_space = self.storage_auth.get_auth_var('SPACE')
        self.oneprovider_host = self.storage_auth.get_auth_var('HOST')
        self.headers = {'X-Auth-Token': self.storage_auth.get_auth_var('TOKEN')}

    def download_file(self, event, input_dir_path):
        """ Downloads the file from the space of Onedata and
        returns the path were the download is placed. """
        file_download_path = ""
        url = 'https://{0}/{1}{2}'.format(self.oneprovider_host,
                                          self._CDMI_PATH,
                                          event.event.object_key)
        get_logger().info("Downloading item from host '%s' with key '%s'",
                          self.oneprovider_host,
                          event.event.object_key)
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            file_download_path = SysUtils.join_paths(input_dir_path, event.event.file_name)
            FileUtils.create_file_with_content(file_download_path, response.content, mode='wb')

            get_logger().info("Successful download of file '%s' with key '%s' in path '%s'",
                              event.event.file_name,
                              event.event.object_key,
                              file_download_path)
        else:
            get_logger().error("File '%s' download from Onedata host '%s' failed!",
                               event.event.file_name,
                               self.oneprovider_host)
        return file_download_path

    def upload_file(self, file_path, file_name):
        url = 'https://{0}/{1}/{2}/{3}/{4}'.format(self.oneprovider_host,
                                                   self._CDMI_PATH,
                                                   self.oneprovider_space,
                                                   self.storage_path.path, file_name)
        get_logger().info("Uploading file '%s' to '%s/%s'",
                          file_name,
                          self.oneprovider_space,
                          self.storage_path.path)
        with open(file_path, 'rb') as data:
            response = requests.put(url, data=data, headers=self.headers)
            if response.status_code not in [201, 202, 204]:
                get_logger().error("Upload failed. Status code: %s", response.status_code)
