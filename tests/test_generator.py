from os import path as osp

import numpy as np
import pytest

from smartsim import Experiment
from smartsim.database import Orchestrator
from smartsim.generation import Generator
from smartsim.settings import RunSettings

rs = RunSettings("python", exe_args="sleep.py")


"""
Test the generation of files and input data for an experiment

TODO
 - test lists of inputs for each file type
 - test empty directories
 - test re-generation

"""


def test_ensemble(fileutils):
    exp = Experiment("gen-test", launcher="local")
    test_dir = fileutils.get_test_dir("gen_ensemble_test")
    gen = Generator(test_dir)

    params = {"THERMO": [10, 20, 30], "STEPS": [10, 20, 30]}
    ensemble = exp.create_ensemble("test", params=params, run_settings=rs)

    config = fileutils.get_test_conf_path("in.atm")
    ensemble.attach_generator_files(to_configure=config)
    gen.generate_experiment(ensemble)

    assert len(ensemble) == 9
    assert osp.isdir(osp.join(test_dir, "test"))
    for i in range(9):
        assert osp.isdir(osp.join(test_dir, "test/test_" + str(i)))


def test_ensemble_overwrite(fileutils):
    exp = Experiment("gen-test-overwrite", launcher="local")
    test_dir = fileutils.get_test_dir("test_gen_overwrite")
    gen = Generator(test_dir, overwrite=True)

    params = {"THERMO": [10, 20, 30], "STEPS": [10, 20, 30]}
    ensemble = exp.create_ensemble("test", params=params, run_settings=rs)

    config = fileutils.get_test_conf_path("in.atm")
    ensemble.attach_generator_files(to_configure=[config])
    gen.generate_experiment(ensemble)

    # re generate without overwrite
    config = fileutils.get_test_conf_path("in.atm")
    ensemble.attach_generator_files(to_configure=[config])
    gen.generate_experiment(ensemble)

    assert len(ensemble) == 9
    assert osp.isdir(osp.join(test_dir, "test"))
    for i in range(9):
        assert osp.isdir(osp.join(test_dir, "test/test_" + str(i)))


def test_ensemble_overwrite_error(fileutils):
    exp = Experiment("gen-test-overwrite-error", launcher="local")
    test_dir = fileutils.get_test_dir("test_gen_overwrite_error")
    gen = Generator(test_dir)

    params = {"THERMO": [10, 20, 30], "STEPS": [10, 20, 30]}
    ensemble = exp.create_ensemble("test", params=params, run_settings=rs)

    config = fileutils.get_test_conf_path("in.atm")
    ensemble.attach_generator_files(to_configure=[config])
    gen.generate_experiment(ensemble)

    # re generate without overwrite
    config = fileutils.get_test_conf_path("in.atm")
    ensemble.attach_generator_files(to_configure=[config])
    with pytest.raises(FileExistsError):
        gen.generate_experiment(ensemble)


def test_full_exp(fileutils):

    test_dir = fileutils.make_test_dir("gen_full_test")
    exp = Experiment("gen-test", test_dir, launcher="local")

    model = exp.create_model("model", run_settings=rs)
    script = fileutils.get_test_conf_path("sleep.py")
    model.attach_generator_files(to_copy=script)

    orc = Orchestrator(6780)
    params = {"THERMO": [10, 20, 30], "STEPS": [10, 20, 30]}
    ensemble = exp.create_ensemble("test_ens", params=params, run_settings=rs)

    config = fileutils.get_test_conf_path("in.atm")
    ensemble.attach_generator_files(to_configure=config)
    exp.generate(orc, ensemble, model)

    # test for ensemble
    assert osp.isdir(osp.join(test_dir, "test_ens/"))
    for i in range(9):
        assert osp.isdir(osp.join(test_dir, "test_ens/test_ens_" + str(i)))

    # test for orc dir
    assert osp.isdir(osp.join(test_dir, "database"))

    # test for model file
    assert osp.isdir(osp.join(test_dir, "model"))
    assert osp.isfile(osp.join(test_dir, "model/sleep.py"))


def test_dir_files(fileutils):
    """test the generate of models with files that
    are directories with subdirectories and files
    """

    test_dir = fileutils.make_test_dir("gen_dir_test")
    exp = Experiment("gen-test", test_dir, launcher="local")

    params = {"THERMO": [10, 20, 30], "STEPS": [10, 20, 30]}
    ensemble = exp.create_ensemble("dir_test", params=params, run_settings=rs)
    conf_dir = fileutils.get_test_dir_path("test_dir")
    ensemble.attach_generator_files(to_copy=conf_dir)

    exp.generate(ensemble)

    assert osp.isdir(osp.join(test_dir, "dir_test/"))
    for i in range(9):
        model_path = osp.join(test_dir, "dir_test/dir_test_" + str(i))
        assert osp.isdir(model_path)
        assert osp.isdir(osp.join(model_path, "test_dir_1"))
        assert osp.isfile(osp.join(model_path, "test.py"))
