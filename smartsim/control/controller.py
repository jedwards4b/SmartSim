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

import os.path as osp
import pickle
import threading
import time

from ..config import CONFIG
from ..constants import STATUS_RUNNING, TERMINAL_STATUSES
from ..database import Orchestrator
from ..entity import DBNode, EntityList, SmartSimEntity
from ..error import LauncherError, SmartSimError, SSConfigError, SSUnsupportedError
from ..launcher import CobaltLauncher, LocalLauncher, PBSLauncher, SlurmLauncher
from ..utils import get_logger
from ..utils.entityutils import separate_entities
from .jobmanager import JobManager

logger = get_logger(__name__)

# job manager lock
JM_LOCK = threading.RLock()


class Controller:
    """The controller module provides an interface between the
    smartsim entities created in the experiment and the
    underlying workload manager or run framework.
    """

    def __init__(self, launcher="local"):
        """Initialize a Controller

        :param launcher: the type of launcher being used
        :type launcher: str
        """
        self._jobs = JobManager(JM_LOCK)
        self.init_launcher(launcher)

    def start(self, *args, block=True):
        """Start the passed SmartSim entities

        This function should not be called directly, but rather
        through the experiment interface.

        The controller will start the job-manager thread upon
        execution of all jobs.
        """
        entities, entity_lists, orchestrator = separate_entities(args)
        self._sanity_check_launch(orchestrator, entity_lists)

        self._launch(entities, entity_lists, orchestrator)

        # start the job manager thread if not already started
        if not self._jobs.actively_monitoring:
            self._jobs.start()

        # block until all non-database jobs are complete
        if block:
            self.poll(5, True)

    @property
    def orchestrator_active(self):
        JM_LOCK.acquire()
        try:
            if len(self._jobs.db_jobs) > 0:
                return True
            return False
        finally:
            JM_LOCK.release()

    def poll(self, interval, verbose):
        """Poll running jobs and receive logging output of job status

        :param interval: number of seconds to wait before polling again
        :type interval: int
        :param verbose: set verbosity
        :type verbose: bool
        """
        to_monitor = self._jobs.jobs
        while len(to_monitor) > 0:
            time.sleep(interval)

            # acquire lock to avoid "dictionary changed during iteration" error
            # without having to copy dictionary each time.
            if verbose:
                JM_LOCK.acquire()
                try:
                    for job in to_monitor.values():
                        logger.info(job)
                finally:
                    JM_LOCK.release()

    def finished(self, entity):
        """Return a boolean indicating wether a job has finished or not

        :param entity: object launched by SmartSim.
        :type entity: Model | Ensemble
        :returns: bool
        """
        try:
            if isinstance(entity, Orchestrator):
                raise TypeError("Finished() does not support Orchestrator instances")
            if isinstance(entity, EntityList):
                return all([self.finished(ent) for ent in entity.entities])
            if not isinstance(entity, SmartSimEntity):
                raise TypeError(
                    f"Argument was of type {type(entity)} not Model or Ensemble"
                )

            return self._jobs.is_finished(entity)
        except KeyError:
            raise SmartSimError(
                f"Entity by the name of {entity.name} has not been launched by this Controller"
            ) from None

    def stop_entity(self, entity):
        """Stop an instance of an entity

        This function will also update the status of the job in
        the jobmanager so that the job appears as "cancelled".

        :param entity: entity to be stopped
        :type entity: SmartSimEntity
        """
        JM_LOCK.acquire()
        try:
            job = self._jobs[entity.name]
            if job.status not in TERMINAL_STATUSES:
                logger.info(
                    " ".join(
                        ("Stopping model", entity.name, "with job name", str(job.name))
                    )
                )
                status = self._launcher.stop(job.name)

                job.set_status(
                    status.status,
                    status.launcher_status,
                    status.returncode,
                    error=status.error,
                    output=status.output,
                )
                self._jobs.move_to_completed(job)
        finally:
            JM_LOCK.release()

    def stop_entity_list(self, entity_list):
        """Stop an instance of an entity list

        :param entity_list: entity list to be stopped
        :type entity_list: EntityList
        """
        if entity_list.batch:
            self.stop_entity(entity_list)
        else:
            for entity in entity_list.entities:
                self.stop_entity(entity)

    def get_entity_status(self, entity):
        """Get the status of an entity

        :param entity: entity to get status of
        :type entity: SmartSimEntity
        :raises TypeError: if not SmartSimEntity
        :return: status of entity
        :rtype: str
        """
        if not isinstance(entity, (SmartSimEntity, EntityList)):
            raise TypeError(
                f"Argument must be of type SmartSimEntity or EntityList, not {type(entity)}"
            )
        return self._jobs.get_status(entity)

    def get_entity_list_status(self, entity_list):
        """Get the statuses of an entity list

        :param entity_list: entity list containing entities to
                            get statuses of
        :type entity_list: EntityList
        :raises TypeError: if not EntityList
        :return: list of str statuses
        :rtype: list
        """
        if not isinstance(entity_list, EntityList):
            raise TypeError(f"Argument was of type {type(entity_list)} not EntityList")
        if entity_list.batch:
            return [self.get_entity_status(entity_list)]
        statuses = []
        for entity in entity_list.entities:
            statuses.append(self.get_entity_status(entity))
        return statuses

    def init_launcher(self, launcher):
        """Initialize the controller with a specific type of launcher.

        SmartSim currently supports slurm, pbs(pro), and local launching

        Since the JobManager and the controller share a launcher
        instance, set the JobManager launcher if we create a new
        launcher instance here.

        :param launcher: which launcher to initialize
        :type launcher: str
        :raises SSUnsupportedError: if a string is passed that is not
                                    a supported launcher
        :raises SSConfigError: if no launcher argument is provided.
        """
        if launcher is not None:
            launcher = launcher.lower()
            # Init Slurm Launcher
            if launcher == "slurm":
                self._launcher = SlurmLauncher()
                self._jobs.set_launcher(self._launcher)
            # Run all ensembles locally
            elif launcher == "local":
                self._launcher = LocalLauncher()
                self._jobs.set_launcher(self._launcher)
            # Init PBSPro launcher
            elif launcher == "pbs":
                self._launcher = PBSLauncher()
                self._jobs.set_launcher(self._launcher)
            elif launcher == "cobalt":
                self._launcher = CobaltLauncher()
                self._jobs.set_launcher(self._launcher)
            else:
                raise SSUnsupportedError("Launcher type not supported: " + launcher)
        else:
            raise SSConfigError("Must provide a 'launcher' argument")

    def _launch(self, entities, entity_lists, orchestrator):
        """Main launching function of the controller

        Orchestrators are always launched first so that the
        address of the database can be given to following entities

        :param entities: entities to launch
        :type entities: SmartSimEntity
        :param entity_lists: entity lists to launch
        :type entity_lists: EntityList
        :param orchestrator: orchestrator to launch
        :type orchestrator: Orchestrator
        """
        if orchestrator:
            if self.orchestrator_active:
                msg = "Attempted to launch a second Orchestrator instance. "
                msg += "Only 1 Orchestrator can be active at a time"
                raise SmartSimError(msg)
            self._launch_orchestrator(orchestrator)

        # create all steps prior to launch
        steps = []
        if entity_lists:
            for elist in entity_lists:
                if elist.batch:
                    batch_step = self._create_batch_job_step(elist)
                    steps.append((batch_step, elist))
                else:
                    # if ensemble is to be run as seperate job steps, aka not in a batch
                    job_steps = [(self._create_job_step(e), e) for e in elist.entities]
                    steps.extend(job_steps)
        if entities:
            # models themselves cannot be batch steps
            job_steps = [(self._create_job_step(e), e) for e in entities]
            steps.extend(job_steps)

        # launch steps
        for job_step in steps:
            self._launch_step(*job_step)

    def _launch_orchestrator(self, orchestrator):
        """Launch an Orchestrator instance

        This function will launch the Orchestrator instance and
        if on WLM, find the nodes where it was launched and
        set them in the JobManager

        :param orchestrator: orchestrator to launch
        :type orchestrator: Orchestrator
        """
        orchestrator.remove_stale_files()

        # if the orchestrator was launched as a batch workload
        if orchestrator.batch:
            orc_batch_step = self._create_batch_job_step(orchestrator)
            self._launch_step(orc_batch_step, orchestrator)
            self._orchestrator_launch_wait(orchestrator)
            try:
                nodelist = self._launcher.get_step_nodes([orc_batch_step.name])
                orchestrator._hosts = nodelist[0]

            # catch if it fails or launcher doesn't support it
            except LauncherError:
                logger.debug("WLM node aquisition failed, moving to RedisIP fallback")
            except SSUnsupportedError:
                logger.debug(
                    "WLM node aquisition unsupported, moving to RedisIP fallback"
                )

        # if orchestrator was run on existing allocation, locally, or in allocation
        else:
            db_steps = [(self._create_job_step(db), db) for db in orchestrator]
            for db_step in db_steps:
                self._launch_step(*db_step)

            # wait for orchestrator to spin up
            self._orchestrator_launch_wait(orchestrator)
            try:
                db_step_names = [db_step[0].name for db_step in db_steps]
                nodes = self._launcher.get_step_nodes(db_step_names)
                for db, node in zip(orchestrator, nodes):
                    db._host = node[0]

            # catch if it fails or launcher doesn't support it
            except LauncherError:
                logger.debug("WLM node aquisition failed, moving to RedisIP fallback")
            except SSUnsupportedError:
                logger.debug(
                    "WLM node aquisition unsupported, moving to RedisIP fallback"
                )

        # set the jobs in the job manager to provide SSDB variable to entities
        # if _host isnt set within each
        self._jobs.set_db_hosts(orchestrator)

        # create the database cluster
        if len(orchestrator) > 2:
            orchestrator.create_cluster()
        self._save_orchestrator(orchestrator)
        logger.debug(f"Orchestrator launched on nodes: {orchestrator.hosts}")

    def _launch_step(self, job_step, entity):
        """Use the launcher to launch a job stop

        :param job_step: a job step instance
        :type job_step: Step
        :param entity: entity instance
        :type entity: SmartSimEntity
        :raises SmartSimError: if launch fails
        """

        try:
            job_id = self._launcher.run(job_step)
        except LauncherError as e:
            msg = f"An error occurred when launching {entity.name} \n"
            msg += "Check error and output files for details.\n"
            msg += f"{entity}"
            logger.error(msg)
            raise SmartSimError(f"Job step {entity.name} failed to launch") from e

        if self._jobs.query_restart(entity.name):
            logger.debug(f"Restarting {entity.name}")
            self._jobs.restart_job(job_step.name, job_id, entity.name)
        else:
            logger.debug(f"Launching {entity.name}")
            self._jobs.add_job(job_step.name, job_id, entity)

    def _create_batch_job_step(self, entity_list):
        """Use launcher to create batch job step

        :param entity_list: EntityList to launch as batch
        :type entity_list: EntityList
        :return: job step instance
        :rtype: Step
        """
        batch_step = self._launcher.create_step(
            entity_list.name, entity_list.path, entity_list.batch_settings
        )
        for entity in entity_list.entities:
            # tells step creation not to look for an allocation
            entity.run_settings.in_batch = True
            step = self._create_job_step(entity)
            batch_step.add_to_batch(step)
        return batch_step

    def _create_job_step(self, entity):
        """Create job steps for all entities with the launcher

        :param entities: list of all entities to create steps for
        :type entities: list of SmartSimEntities
        :return: list of tuples of (launcher_step, entity)
        :rtype: list of tuples
        """
        # get SSDB, SSIN, SSOUT and add to entity run settings
        if not isinstance(entity, DBNode):
            self._prep_entity_client_env(entity)

        step = self._launcher.create_step(entity.name, entity.path, entity.run_settings)
        return step

    def _prep_entity_client_env(self, entity):
        """Retrieve all connections registered to this entity

        :param entity: The entity to retrieve connections from
        :type entity:  SmartSimEntity
        :returns: Dictionary whose keys are environment variables to be set
        :rtype: dict
        """
        client_env = {}
        addresses = self._jobs.get_db_host_addresses()
        if addresses:
            client_env["SSDB"] = ",".join(addresses)
            if entity.incoming_entities:
                client_env["SSKEYIN"] = ",".join(
                    [in_entity.name for in_entity in entity.incoming_entities]
                )
            if entity.query_key_prefixing():
                client_env["SSKEYOUT"] = entity.name
        entity.run_settings.update_env(client_env)

    def _sanity_check_launch(self, orchestrator, entity_lists):
        """Check the orchestrator settings

        Sanity check the orchestrator settings in case the
        user tries to do something silly. This function will
        serve as the location of many such sanity checks to come.

        :param orchestrator: Orchestrator instance
        :type orchestrator: Orchestrator
        :raises SSConfigError: If local launcher is being used to
                               launch a database cluster
        """

        if isinstance(self._launcher, LocalLauncher) and orchestrator:
            if len(orchestrator) > 1:
                raise SSConfigError(
                    "Local launcher does not support launching multiple databases"
                )
        # check for empty ensembles
        for elist in entity_lists:
            if len(elist) < 1:
                raise SSConfigError("User attempted to run an empty ensemble")

    def _save_orchestrator(self, orchestrator):
        """Save the orchestrator object via pickle

        This function saves the orchestrator information to a pickle
        file that can be imported by subsequent experiments to reconnect
        to the orchestrator.

        :param orchestrator: Orchestrator configuration to be saved
        :type orchestrator: Orchestrator
        """

        dat_file = "/".join((orchestrator.path, "smartsim_db.dat"))
        db_jobs = self._jobs.db_jobs
        orc_data = {"db": orchestrator, "db_jobs": db_jobs}
        steps = []
        for db_job in db_jobs.values():
            steps.append(self._launcher.step_mapping[db_job.name])
        orc_data["steps"] = steps
        with open(dat_file, "wb") as pickle_file:
            pickle.dump(orc_data, pickle_file)

    def _orchestrator_launch_wait(self, orchestrator):
        """Wait for the orchestrator instances to run

        In the case where the orchestrator is launched as a batch
        through a WLM, we wait for the orchestrator to exit the
        queue before proceeding so new launched entities can
        be launched with SSDB address

        :param orchestrator: orchestrator instance
        :type orchestrator: Orchestrator
        :raises SmartSimError: if launch fails or manually stopped by user
        """
        if orchestrator.batch:
            logger.info("Orchestrator launched as a batch")
            logger.info("While queued, SmartSim will wait for Orchestrator to run")
            logger.info("CTRL+C interrupt to abort and cancel launch")

        ready = False
        while not ready:
            try:
                time.sleep(CONFIG.jm_interval)
                # manually trigger job update if JM not running
                if not self._jobs.actively_monitoring:
                    self._jobs.check_jobs()

                # _jobs.get_status aquires JM lock for main thread, no need for locking
                statuses = self.get_entity_list_status(orchestrator)
                if all([stat == STATUS_RUNNING for stat in statuses]):
                    ready = True
                    # TODO remove in favor of by node status check
                    time.sleep(CONFIG.jm_interval)
                elif any([stat in TERMINAL_STATUSES for stat in statuses]):
                    self.stop_entity_list(orchestrator)
                    msg = "Orchestrator failed during startup"
                    msg += f" See {orchestrator.path} for details"
                    raise SmartSimError(msg)
                else:
                    logger.debug("Waiting for orchestrator instances to spin up...")
            except KeyboardInterrupt as e:
                logger.info("Orchestrator launch cancelled - requesting to stop")
                self.stop_entity_list(orchestrator)
                raise SmartSimError("Orchestrator launch manually stopped") from e
                # TODO stop all running jobs here?

    def reload_saved_db(self, checkpoint_file):
        JM_LOCK.acquire()
        try:
            if self.orchestrator_active:
                raise SmartSimError("Orchestrator exists and is active")

            if not osp.exists(checkpoint_file):
                raise FileNotFoundError(
                    f"The SmartSim database config file {checkpoint_file} cannot be found."
                )

            try:
                with open(checkpoint_file, "rb") as pickle_file:
                    db_config = pickle.load(pickle_file)
            except (OSError, IOError) as e:
                msg = "Database checkpoint corrupted"
                raise SmartSimError(msg) from e

            err_message = (
                "The SmartSim database checkpoint is incomplete or corrupted. "
            )
            if not "db" in db_config:
                raise SmartSimError(
                    err_message + "Could not find the orchestrator object."
                )

            if not "db_jobs" in db_config:
                raise SmartSimError(
                    err_message + "Could not find database job objects."
                )

            if not "steps" in db_config:
                raise SmartSimError(
                    err_message + "Could not find database job objects."
                )
            orc = db_config["db"]

            # TODO check that each db_object is running

            job_steps = zip(db_config["db_jobs"].values(), db_config["steps"])
            try:
                for db_job, step in job_steps:
                    self._jobs.db_jobs[db_job.ename] = db_job
                    self._launcher.step_mapping[db_job.name] = step
                    if step.task_id:
                        self._launcher.task_manager.add_existing(int(step.task_id))
            except LauncherError as e:
                raise SmartSimError("Failed to reconnect orchestrator") from e

            # start job manager if not already started
            if not self._jobs.actively_monitoring:
                self._jobs.start()

            return orc
        finally:
            JM_LOCK.release()
