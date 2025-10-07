from unittest import mock

from adhash.service import __main__ as service_main


def test_service_main_invokes_uvicorn_with_expected_configuration(tmp_path):
    argv = [
        "--host",
        "0.0.0.0",
        "--port",
        "8100",
        "--job-root",
        str(tmp_path),
        "--max-jobs",
        "8",
        "--reload",
        "--log-level",
        "debug",
    ]

    job_manager_instance = mock.Mock()
    job_manager_cls = mock.Mock(return_value=job_manager_instance)
    create_app_mock = mock.Mock(return_value="app")
    uvicorn_run = mock.Mock()
    uvicorn_module = mock.Mock(run=uvicorn_run)
    logger = mock.Mock()

    with mock.patch.object(service_main, "JobManager", job_manager_cls), mock.patch.object(
        service_main, "create_app", create_app_mock
    ), mock.patch.object(service_main.importlib, "import_module", return_value=uvicorn_module) as import_module_mock, mock.patch.object(
        service_main.logging, "getLogger", return_value=logger
    ) as get_logger_mock:
        service_main.main(argv)

    job_manager_cls.assert_called_once_with(base_dir=str(tmp_path), max_workers=8)
    create_app_mock.assert_called_once_with(job_manager_instance)
    import_module_mock.assert_called_once_with("uvicorn")
    uvicorn_run.assert_called_once_with("app", host="0.0.0.0", port=8100, log_level="debug", reload=True)
    get_logger_mock.assert_called_once_with("adhash.service")
    logger.setLevel.assert_called_once_with("DEBUG")
