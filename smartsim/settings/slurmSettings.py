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

import os

from .settings import BatchSettings, RunSettings


class SrunSettings(RunSettings):
    def __init__(self, exe, exe_args=None, run_args=None, env_vars=None, alloc=None):
        """Initialize run parameters for a slurm job with ``srun``

        ``SrunSettings`` should only be used on Slurm based systems.

        If an allocation is specified, the instance receiving these run
        parameters will launch on that allocation.

        :param exe: executable
        :type exe: str
        :param exe_args: executable arguments
        :type exe_args: list[str] | str, optional
        :param run_args: srun arguments without dashes
        :type run_args: dict[str, str | None], optional
        :param env_vars: environment variables for job
        :type env_vars: dict[str, str], optional
        :param alloc: allocation ID if running on existing alloc
        :type alloc: str, optional
        """
        super().__init__(
            exe, exe_args, run_command="srun", run_args=run_args, env_vars=env_vars
        )
        self.alloc = alloc
        self.mpmd = False

    def set_nodes(self, num_nodes):
        """Set the number of nodes

        Effectively this is setting: ``srun --nodes <num_nodes>``

        :param num_nodes: number of nodes to run with
        :type num_nodes: int
        """
        self.run_args["nodes"] = int(num_nodes)

    def set_hostlist(self, host_list):
        """Specify the hostlist for this job

        :param host_list: hosts to launch on
        :type host_list: list[str]
        :raises TypeError:
        """
        if isinstance(host_list, str):
            host_list = [host_list.strip()]
        if not isinstance(host_list, list):
            raise TypeError("host_list argument must be a list of strings")
        if not all([isinstance(host, str) for host in host_list]):
            raise TypeError("host_list argument must be list of strings")
        self.run_args["nodelist"] = ",".join(host_list)

    def set_cpus_per_task(self, num_cpus):
        """Set the number of cpus to use per task

        This sets ``--cpus-per-task``

        :param num_cpus: number of cpus to use per task
        :type num_cpus: int
        """
        self.run_args["cpus-per-task"] = int(num_cpus)

    def set_tasks(self, num_tasks):
        """Set the number of tasks for this job

        This sets ``--ntasks``

        :param num_tasks: number of tasks
        :type num_tasks: int
        """
        self.run_args["ntasks"] = int(num_tasks)

    def set_tasks_per_node(self, num_tpn):
        """Set the number of tasks for this job

        This sets ``--ntasks-per-node``

        :param num_tpn: number of tasks per node
        :type num_tpn: int
        """
        self.run_args["ntasks-per-node"] = int(num_tpn)

    def format_run_args(self):
        """return a list of slurm formatted run arguments

        :return: list slurm arguments for these settings
        :rtype: list[str]
        """
        # add additional slurm arguments based on key length
        opts = []
        for opt, value in self.run_args.items():
            short_arg = bool(len(str(opt)) == 1)
            prefix = "-" if short_arg else "--"
            if not value:
                opts += [prefix + opt]
            else:
                if short_arg:
                    opts += [prefix + opt, str(value)]
                else:
                    opts += ["=".join((prefix + opt, str(value)))]
        return opts

    def format_env_vars(self):
        """Build environment variable string for Slurm

        Slurm takes exports in comma seperated lists
        the list starts with all as to not disturb the rest of the environment
        for more information on this, see the slurm documentation for srun

        :returns: the formatted string of environment variables
        :rtype: str
        """
        # TODO make these overridable by user
        presets = ["PATH", "LD_LIBRARY_PATH", "PYTHONPATH"]

        def add_env_var(var, format_str):
            try:
                value = os.environ[var]
                format_str += "=".join((var, value)) + ","
                return format_str
            except KeyError:
                return format_str

        format_str = ""

        # add env var presets due to slurm weirdness
        for preset in presets:
            format_str = add_env_var(preset, format_str)

        # add user supplied variables
        for k, v in self.env_vars.items():
            format_str += "=".join((k, str(v))) + ","
        return format_str.rstrip(",")


class SbatchSettings(BatchSettings):
    def __init__(self, nodes=None, time="", account=None, batch_args=None):
        """Specify run parameters for a Slurm batch job

        Slurm `sbatch` arguments can be written into ``batch_args``
        as a dictionary. e.g. {'ntasks': 1}

        If the argument doesn't have a parameter, put `None`
        as the value. e.g. {'exclusive': None}

        Initialization values provided (nodes, time, account)
        will overwrite the same arguments in ``batch_args`` if present

        :param nodes: number of nodes
        :type nodes: int, optional
        :param time: walltime for job, e.g. "10:00:00" for 10 hours
        :type time: str, optional
        :param account: account for job
        :type account: str, optional
        :param batch_args: extra batch arguments
        :type batch_args: dict[str, str], optional
        """
        super().__init__("sbatch", batch_args=batch_args)
        if nodes:
            self.set_nodes(nodes)
        if time:
            self.set_walltime(time)
        if account:
            self.set_account(account)

    def set_walltime(self, walltime):
        """Set the walltime of the job

        format = "HH:MM:SS"

        :param walltime: wall time
        :type walltime: str
        """
        # TODO check for errors here
        self.batch_args["time"] = walltime

    def set_nodes(self, num_nodes):
        """Set the number of nodes for this batch job

        :param num_nodes: number of nodes
        :type num_nodes: int
        """
        self.batch_args["nodes"] = int(num_nodes)

    def set_account(self, acct):
        """Set the account for this batch job

        :param acct: account id
        :type acct: str
        """
        self.batch_args["account"] = acct

    def set_partition(self, partition):
        """Set the partition for the batch job

        :param partition: partition name
        :type partition: str
        """
        self.batch_args["partition"] = str(partition)

    def set_hostlist(self, host_list):
        """Specify the hostlist for this job

        :param host_list: hosts to launch on
        :type host_list: list[str]
        :raises TypeError:
        """
        if isinstance(host_list, str):
            host_list = [host_list.strip()]
        if not isinstance(host_list, list):
            raise TypeError("host_list argument must be a list of strings")
        if not all([isinstance(host, str) for host in host_list]):
            raise TypeError("host_list argument must be list of strings")
        self.batch_args["nodelist"] = ",".join(host_list)

    def format_batch_args(self):
        """Get the formatted batch arguments for a preview

        :return: batch arguments for Sbatch
        :rtype: list[str]
        """
        opts = []
        # TODO add restricted here
        for opt, value in self.batch_args.items():
            # attach "-" prefix if argument is 1 character otherwise "--"
            short_arg = bool(len(str(opt)) == 1)
            prefix = "-" if short_arg else "--"

            if not value:
                opts += [prefix + opt]
            else:
                if short_arg:
                    opts += [prefix + opt, str(value)]
                else:
                    opts += ["=".join((prefix + opt, str(value)))]
        return opts
