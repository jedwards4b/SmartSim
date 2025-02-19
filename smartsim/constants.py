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

# Constants for SmartSim

# Interval for Job Manager
LOCAL_JM_INTERVAL = 2

# Task Manager Interval
TM_INTERVAL = 1

# Statuses that are applied to jobs
STATUS_RUNNING = "Running"
STATUS_COMPLETED = "Completed"
STATUS_CANCELLED = "Cancelled"
STATUS_FAILED = "Failed"
STATUS_NEW = "New"
STATUS_PAUSED = "Paused"

# SmartSim status mapping
SMARTSIM_STATUS = {
    "Paused": STATUS_PAUSED,
    "Completed": STATUS_COMPLETED,
    "Cancelled": STATUS_CANCELLED,
    "Failed": STATUS_FAILED,
    "New": STATUS_NEW,
}

# Status groupings
TERMINAL_STATUSES = (STATUS_CANCELLED, STATUS_COMPLETED, STATUS_FAILED)
LIVE_STATUSES = (STATUS_RUNNING, STATUS_PAUSED, STATUS_NEW)
