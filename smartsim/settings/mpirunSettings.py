# BSD 2-Clause License
#
# Copyright (c) 2021, Hewlett Packard Enterprise
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from .settings import RunSettings


class MpirunSettings(RunSettings):
    def __init__(self, exe, exe_args=None, run_args=None, env_vars=None):
        """Settings to run job with ``mpirun`` command (OpenMPI)

        Note that environment variables can be passed with a None
        value to signify that they should be exported from the current
        environment

        Any arguments passed in the ``run_args`` dict will be converted
        into ``mpirun`` arguments and prefixed with ``--``. Values of
        None can be provided for arguments that do not have values.

        :param exe: executable
        :type exe: str
        :param exe_args: executable arguments, defaults to None
        :type exe_args: str | list[str], optional
        :param run_args: arguments for run command, defaults to None
        :type run_args: dict[str, str], optional
        :param env_vars: environment vars to launch job with, defaults to None
        :type env_vars: dict[str, str], optional
        """
        super().__init__(
            exe, exe_args, run_command="mpirun", run_args=run_args, env_vars=env_vars
        )
        self.mpmd = []

    def make_mpmd(self, mpirun_settings):
        """Make a mpmd workload by combining two ``mpirun`` commands

        This connectes the two settings to be executed with a single
        Model instance

        :param mpirun_settings: MpirunSettings instance
        :type mpirun_settings: MpirunSettings
        """
        self.mpmd.append(mpirun_settings)

    def set_task_map(self, task_mapping):
        """Set ``mpirun`` task mapping

        this sets ``--map-by <mapping>``

        For examples, see the man page for ``mpirun``

        :param task_mapping: task mapping
        :type task_mapping: str
        """
        self.run_args["map-by"] = str(task_mapping)

    def set_cpus_per_task(self, num_cpus):
        """Set the number of tasks for this job

        This sets ``--cpus-per-proc``

        note: this option has been deprecated in openMPI 4.0+
        and will soon be replaced.

        :param num_tasks: number of tasks
        :type num_tasks: int
        """
        self.run_args["cpus-per-proc"] = int(num_cpus)

    def set_tasks(self, num_tasks):
        """Set the number of tasks for this job

        This sets ``--n``

        :param num_tasks: number of tasks
        :type num_tasks: int
        """
        self.run_args["n"] = int(num_tasks)

    def set_hostlist(self, host_list):
        """Set the hostlist for the ``mpirun`` command

        :param host_list: list of host names
        :type host_list: list[str]
        :raises TypeError: if not list of str
        """
        if isinstance(host_list, str):
            host_list = [host_list.strip()]
        if not isinstance(host_list, list):
            raise TypeError("host_list argument must be a list of strings")
        if not all([isinstance(host, str) for host in host_list]):
            raise TypeError("host_list argument must be list of strings")
        self.run_args["host"] = ",".join(host_list)

    def format_run_args(self):
        """return a list of OpenMPI formatted run arguments

        :return: list OpenMPI arguments for these settings
        :rtype: list[str]
        """
        # args launcher uses
        args = []
        restricted = ["wdir", "wd"]

        for opt, value in self.run_args.items():
            if opt not in restricted:
                prefix = "--"
                if not value:
                    args += [prefix + opt]
                else:
                    args += [prefix + opt, str(value)]
        return args

    def format_env_vars(self):
        """Format the environment variables for mpirun

        Automatically exports ``PYTHONPATH``, ``LD_LIBRARY_PATH``
        and ``PATH``

        :return: list of env vars
        :rtype: list[str]
        """
        formatted = []
        presets = ["PATH", "LD_LIBRARY_PATH", "PYTHONPATH"]
        for preset in presets:
            formatted.extend(["-x", preset])

        if self.env_vars:
            for name, value in self.env_vars.items():
                if value:
                    formatted += ["-x", "=".join((name, str(value)))]
                else:
                    formatted += ["-x", name]
        return formatted
