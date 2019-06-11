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

""" Module with all the generic supervisor classes and methods.
Also entry point of the faassupervisor package."""

from faassupervisor.storage import create_provider
from faassupervisor.events import parse_event
from faassupervisor.exceptions import exception, InvalidSupervisorTypeError, \
    FaasSupervisorError
from faassupervisor.storage.auth import StorageAuth
import faassupervisor.storage as storage
from faassupervisor.utils import SysUtils, FileUtils
from faassupervisor.logger import configure_logger, get_logger
from faassupervisor.faas.aws.lambda_.supervisor import LambdaSupervisor
from faassupervisor.faas.aws.batch.supervisor import BatchSupervisor
from faassupervisor.faas.openfaas.supervisor import OpenfaasSupervisor


class Supervisor():
    """Generic supervisor used to create the required supervisors
    based on the environment variable 'SUPERVISOR_TYPE'."""

    # pylint: disable=too-few-public-methods

    def __init__(self, event, context=None):
        self._create_tmp_dirs()
        # Parse the event_info data
        self.parsed_event = parse_event(event)
        self._read_storage_variables()
        # Create the supervisor
        self.supervisor = _create_supervisor(event, context)

    def _create_tmp_dirs(self):
        """Creates the temporal directories where the
        input/output data is going to be stored.

        The folders are deleted automatically
        when the execution finishes.

        In Batch mode the folders have to be created
        only at the INIT step.
        """
        if _is_batch_environment():
            if SysUtils.get_env_var("STEP") == "INIT":
                FileUtils.create_folder(SysUtils.get_env_var("TMP_INPUT_DIR"))
                FileUtils.create_folder(SysUtils.get_env_var("TMP_OUTPUT_DIR"))
        else:
            self.input_tmp_dir = FileUtils.create_tmp_dir()
            self.output_tmp_dir = FileUtils.create_tmp_dir()
            SysUtils.set_env_var("TMP_INPUT_DIR", self.input_tmp_dir.name)
            SysUtils.set_env_var("TMP_OUTPUT_DIR", self.output_tmp_dir.name)

    def _read_storage_variables(self):
        get_logger().info("Reading storage authentication variables")
        self.stg_auth = StorageAuth()
        self.stg_auth.read_storage_providers()

    def _get_input_provider(self):
        """Create an input provider based on the event received."""
        event_type = self.parsed_event.get_type()
        auth_data = self.stg_auth.get_auth_data_by_stg_type(event_type)
        return create_provider(auth_data)

    def _get_output_providers(self):
        """Create output providers based on the environment credentials."""
        return [storage.create_provider(self.stg_auth.get_data_by_stg_id(storage_id), output_path)
                for storage_id, output_path in storage.get_output_paths()]

    @exception()
    def _parse_input(self):
        """Download input data from storage provider
        or save data from POST request.

        A function can have information from several storage providers
        but one event always represents only one file (so far), so only
        one provider is going to be used for each event received.
        """
        if _is_batch_environment():
            # Only download if INIT step
            if SysUtils.get_env_var("STEP") != "INIT":
                return
            # Manage batch extra steps
            self.supervisor.parse_input()

        stg_prov = self._get_input_provider()
        get_logger().info("Found '%s' input provider", stg_prov.get_type())
        if stg_prov:
            get_logger().info("Downloading input file using '%s' event",
                              self.parsed_event.get_type())
            input_file_path = storage.download_input(stg_prov,
                                                     self.parsed_event,
                                                     SysUtils.get_env_var("TMP_INPUT_DIR"))
            if input_file_path and FileUtils.is_file(input_file_path):
                SysUtils.set_env_var("INPUT_FILE_PATH", input_file_path)
                get_logger().info("INPUT_FILE_PATH variable set to '%s'", input_file_path)

    @exception()
    def _parse_output(self):
        # In Batch, don't upload anything if not END step
        if _is_batch_environment() and SysUtils.get_env_var("STEP") != "END":
            return

        for stg_prov in self._get_output_providers():
            get_logger().info("Found '%s' output provider", stg_prov.get_type())
            storage.upload_output(stg_prov, SysUtils.get_env_var("TMP_OUTPUT_DIR"))

    @exception()
    def run(self):
        """Generic method to launch the supervisor execution."""
        try:
            self._parse_input()
            self.supervisor.execute_function()
            self._parse_output()
            get_logger().info('Creating response')
            return self.supervisor.create_response()
        except FaasSupervisorError as fse:
            get_logger().exception(fse)
            get_logger().error('Creating error response')
            return self.supervisor.create_error_response()


def _is_batch_environment():
    return SysUtils.get_env_var("SUPERVISOR_TYPE") == 'BATCH'


@exception()
def _create_supervisor(event, context=None):
    """Returns a new supervisor based on the
    environment variable SUPERVISOR_TYPE."""
    supervisor = ""
    _type = SysUtils.get_env_var("SUPERVISOR_TYPE")
    if _type == 'LAMBDA':
        supervisor = LambdaSupervisor(event, context)
    elif _type == 'BATCH':
        supervisor = BatchSupervisor()
    elif _type == 'OPENFAAS':
        supervisor = OpenfaasSupervisor()
    else:
        raise InvalidSupervisorTypeError(sup_typ=_type)
    return supervisor


def _start_supervisor(event, context=None):
    configure_logger()
    get_logger().debug("EVENT received: %s", event)
    if context:
        get_logger().debug("CONTEXT received: %s", context)
    supervisor = Supervisor(event, context)
    return supervisor.run()


def python_main(event, context=None):
    """Called when running from a Python environment.
    Receives the input from the method arguments."""
    return _start_supervisor(event, context)


def main():
    """Called when running as binary.
    Receives the input from stdin."""
    return _start_supervisor(SysUtils.get_stdin())


if __name__ == "__main__":
    main()
