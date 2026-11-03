def pytest_addoption(parser):
    parser.addoption("--model_uri", action="store", default="mlruns/0/")
    parser.addoption("--chain_name", action="store", default="financial_analysis_chain")


def pytest_generate_tests(metafunc):
    # This is called for every test. Only get/set command line arguments
    # if the argument is specified in the list of test "fixturenames".
    option_value = metafunc.config.option.model_uri
    if "model_uri" in metafunc.fixturenames and option_value is not None:
        metafunc.parametrize("model_uri", [option_value])

    option_value = metafunc.config.option.chain_name
    if "chain_name" in metafunc.fixturenames and option_value is not None:
        metafunc.parametrize("chain_name", [option_value])
