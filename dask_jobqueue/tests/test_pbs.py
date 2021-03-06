from time import sleep, time

import pytest
import sys
from distributed import Client
from distributed.utils_test import loop  # noqa: F401

from dask_jobqueue import PBSCluster


def test_header():
    with PBSCluster(walltime='00:02:00', processes=4, threads=2, memory='7GB') as cluster:

        assert '#PBS' in cluster.job_header
        assert '#PBS -N dask-worker' in cluster.job_header
        assert '#PBS -l select=1:ncpus=8:mem=27GB' in cluster.job_header
        assert '#PBS -l walltime=00:02:00' in cluster.job_header
        assert '#PBS -q' not in cluster.job_header
        assert '#PBS -A' not in cluster.job_header

    with PBSCluster(queue='regular', project='DaskOnPBS', processes=4, threads=2, memory='7GB',
                    resource_spec='select=1:ncpus=24:mem=100GB') as cluster:

        assert '#PBS -q regular' in cluster.job_header
        assert '#PBS -N dask-worker' in cluster.job_header
        assert '#PBS -l select=1:ncpus=24:mem=100GB' in cluster.job_header
        assert '#PBS -l select=1:ncpus=8:mem=27GB' not in cluster.job_header
        assert '#PBS -l walltime=' in cluster.job_header
        assert '#PBS -A DaskOnPBS' in cluster.job_header

    with PBSCluster() as cluster:

        assert '#PBS -j oe' not in cluster.job_header
        assert '#PBS -N' in cluster.job_header
        assert '#PBS -l select=1:ncpus=' in cluster.job_header
        assert '#PBS -l walltime=' in cluster.job_header
        assert '#PBS -A' not in cluster.job_header
        assert '#PBS -q' not in cluster.job_header

    with PBSCluster(job_extra=['-j oe']) as cluster:

        assert '#PBS -j oe' in cluster.job_header
        assert '#PBS -N' in cluster.job_header
        assert '#PBS -l select=1:ncpus=' in cluster.job_header
        assert '#PBS -l walltime=' in cluster.job_header
        assert '#PBS -A' not in cluster.job_header
        assert '#PBS -q' not in cluster.job_header


def test_job_script():
    with PBSCluster(walltime='00:02:00', processes=4, threads=2, memory='7GB') as cluster:

        job_script = cluster.job_script()
        assert '#PBS' in job_script
        assert '#PBS -N dask-worker' in job_script
        assert '#PBS -l select=1:ncpus=8:mem=27GB' in job_script
        assert '#PBS -l walltime=00:02:00' in job_script
        assert '#PBS -q' not in job_script
        assert '#PBS -A' not in job_script

        assert '{} -m distributed.cli.dask_worker tcp://'.format(sys.executable) in job_script
        assert '--nthreads 2 --nprocs 4 --memory-limit 7GB' in job_script

    with PBSCluster(queue='regular', project='DaskOnPBS', processes=4, threads=2, memory='7GB',
                    resource_spec='select=1:ncpus=24:mem=100GB') as cluster:

        job_script = cluster.job_script()
        assert '#PBS -q regular' in job_script
        assert '#PBS -N dask-worker' in job_script
        assert '#PBS -l select=1:ncpus=24:mem=100GB' in job_script
        assert '#PBS -l select=1:ncpus=8:mem=27GB' not in job_script
        assert '#PBS -l walltime=' in job_script
        assert '#PBS -A DaskOnPBS' in job_script

        assert '{} -m distributed.cli.dask_worker tcp://'.format(sys.executable) in job_script
        assert '--nthreads 2 --nprocs 4 --memory-limit 7GB' in job_script


@pytest.mark.env("pbs")  # noqa: F811
def test_basic(loop):
    with PBSCluster(walltime='00:02:00', processes=1, threads=2, memory='2GB', local_directory='/tmp',
                    job_extra=['-V'], loop=loop) as cluster:
        with Client(cluster) as client:
            workers = cluster.start_workers(2)
            future = client.submit(lambda x: x + 1, 10)
            assert future.result(60) == 11
            assert cluster.jobs

            info = client.scheduler_info()
            w = list(info['workers'].values())[0]
            assert w['memory_limit'] == 2e9
            assert w['ncores'] == 2

            cluster.stop_workers(workers)

            start = time()
            while len(client.scheduler_info()['workers']) > 0:
                sleep(0.100)
                assert time() < start + 10

            assert not cluster.jobs


@pytest.mark.env("pbs")  # noqa: F811
def test_adaptive(loop):
    with PBSCluster(walltime='00:02:00', processes=1, threads=2, memory='2GB', local_directory='/tmp',
                    job_extra=['-V'], loop=loop) as cluster:
        cluster.adapt()
        with Client(cluster) as client:
            future = client.submit(lambda x: x + 1, 10)
            assert future.result(60) == 11

            assert cluster.jobs

            start = time()
            processes = cluster.worker_processes
            while len(client.scheduler_info()['workers']) != processes:
                sleep(0.1)
                assert time() < start + 10

            del future

            start = time()
            while len(client.scheduler_info()['workers']) > 0:
                sleep(0.100)
                assert time() < start + 10

            # There is probably a bug to fix in the adaptive methods of the JobQueueCluster
            # Currently cluster.jobs is not cleaned up.
            #start = time()
            #while cluster.jobs:
            #    sleep(0.100)
            #    assert time() < start + 10
